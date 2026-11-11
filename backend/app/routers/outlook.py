import hashlib
import secrets
from urllib.parse import urlencode, urlsplit
from uuid import UUID

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from itsdangerous import BadSignature, URLSafeTimedSerializer
from pydantic import BaseModel, SecretStr
from sqlalchemy.orm import Session

from app.auth import COOKIE_NAME, require_admin, require_broker
from app.config import get_settings
from app.db import get_db
from app.models import OutlookApp, OutlookConnection
from app.routers.twilio import webhook_url
from app.services.kof_credentials import encrypt_kof_password
from app.services.outlook import (
    AUTHORITY,
    SCOPES,
    OAuthError,
    credentials,
    exchange,
    oauth_error,
)

router = APIRouter(
    prefix="/api/email", tags=["Outlook"], dependencies=[Depends(require_broker)]
)
STATE_COOKIE = "outlook_oauth_state"


def redirect_uri(request: Request) -> str:
    url = urlsplit(webhook_url(request))
    return f"{url.scheme}://{url.netloc}/api/email/oauth/callback"


def state_serializer():
    return URLSafeTimedSerializer(get_settings().secret_key, salt="outlook-oauth")


def session_hash(request: Request) -> str:
    return hashlib.sha256(request.cookies.get(COOKIE_NAME, "").encode()).hexdigest()


def result(reason: str, connected=False):
    response = RedirectResponse(
        "/settings?"
        + urlencode(
            {
                "outlook": "connected" if connected else "error",
                **({} if connected else {"reason": reason}),
            }
        ),
        status_code=303,
    )
    response.delete_cookie(STATE_COOKIE, path="/api/email/oauth")
    return response


class AppInput(BaseModel):
    client_id: UUID
    client_secret: SecretStr


@router.get("/connection")
def connection(request: Request, db: Session = Depends(get_db)):
    creds = credentials(db)
    account = db.get(OutlookConnection, 1)
    return {
        "configured": bool(creds),
        "source": creds.source if creds else None,
        "client_id": creds.client_id if creds else None,
        "redirect_uri": redirect_uri(request),
        "status": "needs_reconnect"
        if account and account.needs_reconnect
        else "connected"
        if account
        else "ready"
        if creds
        else "not_set_up",
        "account": {"email": account.email, "name": account.name} if account else None,
    }


@router.put("/connection", dependencies=[Depends(require_admin)])
def save(body: AppInput, request: Request, db: Session = Depends(get_db)):
    secret = body.client_secret.get_secret_value().strip()
    if not secret or len(secret) > 2000:
        raise HTTPException(
            422, "Client secret must contain 1–2000 nonblank characters"
        )
    row = db.get(OutlookApp, 1)
    if not row:
        row = OutlookApp(id=1)
        db.add(row)
    row.client_id = str(body.client_id)
    row.secret_encrypted = encrypt_kof_password(secret)
    account = db.get(OutlookConnection, 1)
    if account:
        db.delete(account)
    db.commit()
    return connection(request, db)


@router.delete("/connection", status_code=204, dependencies=[Depends(require_admin)])
def remove(db: Session = Depends(get_db)):
    for model in (OutlookApp, OutlookConnection):
        row = db.get(model, 1)
        if row:
            db.delete(row)
    db.commit()


@router.delete("/account", status_code=204)
def disconnect(db: Session = Depends(get_db)):
    row = db.get(OutlookConnection, 1)
    if row:
        db.delete(row)
        db.commit()


@router.get("/oauth/start")
def start(request: Request, db: Session = Depends(get_db)):
    creds = credentials(db)
    if not creds:
        return result("Save the Azure app client ID and secret first.")
    state = state_serializer().dumps(
        {
            "session": session_hash(request),
            "nonce": secrets.token_urlsafe(32),
            "client_id": creds.client_id,
            "redirect_uri": redirect_uri(request),
        }
    )
    response = RedirectResponse(
        f"{AUTHORITY}/authorize?"
        + urlencode(
            {
                "client_id": creds.client_id,
                "response_type": "code",
                "redirect_uri": redirect_uri(request),
                "response_mode": "query",
                "scope": SCOPES,
                "state": state,
                "prompt": "select_account",
            }
        ),
        status_code=302,
    )
    response.set_cookie(
        STATE_COOKIE,
        state,
        max_age=600,
        httponly=True,
        secure=get_settings().env == "production",
        samesite="lax",
        path="/api/email/oauth",
    )
    return response


@router.get("/oauth/callback")
def callback(
    request: Request, state: str = "", code: str = "", db: Session = Depends(get_db)
):
    try:
        payload = state_serializer().loads(state, max_age=600)
        creds = credentials(db)
        if (
            not isinstance(payload, dict)
            or not state
            or not secrets.compare_digest(state, request.cookies.get(STATE_COOKIE, ""))
            or payload.get("session") != session_hash(request)
            or not creds
            or payload.get("client_id") != creds.client_id
            or payload.get("redirect_uri") != redirect_uri(request)
        ):
            raise BadSignature("state mismatch")
    except BadSignature:
        return result(
            "Outlook connection expired or could not be verified. Please connect again."
        )
    if request.query_params.get("error"):
        return result(oauth_error(dict(request.query_params)))
    if not code:
        return result(
            "Microsoft did not return an authorization code. Please connect again."
        )
    try:
        token = exchange(
            creds,
            grant_type="authorization_code",
            code=code,
            redirect_uri=payload["redirect_uri"],
        )
        if not token.get("refresh_token"):
            return result(
                "Microsoft did not grant offline access. Please connect again."
            )
        response = httpx.get(
            "https://graph.microsoft.com/v1.0/me",
            headers={"Authorization": f"Bearer {token['access_token']}"},
            params={"$select": "displayName,mail,userPrincipalName"},
            timeout=30,
        )
        response.raise_for_status()
        profile = response.json()
        email = profile.get("mail") or profile.get("userPrincipalName")
        if not email:
            return result("Microsoft did not return an account email address.")
        row = db.get(OutlookConnection, 1)
        if not row:
            row = OutlookConnection(id=1)
            db.add(row)
        row.token_encrypted = encrypt_kof_password(token["refresh_token"])
        row.email = email
        row.name = profile.get("displayName") or email
        row.needs_reconnect = False
        db.commit()
        return result("", connected=True)
    except OAuthError as error:
        return result(str(error))
    except ValueError:
        return result("Microsoft returned an invalid response. Please try again.")
    except httpx.HTTPError:
        return result(
            "Microsoft is unreachable or could not return your account. Please try again."
        )
