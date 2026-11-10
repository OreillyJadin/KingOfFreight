import base64
import hashlib
import hmac
import secrets
from typing import Any

from fastapi import Depends, HTTPException, Request, status
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import SessionLocal, get_db
from app.models import User

COOKIE_NAME = "broker_session"
_SCRYPT_N = 2**14
_SCRYPT_R = 8
_SCRYPT_P = 1
_SCRYPT_KEY_LENGTH = 64


def _serializer() -> URLSafeTimedSerializer:
    settings = get_settings()
    secret = (
        settings.secret_key
        + hashlib.sha256(settings.broker_password.encode()).hexdigest()
    )
    return URLSafeTimedSerializer(secret, salt="broker-session")


def create_session(
    uid: int | None = None, password_version: int | None = None, role: str | None = None
) -> str:
    return _serializer().dumps(
        {
            "broker": True,
            "uid": uid,
            "password_version": password_version,
            "role": role,
        }
    )


def decode_session(token: str) -> dict[str, Any] | None:
    try:
        payload = _serializer().loads(token, max_age=60 * 60 * 24 * 30)
    except (BadSignature, SignatureExpired):
        return None
    if not isinstance(payload, dict) or payload.get("broker") is not True:
        return None
    return payload


def session_user(payload: dict[str, Any], db: Session) -> User | None:
    uid = payload.get("uid")
    version = payload.get("password_version")
    if not isinstance(uid, int) or not isinstance(version, int):
        return None
    user = db.get(User, uid)
    if user is None or not user.is_active or user.password_version != version:
        return None
    return user


def validate_session(token: str, db: Session | None = None) -> bool:
    payload = decode_session(token)
    if payload is None:
        return False
    if payload.get("uid") is None:
        return True
    if db is not None:
        return session_user(payload, db) is not None
    with SessionLocal() as session:
        return session_user(payload, session) is not None


def require_broker(request: Request, db: Session = Depends(get_db)) -> User | None:
    token = request.cookies.get(COOKIE_NAME)
    payload = decode_session(token) if token else None
    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Broker authentication required",
        )
    if payload.get("uid") is None:
        request.state.usage_identity = (None, None)
        return None
    user = session_user(payload, db)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Broker authentication required",
        )
    request.state.usage_identity = (user.id, user.username)
    return user


def password_matches(candidate: str) -> bool:
    return hmac.compare_digest(candidate, get_settings().broker_password)


def require_admin(
    user: User | None = Depends(require_broker), db: Session = Depends(get_db)
) -> User:
    lock_admin_changes(db)
    if user is not None:
        db.refresh(user)
    if user is None or not user.is_active or user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    return user


def admin_exists(db: Session) -> bool:
    return db.scalar(select(User.id).where(User.role == "admin").limit(1)) is not None


def lock_admin_changes(db: Session) -> None:
    if db.get_bind().dialect.name == "postgresql":
        db.execute(text("SELECT pg_advisory_xact_lock(584739201)"))


def ensure_bootstrap_user(db: Session, username: str | None) -> User | None:
    normalized = (username or "").strip()
    if not normalized:
        return None
    user = db.scalar(
        select(User).where(func.lower(User.username) == normalized.lower())
    )
    if user is not None:
        return user
    user = User(
        username=normalized,
        password_hash=None,
        password_version=0,
        must_set_password=True,
    )
    db.add(user)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        return db.scalar(
            select(User).where(func.lower(User.username) == normalized.lower())
        )
    db.refresh(user)
    return user


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(
        password.encode(),
        salt=salt,
        n=_SCRYPT_N,
        r=_SCRYPT_R,
        p=_SCRYPT_P,
        dklen=_SCRYPT_KEY_LENGTH,
    )
    encoded_salt = base64.urlsafe_b64encode(salt).decode().rstrip("=")
    encoded_digest = base64.urlsafe_b64encode(digest).decode().rstrip("=")
    return f"scrypt${_SCRYPT_N}${_SCRYPT_R}${_SCRYPT_P}${encoded_salt}${encoded_digest}"


def password_hash_matches(password: str, stored_hash: str | None) -> bool:
    if not stored_hash:
        return False
    try:
        algorithm, n_text, r_text, p_text, salt_text, digest_text = stored_hash.split(
            "$"
        )
        if algorithm != "scrypt":
            return False
        n, r, p = int(n_text), int(r_text), int(p_text)
        if n < 2**10 or n > 2**18 or n & (n - 1) or r < 1 or r > 16 or p < 1 or p > 4:
            return False
        salt = base64.urlsafe_b64decode(salt_text + "=" * (-len(salt_text) % 4))
        expected = base64.urlsafe_b64decode(digest_text + "=" * (-len(digest_text) % 4))
        actual = hashlib.scrypt(
            password.encode(), salt=salt, n=n, r=r, p=p, dklen=len(expected)
        )
        return hmac.compare_digest(actual, expected)
    except (ValueError, TypeError, MemoryError):
        return False
