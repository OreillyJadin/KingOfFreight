import re
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse, Response
from sqlalchemy import desc, inspect, select
from sqlalchemy.orm import Session, joinedload
from twilio.request_validator import RequestValidator

from app.auth import require_broker
from app.config import get_settings
from app.db import get_db
from app.integrations.email import EmailProvider, get_email_provider
from app.integrations.fmcsa import FmcsaProvider, get_fmcsa_provider
from app.integrations.llm import LlmProvider, get_llm_provider
from app.integrations.sms import SmsProvider, get_sms_provider
from app.models import (
    BrokerSettings,
    Carrier,
    Communication,
    Load,
    LocationPing,
    ScheduledCheckIn,
    StatusUpdate,
    utcnow,
)
from app.schemas import (
    ApproveStatus,
    BookLoad,
    BrokerSettingsUpdate,
    CarrierOut,
    CheckInOut,
    CommunicationOut,
    CreateLoadOverrides,
    LoadCreate,
    LoadOut,
    LoadPatch,
    ManualStatus,
    SimulateEmail,
    SimulateSms,
    SkipStatus,
    StatusUpdateOut,
    TrackingPing,
    VerifyCarrier,
)
from app.services.checkins import (
    DELIVERY_PASSED,
    PICKUP_PASSED,
    draft_status_update,
    handle_driver_reply,
    normalize_contact,
    run_checkin_tick,
)
from app.services.fmcsa import score_carrier
from app.services.messaging import send_outbound
from app.services.preferences import get_prefs
from app.services.templates import city_state, render_checkin, render_tracking_link

protected = APIRouter(prefix="/api", dependencies=[Depends(require_broker)])
public = APIRouter(prefix="/api")
dev_public = APIRouter(prefix="/api", dependencies=[Depends(require_broker)])


def _orm_values(value) -> dict | None:
    if value is None:
        return None
    return {
        attribute.key: getattr(value, attribute.key)
        for attribute in inspect(value).mapper.column_attrs
    }


def _get_load(db: Session, load_id: int) -> Load:
    load = db.get(Load, load_id)
    if load is None:
        raise HTTPException(status_code=404, detail="Load not found")
    return load


@protected.get("/settings")
def read_settings(db: Session = Depends(get_db)) -> dict:
    return asdict(get_prefs(db))


@protected.put("/settings")
def update_settings(
    payload: BrokerSettingsUpdate, db: Session = Depends(get_db)
) -> dict:
    row = db.get(BrokerSettings, 1)
    if row is None:
        row = BrokerSettings(id=1)
        db.add(row)
    for field in payload.model_fields_set:
        setattr(row, field, getattr(payload, field))
    row.updated_at = utcnow()
    db.commit()
    return asdict(get_prefs(db))


def _normalized_mc(value: str) -> str:
    mc = re.sub(r"\D", "", value)
    if not mc or len(mc) > 8:
        raise HTTPException(status_code=422, detail="Invalid MC number")
    return mc


def _normalized_phone(value: str | None) -> str | None:
    return normalize_contact(value, "sms") if value else None


def _to_local_aware(value: datetime | None, tz: str) -> datetime | None:
    if value is None:
        return None
    zone = ZoneInfo(tz)
    interpreted = value.replace(tzinfo=zone) if value.tzinfo is None else value
    return interpreted.astimezone(timezone.utc)


def _apply_status(load: Load, status: str) -> None:
    load.status = status
    if status == "delivered":
        load.delivered_at = utcnow()


def _appointment_checkin(
    load: Load,
    kind: str,
    when: datetime,
    offset: int,
    channel: str,
    contact: str,
    tz: str,
) -> ScheduledCheckIn:
    from app.services.templates import local_datetime

    scheduled = local_datetime(when, tz)
    assert scheduled is not None
    return ScheduledCheckIn(
        load_id=load.id,
        kind=kind,
        scheduled_time=scheduled,
        send_at=scheduled + timedelta(minutes=offset),
        checkin_channel=channel,
        driver_contact=contact,
        state="scheduled",
    )


@protected.get("/loads", response_model=list[LoadOut])
def list_loads(
    tab: str = Query("truckstop", pattern="^(truckstop|delivery)$"),
    include_delivered: bool = False,
    db: Session = Depends(get_db),
) -> list[Load]:
    if tab == "truckstop":
        query = select(Load).where(Load.status.in_(["new", "posted"]))
    else:
        query = select(Load).where(
            Load.status.in_(
                ["booked", "picked_up", "in_transit", "delayed", "delivered"]
            )
        )
        if not include_delivered:
            cutoff = utcnow() - timedelta(hours=24)
            query = query.where(
                (Load.status != "delivered")
                | (Load.delivered_at >= cutoff)
                | (Load.delivered_at.is_(None))
            )
    return list(db.scalars(query.order_by(desc(Load.updated_at))).all())


@protected.get("/loads/{load_id}")
def get_load(load_id: int, db: Session = Depends(get_db)) -> dict:
    load = (
        db.execute(
            select(Load)
            .options(
                joinedload(Load.carrier),
                joinedload(Load.status_updates),
                joinedload(Load.checkins),
                joinedload(Load.communications),
            )
            .where(Load.id == load_id)
        )
        .unique()
        .scalar_one_or_none()
    )
    if load is None:
        raise HTTPException(status_code=404, detail="Load not found")
    latest_ping = db.scalar(
        select(LocationPing)
        .where(LocationPing.load_id == load_id)
        .order_by(desc(LocationPing.captured_at))
        .limit(1)
    )
    return {
        **LoadOut.model_validate(load).model_dump(),
        "carrier": _orm_values(load.carrier),
        "status_updates": [_orm_values(item) for item in load.status_updates],
        "checkins": [_orm_values(item) for item in load.checkins],
        "latest_location_ping": _orm_values(latest_ping),
        "communications": [_orm_values(item) for item in load.communications],
    }


@protected.post("/loads", response_model=LoadOut, status_code=201)
def create_load(payload: LoadCreate, db: Session = Depends(get_db)) -> Load:
    values = payload.model_dump()
    broker_timezone = get_prefs(db).broker_timezone
    for field in ("driver_phone", "dispatcher_phone"):
        values[field] = _normalized_phone(values[field])
    values["pickup_datetime"] = _to_local_aware(
        values["pickup_datetime"], broker_timezone
    )
    values["delivery_datetime"] = _to_local_aware(
        values["delivery_datetime"], broker_timezone
    )
    load = Load(**values)
    db.add(load)
    db.commit()
    db.refresh(load)
    return load


@protected.patch("/loads/{load_id}", response_model=LoadOut)
def patch_load(load_id: int, payload: LoadPatch, db: Session = Depends(get_db)) -> Load:
    load = _get_load(db, load_id)
    broker_timezone = get_prefs(db).broker_timezone
    for key, value in payload.model_dump(exclude_unset=True).items():
        if key.endswith("_datetime"):
            value = _to_local_aware(value, broker_timezone)
        elif key in {"driver_phone", "dispatcher_phone"}:
            value = _normalized_phone(value)
        setattr(load, key, value)
    load.updated_at = utcnow()
    db.commit()
    db.refresh(load)
    return load


@protected.post("/loads/{load_id}/post", response_model=LoadOut)
def post_load(load_id: int, db: Session = Depends(get_db)) -> Load:
    load = _get_load(db, load_id)
    load.status = "posted"
    db.commit()
    db.refresh(load)
    return load


@protected.get("/loads/{load_id}/post-text", response_class=Response)
def post_text(load_id: int, db: Session = Depends(get_db)) -> Response:
    load = _get_load(db, load_id)
    lines = [
        f"Lane: {city_state(load.pickup_city, load.pickup_state)} to {city_state(load.delivery_city, load.delivery_state)}",
        f"Pickup: {load.pickup_datetime.isoformat() if load.pickup_datetime else 'TBD'}",
        f"Delivery: {load.delivery_datetime.isoformat() if load.delivery_datetime else 'TBD'}",
        f"Equipment: {load.equipment_type or 'TBD'}",
        f"Weight: {f'{load.weight_lbs} lbs' if load.weight_lbs is not None else 'TBD'}",
        f"Commodity: {load.commodity or 'TBD'}",
        f"Special requirements: {load.special_requirements or 'None'}",
    ]
    return Response(content="\n".join(lines), media_type="text/plain")


@protected.post("/loads/{load_id}/book", response_model=LoadOut)
def book_load(
    load_id: int,
    payload: BookLoad,
    db: Session = Depends(get_db),
) -> Load:
    load = _get_load(db, load_id)
    driver_phone = _normalized_phone(payload.driver_phone)
    dispatcher_phone = _normalized_phone(payload.dispatcher_phone)
    contact_phone = driver_phone or dispatcher_phone
    contact_email = payload.driver_email or payload.dispatcher_email
    if not any(
        (
            payload.driver_phone,
            payload.driver_email,
            payload.dispatcher_phone,
            payload.dispatcher_email,
        )
    ):
        raise HTTPException(
            status_code=422,
            detail="At least one driver or dispatcher contact is required",
        )
    mc = _normalized_mc(payload.carrier_mc)
    carrier = db.scalar(select(Carrier).where(Carrier.mc_number == mc))
    if carrier is None or carrier.verified_at is None:
        raise HTTPException(
            status_code=422, detail="Carrier must be verified before booking"
        )
    if carrier.flag == "red" and not payload.override_red_flag:
        raise HTTPException(
            status_code=422, detail="Red-flag carrier requires override_red_flag"
        )
    if carrier.flag == "red":
        load.notes = f"{load.notes or ''}\nBroker override: booked red-flag carrier MC {mc}.".strip()
    load.carrier_id = carrier.id
    load.carrier_rate = payload.carrier_rate
    load.customer_rate = payload.customer_rate
    load.driver_name = payload.driver_name
    load.driver_phone = driver_phone
    load.driver_email = payload.driver_email
    load.dispatcher_name = payload.dispatcher_name
    load.dispatcher_phone = dispatcher_phone
    load.dispatcher_email = payload.dispatcher_email
    load.checkin_offset_minutes = payload.checkin_offset_minutes
    load.checkin_channel = payload.checkin_channel
    load.status = "booked"
    load.booked_at = utcnow()
    prefs = get_prefs(db)
    default = prefs.checkin_default_channel
    channel = payload.checkin_channel or (
        "sms" if default == "sms" and contact_phone else "email"
    )
    contact = (
        (driver_phone or dispatcher_phone)
        if channel == "sms"
        else (payload.driver_email or payload.dispatcher_email)
    )
    if not contact:
        channel = "email" if contact_email else "sms"
        contact = contact_email if channel == "email" else contact_phone
    offset = (
        payload.checkin_offset_minutes
        if payload.checkin_offset_minutes is not None
        else prefs.checkin_offset_minutes
    )
    if load.pickup_datetime:
        db.add(
            _appointment_checkin(
                load,
                "pickup",
                load.pickup_datetime,
                offset,
                channel,
                contact,
                prefs.broker_timezone,
            )
        )
    if load.delivery_datetime:
        db.add(
            _appointment_checkin(
                load,
                "dropoff",
                load.delivery_datetime,
                offset,
                channel,
                contact,
                prefs.broker_timezone,
            )
        )
    draft_status_update(db, load, "booked", "manual", None, None, applied=True)
    db.commit()
    db.refresh(load)
    return load


@protected.post("/loads/{load_id}/status", response_model=StatusUpdateOut)
def manual_status(
    load_id: int, payload: ManualStatus, db: Session = Depends(get_db)
) -> StatusUpdate:
    load = _get_load(db, load_id)
    broker_timezone = get_prefs(db).broker_timezone
    _apply_status(load, payload.status)
    update = draft_status_update(
        db,
        load,
        payload.status,
        "manual",
        payload.note,
        _to_local_aware(payload.eta, broker_timezone),
        applied=True,
    )
    db.commit()
    db.refresh(update)
    return update


@protected.get("/status-updates", response_model=list[StatusUpdateOut])
def list_status_updates(
    state: str | None = None, db: Session = Depends(get_db)
) -> list[StatusUpdate]:
    query = select(StatusUpdate)
    if state:
        query = query.where(StatusUpdate.state == state)
    return list(db.scalars(query.order_by(desc(StatusUpdate.created_at))).all())


@protected.post("/status-updates/{update_id}/approve", response_model=StatusUpdateOut)
def approve_status(
    update_id: int,
    payload: ApproveStatus,
    db: Session = Depends(get_db),
    sms: SmsProvider = Depends(get_sms_provider),
    email: EmailProvider = Depends(get_email_provider),
) -> StatusUpdate:
    update = db.get(StatusUpdate, update_id)
    if update is None:
        raise HTTPException(status_code=404, detail="Status update not found")
    if update.state != "pending_approval":
        raise HTTPException(
            status_code=409, detail="Status update is no longer pending"
        )
    load = _get_load(db, update.load_id)
    channel = payload.channel or update.customer_channel or "email"
    to = load.customer_email if channel == "email" else load.customer_phone
    if not to:
        raise HTTPException(
            status_code=422, detail=f"Customer has no {channel} contact"
        )
    subject = (
        payload.subject
        if payload.subject is not None
        else update.customer_message_subject
    )
    body = (
        payload.body
        if payload.body is not None
        else update.customer_message_preview or ""
    )
    if not update.applied:
        _apply_status(load, update.status)
        update.applied = True
    send_outbound(db, load, channel, to, subject, body, "customer_update", sms, email)
    update.customer_channel = channel
    update.customer_message_subject = subject
    update.customer_message_preview = body
    update.approved_by_broker = True
    update.sent_to_customer = True
    update.sent_at = utcnow()
    update.state = "sent"
    db.commit()
    db.refresh(update)
    return update


@protected.post("/status-updates/{update_id}/skip", response_model=StatusUpdateOut)
def skip_status(
    update_id: int, payload: SkipStatus, db: Session = Depends(get_db)
) -> StatusUpdate:
    update = db.get(StatusUpdate, update_id)
    if update is None:
        raise HTTPException(status_code=404, detail="Status update not found")
    if payload.apply and not update.applied:
        _apply_status(_get_load(db, update.load_id), update.status)
        update.applied = True
    update.state = "skipped"
    db.commit()
    db.refresh(update)
    return update


@protected.post("/carriers/verify", response_model=CarrierOut)
def verify_carrier(
    payload: VerifyCarrier,
    db: Session = Depends(get_db),
    provider: FmcsaProvider = Depends(get_fmcsa_provider),
) -> Carrier:
    mc = _normalized_mc(payload.mc_number)
    snapshot = provider.lookup_mc(mc)
    flag, reasons = score_carrier(snapshot, mc)
    carrier = db.scalar(select(Carrier).where(Carrier.mc_number == mc))
    if carrier is None:
        carrier = Carrier(mc_number=mc)
        db.add(carrier)
    if snapshot:
        for key in (
            "dot_number",
            "legal_name",
            "dba_name",
            "phone",
            "email",
            "allowed_to_operate",
            "authority_status",
            "safety_rating",
            "insurance_on_file",
            "bipd_on_file_amount",
            "bipd_required_amount",
            "out_of_service_date",
            "raw",
        ):
            setattr(carrier, key, getattr(snapshot, key))
    carrier.flag = flag
    carrier.flag_reasons = reasons
    carrier.verified_at = utcnow()
    db.commit()
    db.refresh(carrier)
    return carrier


@protected.get("/checkins/{checkin_id}", response_model=CheckInOut)
def get_checkin(checkin_id: int, db: Session = Depends(get_db)) -> ScheduledCheckIn:
    checkin = db.get(ScheduledCheckIn, checkin_id)
    if checkin is None:
        raise HTTPException(status_code=404, detail="Check-in not found")
    return checkin


@protected.post("/checkins/{checkin_id}/send-now", response_model=CheckInOut)
def send_checkin_now(
    checkin_id: int,
    db: Session = Depends(get_db),
    sms: SmsProvider = Depends(get_sms_provider),
    email: EmailProvider = Depends(get_email_provider),
) -> ScheduledCheckIn:
    checkin = db.scalar(
        select(ScheduledCheckIn)
        .options(joinedload(ScheduledCheckIn.load))
        .where(ScheduledCheckIn.id == checkin_id)
    )
    if checkin is None:
        raise HTTPException(status_code=404, detail="Check-in not found")
    if checkin.state not in {"scheduled", "no_reply"}:
        raise HTTPException(status_code=409, detail="Check-in has already been handled")
    body = checkin.message_text or render_checkin(checkin.load, checkin.kind)
    send_outbound(
        db,
        checkin.load,
        checkin.checkin_channel,
        checkin.driver_contact,
        None,
        body,
        "checkin",
        sms,
        email,
    )
    checkin.message_text = body
    checkin.checkin_sent_at = utcnow()
    checkin.state = "sent"
    checkin.alert_raised_at = None
    checkin.alert_dismissed_at = None
    db.commit()
    db.refresh(checkin)
    return _orm_values(checkin)


@protected.post("/checkins/{checkin_id}/dismiss-alert", response_model=CheckInOut)
def dismiss_alert(checkin_id: int, db: Session = Depends(get_db)) -> ScheduledCheckIn:
    checkin = db.get(ScheduledCheckIn, checkin_id)
    if checkin is None:
        raise HTTPException(status_code=404, detail="Check-in not found")
    checkin.alert_dismissed_at = utcnow()
    db.commit()
    db.refresh(checkin)
    return checkin


@protected.get("/alerts")
def alerts(db: Session = Depends(get_db)) -> list[dict]:
    checkins = (
        db.scalars(
            select(ScheduledCheckIn)
            .options(joinedload(ScheduledCheckIn.load))
            .where(
                (ScheduledCheckIn.state == "no_reply")
                | (
                    (ScheduledCheckIn.state == "replied")
                    & (ScheduledCheckIn.needs_broker_attention.is_(True))
                )
            )
            .order_by(
                desc(ScheduledCheckIn.alert_raised_at),
                desc(ScheduledCheckIn.reply_received_at),
            )
        )
        .unique()
        .all()
    )
    return [
        {
            "id": item.id,
            "kind": item.kind,
            "state": item.state,
            "checkin_sent_at": item.checkin_sent_at,
            "scheduled_time": item.scheduled_time,
            "reply_raw_text": item.reply_raw_text,
            "parsed_status": item.parsed_status,
            "parsed_summary": item.parsed_summary,
            "needs_broker_attention": item.needs_broker_attention,
            "alert_raised_at": item.alert_raised_at,
            "alert_dismissed_at": item.alert_dismissed_at,
            "load": {
                "id": item.load.id,
                "reference": item.load.reference,
                "status": item.load.status,
                "pickup_city": item.load.pickup_city,
                "delivery_city": item.load.delivery_city,
            },
        }
        for item in checkins
        if item.alert_dismissed_at is None
        and item.load.status not in DELIVERY_PASSED
        and not (item.kind == "pickup" and item.load.status in PICKUP_PASSED)
    ]


@protected.get("/inbox", response_model=list[CommunicationOut])
def inbox(
    tag: str | None = None,
    include_archived: bool = False,
    db: Session = Depends(get_db),
) -> list[Communication]:
    query = select(Communication).where(Communication.direction == "inbound")
    if tag:
        query = query.where(Communication.tag == tag)
    if not include_archived:
        query = query.where(Communication.archived.is_(False))
    return list(db.scalars(query.order_by(desc(Communication.created_at))).all())


@protected.post("/inbox/{communication_id}/archive", response_model=CommunicationOut)
def archive_communication(
    communication_id: int, db: Session = Depends(get_db)
) -> Communication:
    communication = db.get(Communication, communication_id)
    if communication is None:
        raise HTTPException(status_code=404, detail="Communication not found")
    communication.archived = True
    db.commit()
    db.refresh(communication)
    return communication


@protected.post("/bol/upload", response_model=CommunicationOut)
async def upload_bol(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    llm: LlmProvider = Depends(get_llm_provider),
) -> Communication:
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="A PDF file is required")
    contents = await file.read(15 * 1024 * 1024 + 1)
    if len(contents) > 15 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="PDF must not exceed 15 MB")
    if not contents.startswith(b"%PDF"):
        raise HTTPException(status_code=400, detail="Uploaded file is not a valid PDF")
    target_dir = Path(get_settings().upload_dir)
    target_dir.mkdir(parents=True, exist_ok=True)
    file_path = (
        target_dir / f"{utcnow().strftime('%Y%m%d%H%M%S%f')}-{Path(file.filename).name}"
    )
    file_path.write_bytes(contents)
    extracted = llm.extract_bol(contents, file.filename).model_dump(mode="json")
    communication = Communication(
        channel="email",
        direction="inbound",
        from_addr="manual upload",
        subject=f"BOL: {file.filename}",
        content="Manual BOL upload",
        tag="bol",
        attachment_path=str(file_path),
        extracted=extracted,
    )
    db.add(communication)
    db.commit()
    db.refresh(communication)
    return communication


@protected.post(
    "/inbox/{communication_id}/create-load",
    response_model=LoadOut,
    status_code=201,
)
def create_load_from_inbox(
    communication_id: int,
    payload: CreateLoadOverrides | None = None,
    db: Session = Depends(get_db),
) -> Load:
    communication = db.get(Communication, communication_id)
    if communication is None or not communication.extracted:
        raise HTTPException(
            status_code=404, detail="Extracted BOL communication not found"
        )
    extracted = communication.extracted
    overrides = payload.model_dump(exclude_unset=True) if payload else {}
    references = extracted.get("reference_numbers") or {}
    reference = (
        overrides.pop("reference", None)
        or extracted.get("reference")
        or next(iter(references.values()), None)
    )
    overrides.pop("status", None)
    reference = reference or f"BOL-{communication.id}"
    fields = {
        key: extracted.get(key)
        for key in (
            "pickup_location",
            "pickup_city",
            "pickup_state",
            "pickup_datetime",
            "delivery_location",
            "delivery_city",
            "delivery_state",
            "delivery_datetime",
            "weight_lbs",
            "equipment_type",
            "commodity",
            "special_requirements",
            "notes",
            "customer_name",
            "customer_contact_name",
            "customer_email",
            "customer_phone",
        )
    }
    fields.update(overrides)
    broker_timezone = get_prefs(db).broker_timezone
    for key in ("pickup_datetime", "delivery_datetime"):
        if fields[key]:
            value = (
                datetime.fromisoformat(fields[key])
                if isinstance(fields[key], str)
                else fields[key]
            )
            fields[key] = _to_local_aware(value, broker_timezone)
    load = Load(
        reference=reference,
        status="new",
        bol_source=communication.id,
        bol_file_path=communication.attachment_path,
        **fields,
    )
    db.add(load)
    db.flush()
    communication.load_id = load.id
    communication.archived = True
    db.commit()
    db.refresh(load)
    return load


@protected.get("/files/bol/{communication_id}")
def bol_file(communication_id: int, db: Session = Depends(get_db)) -> FileResponse:
    communication = db.get(Communication, communication_id)
    if (
        communication is None
        or not communication.attachment_path
        or not Path(communication.attachment_path).is_file()
    ):
        raise HTTPException(status_code=404, detail="BOL file not found")
    return FileResponse(communication.attachment_path, media_type="application/pdf")


@protected.post("/loads/{load_id}/send-tracking-link", response_model=CommunicationOut)
def send_tracking_link(
    load_id: int,
    db: Session = Depends(get_db),
    sms: SmsProvider = Depends(get_sms_provider),
    email: EmailProvider = Depends(get_email_provider),
) -> Communication:
    load = _get_load(db, load_id)
    phone = load.driver_phone or load.dispatcher_phone
    address = load.driver_email or load.dispatcher_email
    if phone:
        channel, to = "sms", phone
    elif address:
        channel, to = "email", address
    else:
        raise HTTPException(status_code=422, detail="Load has no driver contact")
    communication = send_outbound(
        db,
        load,
        channel,
        to,
        None,
        render_tracking_link(load),
        "tracking_link",
        sms,
        email,
    )
    db.commit()
    db.refresh(communication)
    return communication


@public.get("/track/{token}")
def public_tracking(token: str, db: Session = Depends(get_db)) -> dict:
    load = db.scalar(select(Load).where(Load.tracking_token == token))
    if load is None:
        raise HTTPException(status_code=404, detail="Tracking link not found")
    return {
        "reference": load.reference,
        "pickup_city": load.pickup_city,
        "pickup_state": load.pickup_state,
        "delivery_city": load.delivery_city,
        "delivery_state": load.delivery_state,
        "broker_company": get_prefs(db).broker_company,
    }


@public.post("/track/{token}/ping")
def tracking_ping(
    token: str,
    payload: TrackingPing,
    request: Request,
    db: Session = Depends(get_db),
) -> dict[str, bool]:
    load = db.scalar(select(Load).where(Load.tracking_token == token))
    if load is None:
        raise HTTPException(status_code=404, detail="Tracking link not found")
    latest = db.scalar(
        select(LocationPing)
        .where(LocationPing.load_id == load.id)
        .order_by(desc(LocationPing.captured_at))
        .limit(1)
    )
    current = utcnow()
    latest_captured = (
        latest.captured_at
        if latest and latest.captured_at.tzinfo
        else (latest.captured_at.replace(tzinfo=timezone.utc) if latest else None)
    )
    if latest_captured and current - latest_captured < timedelta(seconds=60):
        return {"stored": False}
    db.add(
        LocationPing(
            load_id=load.id,
            lat=payload.lat,
            lng=payload.lng,
            accuracy_m=payload.accuracy_m,
            captured_at=current,
            user_agent=request.headers.get("user-agent"),
        )
    )
    db.commit()
    return {"stored": True}


@public.post("/webhooks/twilio/sms")
async def twilio_sms(
    request: Request,
    db: Session = Depends(get_db),
    llm: LlmProvider = Depends(get_llm_provider),
) -> Response:
    form = await request.form()
    sender = str(form.get("From", ""))
    body = str(form.get("Body", ""))
    sid = str(form.get("MessageSid", "")) or None
    settings = get_settings()
    if settings.sms_provider == "twilio":
        signature = request.headers.get("X-Twilio-Signature", "")
        url = f"{settings.public_base_url.rstrip('/')}{request.url.path}"
        validator = RequestValidator(settings.twilio_auth_token or "")
        if not validator.validate(url, dict(form), signature):
            raise HTTPException(status_code=403, detail="Invalid Twilio signature")
    handle_driver_reply(db, sender, body, "sms", sid, llm)
    return Response(content="<Response/>", media_type="application/xml")


def _ingest_email_message(db: Session, message: dict, llm: LlmProvider) -> None:
    sender = message.get("from", "")
    subject = message.get("subject", "")
    body = message.get("body_text", "")
    external_id = message.get("external_id")
    if external_id and db.scalar(
        select(Communication.id).where(Communication.external_id == external_id)
    ):
        return
    pdfs = message.get("pdf_attachments", [])
    if pdfs:
        filename, content = pdfs[0]
        if content.startswith(b"%PDF") and len(content) <= 15 * 1024 * 1024:
            folder = Path(get_settings().upload_dir)
            folder.mkdir(parents=True, exist_ok=True)
            path = (
                folder / f"{utcnow().strftime('%Y%m%d%H%M%S%f')}-{Path(filename).name}"
            )
            path.write_bytes(content)
            extracted = llm.extract_bol(content, filename).model_dump(mode="json")
            db.add(
                Communication(
                    channel="email",
                    direction="inbound",
                    from_addr=sender,
                    subject=subject,
                    content=body,
                    tag="bol",
                    attachment_path=str(path),
                    extracted=extracted,
                    external_id=external_id,
                )
            )
            db.commit()
            return
    normalized = normalize_contact(sender, "email")
    candidates = (
        db.scalars(
            select(ScheduledCheckIn)
            .options(joinedload(ScheduledCheckIn.load))
            .where(ScheduledCheckIn.state.in_(["sent", "no_reply"]))
            .order_by(desc(ScheduledCheckIn.checkin_sent_at))
        )
        .unique()
        .all()
    )
    if any(
        candidate.load.status != "delivered"
        and any(
            value and normalize_contact(value, "email") == normalized
            for value in (candidate.load.driver_email, candidate.load.dispatcher_email)
        )
        for candidate in candidates
    ):
        handle_driver_reply(db, sender, body, "email", external_id, llm)
        return
    match = re.search(r"MC[#\s-]*(\d{5,8})", f"{subject}\n{body}", re.I)
    tag = "mc_provided" if match else None
    if tag is None:
        refs = db.scalars(select(Load.reference)).all()
        if any(
            reference and reference.lower() in f"{subject}\n{body}".lower()
            for reference in refs
        ):
            tag = "availability"
    if tag:
        db.add(
            Communication(
                channel="email",
                direction="inbound",
                from_addr=sender,
                subject=subject,
                content=body,
                tag=tag,
                external_id=external_id,
            )
        )
        db.commit()


@dev_public.post("/dev/simulate/sms-reply")
def simulate_sms(
    payload: SimulateSms,
    db: Session = Depends(get_db),
    llm: LlmProvider = Depends(get_llm_provider),
) -> dict[str, bool]:
    handle_driver_reply(db, payload.from_, payload.body, "sms", llm=llm)
    return {"accepted": True}


@dev_public.post("/dev/simulate/inbound-email")
def simulate_email(
    payload: SimulateEmail,
    db: Session = Depends(get_db),
    llm: LlmProvider = Depends(get_llm_provider),
) -> dict[str, bool]:
    _ingest_email_message(
        db,
        {
            "from": payload.from_,
            "subject": payload.subject,
            "body_text": payload.body,
            "external_id": None,
            "pdf_attachments": [],
        },
        llm,
    )
    return {"accepted": True}


@dev_public.post("/dev/run-tick")
def dev_tick(db: Session = Depends(get_db)) -> dict[str, bool]:
    run_checkin_tick(db)
    return {"completed": True}
