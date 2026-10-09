import secrets
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    LargeBinary,
    JSON,
    Numeric,
    String,
    Text,
    UniqueConstraint,
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
    pickup_datetime: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    delivery_location: Mapped[str | None] = mapped_column(Text, nullable=True)
    delivery_city: Mapped[str | None] = mapped_column(String(100), nullable=True)
    delivery_state: Mapped[str | None] = mapped_column(String(30), nullable=True)
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
