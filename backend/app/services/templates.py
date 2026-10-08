import re
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from zoneinfo import ZoneInfo

import yaml

from app.config import get_settings
from app.models import Load


@lru_cache
def _templates() -> dict:
    path = Path(__file__).resolve().parents[1] / "message_templates.yaml"
    return yaml.safe_load(path.read_text())


def local_datetime(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    zone = ZoneInfo(get_settings().broker_timezone)
    if value.tzinfo is None:
        return value.replace(tzinfo=zone)
    return value.astimezone(zone)


def eta_text(value: datetime | None) -> str:
    local = local_datetime(value)
    if local is None:
        return ""
    return local.strftime("%a %-m/%-d around %-I:%M %p")


def render_status_message(
    load: Load, status: str, note: str | None = None, eta: datetime | None = None
) -> tuple[str, str]:
    templates = _templates()["customer_status"][status]
    eta_value = eta_text(eta)
    body_template = templates.get("body_no_eta") if not eta_value else None
    body_template = body_template or templates["body"]
    values = {
        "customer_contact_name": load.customer_contact_name or "there",
        "reference": load.reference,
        "pickup_city_state": city_state(load.pickup_city, load.pickup_state),
        "delivery_city_state": city_state(load.delivery_city, load.delivery_state),
        "eta_text": eta_value,
        "broker_name": get_settings().broker_name,
        "broker_company": get_settings().broker_company,
        "note": (note or "").strip(),
    }
    subject = templates["subject"].format(**values)
    body = body_template.format(**values)
    body = re.sub(r"[ \t]{2,}", " ", body)
    body = re.sub(r"(?m)^[ \t]+|[ \t]+$", "", body)
    return subject, body


def city_state(city: str | None, state: str | None) -> str:
    return ", ".join(value for value in (city, state) if value) or "location TBD"


def render_checkin(load: Load, kind: str) -> str:
    template = _templates()["driver_checkin"][kind]
    return template.format(
        broker_company=get_settings().broker_company,
        reference=load.reference,
        pickup_city_state=city_state(load.pickup_city, load.pickup_state),
        delivery_city_state=city_state(load.delivery_city, load.delivery_state),
    )


def render_tracking_link(load: Load) -> str:
    return _templates()["driver_checkin"]["tracking_link"].format(
        broker_company=get_settings().broker_company,
        reference=load.reference,
        tracking_url=f"{get_settings().public_base_url.rstrip('/')}/t/{load.tracking_token}",
    )
