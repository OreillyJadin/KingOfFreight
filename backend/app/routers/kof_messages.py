from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.auth import require_broker
from app.db import get_db
from app.integrations.sms import SmsProvider, get_sms_provider
from app.models import KofLoad
from app.services.kof_messages import send_message, thread
from app.services.usage import feature_event

router = APIRouter(
    prefix="/api/kof/loads",
    tags=["KOF messages"],
    dependencies=[Depends(require_broker)],
)


class SendInput(BaseModel):
    recipient: Literal["carrier", "dispatch"]
    body: str = Field(min_length=1, max_length=1600)


@router.get("/{order_no}/messages")
def messages(order_no: int, db: Session = Depends(get_db)) -> list[dict]:
    if db.get(KofLoad, order_no) is None:
        raise HTTPException(404, "KOF load not found")
    return thread(db, order_no)


@router.post("/{order_no}/messages")
def send(
    order_no: int,
    body: SendInput,
    request: Request,
    db: Session = Depends(get_db),
    sms: SmsProvider = Depends(get_sms_provider),
) -> dict:
    if not body.body.strip():
        raise HTTPException(422, "Message must not be blank")
    result = send_message(db, order_no, body.recipient, body.body, sms)
    if result["status"] == "sent":
        feature_event(request, "kof_text_send")
    return result
