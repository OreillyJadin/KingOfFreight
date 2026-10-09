from datetime import datetime
from decimal import Decimal
from typing import Any, Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class LoadCreate(BaseModel):
    reference: str
    status: Literal[
        "new", "posted", "booked", "picked_up", "in_transit", "delayed", "delivered"
    ] = "new"
    pickup_location: str | None = None
    pickup_city: str | None = None
    pickup_state: str | None = None
    pickup_datetime: datetime | None = None
    delivery_location: str | None = None
    delivery_city: str | None = None
    delivery_state: str | None = None
    delivery_datetime: datetime | None = None
    weight_lbs: float | None = None
    equipment_type: str | None = None
    commodity: str | None = None
    special_requirements: str | None = None
    notes: str | None = None
    customer_name: str | None = None
    customer_contact_name: str | None = None
    customer_email: str | None = None
    customer_phone: str | None = None
    customer_rate: Decimal | None = None
    carrier_rate: Decimal | None = None
    carrier_id: int | None = None
    driver_name: str | None = None
    driver_phone: str | None = None
    driver_email: str | None = None
    dispatcher_name: str | None = None
    dispatcher_phone: str | None = None
    dispatcher_email: str | None = None


class LoadPatch(BaseModel):
    reference: str | None = None
    status: str | None = None
    pickup_location: str | None = None
    pickup_city: str | None = None
    pickup_state: str | None = None
    pickup_datetime: datetime | None = None
    delivery_location: str | None = None
    delivery_city: str | None = None
    delivery_state: str | None = None
    delivery_datetime: datetime | None = None
    weight_lbs: float | None = None
    equipment_type: str | None = None
    commodity: str | None = None
    special_requirements: str | None = None
    notes: str | None = None
    customer_name: str | None = None
    customer_contact_name: str | None = None
    customer_email: str | None = None
    customer_phone: str | None = None
    customer_rate: Decimal | None = None
    carrier_rate: Decimal | None = None
    driver_name: str | None = None
    driver_phone: str | None = None
    driver_email: str | None = None
    dispatcher_name: str | None = None
    dispatcher_phone: str | None = None
    dispatcher_email: str | None = None


class BookLoad(BaseModel):
    carrier_mc: str
    carrier_rate: Decimal
    customer_rate: Decimal
    driver_name: str | None = None
    driver_phone: str | None = None
    driver_email: str | None = None
    dispatcher_name: str | None = None
    dispatcher_phone: str | None = None
    dispatcher_email: str | None = None
    checkin_offset_minutes: int | None = None
    checkin_channel: Literal["sms", "email"] | None = None
    override_red_flag: bool = False


class ManualStatus(BaseModel):
    status: Literal["booked", "picked_up", "in_transit", "delayed", "delivered"]
    note: str | None = None
    eta: datetime | None = None


class ApproveStatus(BaseModel):
    subject: str | None = None
    body: str | None = None
    channel: Literal["email", "sms"] | None = None


class SkipStatus(BaseModel):
    apply: bool = True


class VerifyCarrier(BaseModel):
    mc_number: str


class BolExtraction(BaseModel):
    reference: str | None = None
    pickup_location: str | None = None
    pickup_city: str | None = None
    pickup_state: str | None = None
    pickup_datetime: datetime | None = None
    pickup_time_known: bool | None = None
    delivery_location: str | None = None
    delivery_city: str | None = None
    delivery_state: str | None = None
    delivery_datetime: datetime | None = None
    delivery_time_known: bool | None = None
    weight_lbs: float | None = None
    equipment_type: str | None = None
    commodity: str | None = None
    pieces: int | None = None
    pallets: int | None = None
    reference_numbers: dict[str, str] | None = None
    customer_name: str | None = None
    customer_contact_name: str | None = None
    customer_email: str | None = None
    customer_phone: str | None = None
    special_requirements: str | None = None
    confidence: float = Field(default=0.3, ge=0, le=1)
    notes: str | None = None


class ReplyParse(BaseModel):
    status: Literal["picked_up", "in_transit", "delayed", "delivered", "unclear"] = (
        "unclear"
    )
    eta: datetime | None = None
    delay_minutes: int | None = None
    summary: str = ""
    needs_broker_attention: bool = False
    confidence: float = Field(default=0.3, ge=0, le=1)


class CarrierSnapshot(BaseModel):
    mc_number: str
    dot_number: str | None = None
    legal_name: str | None = None
    dba_name: str | None = None
    phone: str | None = None
    email: str | None = None
    allowed_to_operate: str | None = None
    authority_status: str | None = None
    safety_rating: str | None = None
    insurance_on_file: bool | None = None
    bipd_on_file_amount: float | None = None
    bipd_required_amount: float | None = None
    out_of_service_date: str | None = None
    raw: dict[str, Any] | None = None


class TrackingPing(BaseModel):
    lat: float = Field(ge=-90, le=90)
    lng: float = Field(ge=-180, le=180)
    accuracy_m: float | None = Field(default=None, ge=0)


class BrokerSettingsUpdate(BaseModel):
    broker_name: str | None = None
    broker_company: str | None = None
    broker_timezone: str | None = None
    checkin_offset_minutes: int | None = Field(default=None, ge=0, le=720)
    no_reply_alert_minutes: int | None = Field(default=None, ge=5, le=240)
    checkin_default_channel: Literal["sms", "email"] | None = None

    @field_validator("broker_name", "broker_company", mode="before")
    @classmethod
    def normalize_broker_details(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if not isinstance(value, str):
            return value
        normalized = value.strip()
        if not 1 <= len(normalized) <= 100:
            raise ValueError("Must be between 1 and 100 characters")
        return normalized

    @field_validator("broker_timezone")
    @classmethod
    def validate_broker_timezone(cls, value: str | None) -> str | None:
        if value is None:
            return None
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError, TypeError) as exc:
            raise ValueError("Invalid timezone") from exc
        return value


class CreateLoadOverrides(LoadCreate):
    reference: str | None = None
    status: (
        Literal[
            "new", "posted", "booked", "picked_up", "in_transit", "delayed", "delivered"
        ]
        | None
    ) = None


class SimulateSms(BaseModel):
    from_: str = Field(alias="from")
    body: str


class SimulateEmail(BaseModel):
    from_: str = Field(alias="from")
    subject: str
    body: str


class LoadOut(ORMModel):
    id: int
    reference: str
    status: str
    pickup_location: str | None
    pickup_city: str | None
    pickup_state: str | None
    pickup_datetime: datetime | None
    delivery_location: str | None
    delivery_city: str | None
    delivery_state: str | None
    delivery_datetime: datetime | None
    weight_lbs: Decimal | None
    equipment_type: str | None
    commodity: str | None
    special_requirements: str | None
    notes: str | None
    customer_name: str | None
    customer_contact_name: str | None
    customer_email: str | None
    customer_phone: str | None
    customer_rate: Decimal | None
    carrier_rate: Decimal | None
    margin: Decimal | None
    margin_pct: Decimal | None
    carrier_id: int | None
    driver_name: str | None
    driver_phone: str | None
    driver_email: str | None
    dispatcher_name: str | None
    dispatcher_phone: str | None
    dispatcher_email: str | None
    tracking_token: str
    created_at: datetime
    booked_at: datetime | None
    delivered_at: datetime | None


class GenericResponse(BaseModel):
    detail: str


class CarrierOut(ORMModel):
    id: int
    mc_number: str
    dot_number: str | None
    legal_name: str | None
    dba_name: str | None
    phone: str | None
    email: str | None
    allowed_to_operate: str | None
    authority_status: str | None
    safety_rating: str | None
    insurance_on_file: bool | None
    bipd_on_file_amount: Decimal | None
    bipd_required_amount: Decimal | None
    out_of_service_date: str | None
    flag: str
    flag_reasons: list[str]
    raw: dict[str, Any] | None
    verified_at: datetime | None


class CommunicationOut(ORMModel):
    id: int
    load_id: int | None
    carrier_id: int | None
    channel: str
    direction: str
    from_addr: str | None
    to_addr: str | None
    subject: str | None
    content: str
    tag: str
    has_attachment: bool
    attachment_filename: str | None
    extracted: dict[str, Any] | None
    external_id: str | None
    archived: bool
    created_at: datetime


class StatusUpdateOut(ORMModel):
    id: int
    load_id: int
    status: str
    source: str
    note: str | None
    eta: datetime | None
    applied: bool
    customer_channel: str | None
    customer_message_subject: str | None
    customer_message_preview: str | None
    approved_by_broker: bool
    sent_to_customer: bool
    sent_at: datetime | None
    state: str
    checkin_id: int | None
    created_at: datetime


class CheckInOut(ORMModel):
    id: int
    load_id: int
    kind: str
    scheduled_time: datetime
    send_at: datetime
    checkin_sent_at: datetime | None
    checkin_channel: str
    driver_contact: str
    message_text: str | None
    reply_received: bool
    reply_raw_text: str | None
    reply_received_at: datetime | None
    parsed_status: str | None
    parsed_eta: datetime | None
    parsed_summary: str | None
    parse_confidence: Decimal | None
    needs_broker_attention: bool
    state: str
    alert_raised_at: datetime | None
    alert_dismissed_at: datetime | None
