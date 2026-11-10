from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.config import get_settings
from app.integrations.email import MockEmailProvider, resolve_email_mode
from app.integrations.sms import MockSmsProvider, resolve_sms_mode
from app.services.assistant_credentials import get_assistant_key
from app.services.twilio_credentials import get_twilio_credentials


def capabilities(db: Session) -> dict:
    settings = get_settings()
    graph_complete = all(
        value and value.strip()
        for value in (
            settings.graph_tenant_id,
            settings.graph_client_id,
            settings.graph_client_secret,
            settings.graph_mailbox,
        )
    )
    email_mode = resolve_email_mode(db)
    twilio = bool(get_twilio_credentials(db))
    return {
        "email_live": email_mode == "outlook"
        or (email_mode == "graph" and bool(graph_complete)),
        "sms_live": twilio and resolve_sms_mode(twilio) == "twilio",
        "assistant_live": bool(get_assistant_key(db)),
    }


def require_live_send(channel: str, provider) -> None:
    if get_settings().env.lower() in {"production", "prod"} and isinstance(
        provider, (MockSmsProvider, MockEmailProvider)
    ):
        label = "Texting" if channel == "sms" else "Email"
        raise HTTPException(409, f"{label} isn't connected yet")
