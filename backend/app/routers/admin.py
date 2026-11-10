from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth import (
    admin_exists,
    hash_password,
    lock_admin_changes,
    require_admin,
    require_broker,
)
from app.db import get_db
from app.models import User, utcnow
from app.routers.auth import _set_session_cookie
from app.services.usage_report import report

router = APIRouter(prefix="/api/admin", tags=["Admin"])


@router.get("/usage", dependencies=[Depends(require_admin)])
def usage(
    days: Literal["7", "30", "90"] = Query(default="7"), db: Session = Depends(get_db)
):
    return report(db, int(days))


class Credentials(BaseModel):
    username: str = Field(min_length=1, max_length=120)
    password: str = Field(min_length=10, max_length=256)

    @field_validator("username")
    @classmethod
    def normalize_username(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Username is required")
        return value


class CreateUser(Credentials):
    role: Literal["admin", "member"] = "member"


class ResetPassword(BaseModel):
    password: str = Field(min_length=10, max_length=256)


class UpdateUser(BaseModel):
    role: Literal["admin", "member"] | None = None
    is_active: bool | None = None


def user_response(user: User) -> dict:
    return {
        "id": user.id,
        "username": user.username,
        "role": user.role,
        "is_active": user.is_active,
        "created_at": user.created_at,
        "last_login_at": user.last_login_at,
        "must_set_password": user.must_set_password,
    }


def save_user(db: Session, user: User) -> None:
    db.add(user)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Username already exists") from None
    db.refresh(user)


@router.post("/claim")
def claim(
    body: Credentials,
    response: Response,
    user=Depends(require_broker),
    db: Session = Depends(get_db),
):
    lock_admin_changes(db)
    if admin_exists(db):
        raise HTTPException(409, "An admin account already exists")
    if user is not None:
        raise HTTPException(
            403, "Use a shared-password session to claim the first admin account"
        )
    account = User(
        username=body.username,
        password_hash=hash_password(body.password),
        role="admin",
        must_set_password=False,
        last_login_at=utcnow(),
    )
    save_user(db, account)
    _set_session_cookie(response, account)
    return user_response(account)


@router.get("/users", dependencies=[Depends(require_admin)])
def list_users(db: Session = Depends(get_db)):
    return [
        user_response(user)
        for user in db.scalars(select(User).order_by(func.lower(User.username)))
    ]


@router.post("/users", status_code=201, dependencies=[Depends(require_admin)])
def create_user(body: CreateUser, db: Session = Depends(get_db)):
    lock_admin_changes(db)
    user = User(
        username=body.username,
        password_hash=hash_password(body.password),
        role=body.role,
        must_set_password=True,
    )
    save_user(db, user)
    return user_response(user)


def find_user(db: Session, user_id: int) -> User:
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(404, "User not found")
    return user


@router.post("/users/{user_id}/reset-password", dependencies=[Depends(require_admin)])
def reset_password(user_id: int, body: ResetPassword, db: Session = Depends(get_db)):
    lock_admin_changes(db)
    user = find_user(db, user_id)
    user.password_hash = hash_password(body.password)
    user.must_set_password = True
    user.password_version += 1
    db.commit()
    return user_response(user)


@router.patch("/users/{user_id}", dependencies=[Depends(require_admin)])
def update_user(user_id: int, body: UpdateUser, db: Session = Depends(get_db)):
    lock_admin_changes(db)
    user = find_user(db, user_id)
    if (
        user.role == "admin"
        and user.is_active
        and (body.role == "member" or body.is_active is False)
    ):
        active_admins = db.scalar(
            select(func.count())
            .select_from(User)
            .where(User.role == "admin", User.is_active.is_(True))
        )
        if active_admins == 1:
            raise HTTPException(
                409, "The last active admin cannot be demoted or deactivated"
            )
    if body.role is not None:
        user.role = body.role
    if body.is_active is not None and body.is_active != user.is_active:
        user.is_active = body.is_active
        user.password_version += 1
    db.commit()
    return user_response(user)
