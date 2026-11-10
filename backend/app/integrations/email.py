from datetime import datetime, timedelta, timezone
import html
import re
import hashlib
from urllib.parse import quote
from typing import Any, Protocol
from uuid import uuid4

import httpx

from app.config import get_settings
from app.db import SessionLocal
from app.models import EmailPollState, OutlookConnection
from app.services.outlook import access_token


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
    def __init__(self) -> None:
        import msal

        settings = get_settings()
        self.mailbox = settings.graph_mailbox
        self.path = f"https://graph.microsoft.com/v1.0/users/{quote(self.mailbox or '', safe='')}"
        self.poll_key = hashlib.sha256(
            f"graph:{settings.graph_tenant_id}:{settings.graph_client_id}:{self.mailbox}".encode()
        ).hexdigest()
        self.poll_started: datetime | None = None
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
            f"{self.path}/sendMail",
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
        self.poll_started = datetime.now(timezone.utc)
        with SessionLocal() as db:
            stored = db.get(EmailPollState, self.poll_key)
            since = (
                stored.last_poll if stored else self.poll_started - timedelta(hours=24)
            )
            if since.tzinfo is None:
                since = since.replace(tzinfo=timezone.utc)
            if stored:
                since -= timedelta(minutes=1)
        last_poll = since.isoformat().replace("+00:00", "Z")
        params = {
            "$top": "50",
            "$select": "id,from,subject,body,receivedDateTime,hasAttachments",
            "$orderby": "receivedDateTime desc",
            "$filter": f"receivedDateTime gt {last_poll} and receivedDateTime le {self.poll_started.isoformat()}",
        }
        items = []
        url = f"{self.path}/mailFolders/inbox/messages"
        while url:
            if not url.startswith("https://graph.microsoft.com/v1.0/"):
                raise ValueError("Unexpected Microsoft pagination URL")
            response = httpx.get(url, headers=headers, params=params, timeout=30)
            response.raise_for_status()
            page = response.json()
            items.extend(page.get("value", []))
            url = page.get("@odata.nextLink")
            params = None
        results = []
        for item in items:
            sender = item.get("from", {}).get("emailAddress", {}).get("address", "")
            body_html = item.get("body", {}).get("content", "")
            attachments: list[tuple[str, bytes]] = []
            if item.get("hasAttachments"):
                att_response = httpx.get(
                    f"{self.path}/messages/{quote(item['id'], safe='')}/attachments",
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
        return results

    def commit_poll(self) -> None:
        if self.poll_started is not None:
            with SessionLocal() as db:
                db.merge(EmailPollState(key=self.poll_key, last_poll=self.poll_started))
                db.commit()


class OutlookEmailProvider(GraphEmailProvider):
    def __init__(self, email: str):
        self.path = "https://graph.microsoft.com/v1.0/me"
        self.poll_key = hashlib.sha256(f"outlook:{email.lower()}".encode()).hexdigest()
        self.poll_started = None

    def _headers(self) -> dict[str, str]:
        with SessionLocal() as db:
            token = access_token(db)
        return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


def resolve_email_mode(db) -> str:
    settings = get_settings()
    account = db.get(OutlookConnection, 1)
    if (
        settings.email_provider in {"auto", "outlook"}
        and account
        and not account.needs_reconnect
    ):
        return "outlook"
    if (
        settings.email_provider == "graph"
        or settings.email_provider == "auto"
        and all(
            value and value.strip()
            for value in (
                settings.graph_tenant_id,
                settings.graph_client_id,
                settings.graph_client_secret,
                settings.graph_mailbox,
            )
        )
    ):
        return "graph"
    return "mock"


def get_email_provider() -> EmailProvider:
    with SessionLocal() as db:
        mode = resolve_email_mode(db)
        account = db.get(OutlookConnection, 1)
        if mode == "outlook":
            return OutlookEmailProvider(account.email)
    return GraphEmailProvider() if mode == "graph" else MockEmailProvider()
