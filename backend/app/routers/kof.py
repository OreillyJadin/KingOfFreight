from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
import re
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import (
    Integer,
    String,
    and_,
    case,
    cast,
    func,
    literal,
    or_,
    select,
)
from sqlalchemy.orm import Session

from app.auth import require_broker
from app.config import get_settings
from app.db import get_db
from app.integrations.kof.parser import parse_time, strip_more_suffix
from app.models import KofBranch, KofListSnapshot, KofLoad, KofSyncRun
from app.services.kof_sync import start_sync

router = APIRouter(
    prefix="/api/kof",
    tags=["KOF"],
    dependencies=[Depends(require_broker)],
)
_ACTIVE_STAGES = ("awaiting_pickup", "in_transit", "awaiting_delivery")
_NOTE_TIMESTAMP = re.compile(
    r"(?<!\d)(?P<at>\d{4}-\d{2}-\d{2}[ \t]+\d{2}:\d{2}:\d{2}|"
    r"\d{1,2}/\d{1,2}/\d{4}[ \t]+\d{1,2}:\d{2}:\d{2}[ \t]+[ap]m)(?!\d)",
    re.IGNORECASE,
)


def _date_range(start: date | None, end: date | None) -> tuple[date, date]:
    end_date = end or date.today()
    start_date = start or end_date - timedelta(days=89)
    if start_date > end_date:
        raise HTTPException(status_code=422, detail="start must be on or before end")
    return start_date, end_date


def _date_filters(start: date | None, end: date | None) -> tuple[date, date, list]:
    start_date, end_date = _date_range(start, end)
    return (
        start_date,
        end_date,
        [
            KofLoad.is_deleted.is_(False),
            KofLoad.date_of_sale >= start_date,
            KofLoad.date_of_sale <= end_date,
        ],
    )


def _number(value) -> float | None:
    if value is None:
        return None
    return round(float(value), 2)


def _margin_expression():
    return func.sum(KofLoad.profit) * 100.0 / func.nullif(func.sum(KofLoad.price), 0)


def _on_time_expressions():
    numerator = func.sum(case((KofLoad.on_time.is_(True), 1), else_=0))
    denominator = func.sum(case((KofLoad.on_time.is_not(None), 1), else_=0))
    return numerator, denominator


def _on_time_percent(numerator, denominator) -> float | None:
    if not denominator:
        return None
    return round(float(numerator or 0) * 100 / float(denominator), 2)


def _period_expression(interval: str, dialect: str):
    if dialect == "postgresql":
        return cast(func.date_trunc(interval, KofLoad.date_of_sale), String)
    if interval == "month":
        return func.strftime("%Y-%m-01", KofLoad.date_of_sale)
    weekday = cast(func.strftime("%w", KofLoad.date_of_sale), Integer)
    days_from_monday = (weekday + 6) % 7
    return func.date(
        KofLoad.date_of_sale,
        func.printf("-%d days", days_from_monday),
    )


def _period_string(value) -> str:
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return str(value)[:10]


def _status_reached(value: str | None) -> bool:
    normalized = (value or "").strip().lower()
    if normalized in {"1", "yes", "y", "true", "checked", "✓", "☑", "x"}:
        return True
    if normalized in {"", "0", "no", "n", "false", "unchecked", "pending"}:
        return False
    if normalized.startswith(("not ", "unpaid")):
        return False
    return any(
        phrase in normalized
        for phrase in (
            "picked up",
            "picked-up",
            "in transit",
            "in-transit",
            "delivered",
            "complete",
            "paid",
            "billed",
            "invoiced",
            "confirmed",
            "received",
        )
    )


def _appointment_passed(
    appointment: datetime | None,
    tz_name: str | None,
    now: datetime,
    *,
    time_known: bool = True,
) -> bool:
    if appointment is None:
        return False
    try:
        zone = ZoneInfo(tz_name or get_settings().broker_timezone)
    except (ZoneInfoNotFoundError, ValueError):
        zone = ZoneInfo(get_settings().broker_timezone)
    if not time_known:
        appointment_day = appointment.date()
        return now.astimezone(zone).date() > appointment_day
    local_appointment = (
        appointment.replace(tzinfo=zone)
        if appointment.tzinfo is None
        else appointment.astimezone(zone)
    )
    return local_appointment.astimezone(timezone.utc) < now.astimezone(timezone.utc)


def _raw_time_known(load: KofLoad, labels: tuple[str, ...]) -> bool:
    values = {
        re.sub(r"[^a-z0-9]+", "", key.lower()): value for key, value in load.raw.items()
    }
    return any(
        parse_time(values.get(re.sub(r"[^a-z0-9]+", "", label.lower())))
        for label in labels
    )


def _is_late(load: KofLoad, now: datetime | None = None) -> bool:
    now_utc = now or datetime.now(timezone.utc)
    pick_time_known = _raw_time_known(load, ("Pick Time", "Pickup Time"))
    delivery_time_known = _raw_time_known(
        load, ("Delivery Time", "Drop Time", "Delivery Appointment Time")
    )
    if load.stage == "awaiting_pickup":
        return bool(
            not _status_reached(load.pick_status)
            and _appointment_passed(
                load.pick_at, load.pick_tz, now_utc, time_known=pick_time_known
            )
        )
    if load.stage in {"in_transit", "awaiting_delivery"}:
        return bool(
            not _status_reached(load.delivery_status)
            and _appointment_passed(
                load.delivery_at,
                load.drop_tz,
                now_utc,
                time_known=delivery_time_known,
            )
        )
    if not _status_reached(load.pick_status):
        return bool(
            _appointment_passed(
                load.pick_at, load.pick_tz, now_utc, time_known=pick_time_known
            )
        )
    return bool(
        not _status_reached(load.delivery_status)
        and _appointment_passed(
            load.delivery_at,
            load.drop_tz,
            now_utc,
            time_known=delivery_time_known,
        )
    )


def _load_row(load: KofLoad, now: datetime | None = None) -> dict:
    return {
        "order_no": load.order_no,
        "date_of_sale": load.date_of_sale.isoformat() if load.date_of_sale else None,
        "customer": load.customer,
        "branch": load.branch,
        "carrier": load.carrier,
        "mc": load.mc,
        "origin_city": load.origin_city,
        "origin_state": load.origin_state,
        "dest_city": load.dest_city,
        "dest_state": load.dest_state,
        "pick_at": load.pick_at.isoformat() if load.pick_at else None,
        "pick_tz": load.pick_tz,
        "delivery_at": load.delivery_at.isoformat() if load.delivery_at else None,
        "drop_tz": load.drop_tz,
        "equipment": load.equipment,
        "weight": _number(load.weight),
        "price": _number(load.price),
        "cost": _number(load.cost),
        "profit": _number(load.profit),
        "stage": load.stage,
        "billed_status": load.billed_status,
        "paid_status": load.paid_status,
        "late": _is_late(load, now),
    }


def _parse_note_entries(text: str | None) -> list[dict]:
    text = strip_more_suffix(text)
    if not text or not text.strip():
        return []
    matches = list(_NOTE_TIMESTAMP.finditer(text))
    if not matches:
        return [{"at": None, "text": text.strip()}]
    entries = []
    for index, match in enumerate(matches):
        next_start = (
            matches[index + 1].start() if index + 1 < len(matches) else len(text)
        )
        entry_text = text[match.end() : next_start].strip(" \t\r\n-")
        author_match = re.match(
            r"(?P<author>[^\r\n]{1,100}?)\s+-\s+(?P<text>.*)",
            entry_text,
            re.DOTALL,
        )
        author = author_match.group("author").strip() if author_match else None
        entry_text = author_match.group("text").strip() if author_match else entry_text
        entry_text = strip_more_suffix(entry_text) or ""
        try:
            raw_timestamp = re.sub(
                r"\s+", " ", match.group("at").replace(".", "")
            ).strip()
            if raw_timestamp[4] == "-":
                timestamp = datetime.strptime(raw_timestamp, "%Y-%m-%d %H:%M:%S")
            else:
                timestamp = datetime.strptime(raw_timestamp, "%m/%d/%Y %I:%M:%S %p")
        except ValueError:
            timestamp = None
        entry = {
            "at": (
                timestamp.replace(tzinfo=ZoneInfo("America/Chicago")).isoformat()
                if timestamp
                else None
            ),
            "text": entry_text,
        }
        if author:
            entry["author"] = author
        entries.append(entry)
    entries.sort(
        key=lambda entry: (
            datetime.fromisoformat(entry["at"]).astimezone(timezone.utc)
            if entry["at"]
            else datetime.min.replace(tzinfo=timezone.utc)
        ),
        reverse=True,
    )
    return entries


def _latest_note(
    notes_text: str | None, log_text: str | None, now: datetime
) -> dict | None:
    entries = _parse_note_entries(notes_text) + _parse_note_entries(log_text)
    cutoff = now.astimezone(timezone.utc) + timedelta(minutes=5)
    timestamped = [
        entry
        for entry in entries
        if entry["at"]
        and datetime.fromisoformat(entry["at"]).astimezone(timezone.utc) <= cutoff
    ]
    if not timestamped:
        return None
    return max(
        timestamped,
        key=lambda entry: datetime.fromisoformat(entry["at"]).astimezone(timezone.utc),
    )


def _hours_since_update(entry: dict | None, now: datetime) -> float | None:
    if not entry or not entry["at"]:
        return None
    updated_at = datetime.fromisoformat(entry["at"]).astimezone(timezone.utc)
    elapsed_seconds = (now.astimezone(timezone.utc) - updated_at).total_seconds()
    if elapsed_seconds < -timedelta(minutes=5).total_seconds():
        return None
    return round(max(0, elapsed_seconds) / 3600, 2)


def _lane_expressions(level: str):
    if level == "state":
        return (
            func.coalesce(KofLoad.origin_state, "Unknown"),
            func.coalesce(KofLoad.dest_state, "Unknown"),
        )
    origin_city = func.nullif(func.lower(func.trim(KofLoad.origin_city)), "")
    origin_state = func.nullif(func.upper(func.trim(KofLoad.origin_state)), "")
    dest_city = func.nullif(func.lower(func.trim(KofLoad.dest_city)), "")
    dest_state = func.nullif(func.upper(func.trim(KofLoad.dest_state)), "")
    origin = case(
        (
            and_(origin_city.is_not(None), origin_state.is_not(None)),
            origin_city + literal(", ") + origin_state,
        ),
        (origin_city.is_not(None), origin_city),
        else_=func.coalesce(origin_state, "Unknown"),
    )
    destination = case(
        (
            and_(dest_city.is_not(None), dest_state.is_not(None)),
            dest_city + literal(", ") + dest_state,
        ),
        (dest_city.is_not(None), dest_city),
        else_=func.coalesce(dest_state, "Unknown"),
    )
    return origin, destination


def _known_lane_filters() -> list:
    unknown_states = ("", "unknown", "n/a", "na", "?")
    return [
        KofLoad.origin_state.is_not(None),
        KofLoad.dest_state.is_not(None),
        func.lower(func.trim(KofLoad.origin_state)).notin_(unknown_states),
        func.lower(func.trim(KofLoad.dest_state)).notin_(unknown_states),
    ]


def _format_city_label(value: str | None) -> str | None:
    if value is None:
        return None
    value = value.strip()
    if re.fullmatch(r"[A-Za-z]{2}", value):
        return value.upper()
    city, separator, state = value.rpartition(",")
    if separator and re.fullmatch(r"\s*[A-Za-z]{2}\s*", state):
        return f"{city.strip().title()}, {state.strip().upper()}"
    return value.title()


def _branch_text(raw: dict, key: str) -> str | None:
    value = raw.get(key)
    if value is None:
        return None
    value = str(value).strip()
    return value or None


def _strip_branch_suffixes(value: str) -> str:
    normalized = value.strip().upper()
    normalized = re.sub(r"\s+-\s+[^,]*$", "", normalized)
    normalized = re.sub(r"\s+\d{5}(?:-\d{4})?$", "", normalized)
    normalized = re.sub(r"\s+[A-Z]{1,2}\d{1,3}$", "", normalized)
    return normalized.strip()


def _parse_branch_label(label: str) -> tuple[str | None, str | None]:
    normalized = _strip_branch_suffixes(label)
    match = re.search(r"(?:,\s*|\s+)([A-Z]{2})$", normalized)
    if not match:
        return None, None
    city = normalized[: match.start()].strip(" ,")
    city = re.sub(r"^[A-Z]{1,2}\d{1,3}\s+", "", city)
    return city.title() or None, match.group(1)


def _clean_branch_city(value: str, state: str | None) -> str | None:
    parsed_city, _ = _parse_branch_label(value)
    if parsed_city:
        return parsed_city
    normalized = _strip_branch_suffixes(value)
    if state:
        normalized = re.sub(
            rf"(?:,\s*|\s+){re.escape(state.strip().upper())}$",
            "",
            normalized,
        )
    normalized = re.sub(r"^[A-Z]{1,2}\d{1,3}\s+", "", normalized)
    return normalized.strip(" ,").title() or None


def _matching_branch_raw(
    branches: list[KofBranch], label: str, customer: str | None
) -> dict:
    for branch in branches:
        raw = branch.raw if isinstance(branch.raw, dict) else {}
        if _branch_text(raw, "Branch No. / Loc.") != label:
            continue
        company = _branch_text(raw, "Company")
        if (
            company
            and customer
            and not customer.strip().casefold().startswith(company.casefold())
        ):
            continue
        if company and not customer:
            continue
        return raw
    return {}


def _branch_location(label: str, raw: dict) -> tuple[str | None, str | None]:
    parsed_label_city, parsed_label_state = _parse_branch_label(label)
    raw_city = _branch_text(raw, "City")
    raw_state = _branch_text(raw, "State/Province")
    parsed_raw_city, parsed_raw_state = (
        _parse_branch_label(raw_city) if raw_city else (None, None)
    )
    state = raw_state or parsed_raw_state or parsed_label_state
    city = (
        parsed_raw_city or _clean_branch_city(raw_city, state)
        if raw_city
        else parsed_label_city
    )
    return (
        _format_city_label(city),
        state.upper() if state else None,
    )


def _branch_contact(raw: dict) -> dict | None:
    first = _branch_text(raw, "First Name")
    last = _branch_text(raw, "Last Name")
    contact = {
        "name": " ".join(part for part in (first, last) if part) or None,
        "phone": _branch_text(raw, "Business Phone")
        or _branch_text(raw, "Mobile Phone"),
        "email": _branch_text(raw, "E-mail Address"),
        "address": _branch_text(raw, "Address"),
    }
    return contact if any(contact.values()) else None


def _customer_prefix_filter(customer: str):
    return func.lower(func.trim(KofLoad.customer)).startswith(
        customer.strip().casefold(), autoescape=True
    )


def _lane_filters(
    start: date | None,
    end: date | None,
    branch: str | None,
    customer: str | None,
    origin_city: str | None,
) -> list:
    _, _, filters = _date_filters(start, end)
    if branch and branch.strip():
        filters.append(KofLoad.branch == branch.strip())
    if customer and customer.strip():
        filters.append(_customer_prefix_filter(customer))
    if origin_city and origin_city.strip():
        filters.append(
            func.lower(func.trim(KofLoad.origin_city)) == origin_city.strip().casefold()
        )
    return filters


def _lane_metrics(
    db: Session,
    filters: list,
    level: str,
    *,
    min_loads: int = 1,
    limit: int | None = None,
) -> list[dict]:
    lane_filters = [*filters, *_known_lane_filters()]
    origin, destination = _lane_expressions(level)
    metrics_query = (
        select(
            origin.label("origin"),
            destination.label("destination"),
            func.count(KofLoad.order_no),
            func.avg(KofLoad.price),
            func.avg(KofLoad.cost),
            func.avg(KofLoad.profit),
            _margin_expression(),
            func.min(KofLoad.cost),
            func.max(KofLoad.cost),
        )
        .where(*lane_filters)
        .group_by(origin, destination)
        .having(func.count(KofLoad.order_no) >= min_loads)
        .order_by(func.count(KofLoad.order_no).desc(), origin, destination)
    )
    if limit is not None:
        metrics_query = metrics_query.limit(limit)
    metrics = db.execute(metrics_query).all()
    ranked = (
        select(
            origin.label("origin"),
            destination.label("destination"),
            KofLoad.cost.label("last_cost"),
            KofLoad.date_of_sale.label("last_date"),
            func.row_number()
            .over(
                partition_by=(origin, destination),
                order_by=(KofLoad.date_of_sale.desc(), KofLoad.order_no.desc()),
            )
            .label("position"),
        )
        .where(*lane_filters)
        .subquery()
    )
    last_rows = db.execute(
        select(
            ranked.c.origin,
            ranked.c.destination,
            ranked.c.last_cost,
            ranked.c.last_date,
        ).where(ranked.c.position == 1)
    ).all()
    last_by_lane = {(row[0], row[1]): (row[2], row[3]) for row in last_rows}
    return [
        {
            "origin": _format_city_label(row[0]) if level == "city" else row[0],
            "destination": (_format_city_label(row[1]) if level == "city" else row[1]),
            "loads": int(row[2] or 0),
            "avg_price": _number(row[3]),
            "avg_cost": _number(row[4]),
            "avg_profit": _number(row[5]),
            "margin_pct": _number(row[6]),
            "min_cost": _number(row[7]),
            "max_cost": _number(row[8]),
            "last_cost": _number(last_by_lane.get((row[0], row[1]), (None, None))[0]),
            "last_date": (
                last_by_lane[(row[0], row[1])][1].isoformat()
                if last_by_lane.get((row[0], row[1]), (None, None))[1]
                else None
            ),
        }
        for row in metrics
    ]


def _average_summary(db: Session, filters: list) -> dict:
    on_time_num, on_time_den = _on_time_expressions()
    row = db.execute(
        select(
            func.count(KofLoad.order_no),
            func.sum(KofLoad.price),
            func.sum(KofLoad.cost),
            func.sum(KofLoad.profit),
            func.avg(KofLoad.price),
            func.avg(KofLoad.cost),
            func.avg(KofLoad.profit),
            _margin_expression(),
            on_time_num,
            on_time_den,
        ).where(*filters)
    ).one()
    return {
        "loads": int(row[0] or 0),
        "revenue": _number(row[1]) or 0,
        "cost": _number(row[2]) or 0,
        "profit": _number(row[3]) or 0,
        "margin_pct": _number(row[7]),
        "avg_price": _number(row[4]),
        "avg_cost": _number(row[5]),
        "avg_profit": _number(row[6]),
        "on_time_pct": _on_time_percent(row[8], row[9]),
    }


@router.get("/sync")
def sync_status(db: Session = Depends(get_db)) -> dict:
    settings = get_settings()
    last_run = db.scalar(
        select(KofSyncRun).order_by(KofSyncRun.started_at.desc()).limit(1)
    )
    last_success = db.scalar(
        select(KofSyncRun.finished_at)
        .where(KofSyncRun.status == "ok")
        .order_by(KofSyncRun.finished_at.desc())
        .limit(1)
    )
    return {
        "configured": bool(settings.kof_username and settings.kof_password),
        "enabled": settings.kof_sync_enabled,
        "running": bool(last_run and last_run.status == "running"),
        "load_count": int(db.scalar(select(func.count(KofLoad.order_no))) or 0),
        "last_run": (
            {
                "id": last_run.id,
                "kind": last_run.kind,
                "status": last_run.status,
                "started_at": last_run.started_at,
                "finished_at": last_run.finished_at,
                "loads_upserted": last_run.loads_upserted,
                "error": last_run.error,
            }
            if last_run
            else None
        ),
        "last_success_at": last_success,
    }


@router.post("/sync", status_code=202)
def start_sync_endpoint(
    kind: Literal["incremental", "full"] = Query(default="incremental"),
) -> dict[str, bool]:
    settings = get_settings()
    if not settings.kof_username or not settings.kof_password:
        raise HTTPException(status_code=400, detail="KOF sync is not configured")
    try:
        run_id = start_sync(kind)
    except ValueError as exc:
        raise HTTPException(
            status_code=400, detail="KOF sync is not configured"
        ) from exc
    if run_id is None:
        raise HTTPException(status_code=409, detail="KOF sync is already running")
    return {"started": True}


@router.get("/sales")
def sales(db: Session = Depends(get_db)) -> dict:
    keys = (
        "leads_no_callback",
        "leads_callback",
        "priority_leads",
        "past_due",
        "charge_backs",
        "shipped_30",
        "not_shipped_30",
        "open_live_loads",
    )
    snapshots = {
        record.key: record
        for record in db.scalars(
            select(KofListSnapshot).where(KofListSnapshot.key.in_(keys))
        )
    }
    return {
        "lists": [
            {
                "key": key,
                "label": snapshots[key].label if key in snapshots else key,
                "count": snapshots[key].count if key in snapshots else 0,
                "columns": snapshots[key].columns if key in snapshots else [],
                "rows": snapshots[key].rows if key in snapshots else [],
            }
            for key in keys
        ]
    }


@router.get("/summary")
def summary(
    start: date | None = None,
    end: date | None = None,
    interval: Literal["week", "month"] = "week",
    db: Session = Depends(get_db),
) -> dict:
    start_date, end_date, filters = _date_filters(start, end)
    totals = _average_summary(db, filters)
    undated_loads = int(
        db.scalar(
            select(func.count(KofLoad.order_no)).where(
                KofLoad.is_deleted.is_(False),
                KofLoad.date_of_sale.is_(None),
            )
        )
        or 0
    )
    period = _period_expression(interval, db.bind.dialect.name)
    series_rows = db.execute(
        select(
            period.label("period"),
            func.count(KofLoad.order_no),
            func.sum(KofLoad.price),
            func.sum(KofLoad.cost),
            func.sum(KofLoad.profit),
            _margin_expression(),
        )
        .where(*filters)
        .group_by(period)
        .order_by(period)
    ).all()
    series = [
        {
            "period": _period_string(row[0]),
            "loads": int(row[1] or 0),
            "revenue": _number(row[2]) or 0,
            "cost": _number(row[3]) or 0,
            "profit": _number(row[4]) or 0,
            "margin_pct": _number(row[5]),
        }
        for row in series_rows
    ]
    equipment = func.coalesce(KofLoad.equipment, "Unknown")
    equipment_rows = db.execute(
        select(
            equipment.label("equipment"),
            func.count(KofLoad.order_no),
            func.avg(KofLoad.price),
            func.avg(KofLoad.cost),
            _margin_expression(),
        )
        .where(*filters)
        .group_by(equipment)
        .order_by(func.count(KofLoad.order_no).desc())
    ).all()
    return {
        "totals": totals,
        "undated_loads": undated_loads,
        "series": series,
        "by_equipment": [
            {
                "equipment": row[0],
                "loads": int(row[1] or 0),
                "avg_price": _number(row[2]),
                "avg_cost": _number(row[3]),
                "margin_pct": _number(row[4]),
            }
            for row in equipment_rows
        ],
    }


@router.get("/lanes")
def lanes(
    start: date | None = None,
    end: date | None = None,
    level: Literal["state", "city"] = "state",
    min_loads: int = Query(default=1, ge=1),
    limit: int = Query(default=100, ge=1, le=500),
    branch: str | None = None,
    customer: str | None = None,
    origin_city: str | None = None,
    db: Session = Depends(get_db),
) -> list[dict]:
    filters = _lane_filters(start, end, branch, customer, origin_city)
    return _lane_metrics(db, filters, level, min_loads=min_loads, limit=limit)


@router.get("/branches")
def branches(
    start: date | None = None,
    end: date | None = None,
    customer: str | None = "united rentals",
    db: Session = Depends(get_db),
) -> list[dict]:
    _, _, filters = _date_filters(start, end)
    filters.extend(
        [
            KofLoad.branch.is_not(None),
            func.trim(KofLoad.branch) != "",
        ]
    )
    if customer and customer.strip():
        filters.append(_customer_prefix_filter(customer))
    rows = db.execute(
        select(
            KofLoad.branch,
            KofLoad.customer,
            func.count(KofLoad.order_no),
            func.sum(KofLoad.price),
            func.sum(KofLoad.cost),
            func.sum(KofLoad.profit),
            _margin_expression(),
            func.avg(KofLoad.price),
            func.avg(KofLoad.cost),
            func.max(KofLoad.date_of_sale),
        )
        .where(*filters)
        .group_by(KofLoad.branch, KofLoad.customer)
        .order_by(func.count(KofLoad.order_no).desc(), KofLoad.branch, KofLoad.customer)
    ).all()

    origin, destination = _lane_expressions("city")
    load_count = func.count(KofLoad.order_no)
    ranked_lanes = (
        select(
            KofLoad.branch.label("branch"),
            KofLoad.customer.label("customer"),
            origin.label("origin"),
            destination.label("destination"),
            load_count.label("loads"),
            func.row_number()
            .over(
                partition_by=(KofLoad.branch, KofLoad.customer),
                order_by=(load_count.desc(), origin, destination),
            )
            .label("position"),
        )
        .where(*filters, *_known_lane_filters())
        .group_by(KofLoad.branch, KofLoad.customer, origin, destination)
        .subquery()
    )
    lane_rows = db.execute(
        select(
            ranked_lanes.c.branch,
            ranked_lanes.c.customer,
            ranked_lanes.c.origin,
            ranked_lanes.c.destination,
        )
        .where(ranked_lanes.c.position <= 3)
        .order_by(
            ranked_lanes.c.branch,
            ranked_lanes.c.customer,
            ranked_lanes.c.position,
        )
    ).all()
    top_lanes: dict[tuple[str, str | None], list[str]] = defaultdict(list)
    for row in lane_rows:
        top_lanes[(row[0], row[1])].append(
            f"{_format_city_label(row[2])} → {_format_city_label(row[3])}"
        )

    branch_records = db.scalars(select(KofBranch)).all()
    results = []
    for row in rows:
        label, load_customer = row[0], row[1]
        raw = _matching_branch_raw(branch_records, label, load_customer)
        city, state = _branch_location(label, raw)
        results.append(
            {
                "branch": label,
                "customer": load_customer,
                "city": city,
                "state": state,
                "loads": int(row[2] or 0),
                "revenue": _number(row[3]) or 0,
                "cost": _number(row[4]) or 0,
                "profit": _number(row[5]) or 0,
                "margin_pct": _number(row[6]),
                "avg_price": _number(row[7]),
                "avg_cost": _number(row[8]),
                "last_load_date": row[9].isoformat() if row[9] else None,
                "top_lanes": top_lanes.get((label, load_customer), []),
                "working_status": _branch_text(raw, "Are We Working With This Branch"),
            }
        )
    return results


@router.get("/branches/detail")
def branch_detail(
    branch: str = Query(min_length=1),
    start: date | None = None,
    end: date | None = None,
    db: Session = Depends(get_db),
) -> dict:
    _, _, filters = _date_filters(start, end)
    filters.append(KofLoad.branch == branch)
    totals_row = db.execute(
        select(
            func.count(KofLoad.order_no),
            func.sum(KofLoad.price),
            func.sum(KofLoad.cost),
            func.sum(KofLoad.profit),
            _margin_expression(),
            func.avg(KofLoad.price),
            func.avg(KofLoad.cost),
        ).where(*filters)
    ).one()
    if not totals_row[0]:
        raise HTTPException(status_code=404, detail="Branch not found")
    customer_row = db.execute(
        select(KofLoad.customer, func.count(KofLoad.order_no))
        .where(*filters, KofLoad.customer.is_not(None))
        .group_by(KofLoad.customer)
        .order_by(func.count(KofLoad.order_no).desc(), KofLoad.customer)
        .limit(1)
    ).first()
    load_customer = customer_row[0] if customer_row else None
    branch_records = db.scalars(select(KofBranch)).all()
    raw = _matching_branch_raw(branch_records, branch, load_customer)
    city, state = _branch_location(branch, raw)

    pickup_filters = [
        *filters,
        KofLoad.shipper_company.is_not(None),
        KofLoad.shipper_city.is_not(None),
        KofLoad.shipper_state.is_not(None),
        func.trim(KofLoad.shipper_company) != "",
        func.trim(KofLoad.shipper_city) != "",
        func.trim(KofLoad.shipper_state) != "",
    ]
    pickup_rows = db.execute(
        select(
            KofLoad.shipper_company,
            KofLoad.shipper_city,
            KofLoad.shipper_state,
            func.count(KofLoad.order_no),
            func.avg(KofLoad.price),
            func.avg(KofLoad.cost),
            _margin_expression(),
            func.max(KofLoad.date_of_sale),
        )
        .where(*pickup_filters)
        .group_by(
            KofLoad.shipper_company,
            KofLoad.shipper_city,
            KofLoad.shipper_state,
        )
        .order_by(
            func.count(KofLoad.order_no).desc(),
            KofLoad.shipper_city,
            KofLoad.shipper_state,
            KofLoad.shipper_company,
        )
    ).all()
    recent_loads = db.scalars(
        select(KofLoad)
        .where(*filters)
        .order_by(KofLoad.date_of_sale.desc(), KofLoad.order_no.desc())
        .limit(10)
    ).all()
    return {
        "branch": branch,
        "customer": load_customer,
        "city": city,
        "state": state,
        "contact": _branch_contact(raw),
        "working_status": _branch_text(raw, "Are We Working With This Branch"),
        "totals": {
            "loads": int(totals_row[0] or 0),
            "revenue": _number(totals_row[1]) or 0,
            "cost": _number(totals_row[2]) or 0,
            "profit": _number(totals_row[3]) or 0,
            "margin_pct": _number(totals_row[4]),
            "avg_price": _number(totals_row[5]),
            "avg_cost": _number(totals_row[6]),
        },
        "lanes": _lane_metrics(db, filters, "city"),
        "pickup_sites": [
            {
                "company": row[0],
                "city": _format_city_label(row[1]),
                "state": row[2].upper(),
                "loads": int(row[3] or 0),
                "avg_price": _number(row[4]),
                "avg_cost": _number(row[5]),
                "margin_pct": _number(row[6]),
                "last_date": row[7].isoformat() if row[7] else None,
            }
            for row in pickup_rows
        ],
        "recent_loads": [_load_row(load) for load in recent_loads],
    }


@router.get("/customers")
def customers(
    start: date | None = None,
    end: date | None = None,
    db: Session = Depends(get_db),
) -> list[dict]:
    _, _, filters = _date_filters(start, end)
    rows = db.execute(
        select(
            KofLoad.customer,
            func.count(KofLoad.order_no),
            func.sum(KofLoad.price),
            func.sum(KofLoad.cost),
            func.sum(KofLoad.profit),
            _margin_expression(),
            func.avg(KofLoad.price),
            func.max(KofLoad.date_of_sale),
        )
        .where(*filters, KofLoad.customer.is_not(None))
        .group_by(KofLoad.customer)
        .order_by(func.sum(KofLoad.profit).desc())
    ).all()
    return [
        {
            "customer": row[0],
            "loads": int(row[1] or 0),
            "revenue": _number(row[2]) or 0,
            "cost": _number(row[3]) or 0,
            "profit": _number(row[4]) or 0,
            "margin_pct": _number(row[5]),
            "avg_price": _number(row[6]),
            "last_load_date": row[7].isoformat() if row[7] else None,
        }
        for row in rows
    ]


@router.get("/carriers")
def carriers(
    start: date | None = None,
    end: date | None = None,
    db: Session = Depends(get_db),
) -> list[dict]:
    _, _, filters = _date_filters(start, end)
    on_time_num, on_time_den = _on_time_expressions()
    rows = db.execute(
        select(
            KofLoad.carrier,
            KofLoad.mc,
            func.count(KofLoad.order_no),
            func.sum(KofLoad.cost),
            func.avg(KofLoad.cost),
            on_time_num,
            on_time_den,
            func.max(KofLoad.date_of_sale),
        )
        .where(*filters, KofLoad.carrier.is_not(None))
        .group_by(KofLoad.carrier, KofLoad.mc)
        .order_by(func.sum(KofLoad.cost).desc())
    ).all()
    origin, destination = _lane_expressions("city")
    lane_rows = db.execute(
        select(
            KofLoad.carrier,
            KofLoad.mc,
            origin,
            destination,
            func.count(KofLoad.order_no).label("loads"),
        )
        .where(*filters, KofLoad.carrier.is_not(None), *_known_lane_filters())
        .group_by(KofLoad.carrier, KofLoad.mc, origin, destination)
        .order_by(KofLoad.carrier, KofLoad.mc, func.count(KofLoad.order_no).desc())
    ).all()
    top_lanes: dict[tuple[str, str | None], list[str]] = defaultdict(list)
    for row in lane_rows:
        key = (row[0], row[1])
        lane = f"{_format_city_label(row[2])} → {_format_city_label(row[3])}"
        if lane not in top_lanes[key] and len(top_lanes[key]) < 3:
            top_lanes[key].append(lane)
    return [
        {
            "carrier": row[0],
            "mc": row[1],
            "loads": int(row[2] or 0),
            "total_cost": _number(row[3]) or 0,
            "avg_cost": _number(row[4]),
            "on_time_pct": _on_time_percent(row[5], row[6]),
            "last_load_date": row[7].isoformat() if row[7] else None,
            "top_lanes": top_lanes.get((row[0], row[1]), []),
        }
        for row in rows
    ]


def _apply_load_filters(
    query,
    *,
    q: str | None,
    stage: str | None,
    customer: str | None,
    carrier: str | None,
    origin_state: str | None,
    dest_state: str | None,
    start: date | None,
    end: date | None,
):
    filters = [KofLoad.is_deleted.is_(False)]
    if start is not None:
        filters.append(KofLoad.date_of_sale >= start)
    if end is not None:
        filters.append(KofLoad.date_of_sale <= end)
    if stage:
        filters.append(KofLoad.stage == stage)
    if customer:
        filters.append(KofLoad.customer.ilike(f"%{customer}%"))
    if carrier:
        filters.append(KofLoad.carrier.ilike(f"%{carrier}%"))
    if origin_state:
        filters.append(KofLoad.origin_state.ilike(origin_state))
    if dest_state:
        filters.append(KofLoad.dest_state.ilike(dest_state))
    if q:
        like = f"%{q}%"
        filters.append(
            or_(
                cast(KofLoad.order_no, String).ilike(like),
                KofLoad.customer.ilike(like),
                KofLoad.carrier.ilike(like),
                KofLoad.mc.ilike(like),
                KofLoad.origin_city.ilike(like),
                KofLoad.origin_state.ilike(like),
                KofLoad.dest_city.ilike(like),
                KofLoad.dest_state.ilike(like),
            )
        )
    return query.where(*filters)


@router.get("/loads")
def loads(
    q: str | None = None,
    stage: str | None = None,
    customer: str | None = None,
    carrier: str | None = None,
    origin_state: str | None = None,
    dest_state: str | None = None,
    start: date | None = None,
    end: date | None = None,
    sort: str = "-date_of_sale",
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=500),
    db: Session = Depends(get_db),
) -> dict:
    base = _apply_load_filters(
        select(KofLoad),
        q=q,
        stage=stage,
        customer=customer,
        carrier=carrier,
        origin_state=origin_state,
        dest_state=dest_state,
        start=start,
        end=end,
    )
    count_query = base.with_only_columns(func.count(KofLoad.order_no))
    total = int(db.scalar(count_query) or 0)
    sort_fields = {
        "order_no": KofLoad.order_no,
        "date_of_sale": KofLoad.date_of_sale,
        "customer": KofLoad.customer,
        "carrier": KofLoad.carrier,
        "price": KofLoad.price,
        "cost": KofLoad.cost,
        "profit": KofLoad.profit,
        "stage": KofLoad.stage,
    }
    descending = sort.startswith("-")
    sort_field = sort[1:] if descending else sort
    sort_expression = sort_fields.get(sort_field, KofLoad.date_of_sale)
    if descending:
        sort_expression = sort_expression.desc()
        if sort_field == "date_of_sale":
            sort_expression = sort_expression.nulls_last()
    query = base.order_by(sort_expression, KofLoad.order_no.desc())
    records = db.scalars(query.offset((page - 1) * page_size).limit(page_size)).all()
    now = datetime.now(timezone.utc)
    return {
        "total": total,
        "items": [_load_row(record, now) for record in records],
    }


@router.get("/loads/{order_no}")
def load_detail(order_no: int, db: Session = Depends(get_db)) -> dict:
    load = db.get(KofLoad, order_no)
    if load is None or load.is_deleted:
        raise HTTPException(status_code=404, detail="KOF load not found")
    detail = _load_row(load)
    detail.update(
        {
            "shipper": {
                "company": load.shipper_company,
                "address": load.shipper_address,
                "city": load.shipper_city,
                "state": load.shipper_state,
                "zip": load.shipper_zip,
                "phone": load.shipper_phone,
                "email": load.shipper_email,
            },
            "consignee": {
                "company": load.consignee_company,
                "address": load.consignee_address,
                "city": load.consignee_city,
                "state": load.consignee_state,
                "zip": load.consignee_zip,
                "phone": load.consignee_phone,
                "email": load.consignee_email,
            },
            "po": load.po,
            "pu": load.pu,
            "invoice_no": load.invoice_no,
            "product_description": load.product_description,
            "carrier_contact": {
                "name": load.carrier_contact_name,
                "phone": load.carrier_contact_phone,
                "email": load.carrier_contact_email,
                "dispatch_contact": load.dispatch_contact,
                "dispatch_phone": load.dispatch_phone,
            },
            "notes": _parse_note_entries(load.notes_text),
            "log": _parse_note_entries(load.log_text),
            "raw": load.raw or {},
        }
    )
    return detail


@router.get("/tracking")
def tracking(db: Session = Depends(get_db)) -> dict:
    now = datetime.now(timezone.utc)
    rows = db.scalars(
        select(KofLoad)
        .where(
            KofLoad.is_deleted.is_(False),
            KofLoad.stage.in_(_ACTIVE_STAGES),
        )
        .order_by(KofLoad.date_of_sale.desc(), KofLoad.order_no.desc())
    ).all()
    grouped = {stage: [] for stage in _ACTIVE_STAGES}
    for load in rows:
        last_note = _latest_note(load.notes_text, load.log_text, now)
        hours = _hours_since_update(last_note, now)
        grouped[load.stage].append(
            {
                **_load_row(load, now),
                "last_note": last_note,
                "hours_since_update": hours,
            }
        )
    labels = {
        "awaiting_pickup": "Awaiting Pickup",
        "in_transit": "In Transit",
        "awaiting_delivery": "Awaiting Delivery",
    }
    return {
        "stages": [
            {"key": stage, "label": labels[stage], "loads": grouped[stage]}
            for stage in _ACTIVE_STAGES
        ]
    }
