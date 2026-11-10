from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session

from app.auth import require_broker
from app.db import get_db
from app.integrations.email import EmailProvider, get_email_provider
from app.models import Communication, KofLoad
from app.services.capabilities import require_live_send
from app.services.usage import feature_event
from app.services.kof_emails import (
    email_dict,
    recipient_contact,
    subject_for,
    template,
    thread,
)

router = APIRouter(prefix="/api/kof/loads", dependencies=[Depends(require_broker)])


class SendInput(BaseModel):
    recipient: Literal["dispatch", "carrier"]
    subject: str = Field(min_length=1, max_length=450)
    body: str = Field(min_length=1, max_length=20000)

    @field_validator("subject", "body")
    @classmethod
    def nonblank(cls, value, info):
        if not value.strip() or (
            info.field_name == "subject" and ("\n" in value or "\r" in value)
        ):
            raise ValueError("Provide a nonblank body and single-line subject")
        return value


@router.get("/{order_no}/emails")
def emails(order_no: int, db: Session = Depends(get_db)):
    load = db.get(KofLoad, order_no)
    if not load or load.is_deleted:
        raise HTTPException(404, "KOF load not found")
    return thread(db, order_no)


@router.get("/{order_no}/emails/draft")
def compose(order_no: int, db: Session = Depends(get_db)):
    return template(db, order_no)


@router.post("/{order_no}/emails")
def send(
    order_no: int,
    payload: SendInput,
    request: Request,
    db: Session = Depends(get_db),
    email: EmailProvider = Depends(get_email_provider),
):
    require_live_send("email", email)
    _, address, _ = recipient_contact(db, order_no, payload.recipient)
    subject = subject_for(order_no, payload.subject)
    try:
        external_id = email.send(address, subject, payload.body)
    except Exception:
        raise HTTPException(
            502, "Delivery could not be confirmed. Check Sent mail before trying again."
        ) from None
    row = Communication(
        kof_order_no=order_no,
        channel="email",
        direction="outbound",
        to_addr=address,
        subject=subject,
        content=payload.body,
        external_id=external_id,
        tag="dispatcher_checkin",
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    feature_event(request, "kof_email_send")
    return email_dict(row)
