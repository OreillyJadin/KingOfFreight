import logging
import re
from datetime import timedelta, timezone
from typing import Literal
from zoneinfo import ZoneInfo

from fastapi import HTTPException
from sqlalchemy import Integer, cast, exists, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from twilio.base.exceptions import TwilioRestException

from app.integrations.llm import LlmProvider
from app.integrations.sms import SmsProvider
from app.models import Communication, KofLoad, KofMessage, utcnow
from app.services.checkins import handle_driver_reply, normalize_contact
from app.services.preferences import get_prefs
from app.services.twilio_credentials import get_twilio_credentials

logger = logging.getLogger(__name__)
Recipient = Literal["carrier", "dispatch"]


def phone(value: str | None) -> str | None:
    if not value or not re.fullmatch(r"\+?[0-9() .\-\s]+", value.strip()):
        return None
    normalized = (
        "+" + re.sub(r"\D", "", value)
        if value.strip().startswith("+")
        else normalize_contact(value, "sms")
    )
    return normalized if re.fullmatch(r"\+[1-9][0-9]{1,14}", normalized) else None


def recipient_contact(
    db: Session, order_no: int, recipient: Recipient
) -> tuple[KofLoad, str, str]:
    load = db.get(KofLoad, order_no)
    if load is None or load.is_deleted:
        raise HTTPException(404, "KOF load not found")
    number = phone(
        load.carrier_contact_phone if recipient == "carrier" else load.dispatch_phone
    )
    if not number:
        raise HTTPException(422, f"The KOF {recipient} phone is missing or invalid")
    name = (
        load.carrier_contact_name if recipient == "carrier" else load.dispatch_contact
    ) or recipient.title()
    return load, number, f"{name} · …{number[-4:]}"


def message_dict(row: KofMessage) -> dict:
    return {
        name: getattr(row, name)
        for name in (
            "id",
            "order_no",
            "direction",
            "to_phone",
            "from_phone",
            "body",
            "status",
            "error",
            "created_at",
            "match_method",
            "candidate_order_nos",
            "parsed_status",
            "parsed_eta",
            "parsed_summary",
        )
    } | {"confirmed": False}


def thread(db: Session, order_no: int, limit: int = 100) -> list[dict]:
    values = (
        func.json_array_elements_text(KofMessage.candidate_order_nos)
        if db.get_bind().dialect.name == "postgresql"
        else func.json_each(KofMessage.candidate_order_nos)
    ).table_valued("value")
    candidate = exists(
        select(1).select_from(values).where(cast(values.c.value, Integer) == order_no)
    )
    rows = db.scalars(
        select(KofMessage)
        .where(or_(KofMessage.order_no == order_no, candidate))
        .order_by(KofMessage.created_at.desc(), KofMessage.id.desc())
        .limit(limit)
    ).all()
    return [message_dict(row) for row in reversed(rows)]


def send_message(
    db: Session, order_no: int, recipient: Recipient, body: str, sms: SmsProvider
) -> dict:
    _, number, _ = recipient_contact(db, order_no, recipient)
    credentials = get_twilio_credentials(db)
    row = KofMessage(
        order_no=order_no,
        direction="out",
        to_phone=number,
        from_phone=phone(credentials.from_number) if credentials else None,
        body=body,
        status="failed",
        match_method="broker_approved",
    )
    db.add(row)
    db.commit()
    try:
        row.external_id = sms.send(number, body)
        row.status = "sent"
    except Exception as error:
        row.error = (
            f"Twilio rejected the message (code {error.code})"
            if isinstance(error, TwilioRestException)
            else f"SMS send failed ({type(error).__name__})"
        )
    db.commit()
    db.refresh(row)
    return message_dict(row)


def _candidates(
    db: Session, sender: str, body: str
) -> tuple[list[KofLoad], list[KofLoad]]:
    candidates = db.scalars(
        select(KofLoad)
        .join(KofMessage, KofMessage.order_no == KofLoad.order_no)
        .where(
            KofMessage.direction == "out",
            KofMessage.status == "sent",
            KofMessage.to_phone == sender,
            KofMessage.created_at >= utcnow() - timedelta(hours=72),
        )
        .distinct()
        .order_by(KofLoad.order_no)
    ).all()
    explicit = [
        load
        for load in candidates
        if any(
            value
            and re.search(r"(?<!\w)" + re.escape(str(value)) + r"(?!\w)", body, re.I)
            for value in (load.order_no, load.po)
        )
    ]
    return candidates, explicit


def handle_kof_sms(
    db: Session,
    sender: str,
    body: str,
    external_id: str | None,
    llm: LlmProvider,
    to: str | None = None,
) -> None:
    if external_id and (
        db.scalar(select(KofMessage.id).where(KofMessage.external_id == external_id))
        or db.scalar(
            select(Communication.id).where(Communication.external_id == external_id)
        )
    ):
        return
    normalized = phone(sender)
    candidates, explicit = _candidates(db, normalized, body) if normalized else ([], [])
    if not explicit:
        operational = handle_driver_reply(
            db, sender, body, "sms", external_id, llm, store_unmatched=False
        )
        if operational is not None:
            return
    selected = explicit or candidates
    if not selected:
        handle_driver_reply(db, sender, body, "sms", external_id, llm)
        return
    matched = selected[0] if len(selected) == 1 else None
    row = KofMessage(
        order_no=matched.order_no if matched else None,
        direction="in",
        from_phone=normalized,
        to_phone=phone(to),
        body=body,
        external_id=external_id,
        status="received" if matched else "ambiguous",
        match_method="explicit_order_or_po"
        if explicit
        else "single_candidate"
        if matched
        else "ambiguous",
        candidate_order_nos=[load.order_no for load in selected] if not matched else [],
    )
    try:
        parsed = llm.parse_reply(
            body,
            {
                "kind": "status_update",
                "reference": str(matched.order_no) if matched else None,
                "po": matched.po if matched else None,
                "candidate_order_nos": [load.order_no for load in selected],
                "current_load_status": matched.stage if matched else "ambiguous",
            },
        )
        row.parsed_status = parsed.status
        row.parsed_summary = parsed.summary
        if parsed.eta:
            eta = parsed.eta
            if eta.tzinfo is None:
                eta = eta.replace(tzinfo=ZoneInfo(get_prefs(db).broker_timezone))
            row.parsed_eta = eta.astimezone(timezone.utc)
    except Exception as error:
        logger.warning("KOF reply parsing failed: %s", type(error).__name__)
        row.parsed_summary = "Reply recorded; automatic parsing unavailable"
    db.add(row)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        if not external_id or not db.scalar(
            select(KofMessage.id).where(KofMessage.external_id == external_id)
        ):
            raise
