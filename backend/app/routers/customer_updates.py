import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from app.auth import require_broker
from app.db import get_db
from app.integrations.email import EmailProvider, get_email_provider, resolve_email_mode
from app.models import (
    Communication,
    CustomerContact,
    CustomerUpdateDraft,
    KofLoad,
    utcnow,
)
from app.services.customer_updates import (
    customer_identity,
    draft_dict,
    drain_deferred,
    email_address,
    pending,
)

logger = logging.getLogger(__name__)
router = APIRouter(
    prefix="/api/customer-updates",
    tags=["Customer updates"],
    dependencies=[Depends(require_broker)],
)


class VersionInput(BaseModel):
    version: int = Field(ge=1)


class DraftEdit(VersionInput):
    to_email: str = Field(max_length=320)
    subject: str = Field(min_length=1, max_length=500)
    body: str = Field(min_length=1, max_length=20000)

    @field_validator("to_email")
    @classmethod
    def validate_email(cls, value):
        value = value.strip()
        if value and not email_address(value):
            raise ValueError("Enter a single valid email address")
        return value

    @field_validator("subject")
    @classmethod
    def validate_subject(cls, value):
        if "\r" in value or "\n" in value or not value.strip():
            raise ValueError("Subject must be a nonblank single line")
        return value

    @field_validator("body")
    @classmethod
    def validate_body(cls, value):
        if not value.strip():
            raise ValueError("Body must not be blank")
        return value


def get_draft(db: Session, draft_id: int) -> CustomerUpdateDraft:
    row = db.scalar(
        select(CustomerUpdateDraft)
        .where(CustomerUpdateDraft.id == draft_id)
        .with_for_update()
    )
    if not row:
        raise HTTPException(404, "Customer update not found")
    return row


def editable(row: CustomerUpdateDraft, version: int):
    if row.state != "pending" or row.version != version or row.send_started_at:
        raise HTTPException(
            409,
            "This draft changed or has already been handled. Reload and review the latest preview.",
        )


@router.get("")
def list_drafts(db: Session = Depends(get_db)) -> dict:
    rows = pending(db)
    return {
        "count": len(rows),
        "drafts": [draft_dict(db, row) for row in rows],
        "email_mode": resolve_email_mode(db),
    }


@router.patch("/{draft_id}")
def edit(draft_id: int, payload: DraftEdit, db: Session = Depends(get_db)) -> dict:
    row = get_draft(db, draft_id)
    editable(row, payload.version)
    for name in ("to_email", "subject", "body"):
        setattr(row, name, getattr(payload, name))
    row.version += 1
    row.updated_at = utcnow()
    db.commit()
    return draft_dict(db, row)


@router.post("/{draft_id}/dismiss")
def dismiss(
    draft_id: int, payload: VersionInput, db: Session = Depends(get_db)
) -> dict:
    row = get_draft(db, draft_id)
    if row.state == "dismissed":
        return draft_dict(db, row)
    if row.state != "pending" or row.version != payload.version:
        raise HTTPException(409, "Draft changed; reload before dismissing")
    row.state = "dismissed"
    row.version += 1
    row.updated_at = utcnow()
    db.commit()
    drain_deferred(db, row)
    return draft_dict(db, row)


@router.post("/{draft_id}/approve")
def approve(
    draft_id: int,
    payload: VersionInput,
    db: Session = Depends(get_db),
    email: EmailProvider = Depends(get_email_provider),
) -> dict:
    row = get_draft(db, draft_id)
    if row.state == "sent":
        return draft_dict(db, row)
    editable(row, payload.version)
    load = db.get(KofLoad, row.order_no)
    if not load or load.is_deleted:
        raise HTTPException(409, "This KOF order is no longer active")
    if not email_address(row.to_email):
        raise HTTPException(422, "Enter a customer email before approving")
    claimed = db.execute(
        update(CustomerUpdateDraft)
        .where(
            CustomerUpdateDraft.id == draft_id,
            CustomerUpdateDraft.state == "pending",
            CustomerUpdateDraft.version == payload.version,
            CustomerUpdateDraft.send_started_at.is_(None),
        )
        .values(send_started_at=utcnow())
    )
    if claimed.rowcount != 1:
        raise HTTPException(409, "This draft has already been handled")
    to_email, subject, body, order_no = (
        row.to_email,
        row.subject,
        row.body,
        row.order_no,
    )
    db.commit()
    try:
        external_id = email.send(to_email, subject, body)
    except Exception as error:
        logger.warning("Customer update delivery unconfirmed: %s", type(error).__name__)
        row.error = "Delivery could not be confirmed. Check Sent mail before dismissing; automatic retry is blocked to prevent duplicates."
        db.commit()
        raise HTTPException(502, row.error) from None
    db.add(
        Communication(
            kof_order_no=order_no,
            channel="email",
            direction="outbound",
            to_addr=to_email,
            subject=subject,
            content=body,
            tag="customer_update",
            external_id=external_id,
        )
    )
    key, _ = customer_identity(db, load)
    if key:
        insert = (
            pg_insert if db.get_bind().dialect.name == "postgresql" else sqlite_insert
        )
        statement = insert(CustomerContact).values(
            customer_key=key, email=to_email, updated_at=utcnow()
        )
        db.execute(
            statement.on_conflict_do_update(
                index_elements=["customer_key"],
                set_={"email": to_email, "updated_at": utcnow()},
            )
        )
    row.state, row.sent_at, row.updated_at = "sent", utcnow(), utcnow()
    row.version += 1
    db.commit()
    drain_deferred(db, row)
    return draft_dict(db, row)
