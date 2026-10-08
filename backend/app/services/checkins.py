import logging
import re
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.config import get_settings
from app.integrations.email import EmailProvider
from app.integrations.llm import LlmProvider
from app.integrations.sms import SmsProvider
from app.models import Communication, Load, ScheduledCheckIn, StatusUpdate, utcnow
from app.services.messaging import send_outbound
from app.services.templates import render_checkin, render_status_message

logger = logging.getLogger(__name__)

PICKUP_PASSED = {"picked_up", "in_transit", "delivered"}
DELIVERY_PASSED = {"delivered"}


def _aware(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


def run_checkin_tick(
    db: Session,
    now: datetime | None = None,
    sms: SmsProvider | None = None,
    email: EmailProvider | None = None,
) -> None:
    from app.integrations.email import get_email_provider
    from app.integrations.sms import get_sms_provider

    current = now or utcnow()
    sms = sms or get_sms_provider()
    email = email or get_email_provider()
    due = (
        db.scalars(
            select(ScheduledCheckIn)
            .options(joinedload(ScheduledCheckIn.load))
            .where(
                ScheduledCheckIn.state == "scheduled",
                ScheduledCheckIn.send_at <= current,
            )
        )
        .unique()
        .all()
    )
    for checkin in due:
        load = checkin.load
        if (checkin.kind == "pickup" and load.status in PICKUP_PASSED) or (
            checkin.kind == "dropoff" and load.status in DELIVERY_PASSED
        ):
            checkin.state = "skipped"
            continue
        body = checkin.message_text or render_checkin(load, checkin.kind)
        try:
            send_outbound(
                db,
                load,
                checkin.checkin_channel,
                checkin.driver_contact,
                None,
                body,
                "checkin",
                sms,
                email,
            )
        except Exception:
            logger.exception(
                "Failed to send scheduled check-in %s; it will retry next tick",
                checkin.id,
            )
            continue
        checkin.message_text = body
        checkin.checkin_sent_at = current
        checkin.state = "sent"

    sent = db.scalars(
        select(ScheduledCheckIn).where(
            ScheduledCheckIn.state == "sent", ScheduledCheckIn.reply_received.is_(False)
        )
    ).all()
    limit = get_settings().no_reply_alert_minutes
    for checkin in sent:
        if checkin.checkin_sent_at and _aware(checkin.checkin_sent_at) + timedelta(
            minutes=limit
        ) <= _aware(current):
            checkin.state = "no_reply"
            checkin.alert_raised_at = current
    db.commit()


def normalize_contact(contact: str, channel: str | None = None) -> str:
    contact = contact.strip()
    if "@" in contact or channel == "email":
        return contact.lower()
    digits = re.sub(r"\D", "", contact)
    if len(digits) == 10:
        return f"+1{digits}"
    if len(digits) == 11 and digits.startswith("1"):
        return f"+{digits}"
    return f"+{digits}" if digits else contact.lower()


def _contact_match(load: Load, normalized: str) -> bool:
    values = (
        load.driver_phone,
        load.dispatcher_phone,
        load.driver_email,
        load.dispatcher_email,
    )
    return any(value and normalize_contact(value) == normalized for value in values)


def handle_driver_reply(
    db: Session,
    from_contact: str,
    body: str,
    channel: str,
    external_id: str | None = None,
    llm: LlmProvider | None = None,
) -> ScheduledCheckIn | None:
    from app.integrations.llm import get_llm_provider

    normalized = normalize_contact(from_contact, channel)
    if external_id and db.scalar(
        select(Communication.id).where(Communication.external_id == external_id)
    ):
        return None
    checkins = (
        db.scalars(
            select(ScheduledCheckIn)
            .options(joinedload(ScheduledCheckIn.load))
            .where(ScheduledCheckIn.state.in_(["sent", "no_reply"]))
            .order_by(ScheduledCheckIn.checkin_sent_at.desc())
        )
        .unique()
        .all()
    )
    match = next(
        (
            item
            for item in checkins
            if item.load.status != "delivered" and _contact_match(item.load, normalized)
        ),
        None,
    )
    communication = Communication(
        load_id=match.load_id if match else None,
        channel=channel,
        direction="inbound",
        from_addr=from_contact,
        content=body,
        tag="checkin_reply" if match else "other",
        external_id=external_id,
    )
    db.add(communication)
    if match is None:
        db.commit()
        return None

    llm = llm or get_llm_provider()
    load = match.load
    parsed = llm.parse_reply(
        body,
        {
            "kind": match.kind,
            "current_load_status": load.status,
            "reference": load.reference,
            "lane": f"{load.pickup_city or ''}, {load.pickup_state or ''} to {load.delivery_city or ''}, {load.delivery_state or ''}",
            "scheduled_time": match.scheduled_time.isoformat(),
            "current_local_time": datetime.now(
                ZoneInfo(get_settings().broker_timezone)
            ).isoformat(),
        },
    )
    parsed_eta = parsed.eta
    if parsed_eta is not None:
        if parsed_eta.tzinfo is None:
            parsed_eta = parsed_eta.replace(
                tzinfo=ZoneInfo(get_settings().broker_timezone)
            )
        parsed_eta = parsed_eta.astimezone(timezone.utc)
    match.reply_received = True
    match.reply_raw_text = body
    match.reply_received_at = utcnow()
    match.parsed_status = parsed.status
    match.parsed_eta = parsed_eta
    match.parsed_summary = parsed.summary
    match.parse_confidence = parsed.confidence
    match.needs_broker_attention = parsed.needs_broker_attention
    match.state = "replied"
    match.alert_dismissed_at = (
        None
        if parsed.needs_broker_attention or parsed.status == "unclear"
        else utcnow()
    )
    if parsed.status != "unclear":
        draft_status_update(
            db,
            load,
            parsed.status,
            "checkin",
            parsed.summary,
            parsed_eta,
            applied=False,
            checkin_id=match.id,
        )
    db.commit()
    return match


def draft_status_update(
    db: Session,
    load: Load,
    status: str,
    source: str,
    note: str | None,
    eta: datetime | None,
    applied: bool,
    checkin_id: int | None = None,
) -> StatusUpdate:
    for previous in db.scalars(
        select(StatusUpdate).where(
            StatusUpdate.load_id == load.id, StatusUpdate.state == "pending_approval"
        )
    ):
        previous.state = "skipped"
    subject, preview = render_status_message(load, status, note, eta)
    update = StatusUpdate(
        load_id=load.id,
        status=status,
        source=source,
        note=note,
        eta=eta,
        applied=applied,
        customer_channel="email",
        customer_message_subject=subject,
        customer_message_preview=preview,
        state="pending_approval",
        checkin_id=checkin_id,
    )
    db.add(update)
    return update
