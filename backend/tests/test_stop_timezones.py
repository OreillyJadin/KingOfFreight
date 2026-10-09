from datetime import datetime, timezone

import pytest
from sqlalchemy import select

from app.models import Load, ScheduledCheckIn
from app.schemas import BolExtraction
from app.services.stop_timezones import (
    resolve_stop_timezone,
    timezone_for_state,
)


def _as_utc(value: str | datetime) -> datetime:
    parsed = datetime.fromisoformat(value) if isinstance(value, str) else value
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


@pytest.mark.parametrize(
    ("state", "expected"),
    [
        ("MI", "America/New_York"),
        (" il ", "America/Chicago"),
        ("AZ", "America/Phoenix"),
        ("Michigan", "America/New_York"),
        ("ON", "America/New_York"),
        ("Ontario", "America/New_York"),
        ("District of Columbia", "America/New_York"),
        ("SK", "America/Regina"),
        ("ZZ", None),
        (None, None),
        ("", None),
    ],
)
def test_timezone_for_state(state, expected):
    assert timezone_for_state(state) == expected


def test_resolve_stop_timezone_precedence():
    assert (
        resolve_stop_timezone("America/Los_Angeles", "MI", "America/Chicago")
        == "America/Los_Angeles"
    )
    assert resolve_stop_timezone(None, "MI", "America/Chicago") == "America/New_York"
    assert resolve_stop_timezone(None, "ZZ", "America/Chicago") == "America/Chicago"


def test_bol_extraction_ignores_invalid_timezone():
    assert BolExtraction(delivery_timezone="nonsense").delivery_timezone is None


def test_stop_timezone_metadata(client):
    response = client.get("/api/meta/stop-timezones")
    assert response.status_code == 200
    assert response.json()["states"]["MI"] == "America/New_York"
    assert len(response.json()["zones"]) == 10


def test_create_load_interprets_stop_times_in_facility_zones(client, db):
    response = client.post(
        "/api/loads",
        json={
            "reference": "TZ-POST",
            "pickup_state": "IL",
            "pickup_datetime": "2026-10-13T08:00",
            "delivery_state": "MI",
            "delivery_datetime": "2026-10-14T07:30",
        },
    )
    assert response.status_code == 201, response.text
    load = db.get(Load, response.json()["id"])
    assert _as_utc(load.pickup_datetime) == datetime(
        2026, 10, 13, 13, tzinfo=timezone.utc
    )
    assert _as_utc(load.delivery_datetime) == datetime(
        2026, 10, 14, 11, 30, tzinfo=timezone.utc
    )
    assert load.pickup_timezone == "America/Chicago"
    assert load.delivery_timezone == "America/New_York"

    explicit = client.post(
        "/api/loads",
        json={
            "reference": "TZ-EXPLICIT",
            "delivery_state": "MI",
            "delivery_timezone": "America/Los_Angeles",
            "delivery_datetime": "2026-10-14T07:30",
        },
    )
    assert explicit.status_code == 201, explicit.text
    assert _as_utc(explicit.json()["delivery_datetime"]) == datetime(
        2026, 10, 14, 14, 30, tzinfo=timezone.utc
    )

    fallback = client.post(
        "/api/loads",
        json={
            "reference": "TZ-FALLBACK",
            "delivery_state": "ZZ",
            "delivery_datetime": "2026-10-14T07:30",
        },
    )
    assert fallback.status_code == 201, fallback.text
    assert _as_utc(fallback.json()["delivery_datetime"]) == datetime(
        2026, 10, 14, 12, 30, tzinfo=timezone.utc
    )
    assert fallback.json()["delivery_timezone"] == "America/Chicago"

    invalid = client.post(
        "/api/loads",
        json={
            "reference": "TZ-INVALID",
            "delivery_timezone": "Mars/Base",
        },
    )
    assert invalid.status_code == 422


@pytest.mark.parametrize(
    ("delivery_timezone", "expected_hour"),
    [(None, 11), ("America/Chicago", 12)],
)
def test_bol_creation_uses_extracted_facility_timezones(
    client, db, providers, monkeypatch, delivery_timezone, expected_hour
):
    extraction = BolExtraction(
        reference="TZ-BOL",
        pickup_city="Chicago",
        pickup_state="IL",
        pickup_datetime="2026-10-13T08:00",
        delivery_city="Grand Rapids",
        delivery_state="MI",
        delivery_datetime="2026-10-14T07:30",
        delivery_timezone=delivery_timezone,
    )
    monkeypatch.setattr(
        providers["llm"], "extract_bol", lambda _pdf, _filename: extraction
    )
    uploaded = client.post(
        "/api/bol/upload",
        files={"file": ("tz-bol.pdf", b"%PDF-1.4 test", "application/pdf")},
    )
    assert uploaded.status_code == 200, uploaded.text
    created = client.post(f"/api/inbox/{uploaded.json()['id']}/create-load", json={})
    assert created.status_code == 201, created.text
    load = db.get(Load, created.json()["id"])
    assert _as_utc(load.pickup_datetime) == datetime(
        2026, 10, 13, 13, tzinfo=timezone.utc
    )
    assert _as_utc(load.delivery_datetime) == datetime(
        2026, 10, 14, expected_hour, 30, tzinfo=timezone.utc
    )
    assert load.pickup_timezone == "America/Chicago"
    assert load.delivery_timezone == (delivery_timezone or "America/New_York")


def test_patch_timezone_conversion_and_timezone_only_update(client, db):
    created = client.post(
        "/api/loads",
        json={
            "reference": "TZ-PATCH",
            "delivery_state": "MI",
            "delivery_datetime": "2026-10-14T07:30",
        },
    )
    load_id = created.json()["id"]
    patched = client.patch(
        f"/api/loads/{load_id}",
        json={
            "delivery_datetime": "2026-10-14T07:30",
            "delivery_timezone": "America/Los_Angeles",
        },
    )
    assert patched.status_code == 200, patched.text
    instant = _as_utc(patched.json()["delivery_datetime"])
    assert instant == datetime(2026, 10, 14, 14, 30, tzinfo=timezone.utc)

    timezone_only = client.patch(
        f"/api/loads/{load_id}",
        json={"delivery_timezone": "America/Chicago"},
    )
    assert timezone_only.status_code == 200, timezone_only.text
    assert _as_utc(timezone_only.json()["delivery_datetime"]) == instant
    assert timezone_only.json()["delivery_timezone"] == "America/Chicago"


def test_booking_checkin_uses_facility_adjusted_delivery_time(client, db, load_data):
    load, carrier = load_data
    patched = client.patch(
        f"/api/loads/{load.id}",
        json={
            "delivery_state": "MI",
            "delivery_datetime": "2026-10-14T07:30",
        },
    )
    assert patched.status_code == 200, patched.text
    booked = client.post(
        f"/api/loads/{load.id}/book",
        json={
            "carrier_mc": carrier.mc_number,
            "carrier_rate": "1000",
            "customer_rate": "1500",
            "driver_phone": "5551234567",
        },
    )
    assert booked.status_code == 200, booked.text
    dropoff = db.scalar(
        select(ScheduledCheckIn).where(
            ScheduledCheckIn.load_id == load.id,
            ScheduledCheckIn.kind == "dropoff",
        )
    )
    assert _as_utc(dropoff.scheduled_time) == datetime(
        2026, 10, 14, 11, 30, tzinfo=timezone.utc
    )
    assert _as_utc(dropoff.send_at) == datetime(
        2026, 10, 14, 12, 30, tzinfo=timezone.utc
    )
