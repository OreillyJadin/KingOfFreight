from datetime import datetime, timedelta, timezone
import html
import re
from typing import Any, Protocol
from uuid import uuid4

import httpx

from app.config import get_settings


class EmailMessage(Protocol):
    external_id: str
    from_addr: str
    subject: str
    body_text: str
    received_at: datetime
    pdf_attachments: list[tuple[str, bytes]]


class EmailProvider(Protocol):
    def send(self, to: str, subject: str, body: str) -> str: ...

    def fetch_new_messages(self) -> list[dict[str, Any]]: ...


class MockEmailProvider:
    def send(self, to: str, subject: str, body: str) -> str:
        return f"mock-email-{uuid4().hex}"

    def fetch_new_messages(self) -> list[dict[str, Any]]:
        return []


class GraphEmailProvider:
    # The overlap recovers mail missed while stopped; external_id deduplicates repeats.
    _last_poll = datetime.now(timezone.utc) - timedelta(hours=24)

    def __init__(self) -> None:
        import msal

        settings = get_settings()
        self.mailbox = settings.graph_mailbox
        self.app = msal.ConfidentialClientApplication(
            settings.graph_client_id,
            authority=f"https://login.microsoftonline.com/{settings.graph_tenant_id}",
            client_credential=settings.graph_client_secret,
        )

    def _headers(self) -> dict[str, str]:
        token = self.app.acquire_token_for_client(
            scopes=["https://graph.microsoft.com/.default"]
        )
        if "access_token" not in token:
            raise RuntimeError("Could not obtain Microsoft Graph access token")
        return {
            "Authorization": f"Bearer {token['access_token']}",
            "Content-Type": "application/json",
        }

    def send(self, to: str, subject: str, body: str) -> str:
        response = httpx.post(
            f"https://graph.microsoft.com/v1.0/users/{self.mailbox}/sendMail",
            headers=self._headers(),
            json={
                "message": {
                    "subject": subject,
                    "body": {"contentType": "Text", "content": body},
                    "toRecipients": [{"emailAddress": {"address": to}}],
                },
                "saveToSentItems": True,
            },
            timeout=30,
        )
        response.raise_for_status()
        return f"graph-{uuid4().hex}"

    def fetch_new_messages(self) -> list[dict[str, Any]]:
        headers = self._headers()
        last_poll = GraphEmailProvider._last_poll.isoformat().replace("+00:00", "Z")
        params = {
            "$top": "50",
            "$orderby": "receivedDateTime desc",
            "$filter": f"receivedDateTime gt {last_poll}",
        }
        poll_started = datetime.now(timezone.utc)
        response = httpx.get(
            f"https://graph.microsoft.com/v1.0/users/{self.mailbox}/mailFolders/inbox/messages",
            headers=headers,
            params=params,
            timeout=30,
        )
        response.raise_for_status()
        results = []
        for item in response.json().get("value", []):
            sender = item.get("from", {}).get("emailAddress", {}).get("address", "")
            body_html = item.get("body", {}).get("content", "")
            attachments: list[tuple[str, bytes]] = []
            if item.get("hasAttachments"):
                att_response = httpx.get(
                    f"https://graph.microsoft.com/v1.0/users/{self.mailbox}/messages/{item['id']}/attachments",
                    headers=headers,
                    timeout=30,
                )
                att_response.raise_for_status()
                import base64

                for attachment in att_response.json().get("value", []):
                    if attachment.get(
                        "@odata.type"
                    ) == "#microsoft.graph.fileAttachment" and attachment.get(
                        "name", ""
                    ).lower().endswith(".pdf"):
                        attachments.append(
                            (
                                attachment["name"],
                                base64.b64decode(attachment.get("contentBytes", "")),
                            )
                        )
            try:
                received_at = datetime.fromisoformat(
                    item["receivedDateTime"].replace("Z", "+00:00")
                )
            except (KeyError, ValueError):
                received_at = datetime.now(timezone.utc)
            results.append(
                {
                    "external_id": item.get("id"),
                    "from": sender,
                    "subject": item.get("subject", ""),
                    "body_text": html.unescape(re.sub(r"<[^>]+>", " ", body_html)),
                    "received_at": received_at,
                    "pdf_attachments": attachments,
                }
            )
        GraphEmailProvider._last_poll = poll_started
        return results


def get_email_provider() -> EmailProvider:
    return (
        GraphEmailProvider()
        if get_settings().email_provider == "graph"
        else MockEmailProvider()
    )
