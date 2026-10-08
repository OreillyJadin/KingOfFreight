from typing import Protocol
from uuid import uuid4

from app.config import get_settings


class SmsProvider(Protocol):
    def send(self, to: str, body: str) -> str: ...


class MockSmsProvider:
    def send(self, to: str, body: str) -> str:
        return f"mock-sms-{uuid4().hex}"


class TwilioSmsProvider:
    def __init__(self) -> None:
        from twilio.rest import Client

        settings = get_settings()
        self.client = Client(settings.twilio_account_sid, settings.twilio_auth_token)
        self.from_number = settings.twilio_from_number

    def send(self, to: str, body: str) -> str:
        message = self.client.messages.create(to=to, from_=self.from_number, body=body)
        return str(message.sid)


def get_sms_provider() -> SmsProvider:
    return (
        TwilioSmsProvider()
        if get_settings().sms_provider == "twilio"
        else MockSmsProvider()
    )
