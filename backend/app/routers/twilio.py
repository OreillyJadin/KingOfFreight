import base64
import re
from urllib.parse import quote, quote_plus

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field, SecretStr
from requests.exceptions import RequestException
from sqlalchemy.orm import Session
from twilio.base.exceptions import TwilioException, TwilioRestException

from app.auth import require_admin, require_broker
from app.config import get_settings
from app.db import get_db
from app.integrations.sms import TwilioSmsProvider, resolve_sms_mode
from app.models import TwilioConnection
from app.services.kof_credentials import encrypt_kof_password
from app.services.twilio_credentials import TwilioCredentials, get_twilio_credentials

router = APIRouter(
    prefix="/api/integrations/twilio",
    tags=["Twilio"],
    dependencies=[Depends(require_broker)],
)
E164 = r"^\+[1-9][0-9]{1,14}$"


class ConnectionInput(BaseModel):
    account_sid: str = Field(pattern=r"^AC[0-9a-fA-F]{32}$")
    auth_token: SecretStr
    from_number: str = Field(pattern=E164)


class TestInput(BaseModel):
    to: str = Field(pattern=E164)


def webhook_url(request: Request) -> str:
    settings = get_settings()
    if "public_base_url" in settings.model_fields_set and settings.public_base_url:
        base = settings.public_base_url.rstrip("/")
    else:
        scheme = (
            request.headers.get("x-forwarded-proto", request.url.scheme)
            .split(",")[0]
            .strip()
        )
        host = (
            request.headers.get(
                "x-forwarded-host", request.headers.get("host", request.url.netloc)
            )
            .split(",")[0]
            .strip()
        )
        base = f"{scheme}://{host}"
    query = f"?{request.url.query}" if request.url.query else ""
    return f"{base}{request.url.path}{query}"


@router.get("/connection")
def connection(db: Session = Depends(get_db)) -> dict:
    credentials = get_twilio_credentials(db)
    return {
        "configured": bool(credentials),
        "source": credentials.source if credentials else None,
        "account_sid": f"AC…{credentials.account_sid[-4:]}" if credentials else None,
        "from_number": f"…{credentials.from_number[-4:]}" if credentials else None,
        "sms": resolve_sms_mode(bool(credentials)),
    }


@router.put("/connection", dependencies=[Depends(require_admin)])
def save_connection(body: ConnectionInput, db: Session = Depends(get_db)) -> dict:
    token = body.auth_token.get_secret_value().strip()
    if not token or len(token) > 500:
        raise HTTPException(422, "Auth Token must contain 1–500 nonblank characters")
    row = db.get(TwilioConnection, 1)
    if row is None:
        row = TwilioConnection(id=1)
        db.add(row)
    row.account_sid = body.account_sid
    row.token_encrypted = encrypt_kof_password(token)
    row.from_number = body.from_number
    db.commit()
    return connection(db)


@router.delete("/connection", status_code=204, dependencies=[Depends(require_admin)])
def delete_connection(db: Session = Depends(get_db)) -> None:
    row = db.get(TwilioConnection, 1)
    if row:
        db.delete(row)
        db.commit()


def _safe_twilio_error(
    error: TwilioRestException, credentials: TwilioCredentials
) -> str:
    message = error.msg or "Twilio rejected the test message"
    secrets = [credentials.account_sid, credentials.auth_token, credentials.from_number]
    secrets.append(
        base64.b64encode(
            f"{credentials.account_sid}:{credentials.auth_token}".encode()
        ).decode()
    )
    for secret in secrets:
        for value in (secret, quote(secret, safe=""), quote_plus(secret)):
            message = message.replace(value, "[redacted]")
    message = re.sub(r"\b(?:AC|SK)[0-9a-fA-F]{32}\b", "[redacted]", message)
    return message[:500]


@router.post("/test", dependencies=[Depends(require_admin)])
def test_sms(body: TestInput, db: Session = Depends(get_db)) -> dict:
    credentials = get_twilio_credentials(db)
    if not credentials:
        raise HTTPException(
            503, "Add complete Twilio credentials before sending a test text"
        )
    try:
        TwilioSmsProvider(credentials).send(
            body.to, "Fifth Wheel: your Twilio texting connection works."
        )
    except TwilioRestException as error:
        raise HTTPException(
            502, f"Twilio test failed: {_safe_twilio_error(error, credentials)}"
        ) from None
    except (TwilioException, RequestException):
        raise HTTPException(502, "Twilio is unreachable. Please try again.") from None
    return {"sent": True}
