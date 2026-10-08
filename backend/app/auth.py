import hashlib
import hmac

from fastapi import HTTPException, Request, status
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from app.config import get_settings

COOKIE_NAME = "broker_session"


def _serializer() -> URLSafeTimedSerializer:
    settings = get_settings()
    secret = (
        settings.secret_key
        + hashlib.sha256(settings.broker_password.encode()).hexdigest()
    )
    return URLSafeTimedSerializer(secret, salt="broker-session")


def create_session() -> str:
    return _serializer().dumps({"broker": True})


def validate_session(token: str) -> bool:
    try:
        payload = _serializer().loads(token, max_age=60 * 60 * 24 * 30)
    except (BadSignature, SignatureExpired):
        return False
    return payload.get("broker") is True


def require_broker(request: Request) -> None:
    token = request.cookies.get(COOKIE_NAME)
    if not token or not validate_session(token):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Broker authentication required",
        )


def password_matches(candidate: str) -> bool:
    return hmac.compare_digest(candidate, get_settings().broker_password)
