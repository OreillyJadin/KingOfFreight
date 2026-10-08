import base64
import re
from pathlib import Path
from typing import Any, Protocol

from pypdf import PdfReader

from app.config import get_settings
from app.schemas import BolExtraction, ReplyParse


class LlmProvider(Protocol):
    def extract_bol(self, pdf_bytes: bytes, filename: str) -> BolExtraction: ...

    def parse_reply(self, reply_text: str, context: dict[str, Any]) -> ReplyParse: ...


class MockLlmProvider:
    def extract_bol(self, pdf_bytes: bytes, filename: str) -> BolExtraction:
        text = ""
        try:
            from io import BytesIO

            text = "\n".join(
                page.extract_text() or ""
                for page in PdfReader(BytesIO(pdf_bytes)).pages
            )
        except Exception:
            pass
        weight_match = re.search(r"([\d,]+)\s*(?:lbs?|pounds)", text, re.I)
        ref_match = re.search(r"(?:BOL|PO|Load)\s*#?:?\s*([A-Z0-9-]+)", text, re.I)
        return BolExtraction(
            reference=ref_match.group(1) if ref_match else Path(filename).stem,
            weight_lbs=float(weight_match.group(1).replace(",", ""))
            if weight_match
            else None,
            confidence=0.3,
            notes="mock extraction",
        )

    def parse_reply(self, reply_text: str, context: dict[str, Any]) -> ReplyParse:
        lower = reply_text.lower()
        attention = any(
            word in lower
            for word in ("breakdown", "accident", "call me", "wrong address")
        )
        if any(
            word in lower
            for word in (
                "behind",
                "late",
                "delay",
                "waiting",
                "breakdown",
                "traffic",
                "detained",
            )
        ):
            return ReplyParse(
                status="delayed",
                summary=reply_text[:250],
                needs_broker_attention=attention,
                confidence=0.65,
            )
        if any(word in lower for word in ("delivered", "empty", "unloaded", "dropped")):
            status = "delivered"
        elif any(word in lower for word in ("loaded", "picked up", "got it")):
            status = "picked_up"
        elif any(
            word in lower for word in ("rolling", "on the way", "en route", "out")
        ):
            status = "in_transit"
        elif re.fullmatch(r"\s*(yes|yep|yeah|y)\.?!?\s*", lower):
            status = "picked_up" if context.get("kind") == "pickup" else "delivered"
        else:
            return ReplyParse(
                status="unclear",
                summary="Reply does not clearly identify load status.",
                needs_broker_attention=attention,
            )
        return ReplyParse(
            status=status,
            summary=reply_text[:250],
            needs_broker_attention=attention,
            confidence=0.7,
        )


class AnthropicLlmProvider:
    def __init__(self, client: Any = None) -> None:
        if client is None:
            import anthropic

            client = anthropic.Anthropic(api_key=get_settings().anthropic_api_key)
        self.client = client
        self.model = get_settings().anthropic_model

    @staticmethod
    def _tool_response(response: Any, name: str) -> dict[str, Any]:
        for block in response.content:
            if getattr(block, "type", None) == "tool_use" and block.name == name:
                return block.input
        raise ValueError(f"Anthropic did not return required tool {name}")

    def extract_bol(self, pdf_bytes: bytes, filename: str) -> BolExtraction:
        system = (
            Path(__file__).resolve().parents[1] / "prompts" / "bol_extraction.md"
        ).read_text()
        schema = {
            "type": "object",
            "properties": {
                field: {"type": ["string", "null"]}
                for field in [
                    "pickup_location",
                    "pickup_city",
                    "pickup_state",
                    "pickup_datetime",
                    "delivery_location",
                    "delivery_city",
                    "delivery_state",
                    "delivery_datetime",
                    "equipment_type",
                    "commodity",
                    "customer_name",
                    "customer_contact_name",
                    "customer_email",
                    "customer_phone",
                    "special_requirements",
                    "notes",
                ]
            },
            "required": [
                "pickup_location",
                "pickup_city",
                "pickup_state",
                "pickup_datetime",
                "delivery_location",
                "delivery_city",
                "delivery_state",
                "delivery_datetime",
                "weight_lbs",
                "equipment_type",
                "commodity",
                "customer_name",
                "customer_contact_name",
                "customer_email",
                "customer_phone",
                "special_requirements",
                "confidence",
                "notes",
            ],
        }
        schema["properties"].update(
            {
                "weight_lbs": {"type": ["number", "null"]},
                "confidence": {"type": "number"},
                "pickup_time_known": {"type": ["boolean", "null"]},
                "delivery_time_known": {"type": ["boolean", "null"]},
                "pieces": {"type": ["integer", "null"]},
                "pallets": {"type": ["integer", "null"]},
                "reference_numbers": {
                    "type": ["object", "null"],
                    "additionalProperties": {"type": "string"},
                },
            }
        )
        response = self.client.messages.create(
            model=self.model,
            max_tokens=1800,
            system=system,
            tools=[
                {
                    "name": "record_bol_fields",
                    "description": "Record extracted BOL fields",
                    "input_schema": schema,
                }
            ],
            tool_choice={"type": "tool", "name": "record_bol_fields"},
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "document",
                            "source": {
                                "type": "base64",
                                "media_type": "application/pdf",
                                "data": base64.b64encode(pdf_bytes).decode("ascii"),
                            },
                        },
                        {
                            "type": "text",
                            "text": f"Extract shipment fields from {filename}.",
                        },
                    ],
                }
            ],
        )
        return BolExtraction.model_validate(
            self._tool_response(response, "record_bol_fields")
        )

    def parse_reply(self, reply_text: str, context: dict[str, Any]) -> ReplyParse:
        system = (
            Path(__file__).resolve().parents[1] / "prompts" / "reply_parsing.md"
        ).read_text()
        schema = {
            "type": "object",
            "properties": {
                "status": {
                    "type": "string",
                    "enum": [
                        "picked_up",
                        "in_transit",
                        "delayed",
                        "delivered",
                        "unclear",
                    ],
                },
                "eta": {"type": ["string", "null"]},
                "delay_minutes": {"type": ["integer", "null"]},
                "summary": {"type": "string"},
                "needs_broker_attention": {"type": "boolean"},
                "confidence": {"type": "number"},
            },
            "required": [
                "status",
                "eta",
                "summary",
                "needs_broker_attention",
                "confidence",
            ],
        }
        response = self.client.messages.create(
            model=self.model,
            max_tokens=800,
            system=system,
            tools=[
                {
                    "name": "record_status",
                    "description": "Record interpreted driver status",
                    "input_schema": schema,
                }
            ],
            tool_choice={"type": "tool", "name": "record_status"},
            messages=[
                {
                    "role": "user",
                    "content": f"Driver reply: {reply_text}\n\nLoad context: {context}",
                }
            ],
        )
        return ReplyParse.model_validate(self._tool_response(response, "record_status"))


def get_llm_provider() -> LlmProvider:
    return (
        AnthropicLlmProvider()
        if get_settings().llm_provider == "anthropic"
        else MockLlmProvider()
    )
