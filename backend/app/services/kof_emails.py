import re

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Communication, KofLoad
from app.services.customer_updates import email_address
from app.services.preferences import get_prefs


def recipient_contact(db: Session, order_no: int, recipient: str):
    load = db.get(KofLoad, order_no)
    if not load or load.is_deleted:
        raise HTTPException(404, "KOF load not found")
    raw = {
        re.sub(r"[^a-z]", "", key.lower()): value
        for key, value in (load.raw or {}).items()
    }
    address = (
        load.carrier_contact_email
        if recipient == "carrier"
        else next(
            (
                raw[key]
                for key in ("dispatchemail", "dispatchcontactemail", "dispatcheremail")
                if raw.get(key)
            ),
            load.carrier_contact_email,
        )
    )
    if not isinstance(address, str) or not email_address(address.strip()):
        raise HTTPException(
            422,
            "No dispatcher email is on file in KOF"
            if recipient == "dispatch"
            else "No carrier email is on file in KOF",
        )
    address = address.strip()
    name = (
        load.dispatch_contact if recipient == "dispatch" else load.carrier_contact_name
    ) or recipient.title()
    local, domain = address.rsplit("@", 1)
    return load, address, f"{name} · {local[:1]}…@{domain}"


def subject_for(order_no: int, subject: str) -> str:
    return (
        subject
        if re.search(rf"Order #{order_no}(?!\d)", subject, re.I)
        else f"Order #{order_no} — {subject}"
    )


def email_dict(row: Communication) -> dict:
    return {
        key: getattr(row, key)
        for key in (
            "id",
            "direction",
            "from_addr",
            "to_addr",
            "subject",
            "content",
            "created_at",
        )
    }


def thread(db: Session, order_no: int, limit: int = 100) -> list[dict]:
    rows = db.scalars(
        select(Communication)
        .where(Communication.kof_order_no == order_no, Communication.channel == "email")
        .order_by(Communication.created_at.desc(), Communication.id.desc())
        .limit(limit)
    ).all()
    return [email_dict(row) for row in reversed(rows)]


def draft(db: Session, order_no: int, recipient: str, subject: str, body: str) -> dict:
    _, _, label = recipient_contact(db, order_no, recipient)
    return dict(
        type="send_kof_email",
        order_no=order_no,
        recipient=recipient,
        to_label=label,
        subject=subject_for(order_no, subject),
        body=body,
    )


def template(db: Session, order_no: int) -> dict:
    load, _, _ = recipient_contact(db, order_no, "dispatch")
    prefs = get_prefs(db)
    return draft(
        db,
        order_no,
        "dispatch",
        f"Order #{order_no} (PO {load.po or 'not recorded'}) — Status and ETA",
        f"Hello,\n\nCould you please share the current status and ETA for Order #{order_no} (PO {load.po or 'not recorded'}), {load.origin_city or ''}, {load.origin_state or ''} to {load.dest_city or ''}, {load.dest_state or ''}?\n\nThank you,\n{prefs.broker_name}\n{prefs.broker_company}",
    )
