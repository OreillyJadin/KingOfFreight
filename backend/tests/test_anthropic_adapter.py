from types import SimpleNamespace

from app.integrations.llm import AnthropicLlmProvider


class StubMessages:
    def __init__(self):
        self.request = None

    def create(self, **kwargs):
        self.request = kwargs
        return SimpleNamespace(
            content=[
                SimpleNamespace(
                    type="tool_use",
                    name="record_bol_fields",
                    input={
                        "pickup_city": "Chicago",
                        "weight_lbs": 34000,
                        "confidence": 0.8,
                    },
                )
            ]
        )


class StubClient:
    def __init__(self):
        self.messages = StubMessages()


def test_anthropic_bol_uses_pdf_prompt_forced_tool_and_validates():
    client = StubClient()
    provider = AnthropicLlmProvider(client)
    extracted = provider.extract_bol(b"%PDF-1.4 mock", "sample.pdf")
    request = client.messages.request
    assert request["system"].startswith("You are extracting shipment details")
    assert request["tool_choice"] == {"type": "tool", "name": "record_bol_fields"}
    document = request["messages"][0]["content"][0]
    assert document["type"] == "document" and document["source"]["type"] == "base64"
    assert extracted.pickup_city == "Chicago" and extracted.weight_lbs == 34000
