import secrets
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    JSON,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Load(Base):
    __tablename__ = "loads"

    id: Mapped[int] = mapped_column(primary_key=True)
    reference: Mapped[str] = mapped_column(String(120), index=True)
    status: Mapped[str] = mapped_column(String(20), default="new", index=True)
    bol_source: Mapped[int | None] = mapped_column(
        ForeignKey("communications.id"), nullable=True
    )
    pickup_location: Mapped[str | None] = mapped_column(Text, nullable=True)
    pickup_city: Mapped[str | None] = mapped_column(String(100), nullable=True)
    pickup_state: Mapped[str | None] = mapped_column(String(30), nullable=True)
    pickup_timezone: Mapped[str | None] = mapped_column(String(64), nullable=True)
    pickup_datetime: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    delivery_location: Mapped[str | None] = mapped_column(Text, nullable=True)
    delivery_city: Mapped[str | None] = mapped_column(String(100), nullable=True)
    delivery_state: Mapped[str | None] = mapped_column(String(30), nullable=True)
    delivery_timezone: Mapped[str | None] = mapped_column(String(64), nullable=True)
    delivery_datetime: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    weight_lbs: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)
    equipment_type: Mapped[str | None] = mapped_column(String(40), nullable=True)
    commodity: Mapped[str | None] = mapped_column(String(200), nullable=True)
    special_requirements: Mapped[str | None] = mapped_column(Text, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    customer_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    customer_contact_name: Mapped[str | None] = mapped_column(
        String(160), nullable=True
    )
    customer_email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    customer_phone: Mapped[str | None] = mapped_column(String(40), nullable=True)
    customer_rate: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    carrier_rate: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    carrier_id: Mapped[int | None] = mapped_column(
        ForeignKey("carriers.id"), nullable=True
    )
    driver_name: Mapped[str | None] = mapped_column(String(160), nullable=True)
    driver_phone: Mapped[str | None] = mapped_column(String(40), nullable=True)
    driver_email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    dispatcher_name: Mapped[str | None] = mapped_column(String(160), nullable=True)
    dispatcher_phone: Mapped[str | None] = mapped_column(String(40), nullable=True)
    dispatcher_email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    checkin_offset_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    checkin_channel: Mapped[str | None] = mapped_column(String(10), nullable=True)
    tracking_token: Mapped[str] = mapped_column(
        String(100), unique=True, default=lambda: secrets.token_urlsafe(16)
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )
    booked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    delivered_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    carrier: Mapped["Carrier | None"] = relationship(back_populates="loads")
    status_updates: Mapped[list["StatusUpdate"]] = relationship(
        back_populates="load", cascade="all, delete-orphan"
    )
    checkins: Mapped[list["ScheduledCheckIn"]] = relationship(
        back_populates="load", cascade="all, delete-orphan"
    )
    communications: Mapped[list["Communication"]] = relationship(
        back_populates="load", foreign_keys="Communication.load_id"
    )

    @property
    def margin(self) -> Decimal | None:
        if self.customer_rate is None or self.carrier_rate is None:
            return None
        return self.customer_rate - self.carrier_rate

    @property
    def margin_pct(self) -> Decimal | None:
        if not self.customer_rate:
            return None
        margin = self.margin
        return (
            margin / self.customer_rate * Decimal(100) if margin is not None else None
        )


class Carrier(Base):
    __tablename__ = "carriers"

    id: Mapped[int] = mapped_column(primary_key=True)
    mc_number: Mapped[str] = mapped_column(String(8), unique=True, index=True)
    dot_number: Mapped[str | None] = mapped_column(String(20), nullable=True)
    legal_name: Mapped[str | None] = mapped_column(String(250), nullable=True)
    dba_name: Mapped[str | None] = mapped_column(String(250), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(40), nullable=True)
    email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    allowed_to_operate: Mapped[str | None] = mapped_column(String(5), nullable=True)
    authority_status: Mapped[str | None] = mapped_column(String(40), nullable=True)
    safety_rating: Mapped[str | None] = mapped_column(String(5), nullable=True)
    insurance_on_file: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    bipd_on_file_amount: Mapped[float | None] = mapped_column(
        Numeric(14, 2), nullable=True
    )
    bipd_required_amount: Mapped[float | None] = mapped_column(
        Numeric(14, 2), nullable=True
    )
    out_of_service_date: Mapped[str | None] = mapped_column(String(30), nullable=True)
    flag: Mapped[str] = mapped_column(String(10), default="yellow")
    flag_reasons: Mapped[list[str]] = mapped_column(JSON, default=list)
    raw: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    verified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    loads: Mapped[list[Load]] = relationship(back_populates="carrier")


class BolFile(Base):
    __tablename__ = "bol_files"

    id: Mapped[int] = mapped_column(primary_key=True)
    filename: Mapped[str] = mapped_column(String(255))
    content: Mapped[bytes] = mapped_column(LargeBinary)
    size_bytes: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )


class Communication(Base):
    __tablename__ = "communications"
    __table_args__ = (
        UniqueConstraint("external_id", name="uq_communications_external_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    load_id: Mapped[int | None] = mapped_column(ForeignKey("loads.id"), nullable=True)
    kof_order_no: Mapped[int | None] = mapped_column(
        ForeignKey("kof_loads.order_no"), nullable=True, index=True
    )
    carrier_id: Mapped[int | None] = mapped_column(
        ForeignKey("carriers.id"), nullable=True
    )
    channel: Mapped[str] = mapped_column(String(10))
    direction: Mapped[str] = mapped_column(String(10))
    from_addr: Mapped[str | None] = mapped_column(String(320), nullable=True)
    to_addr: Mapped[str | None] = mapped_column(String(320), nullable=True)
    subject: Mapped[str | None] = mapped_column(String(500), nullable=True)
    content: Mapped[str] = mapped_column(Text, default="")
    tag: Mapped[str] = mapped_column(String(30), default="other", index=True)
    attachment_file_id: Mapped[int | None] = mapped_column(
        ForeignKey(
            "bol_files.id",
            ondelete="SET NULL",
            name="fk_communications_attachment_file_id_bol_files",
        ),
        nullable=True,
    )
    attachment_filename: Mapped[str | None] = mapped_column(String(255), nullable=True)
    extracted: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    external_id: Mapped[str | None] = mapped_column(String(300), nullable=True)
    archived: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, index=True
    )
    load: Mapped[Load | None] = relationship(
        back_populates="communications", foreign_keys=[load_id]
    )
    attachment_file: Mapped[BolFile | None] = relationship(lazy="select")

    @property
    def has_attachment(self) -> bool:
        return self.attachment_file_id is not None


class StatusUpdate(Base):
    __tablename__ = "status_updates"

    id: Mapped[int] = mapped_column(primary_key=True)
    load_id: Mapped[int] = mapped_column(ForeignKey("loads.id"), index=True)
    status: Mapped[str] = mapped_column(String(20))
    source: Mapped[str] = mapped_column(String(20))
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    eta: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    applied: Mapped[bool] = mapped_column(Boolean, default=False)
    customer_channel: Mapped[str | None] = mapped_column(String(10), nullable=True)
    customer_message_subject: Mapped[str | None] = mapped_column(
        String(500), nullable=True
    )
    customer_message_preview: Mapped[str | None] = mapped_column(Text, nullable=True)
    approved_by_broker: Mapped[bool] = mapped_column(Boolean, default=False)
    sent_to_customer: Mapped[bool] = mapped_column(Boolean, default=False)
    sent_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    state: Mapped[str] = mapped_column(
        String(30), default="pending_approval", index=True
    )
    checkin_id: Mapped[int | None] = mapped_column(
        ForeignKey("scheduled_checkins.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )
    load: Mapped[Load] = relationship(back_populates="status_updates")


class ScheduledCheckIn(Base):
    __tablename__ = "scheduled_checkins"

    id: Mapped[int] = mapped_column(primary_key=True)
    load_id: Mapped[int] = mapped_column(ForeignKey("loads.id"), index=True)
    kind: Mapped[str] = mapped_column(String(10))
    scheduled_time: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    send_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    checkin_sent_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    checkin_channel: Mapped[str] = mapped_column(String(10))
    driver_contact: Mapped[str] = mapped_column(String(320))
    message_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    reply_received: Mapped[bool] = mapped_column(Boolean, default=False)
    reply_raw_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    reply_received_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    parsed_status: Mapped[str | None] = mapped_column(String(20), nullable=True)
    parsed_eta: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    parsed_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    parse_confidence: Mapped[float | None] = mapped_column(Numeric(4, 3), nullable=True)
    needs_broker_attention: Mapped[bool] = mapped_column(Boolean, default=False)
    state: Mapped[str] = mapped_column(String(20), default="scheduled", index=True)
    alert_raised_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    alert_dismissed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    load: Mapped[Load] = relationship(back_populates="checkins")


class LocationPing(Base):
    __tablename__ = "location_pings"

    id: Mapped[int] = mapped_column(primary_key=True)
    load_id: Mapped[int] = mapped_column(ForeignKey("loads.id"), index=True)
    lat: Mapped[float] = mapped_column(Numeric(10, 7))
    lng: Mapped[float] = mapped_column(Numeric(10, 7))
    accuracy_m: Mapped[float | None] = mapped_column(Numeric(10, 2), nullable=True)
    captured_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )
    user_agent: Mapped[str | None] = mapped_column(String(500), nullable=True)


class BrokerSettings(Base):
    __tablename__ = "broker_settings"
    __table_args__ = (CheckConstraint("id = 1", name="ck_broker_settings_singleton"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    broker_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    broker_company: Mapped[str | None] = mapped_column(String(100), nullable=True)
    broker_timezone: Mapped[str | None] = mapped_column(String(100), nullable=True)
    checkin_offset_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    no_reply_alert_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    checkin_default_channel: Mapped[str | None] = mapped_column(
        String(10), nullable=True
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint("role IN ('admin', 'member')", name="ck_users_role"),
        Index(
            "uq_users_username_lower",
            func.lower(text("username")),
            unique=True,
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(120), nullable=False)
    role: Mapped[str] = mapped_column(String(20), default="member", nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    last_login_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    password_hash: Mapped[str | None] = mapped_column(Text, nullable=True)
    password_version: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    must_set_password: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )


class TeamMember(Base):
    __tablename__ = "team_members"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    __table_args__ = (Index("ix_team_members_name_ci", func.lower(name), unique=True),)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )


class UsageEvent(Base):
    __tablename__ = "usage_events"
    __table_args__ = (
        CheckConstraint(
            "device IN ('mobile', 'desktop', 'tablet')", name="ck_usage_events_device"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    username: Mapped[str | None] = mapped_column(String(120), nullable=True)
    team_member_id: Mapped[int | None] = mapped_column(
        ForeignKey("team_members.id", ondelete="SET NULL"), nullable=True
    )
    operator_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    event: Mapped[str] = mapped_column(String(80))
    path: Mapped[str | None] = mapped_column(String(160), nullable=True)
    device: Mapped[str] = mapped_column(String(10))
    detail: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, index=True
    )


class CustomerContact(Base):
    __tablename__ = "customer_contacts"
    customer_key: Mapped[str] = mapped_column(String(300), primary_key=True)
    email: Mapped[str] = mapped_column(String(320))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )


class CustomerUpdateDraft(Base):
    __tablename__ = "customer_update_drafts"
    __table_args__ = (
        Index(
            "uq_customer_update_pending",
            "order_no",
            unique=True,
            postgresql_where=text("state = 'pending'"),
            sqlite_where=text("state = 'pending'"),
        ),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    order_no: Mapped[int] = mapped_column(ForeignKey("kof_loads.order_no"), index=True)
    source_refs: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    summary: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(30))
    eta: Mapped[str | None] = mapped_column(String(250), nullable=True)
    confidence: Mapped[float] = mapped_column(Numeric(4, 3))
    to_email: Mapped[str] = mapped_column(String(320), default="")
    subject: Mapped[str] = mapped_column(String(500))
    body: Mapped[str] = mapped_column(Text)
    state: Mapped[str] = mapped_column(String(20), default="pending", index=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )
    sent_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    send_started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    error: Mapped[str | None] = mapped_column(Text, nullable=True)


class KofMessage(Base):
    __tablename__ = "kof_messages"

    id: Mapped[int] = mapped_column(primary_key=True)
    order_no: Mapped[int | None] = mapped_column(
        ForeignKey("kof_loads.order_no"), index=True, nullable=True
    )
    direction: Mapped[str] = mapped_column(String(3))
    to_phone: Mapped[str | None] = mapped_column(String(16), nullable=True, index=True)
    from_phone: Mapped[str | None] = mapped_column(String(16), nullable=True)
    body: Mapped[str] = mapped_column(Text)
    external_id: Mapped[str | None] = mapped_column(
        String(100), unique=True, nullable=True
    )
    status: Mapped[str] = mapped_column(String(20))
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, index=True
    )
    match_method: Mapped[str | None] = mapped_column(String(40), nullable=True)
    candidate_order_nos: Mapped[list[int]] = mapped_column(JSON, default=list)
    parsed_status: Mapped[str | None] = mapped_column(String(30), nullable=True)
    parsed_eta: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    parsed_summary: Mapped[str | None] = mapped_column(Text, nullable=True)


class OutlookApp(Base):
    __tablename__ = "outlook_app"
    __table_args__ = (CheckConstraint("id = 1", name="ck_outlook_app_singleton"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    client_id: Mapped[str] = mapped_column(String(100))
    secret_encrypted: Mapped[str] = mapped_column(Text)


class OutlookConnection(Base):
    __tablename__ = "outlook_connection"
    __table_args__ = (
        CheckConstraint("id = 1", name="ck_outlook_connection_singleton"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    token_encrypted: Mapped[str] = mapped_column(Text)
    email: Mapped[str] = mapped_column(String(320))
    name: Mapped[str] = mapped_column(String(250))
    needs_reconnect: Mapped[bool] = mapped_column(Boolean, default=False)


class EmailPollState(Base):
    __tablename__ = "email_poll_state"
    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    last_poll: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class TwilioConnection(Base):
    __tablename__ = "twilio_connection"
    __table_args__ = (CheckConstraint("id = 1", name="ck_twilio_connection_singleton"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    account_sid: Mapped[str] = mapped_column(String(34), nullable=False)
    token_encrypted: Mapped[str] = mapped_column(Text, nullable=False)
    from_number: Mapped[str] = mapped_column(String(16), nullable=False)


class AssistantConnection(Base):
    __tablename__ = "assistant_connection"
    __table_args__ = (
        CheckConstraint("id = 1", name="ck_assistant_connection_singleton"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    key_encrypted: Mapped[str] = mapped_column(Text, nullable=False)


class KofConnection(Base):
    __tablename__ = "kof_connection"
    __table_args__ = (CheckConstraint("id = 1", name="ck_kof_connection_singleton"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(120), nullable=False)
    password_encrypted: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )
    updated_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )


class KofLoad(Base):
    __tablename__ = "kof_loads"

    order_no: Mapped[int] = mapped_column(primary_key=True)
    date_of_sale: Mapped[date | None] = mapped_column(Date, nullable=True)
    customer: Mapped[str | None] = mapped_column(String(250), nullable=True)
    branch: Mapped[str | None] = mapped_column(String(250), nullable=True)
    carrier: Mapped[str | None] = mapped_column(String(250), nullable=True)
    mc: Mapped[str | None] = mapped_column(String(40), nullable=True)
    origin_city: Mapped[str | None] = mapped_column(String(150), nullable=True)
    origin_state: Mapped[str | None] = mapped_column(String(40), nullable=True)
    origin_zip: Mapped[str | None] = mapped_column(String(20), nullable=True)
    dest_city: Mapped[str | None] = mapped_column(String(150), nullable=True)
    dest_state: Mapped[str | None] = mapped_column(String(40), nullable=True)
    dest_zip: Mapped[str | None] = mapped_column(String(20), nullable=True)
    shipper_company: Mapped[str | None] = mapped_column(String(250), nullable=True)
    shipper_address: Mapped[str | None] = mapped_column(Text, nullable=True)
    shipper_city: Mapped[str | None] = mapped_column(String(150), nullable=True)
    shipper_state: Mapped[str | None] = mapped_column(String(40), nullable=True)
    shipper_zip: Mapped[str | None] = mapped_column(String(20), nullable=True)
    shipper_phone: Mapped[str | None] = mapped_column(String(80), nullable=True)
    shipper_email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    consignee_company: Mapped[str | None] = mapped_column(String(250), nullable=True)
    consignee_address: Mapped[str | None] = mapped_column(Text, nullable=True)
    consignee_city: Mapped[str | None] = mapped_column(String(150), nullable=True)
    consignee_state: Mapped[str | None] = mapped_column(String(40), nullable=True)
    consignee_zip: Mapped[str | None] = mapped_column(String(20), nullable=True)
    consignee_phone: Mapped[str | None] = mapped_column(String(80), nullable=True)
    consignee_email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    pick_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    pick_tz: Mapped[str | None] = mapped_column(String(80), nullable=True)
    delivery_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    drop_tz: Mapped[str | None] = mapped_column(String(80), nullable=True)
    equipment: Mapped[str | None] = mapped_column(String(120), nullable=True)
    weight: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    price: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    cost: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    profit: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    billed_status: Mapped[str | None] = mapped_column(String(120), nullable=True)
    paid_status: Mapped[str | None] = mapped_column(String(120), nullable=True)
    invoice_no: Mapped[str | None] = mapped_column(String(120), nullable=True)
    po: Mapped[str | None] = mapped_column(String(120), nullable=True)
    pu: Mapped[str | None] = mapped_column(String(120), nullable=True)
    confirmation_sent: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    confirmation_received: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    confirmation_returned: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    pick_status: Mapped[str | None] = mapped_column(String(120), nullable=True)
    delivery_status: Mapped[str | None] = mapped_column(String(120), nullable=True)
    on_time: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    notes_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    log_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    booker: Mapped[str | None] = mapped_column(String(200), nullable=True)
    rep: Mapped[str | None] = mapped_column(String(200), nullable=True)
    product_description: Mapped[str | None] = mapped_column(Text, nullable=True)
    carrier_contact_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    carrier_contact_phone: Mapped[str | None] = mapped_column(String(80), nullable=True)
    carrier_contact_email: Mapped[str | None] = mapped_column(
        String(320), nullable=True
    )
    dispatch_contact: Mapped[str | None] = mapped_column(String(200), nullable=True)
    dispatch_phone: Mapped[str | None] = mapped_column(String(80), nullable=True)
    stage: Mapped[str] = mapped_column(String(40), default="booked", index=True)
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    raw: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )
    synced_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, index=True
    )


class KofCustomer(Base):
    __tablename__ = "kof_customers"

    customer_key: Mapped[str] = mapped_column(String(120), primary_key=True)
    name: Mapped[str | None] = mapped_column(String(250), nullable=True)
    raw: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    synced_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class KofBranch(Base):
    __tablename__ = "kof_branches"

    branch_key: Mapped[str] = mapped_column(String(120), primary_key=True)
    name: Mapped[str | None] = mapped_column(String(250), nullable=True)
    raw: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    synced_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class KofListSnapshot(Base):
    __tablename__ = "kof_list_snapshots"

    key: Mapped[str] = mapped_column(String(80), primary_key=True)
    label: Mapped[str] = mapped_column(String(200))
    columns: Mapped[list[str]] = mapped_column(JSON, default=list)
    rows: Mapped[list[list[str]]] = mapped_column(JSON, default=list)
    count: Mapped[int] = mapped_column(Integer, default=0)
    synced_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class KofSyncRun(Base):
    __tablename__ = "kof_sync_runs"
    __table_args__ = (
        Index(
            "uq_kof_sync_runs_single_running",
            "status",
            unique=True,
            postgresql_where=text("status = 'running'"),
            sqlite_where=text("status = 'running'"),
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    kind: Mapped[str] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(20), index=True)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    loads_upserted: Mapped[int] = mapped_column(Integer, default=0)
    counts: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
