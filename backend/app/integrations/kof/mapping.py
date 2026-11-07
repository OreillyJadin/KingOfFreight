from datetime import datetime
import re
from typing import Any

from app.integrations.kof.parser import (
    parse_checkbox,
    parse_date,
    parse_local_datetime,
    parse_money,
    parse_row_key_or_order,
    strip_more_suffix,
)

_TIMEZONES = {
    "AKST": "America/Anchorage",
    "AKDT": "America/Anchorage",
    "AST": "America/Puerto_Rico",
    "CDT": "America/Chicago",
    "CST": "America/Chicago",
    "CT": "America/Chicago",
    "EDT": "America/New_York",
    "EST": "America/New_York",
    "ET": "America/New_York",
    "MDT": "America/Denver",
    "MST": "America/Denver",
    "MT": "America/Denver",
    "PDT": "America/Los_Angeles",
    "PST": "America/Los_Angeles",
    "PT": "America/Los_Angeles",
    "HST": "Pacific/Honolulu",
    "CENTRAL": "America/Chicago",
    "EASTERN": "America/New_York",
    "MOUNTAIN": "America/Denver",
    "PACIFIC": "America/Los_Angeles",
}
_STOP_LOCATION = re.compile(
    r"\b1st\s+(?:pick|drop)\s*:\s*.+?,\s*(?P<city>[^,]+?)\s*,\s*"
    r"(?P<state>[A-Z]{2})(?:\s+(?P<zip>\d{5}(?:-\d{4})?))?\b",
    re.IGNORECASE,
)


def _key(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.lower())


def _values(row: dict[str, str]) -> dict[str, str]:
    return {_key(label): value for label, value in row.items()}


def _value(values: dict[str, str], *labels: str) -> str | None:
    for label in labels:
        value = values.get(_key(label), "").strip()
        if value:
            return value
    return None


def _stop_location(value: str | None) -> dict[str, str | None]:
    if not value:
        return {}
    match = _STOP_LOCATION.search(value)
    if match is None:
        return {}
    return {
        "city": match.group("city").strip(),
        "state": match.group("state").upper(),
        "zip": match.group("zip"),
    }


def _status_reached(value: str | None) -> bool:
    if not value:
        return False
    checkbox = parse_checkbox(value)
    if checkbox is not None:
        return checkbox
    normalized = value.strip().lower()
    if any(token in normalized for token in ("not ", "unpaid", "pending", "false")):
        return False
    return any(
        token in normalized
        for token in (
            "yes",
            "true",
            "complete",
            "delivered",
            "paid",
            "billed",
            "invoiced",
            "picked up",
            "picked-up",
            "in transit",
            "in-transit",
            "confirmed",
            "received",
        )
    )


def derive_stage(
    row: dict[str, str],
    membership_stage: str | None = None,
    *,
    billed_status: str | None = None,
    paid_status: str | None = None,
    invoice_no: str | None = None,
) -> str:
    if membership_stage is not None:
        return membership_stage
    values = _values(row)
    paid_status = paid_status or _value(
        values, "Paid", "Paid Status", "Payment Status", "Date Paid"
    )
    billed_status = billed_status or _value(
        values, "Billed", "Billed Status", "Billing Status", "Invoice Status"
    )
    if _status_reached(paid_status) or _value(values, "Date Paid", "Paid Date"):
        return "paid"
    if _status_reached(billed_status) or (invoice_no and invoice_no.strip()):
        return "billed"
    delivery_status = _value(values, "Delivery Status", "Delivery")
    if _status_reached(delivery_status):
        return "delivered"
    pick_status = _value(values, "Pick Status", "Pickup Status")
    if _status_reached(pick_status):
        return "in_transit"
    return "booked"


MAPPED_SOURCE_LABELS = frozenset(
    _key(label)
    for label in (
        "Order #",
        "Order Number",
        "Date Of Sale",
        "Sale Date",
        "Customer",
        "Customer Name",
        "Branch No. / Loc.",
        "Branch",
        "Branch Name",
        "Trucking Co",
        "Trucking Company",
        "Carrier",
        "MC #",
        "MC",
        "MC Number",
        "Shipping From City",
        "Origin City",
        "Shipping From State",
        "Origin State",
        "Shipping From Zip",
        "Origin ZIP",
        "Shipping To City",
        "Destination City",
        "Shipping To State",
        "Destination State",
        "Shipping To Zip",
        "Destination ZIP",
        "Shipping From Company",
        "Shipper",
        "Shipping From Address",
        "Shipper Address",
        "Shipping From Phone #",
        "Shipping From Phone",
        "Shipping From Email",
        "Shipping To Company",
        "Consignee",
        "Shipping To Address",
        "Consignee Address",
        "Shipping To Phone #",
        "Shipping To Phone",
        "Shipping To Email",
        "Pick Date",
        "Pickup Date",
        "Pick Time",
        "Pickup Time",
        "Pick Tz",
        "Pickup Time Zone",
        "Delivery Date",
        "Drop Date",
        "Delivery Time",
        "Drop Time",
        "Drop Tz",
        "Delivery Time Zone",
        "Type of Truck",
        "Equipment",
        "Equipment Type",
        "Weight",
        "Weight (lbs)",
        "Weight Lbs",
        "Price",
        "Revenue",
        "Cost",
        "Carrier Cost",
        "Profit",
        "Margin",
        "Billed",
        "Billed Status",
        "Billing Status",
        "Invoice Status",
        "Paid",
        "Paid Status",
        "Payment Status",
        "Date Paid",
        "Paid Date",
        "Invoice #",
        "Invoice No.",
        "Invoice Number",
        "PO #",
        "PO",
        "Purchase Order",
        "PU #",
        "PU",
        "Pickup Number",
        "Confirmation Sent",
        "Confirmation Received",
        "Confirmation Returned",
        "Pick Status",
        "Pickup Status",
        "Delivery Status",
        "Delivery",
        "On Time",
        "On-Time",
        "On Time Delivery",
        "Notes",
        "Notes / Comments",
        "Log",
        "Load Log",
        "Booker",
        "Booked By",
        "Rep",
        "Sales Rep",
        "Commodity, Dimensions, and Weight",
        "Commodity",
        "Product",
        "Contact",
        "Trucker Contact",
        "Trucker Phone #",
        "Carrier Phone",
        "Trucker Email",
        "Carrier Email",
        "Dispatch Contact",
        "Dispatch No",
        "Dispatch Phone",
    )
)


def _timezone(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    if not normalized:
        return None
    return _TIMEZONES.get(normalized.upper(), normalized)


def map_load_row(
    row: dict[str, str],
    row_key: str | None = None,
    *,
    membership_stage: str | None = None,
    is_deleted: bool = False,
    synced_at: datetime | None = None,
) -> dict[str, Any] | None:
    values = _values(row)
    order_no = parse_row_key_or_order(row, row_key)
    if order_no is None:
        return None

    invoice_no = _value(values, "Invoice #", "Invoice No.", "Invoice Number")
    billed_status = _value(
        values, "Billed", "Billed Status", "Billing Status", "Invoice Status"
    )
    paid_status = _value(values, "Paid", "Paid Status", "Payment Status", "Date Paid")
    pick_date = _value(values, "Pick Date", "Pickup Date")
    pick_time = _value(values, "Pick Time", "Pickup Time")
    delivery_date = _value(values, "Delivery Date", "Drop Date")
    delivery_time = _value(values, "Delivery Time", "Drop Time")
    pick_at = parse_local_datetime(pick_date, pick_time)
    delivery_at = parse_local_datetime(delivery_date, delivery_time)
    raw = {str(label): str(value or "") for label, value in row.items()}
    shipper_address = _value(values, "Shipping From Address", "Shipper Address")
    consignee_address = _value(values, "Shipping To Address", "Consignee Address")
    pickup_location = _stop_location(shipper_address)
    delivery_location = _stop_location(consignee_address)
    notes_text = strip_more_suffix(_value(values, "Notes", "Notes / Comments"))
    log_text = strip_more_suffix(_value(values, "Log", "Load Log"))
    for label in list(raw):
        normalized = _key(label)
        if normalized in {"notes", "notescomments"}:
            raw[label] = strip_more_suffix(raw[label]) or ""
        elif normalized in {"log", "loadlog"}:
            raw[label] = strip_more_suffix(raw[label]) or ""

    def checkbox(*labels: str) -> bool | None:
        value = _value(values, *labels)
        return parse_checkbox(value)

    return {
        "order_no": order_no,
        "date_of_sale": parse_date(
            _value(values, "Date Of Sale", "Date of Sale", "Sale Date")
        ),
        "customer": _value(values, "Customer", "Customer Name"),
        "branch": _value(values, "Branch No. / Loc.", "Branch", "Branch Name"),
        "carrier": _value(values, "Trucking Co", "Trucking Company", "Carrier"),
        "mc": _value(values, "MC #", "MC", "MC Number"),
        "origin_city": _value(values, "Shipping From City", "Origin City")
        or pickup_location.get("city"),
        "origin_state": _value(values, "Shipping From State", "Origin State")
        or pickup_location.get("state"),
        "origin_zip": _value(
            values, "Shipping From Zip", "Shipping From ZIP", "Origin ZIP"
        )
        or pickup_location.get("zip"),
        "dest_city": _value(values, "Shipping To City", "Destination City")
        or delivery_location.get("city"),
        "dest_state": _value(values, "Shipping To State", "Destination State")
        or delivery_location.get("state"),
        "dest_zip": _value(
            values, "Shipping To Zip", "Shipping To ZIP", "Destination ZIP"
        )
        or delivery_location.get("zip"),
        "shipper_company": _value(values, "Shipping From Company", "Shipper"),
        "shipper_address": shipper_address,
        "shipper_city": _value(values, "Shipping From City")
        or pickup_location.get("city"),
        "shipper_state": _value(values, "Shipping From State")
        or pickup_location.get("state"),
        "shipper_zip": _value(values, "Shipping From Zip", "Shipping From ZIP")
        or pickup_location.get("zip"),
        "shipper_phone": _value(values, "Shipping From Phone #", "Shipping From Phone"),
        "shipper_email": _value(values, "Shipping From Email"),
        "consignee_company": _value(values, "Shipping To Company", "Consignee"),
        "consignee_address": consignee_address,
        "consignee_city": _value(values, "Shipping To City")
        or delivery_location.get("city"),
        "consignee_state": _value(values, "Shipping To State")
        or delivery_location.get("state"),
        "consignee_zip": _value(values, "Shipping To Zip", "Shipping To ZIP")
        or delivery_location.get("zip"),
        "consignee_phone": _value(values, "Shipping To Phone #", "Shipping To Phone"),
        "consignee_email": _value(values, "Shipping To Email"),
        "pick_at": pick_at,
        "pick_tz": _timezone(_value(values, "Pick Tz", "Pickup Time Zone")),
        "delivery_at": delivery_at,
        "drop_tz": _timezone(_value(values, "Drop Tz", "Delivery Time Zone")),
        "equipment": _value(values, "Type of Truck", "Equipment", "Equipment Type"),
        "weight": parse_money(
            _value(values, "Weight", "Weight (lbs)", "Weight Lbs")
            or _value(values, "Commodity, Dimensions, and Weight")
        ),
        "price": parse_money(_value(values, "Price", "Revenue")),
        "cost": parse_money(_value(values, "Cost", "Carrier Cost")),
        "profit": parse_money(_value(values, "Profit", "Margin")),
        "billed_status": billed_status or ("billed" if invoice_no else None),
        "paid_status": paid_status,
        "invoice_no": invoice_no,
        "po": _value(values, "PO #", "PO", "Purchase Order"),
        "pu": _value(values, "PU #", "PU", "Pickup Number"),
        "confirmation_sent": checkbox("Confirmation Sent"),
        "confirmation_received": checkbox("Confirmation Received"),
        "confirmation_returned": checkbox("Confirmation Returned"),
        "pick_status": _value(values, "Pick Status", "Pickup Status"),
        "delivery_status": _value(values, "Delivery Status", "Delivery"),
        "on_time": checkbox("On Time", "On-Time", "On Time Delivery"),
        "notes_text": notes_text,
        "log_text": log_text,
        "booker": _value(values, "Booker", "Booked By"),
        "rep": _value(values, "Rep", "Sales Rep"),
        "product_description": _value(
            values, "Commodity, Dimensions, and Weight", "Commodity", "Product"
        ),
        "carrier_contact_name": _value(values, "Contact", "Trucker Contact"),
        "carrier_contact_phone": _value(values, "Trucker Phone #", "Carrier Phone"),
        "carrier_contact_email": _value(values, "Trucker Email", "Carrier Email"),
        "dispatch_contact": _value(values, "Dispatch Contact"),
        "dispatch_phone": _value(values, "Dispatch No", "Dispatch Phone"),
        "stage": derive_stage(
            row,
            membership_stage,
            billed_status=billed_status,
            paid_status=paid_status,
            invoice_no=invoice_no,
        ),
        "is_deleted": is_deleted,
        "raw": raw,
        "synced_at": synced_at,
    }
