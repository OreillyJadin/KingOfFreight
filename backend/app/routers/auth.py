from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.auth import (
    COOKIE_NAME,
    create_session,
    hash_password,
    password_hash_matches,
    password_matches,
    require_broker,
)
from app.config import get_settings
from app.db import get_db
from app.models import User
from app.services.preferences import get_prefs

router = APIRouter(prefix="/api/auth", tags=["auth"])


class LoginRequest(BaseModel):
    username: str | None = None
    password: str


class SetPasswordRequest(BaseModel):
    new_password: str = Field(min_length=10)


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str = Field(min_length=10)


def _set_session_cookie(response: Response, user: User | None = None) -> None:
    secure = get_settings().public_base_url.startswith("https://")
    response.set_cookie(
        COOKIE_NAME,
        create_session(
            user.id if user is not None else None,
            user.password_version if user is not None else None,
        ),
        httponly=True,
        secure=secure,
        samesite="lax",
        max_age=60 * 60 * 24 * 30,
        path="/",
    )


@router.post("/login")
def login(
    payload: LoginRequest, response: Response, db: Session = Depends(get_db)
) -> dict[str, bool | str | None]:
    username = (payload.username or "").strip()
    user: User | None = None
    if username:
        user = db.scalar(
            select(User).where(func.lower(User.username) == username.lower())
        )
        if user is None:
            raise HTTPException(status_code=401, detail="Invalid username or password")
        if user.password_hash is not None:
            valid_password = password_hash_matches(payload.password, user.password_hash)
        elif (
            user.must_set_password
            and (
                bootstrap_username := (get_settings().bootstrap_username or "").strip()
            )
            and user.username.casefold() == bootstrap_username.casefold()
        ):
            valid_password = True
        else:
            valid_password = user.must_set_password and password_matches(
                payload.password
            )
        if not valid_password:
            raise HTTPException(status_code=401, detail="Invalid username or password")
    elif not password_matches(payload.password):
        raise HTTPException(status_code=401, detail="Invalid password")

    _set_session_cookie(response, user)
    return {
        "authenticated": True,
        "username": user.username if user is not None else None,
        "must_set_password": user.must_set_password if user is not None else False,
    }


@router.post("/logout")
def logout(response: Response) -> dict[str, bool]:
    response.delete_cookie(COOKIE_NAME, path="/")
    return {"authenticated": False}


@router.get("/me")
def me(
    user: User | None = Depends(require_broker), db: Session = Depends(get_db)
) -> dict[str, bool | str | None]:
    return {
        "authenticated": True,
        "broker_timezone": get_prefs(db).broker_timezone,
        "username": user.username if user is not None else None,
        "must_set_password": user.must_set_password if user is not None else False,
    }


@router.post("/set-password")
def set_password(
    payload: SetPasswordRequest,
    response: Response,
    user: User | None = Depends(require_broker),
    db: Session = Depends(get_db),
) -> dict[str, bool]:
    if user is None or not user.must_set_password:
        raise HTTPException(status_code=403, detail="password_setup_not_required")
    user.password_hash = hash_password(payload.new_password)
    user.password_version += 1
    user.must_set_password = False
    db.commit()
    _set_session_cookie(response, user)
    return {"ok": True}


@router.post("/change-password")
def change_password(
    payload: ChangePasswordRequest,
    response: Response,
    user: User | None = Depends(require_broker),
    db: Session = Depends(get_db),
) -> dict[str, bool]:
    if user is None or user.must_set_password:
        raise HTTPException(status_code=403, detail="personal_account_required")
    if not password_hash_matches(payload.current_password, user.password_hash):
        raise HTTPException(status_code=400, detail="Current password is incorrect")
    user.password_hash = hash_password(payload.new_password)
    user.password_version += 1
    db.commit()
    _set_session_cookie(response, user)
    return {"ok": True}
