import base64
import hashlib
from typing import Literal

from cryptography.fernet import Fernet
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import KofConnection

KofCredentialSource = Literal["env", "app"]


def _fernet() -> Fernet:
    secret_key = get_settings().secret_key.encode()
    key = base64.urlsafe_b64encode(hashlib.sha256(secret_key).digest())
    return Fernet(key)


def encrypt_kof_password(password: str) -> str:
    return _fernet().encrypt(password.encode()).decode()


def decrypt_kof_password(encrypted_password: str) -> str:
    return _fernet().decrypt(encrypted_password.encode()).decode()


def get_kof_credentials(
    db: Session,
) -> tuple[str, str, KofCredentialSource] | None:
    settings = get_settings()
    if settings.kof_username and settings.kof_password:
        return settings.kof_username, settings.kof_password, "env"

    connection = db.get(KofConnection, 1)
    if connection is None:
        return None
    return (
        connection.username,
        decrypt_kof_password(connection.password_encrypted),
        "app",
    )
