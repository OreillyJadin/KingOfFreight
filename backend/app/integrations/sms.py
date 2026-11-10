from typing import Literal, Protocol
from uuid import uuid4

from app.config import get_settings
from app.db import SessionLocal
from app.services.twilio_credentials import TwilioCredentials, get_twilio_credentials


class SmsProvider(Protocol):
    def send(self, to: str, body: str) -> str: ...


class MockSmsProvider:
    def send(self, to: str, body: str) -> str:
        return f"mock-sms-{uuid4().hex}"


class TwilioSmsProvider:
    def __init__(self, credentials: TwilioCredentials | None = None) -> None:
        from twilio.rest import Client

        if credentials is None:
            with SessionLocal() as db:
                credentials = get_twilio_credentials(db)
        if credentials is None:
            raise ValueError("Twilio credentials are not configured")
        self.client = Client(credentials.account_sid, credentials.auth_token)
        self.from_number = credentials.from_number

    def send(self, to: str, body: str) -> str:
        message = self.client.messages.create(to=to, from_=self.from_number, body=body)
        return str(message.sid)


def resolve_sms_mode(configured: bool) -> Literal["twilio", "mock"]:
    mode = get_settings().sms_provider
    return "twilio" if mode == "twilio" or (mode == "auto" and configured) else "mock"


def get_sms_provider() -> SmsProvider:
    if get_settings().sms_provider not in {"auto", "twilio"}:
        return MockSmsProvider()
    with SessionLocal() as db:
        credentials = get_twilio_credentials(db)
    if resolve_sms_mode(bool(credentials)) == "twilio":
        return TwilioSmsProvider(credentials)
    return MockSmsProvider()
