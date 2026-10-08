from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel

from app.auth import COOKIE_NAME, create_session, password_matches, require_broker
from app.config import get_settings
from app.db import get_db
from app.services.preferences import get_prefs
from sqlalchemy.orm import Session

router = APIRouter(prefix="/api/auth", tags=["auth"])


class LoginRequest(BaseModel):
    password: str


@router.post("/login")
def login(payload: LoginRequest, response: Response) -> dict[str, bool]:
    if not password_matches(payload.password):
        raise HTTPException(status_code=401, detail="Invalid password")
    secure = get_settings().public_base_url.startswith("https://")
    response.set_cookie(
        COOKIE_NAME,
        create_session(),
        httponly=True,
        secure=secure,
        samesite="lax",
        max_age=60 * 60 * 24 * 30,
        path="/",
    )
    return {"authenticated": True}


@router.post("/logout")
def logout(response: Response) -> dict[str, bool]:
    response.delete_cookie(COOKIE_NAME, path="/")
    return {"authenticated": False}


@router.get("/me", dependencies=[Depends(require_broker)])
def me(db: Session = Depends(get_db)) -> dict[str, bool | str]:
    return {
        "authenticated": True,
        "broker_timezone": get_prefs(db).broker_timezone,
    }
