from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth import require_broker
from app.db import get_db
from app.models import TeamMember

router = APIRouter(prefix="/api/team-members", dependencies=[Depends(require_broker)])


class MemberInput(BaseModel):
    name: str = Field(min_length=1, max_length=120)

    @field_validator("name")
    @classmethod
    def clean_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Name cannot be blank")
        return value


class MemberEdit(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    is_active: bool | None = None

    @field_validator("name")
    @classmethod
    def clean_name(cls, value: str | None) -> str | None:
        return MemberInput(name=value).name if value is not None else None


def save(db: Session, row: TeamMember) -> dict:
    db.add(row)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            409, "A team member with that name already exists"
        ) from None
    return member_dict(row)


def member_dict(row: TeamMember) -> dict:
    return {
        "id": row.id,
        "name": row.name,
        "is_active": row.is_active,
        "created_at": row.created_at,
    }


@router.get("")
def members(db: Session = Depends(get_db)) -> list[dict]:
    return [
        member_dict(row)
        for row in db.scalars(
            select(TeamMember).order_by(func.lower(TeamMember.name), TeamMember.id)
        )
    ]


@router.post("", status_code=201)
def create(body: MemberInput, db: Session = Depends(get_db)) -> dict:
    return save(db, TeamMember(name=body.name))


@router.patch("/{member_id}")
def update(member_id: int, body: MemberEdit, db: Session = Depends(get_db)) -> dict:
    row = db.get(TeamMember, member_id)
    if row is None:
        raise HTTPException(404, "Team member not found")
    if body.name is not None:
        row.name = body.name
    if body.is_active is not None:
        row.is_active = body.is_active
    return save(db, row)
