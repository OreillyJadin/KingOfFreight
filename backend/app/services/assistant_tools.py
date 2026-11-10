from datetime import date, datetime, timedelta, timezone
from typing import Any

from fastapi import HTTPException
from sqlalchemy import String, case, cast, func, or_, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.integrations.kof.client import KofClient, KofSiteError
from app.models import (
    Carrier,
    Communication,
    KofLoad,
    KofSyncRun,
    Load,
    LocationPing,
    ScheduledCheckIn,
    StatusUpdate,
)
from app.routers.kof import _latest_note, _parse_note_entries
from app.services.kof_credentials import get_kof_credentials
from app.services.kof_messages import recipient_contact, thread
from app.services.kof_emails import draft as email_draft, thread as email_thread
from app.services.customer_updates import draft_dict, pending

LIMIT = 20


def compact(value: Any) -> Any:
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, str):
        return value[:1200]
    if isinstance(value, dict):
        return {key: compact(item) for key, item in value.items()}
    if isinstance(value, list):
        return [compact(item) for item in value]
    return value


def summary(load: KofLoad | Load) -> dict:
    if isinstance(load, KofLoad):
        return compact(
            dict(
                source="kof",
                id=load.order_no,
                order_no=load.order_no,
                po=load.po,
                label=f"Order #{load.order_no}",
                stage=load.stage,
                carrier=load.carrier,
                lane=f"{load.origin_city or ''}, {load.origin_state or ''} → {load.dest_city or ''}, {load.dest_state or ''}",
                pick_at=load.pick_at,
                delivery_at=load.delivery_at,
            )
        )
    return compact(
        dict(
            source="operational",
            id=load.id,
            label=load.reference,
            reference=load.reference,
            status=load.status,
            carrier=load.carrier.legal_name if load.carrier else None,
            lane=f"{load.pickup_city or ''}, {load.pickup_state or ''} → {load.delivery_city or ''}, {load.delivery_state or ''}",
            pick_at=load.pickup_datetime,
            delivery_at=load.delivery_datetime,
        )
    )


def notes(load: KofLoad) -> list[dict]:
    entries = _parse_note_entries(load.notes_text) + _parse_note_entries(load.log_text)
    return compact(
        sorted(entries, key=lambda entry: entry.get("at") or "", reverse=True)[:10]
    )


class AssistantTools:
    def __init__(self, db: Session):
        self.db = db
        self.references: dict[tuple[str, int], dict] = {}
        self.actions: list[dict] = []

    def draft_dispatcher_email(
        self, order_no: int, recipient: str, subject: str, body: str
    ) -> dict:
        if (
            recipient not in {"carrier", "dispatch"}
            or not subject.strip()
            or len(subject) > 450
            or "\n" in subject
            or "\r" in subject
            or not body.strip()
            or len(body) > 20000
        ):
            return {
                "error": "Choose carrier or dispatch and provide a single-line subject and nonblank body"
            }
        try:
            action = email_draft(self.db, order_no, recipient, subject, body)
        except HTTPException as error:
            return {"error": error.detail}
        if len(self.actions) >= 4:
            return {"error": "Review existing drafts before preparing more messages"}
        if action not in self.actions:
            self.actions.append(action)
        return {
            "pending_action": action,
            "sent": False,
            "instruction": "Review and tap Send. Nothing has been sent.",
        }

    def draft_driver_text(self, order_no: int, recipient: str, body: str) -> dict:
        if (
            recipient not in {"carrier", "dispatch"}
            or not body.strip()
            or len(body) > 1600
        ):
            return {
                "error": "Choose carrier or dispatch and provide a nonblank message up to 1600 characters"
            }
        try:
            load, _, label = recipient_contact(self.db, order_no, recipient)
        except HTTPException as error:
            return {"error": error.detail}
        action = {
            "type": "send_kof_text",
            "order_no": order_no,
            "recipient": recipient,
            "to_label": label,
            "body": body,
        }
        if len(self.actions) >= 4:
            return {"error": "Review existing drafts before preparing more messages"}
        if action not in self.actions:
            self.actions.append(action)
        self.remember(load)
        return {
            "pending_action": action,
            "sent": False,
            "instruction": "Ask the broker to review and tap Send. Nothing has been sent.",
        }

    def remember(self, load: KofLoad | Load) -> dict:
        result = summary(load)
        self.references[(result["source"], result["id"])] = {
            key: result[key] for key in ("source", "id", "label")
        }
        return result

    def search_loads(self, query: str) -> dict:
        query = query.strip()[:200]
        if not query:
            return {"loads": []}
        like = f"%{query}%"
        kof_fields = {
            "order_no": cast(KofLoad.order_no, String),
            "po": KofLoad.po,
            "pu": KofLoad.pu,
            "invoice_no": KofLoad.invoice_no,
            "customer": KofLoad.customer,
            "carrier": KofLoad.carrier,
            "mc": KofLoad.mc,
            "raw": cast(KofLoad.raw, String),
            "notes_text": KofLoad.notes_text,
            "log_text": KofLoad.log_text,
        }
        exact = or_(
            *[
                func.lower(field) == query.lower()
                for name, field in kof_fields.items()
                if name in {"order_no", "po", "pu", "invoice_no"}
            ]
        )
        kof = self.db.scalars(
            select(KofLoad)
            .where(
                KofLoad.is_deleted.is_(False),
                or_(*[field.ilike(like) for field in kof_fields.values()]),
            )
            .order_by(func.coalesce(exact, False).desc(), KofLoad.order_no.desc())
            .limit(LIMIT)
        ).all()
        extracted = Communication.extracted
        comm_match = (
            select(Communication.id)
            .where(
                Communication.load_id == Load.id,
                or_(
                    cast(extracted["reference_numbers"], String).ilike(like),
                    cast(extracted["reference"], String).ilike(like),
                ),
            )
            .exists()
        )
        reference_values = func.json_each(
            case(
                (
                    cast(extracted["reference_numbers"], String) != "null",
                    extracted["reference_numbers"],
                ),
                else_=None,
            )
        ).table_valued("key", "value")
        exact_reference = (
            select(reference_values.c.key)
            .where(
                func.lower(func.trim(cast(reference_values.c.value, String), '"'))
                == query.lower()
            )
            .exists()
        )
        comm_exact = (
            select(Communication.id)
            .where(
                Communication.load_id == Load.id,
                or_(
                    func.lower(func.trim(cast(extracted["reference"], String), '"'))
                    == query.lower(),
                    exact_reference,
                ),
            )
            .exists()
        )
        operational = self.db.scalars(
            select(Load)
            .outerjoin(Carrier)
            .where(
                or_(
                    Load.reference.ilike(like),
                    Carrier.legal_name.ilike(like),
                    Carrier.dba_name.ilike(like),
                    comm_match,
                )
            )
            .order_by(
                or_(func.lower(Load.reference) == query.lower(), comm_exact).desc(),
                Load.id.desc(),
            )
            .limit(LIMIT)
        ).all()
        results = []
        for load in [*kof, *operational]:
            if isinstance(load, KofLoad):
                values = {name: getattr(load, name) for name in kof_fields}
            else:
                values = {
                    "reference": load.reference,
                    "carrier": load.carrier.legal_name if load.carrier else None,
                }
                for comm in self.db.scalars(
                    select(Communication).where(
                        Communication.load_id == load.id,
                        Communication.extracted.is_not(None),
                    )
                ):
                    data = comm.extracted or {}
                    values.update(
                        {
                            f"extracted.reference_numbers.{key}": value
                            for key, value in (
                                data.get("reference_numbers") or {}
                            ).items()
                        }
                    )
                    values["extracted.reference"] = data.get("reference")
                if load.carrier:
                    values["carrier_dba"] = load.carrier.dba_name
            matched = [
                name
                for name, value in values.items()
                if query.lower() in str(value or "").lower()
            ]
            identifiers = {
                "reference",
                "order_no",
                "po",
                "pu",
                "invoice_no",
                "extracted.reference",
            }
            exact_match = any(
                str(value).lower() == query.lower()
                for name, value in values.items()
                if name in identifiers
                or name.startswith("extracted.reference_numbers.")
            )
            results.append(
                {
                    **summary(load),
                    "matched_fields": matched[:10],
                    "exact_identifier_match": exact_match,
                }
            )
        results.sort(key=lambda row: not row["exact_identifier_match"])
        for result in results[:LIMIT]:
            self.references[(result["source"], result["id"])] = {
                key: result[key] for key in ("source", "id", "label")
            }
        return {"loads": results[:LIMIT], "limit": LIMIT}

    def list_pending_customer_updates(self) -> dict:
        rows = pending(self.db)
        return compact(
            {
                "count": len(rows),
                "drafts": [draft_dict(self.db, row) for row in rows[:LIMIT]],
                "queue_url": "/customer-updates",
                "instruction": "Review the exact preview in Customer updates. Only the broker can approve and send.",
            }
        )

    def get_load_status(self, source: str, id: int) -> dict:
        if source not in {"kof", "operational"}:
            return {"error": "source must be kof or operational"}
        load = self.db.get(KofLoad if source == "kof" else Load, id)
        if load is None or (source == "kof" and load.is_deleted):
            return {"error": "Load not found"}
        result = self.remember(load)
        if source == "kof":
            return compact(
                {
                    **result,
                    "pick_status": load.pick_status,
                    "delivery_status": load.delivery_status,
                    "pick_tz": load.pick_tz,
                    "drop_tz": load.drop_tz,
                    "synced_at": load.synced_at,
                    "carrier_contact": {
                        name: getattr(load, name)
                        for name in (
                            "carrier_contact_name",
                            "carrier_contact_phone",
                            "carrier_contact_email",
                            "dispatch_contact",
                            "dispatch_phone",
                        )
                    },
                    "notes": notes(load),
                    "latest_note": _latest_note(
                        load.notes_text, load.log_text, datetime.now(timezone.utc)
                    ),
                    "notes_may_be_incomplete": True,
                    "messages": thread(self.db, id, limit=10),
                    "emails": email_thread(self.db, id, limit=10),
                    "pending_customer_update": next(
                        (
                            draft_dict(self.db, row)
                            for row in pending(self.db)
                            if row.order_no == id
                        ),
                        None,
                    ),
                }
            )
        updates = self.db.scalars(
            select(StatusUpdate)
            .where(StatusUpdate.load_id == id)
            .order_by(StatusUpdate.created_at.desc())
            .limit(10)
        ).all()
        checkins = self.db.scalars(
            select(ScheduledCheckIn)
            .where(ScheduledCheckIn.load_id == id)
            .order_by(ScheduledCheckIn.send_at.desc())
            .limit(10)
        ).all()
        inbound = self.db.scalars(
            select(Communication)
            .where(Communication.load_id == id, Communication.direction == "inbound")
            .order_by(Communication.created_at.desc())
            .limit(5)
        ).all()
        ping = self.db.scalar(
            select(LocationPing)
            .where(LocationPing.load_id == id)
            .order_by(LocationPing.captured_at.desc())
            .limit(1)
        )
        return compact(
            {
                **result,
                "booked_at": load.booked_at,
                "delivered_at": load.delivered_at,
                "status_updates": [
                    {
                        "status": row.status,
                        "confirmed": row.applied,
                        "source": row.source,
                        "note": row.note,
                        "created_at": row.created_at,
                    }
                    for row in updates
                ],
                "checkins": [
                    {
                        "sent_at": row.checkin_sent_at,
                        "reply": row.reply_raw_text,
                        "reply_at": row.reply_received_at,
                        "parsed_status": row.parsed_status,
                        "confirmed": False,
                    }
                    for row in checkins
                ],
                "inbound_communications": [
                    {
                        "channel": row.channel,
                        "text": row.content,
                        "received_at": row.created_at,
                    }
                    for row in inbound
                ],
                "latest_gps": {
                    "lat": float(ping.lat),
                    "lng": float(ping.lng),
                    "captured_at": ping.captured_at,
                }
                if ping
                else None,
            }
        )

    def list_loads(
        self, stage: str | None = None, no_update_hours: float | None = None
    ) -> dict:
        if no_update_hours is not None and not 0 <= no_update_hours <= 8760:
            return {"error": "no_update_hours must be between 0 and 8760"}
        now = datetime.now(timezone.utc)
        results = []
        queries = [
            select(KofLoad).where(
                KofLoad.is_deleted.is_(False),
                KofLoad.stage.in_(
                    [
                        "confirmation",
                        "awaiting_pickup",
                        "in_transit",
                        "awaiting_delivery",
                        "booked",
                        "pending",
                    ]
                ),
            ),
            select(Load).where(Load.status != "delivered"),
        ]
        for index, query in enumerate(queries):
            model = KofLoad if index == 0 else Load
            if stage:
                query = query.where(
                    (model.stage if index == 0 else model.status) == stage
                )
            for load in self.db.scalars(
                query.order_by(
                    model.order_no.desc() if index == 0 else model.id.desc()
                ).limit(200)
            ):
                if index == 0:
                    entry = _latest_note(load.notes_text, load.log_text, now)
                    latest = datetime.fromisoformat(entry["at"]) if entry else None
                else:
                    latest = self.db.scalar(
                        select(func.max(Communication.created_at)).where(
                            Communication.load_id == load.id,
                            Communication.direction == "inbound",
                        )
                    )
                    status_at = self.db.scalar(
                        select(func.max(StatusUpdate.created_at)).where(
                            StatusUpdate.load_id == load.id
                        )
                    )
                    candidates = [
                        value.replace(tzinfo=timezone.utc)
                        if value.tzinfo is None
                        else value
                        for value in (latest, status_at)
                        if value
                    ]
                    latest = max(candidates) if candidates else None
                if latest and latest.tzinfo is None:
                    latest = latest.replace(tzinfo=timezone.utc)
                if (
                    no_update_hours is not None
                    and latest
                    and latest > now - timedelta(hours=no_update_hours)
                ):
                    continue
                results.append({**summary(load), "last_update_at": compact(latest)})
        for result in results[:LIMIT]:
            self.references[(result["source"], result["id"])] = {
                key: result[key] for key in ("source", "id", "label")
            }
        return {"loads": results[:LIMIT], "limit": LIMIT, "scan_limit_per_source": 200}

    def refresh_kof_notes(self, order_no: int) -> dict:
        load = self.db.get(KofLoad, order_no)
        if load is None or load.is_deleted:
            return {"error": "KOF load not found"}
        credentials = get_kof_credentials(self.db)
        if not credentials:
            return {
                "error": "KOF credentials are not configured; fresh notes unavailable"
            }
        try:
            with KofClient(
                credentials[0],
                credentials[1],
                get_settings().kof_base_url,
                timeout=(5, 10),
                max_retries=1,
            ) as client:
                fresh = {
                    attribute: client.get_fulltext(order_no, label)
                    for label, attribute in (
                        ("Notes", "notes_text"),
                        ("log", "log_text"),
                    )
                }
            if any(value is None for value in fresh.values()):
                return {
                    "error": "KOF did not return complete notes/log; stored notes unchanged"
                }
            for attribute, value in fresh.items():
                setattr(load, attribute, value)
            self.db.commit()
        except KofSiteError:
            return {
                "error": "KOF notes refresh failed or timed out; stored notes may be stale"
            }
        return {
            **self.remember(load),
            "notes": notes(load),
            "notes_refreshed_at": datetime.now(timezone.utc).isoformat(),
        }

    def get_sync_status(self) -> dict:
        latest = self.db.scalar(
            select(func.max(KofSyncRun.finished_at)).where(KofSyncRun.status == "ok")
        )
        return {"last_successful_kof_sync_at": compact(latest)}
