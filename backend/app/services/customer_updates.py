import logging
import re
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.integrations.llm import LlmProvider
from app.models import (
    CustomerContact,
    CustomerUpdateDraft,
    KofCustomer,
    KofLoad,
    utcnow,
)
from app.schemas import CarrierUpdate
from app.services.preferences import get_prefs

logger = logging.getLogger(__name__)


def email_address(value: str) -> bool:
    return bool(
        len(value) <= 320
        and re.fullmatch(r"[^\s@<>;,]+@[^\s@<>;,]+\.[^\s@<>;,]+", value)
    )


def customer_identity(
    db: Session, load: KofLoad
) -> tuple[str | None, KofCustomer | None]:
    customers = db.scalars(
        select(KofCustomer).where(
            func.lower(func.trim(KofCustomer.name))
            == (load.customer or "").strip().lower()
        )
    ).all()
    customer = customers[0] if len(customers) == 1 else None
    key = (
        f"kof:{customer.customer_key}"
        if customer
        else f"name:{load.customer.strip().casefold()}"
        if load.customer and not customers
        else None
    )
    return key, customer


def recipient(db: Session, load: KofLoad) -> str:
    key, customer = customer_identity(db, load)
    saved = db.get(CustomerContact, key) if key else None
    if not saved and key and load.customer:
        saved = db.get(CustomerContact, f"name:{load.customer.strip().casefold()}")
    if saved:
        return saved.email
    for raw, accepted in (
        (load.raw, {"customeremail", "customercontactemail"}),
        (
            customer.raw if customer else {},
            {
                "email",
                "emailaddress",
                "contactemail",
                "customeremail",
                "customercontactemail",
            },
        ),
    ):
        for name, value in raw.items():
            if (
                re.sub(r"[^a-z]", "", name.lower()) in accepted
                and isinstance(value, str)
                and email_address(value.strip())
            ):
                return value.strip()
    return ""


def draft_dict(db: Session, row: CustomerUpdateDraft) -> dict:
    load = db.get(KofLoad, row.order_no)
    return {
        name: getattr(row, name)
        for name in (
            "id",
            "order_no",
            "source_refs",
            "summary",
            "status",
            "eta",
            "confidence",
            "to_email",
            "subject",
            "body",
            "state",
            "version",
            "created_at",
            "updated_at",
            "sent_at",
            "send_started_at",
            "error",
        )
    } | {"customer": load.customer if load else None, "queue_url": "/customer-updates"}


def pending(db: Session) -> list[CustomerUpdateDraft]:
    return list(
        db.scalars(
            select(CustomerUpdateDraft)
            .where(CustomerUpdateDraft.state == "pending")
            .order_by(CustomerUpdateDraft.updated_at.desc())
        ).all()
    )


def detect_update(
    db: Session,
    order_no: int,
    channel: str,
    source_id: int,
    text: str,
    received_at: datetime,
    llm: LlmProvider | None,
    classification: CarrierUpdate | None = None,
) -> None:
    try:
        classified = classification or llm.classify_carrier_update(text)
        if not classified.is_update:
            return
        load = db.scalar(
            select(KofLoad).where(KofLoad.order_no == order_no).with_for_update()
        )
        if not load or load.is_deleted:
            return
        prior = db.scalars(
            select(CustomerUpdateDraft)
            .where(CustomerUpdateDraft.order_no == order_no)
            .with_for_update()
        ).all()
        if any(
            any(
                ref["channel"] == channel
                and ref["id"] == source_id
                and not ref.get("deferred")
                for ref in row.source_refs
            )
            for row in prior
        ):
            return
        row = next((row for row in prior if row.state == "pending"), None)
        if received_at.tzinfo is None:
            received_at = received_at.replace(tzinfo=timezone.utc)
        ref = {
            "channel": channel,
            "id": source_id,
            "excerpt": text[:2000],
            "received_at": received_at.isoformat(),
        }
        if row and row.send_started_at:
            row.source_refs = row.source_refs + [
                ref | {"deferred": True, "classification": classified.model_dump()}
            ]
            db.commit()
            return
        if row:
            refs = row.source_refs + [ref]
            if received_at < max(
                datetime.fromisoformat(r["received_at"]) for r in row.source_refs
            ):
                row.source_refs = refs
                db.commit()
                return
            row.source_refs = refs
            row.version += 1
        else:
            row = CustomerUpdateDraft(
                order_no=order_no,
                source_refs=[ref],
                to_email=recipient(db, load),
                state="pending",
                version=1,
            )
        prefs = get_prefs(db)
        stamp = received_at.astimezone(ZoneInfo(prefs.broker_timezone)).strftime(
            "%b %d, %Y %I:%M %p %Z"
        )
        lane = f"{load.origin_city or 'Origin'}, {load.origin_state or ''} → {load.dest_city or 'Destination'}, {load.dest_state or ''}"
        row.summary, row.status, row.eta, row.confidence = (
            " ".join(classified.summary.split()),
            classified.status,
            classified.eta,
            classified.confidence,
        )
        row.subject = f"Update on Order #{order_no} (PO {load.po or 'not recorded'})"[
            :500
        ]
        row.body = f"Hello,\n\nAn update on Order #{order_no} (PO {load.po or 'not recorded'}), {lane}:\n\nThe carrier reported at {stamp}: {row.summary}"
        if classified.eta:
            row.body += f"\nReported ETA: {classified.eta}"
        row.body += f"\n\n{prefs.broker_name}\n{prefs.broker_company}"
        row.updated_at = utcnow()
        db.add(row)
        db.commit()
    except Exception as error:
        db.rollback()
        logger.warning("Customer update detection skipped: %s", type(error).__name__)


def drain_deferred(db: Session, row: CustomerUpdateDraft) -> None:
    for ref in list(row.source_refs):
        if ref.get("deferred"):
            detect_update(
                db,
                row.order_no,
                ref["channel"],
                ref["id"],
                ref["excerpt"],
                datetime.fromisoformat(ref["received_at"]),
                None,
                CarrierUpdate.model_validate(ref["classification"]),
            )
