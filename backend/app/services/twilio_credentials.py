from dataclasses import dataclass, field
from typing import Literal

from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import TwilioConnection
from app.services.kof_credentials import decrypt_kof_password


@dataclass(frozen=True)
class TwilioCredentials:
    account_sid: str = field(repr=False)
    auth_token: str = field(repr=False)
    from_number: str = field(repr=False)
    source: Literal["app", "env"]


def get_twilio_credentials(db: Session) -> TwilioCredentials | None:
    row = db.get(TwilioConnection, 1)
    if row:
        return TwilioCredentials(
            row.account_sid,
            decrypt_kof_password(row.token_encrypted),
            row.from_number,
            "app",
        )
    settings = get_settings()
    values = (
        settings.twilio_account_sid,
        settings.twilio_auth_token,
        settings.twilio_from_number,
    )
    if all(value and value.strip() for value in values):
        return TwilioCredentials(*(value.strip() for value in values), source="env")
    return None
