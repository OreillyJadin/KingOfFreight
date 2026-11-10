from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import AssistantConnection
from app.services.kof_credentials import decrypt_kof_password


def get_assistant_key(db: Session) -> tuple[str, str] | None:
    key = get_settings().anthropic_api_key
    if key:
        return key, "env"
    row = db.get(AssistantConnection, 1)
    if row:
        return decrypt_kof_password(row.key_encrypted), "app"
    return None
