from dataclasses import dataclass, field

import httpx
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import OutlookApp, OutlookConnection
from app.services.kof_credentials import decrypt_kof_password, encrypt_kof_password

AUTHORITY = "https://login.microsoftonline.com/common/oauth2/v2.0"
SCOPES = "offline_access User.Read Mail.Read Mail.Send"
CONSENT_ERROR = "Your company requires IT approval for this app. On the Microsoft screen, use the request approval option if available."


class OAuthError(ValueError):
    pass


@dataclass(frozen=True)
class OutlookCredentials:
    client_id: str
    secret: str = field(repr=False)
    source: str


def credentials(db: Session) -> OutlookCredentials | None:
    row = db.get(OutlookApp, 1)
    if row:
        return OutlookCredentials(
            row.client_id, decrypt_kof_password(row.secret_encrypted), "app"
        )
    settings = get_settings()
    if all(
        value and value.strip()
        for value in (settings.outlook_client_id, settings.outlook_client_secret)
    ):
        return OutlookCredentials(
            settings.outlook_client_id.strip(),
            settings.outlook_client_secret.strip(),
            "env",
        )
    return None


def oauth_error(payload: dict) -> str:
    codes = {str(code) for code in payload.get("error_codes", [])}
    description = str(payload.get("error_description", ""))
    if codes.intersection({"65001", "90094", "90095"}) or any(
        f"AADSTS{code}" in description for code in (65001, 90094, 90095)
    ):
        return CONSENT_ERROR
    return {
        "access_denied": "Outlook connection was cancelled or denied.",
        "invalid_client": "Microsoft rejected the app credentials. Check the client ID and secret.",
        "invalid_grant": "Outlook authorization expired or was revoked. Connect Outlook again.",
    }.get(
        payload.get("error"),
        "Microsoft could not connect Outlook. Check the app configuration and try again.",
    )


def exchange(creds: OutlookCredentials, **values) -> dict:
    response = httpx.post(
        f"{AUTHORITY}/token",
        data={
            "client_id": creds.client_id,
            "client_secret": creds.secret,
            "scope": SCOPES,
            **values,
        },
        timeout=30,
    )
    payload = response.json()
    if response.is_error or "access_token" not in payload:
        raise OAuthError(oauth_error(payload))
    return payload


def access_token(db: Session) -> str:
    row = db.get(OutlookConnection, 1)
    creds = credentials(db)
    if row and not creds:
        row.needs_reconnect = True
        db.commit()
    if not row or row.needs_reconnect or not creds:
        raise ValueError("Connect Outlook in Settings before sending email.")
    response = httpx.post(
        f"{AUTHORITY}/token",
        data={
            "client_id": creds.client_id,
            "client_secret": creds.secret,
            "grant_type": "refresh_token",
            "refresh_token": decrypt_kof_password(row.token_encrypted),
            "scope": SCOPES,
        },
        timeout=30,
    )
    payload = response.json()
    if response.is_error or "access_token" not in payload:
        if payload.get("error") in {
            "invalid_grant",
            "invalid_client",
            "interaction_required",
            "consent_required",
            "unauthorized_client",
        }:
            row.needs_reconnect = True
            db.commit()
        raise ValueError(oauth_error(payload))
    if payload.get("refresh_token"):
        row.token_encrypted = encrypt_kof_password(payload["refresh_token"])
        db.commit()
    return payload["access_token"]
