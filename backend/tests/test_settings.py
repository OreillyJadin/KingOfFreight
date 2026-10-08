from datetime import timedelta

import pytest

from app.models import BrokerSettings, ScheduledCheckIn, utcnow
from app.services.checkins import run_checkin_tick
from app.services.templates import render_checkin


def test_settings_default_partial_update_and_reset(client):
    defaults = client.get("/api/settings").json()
    assert defaults["checkin_offset_minutes"] == 60
    assert defaults["broker_timezone"] == "America/Chicago"
    updated = client.put(
        "/api/settings",
        json={"broker_company": "  North Freight  ", "checkin_offset_minutes": 45},
    )
    assert updated.status_code == 200
    assert updated.json()["broker_company"] == "North Freight"
    assert updated.json()["checkin_offset_minutes"] == 45
    assert client.get("/api/settings").json() == updated.json()
    reset = client.put("/api/settings", json={"broker_company": None})
    assert reset.json()["broker_company"] == defaults["broker_company"]
    assert reset.json()["checkin_offset_minutes"] == 45


@pytest.mark.parametrize(
    "payload",
    [
        {"broker_timezone": "Not/A_Zone"},
        {"checkin_offset_minutes": 721},
        {"no_reply_alert_minutes": 241},
        {"checkin_default_channel": "call"},
        {"broker_name": " "},
    ],
)
def test_settings_reject_invalid_values(client, payload):
    assert client.put("/api/settings", json=payload).status_code == 422


def test_settings_require_auth():
    from fastapi.testclient import TestClient

    from app.main import app

    client = TestClient(app)
    assert client.get("/api/settings").status_code == 401


def test_auth_me_uses_database_timezone(client):
    response = client.put("/api/settings", json={"broker_timezone": "America/New_York"})
    assert response.status_code == 200
    assert client.get("/api/auth/me").json()["broker_timezone"] == "America/New_York"


def test_booking_uses_database_checkin_offset(client, db, load_data):
    load, _ = load_data
    assert (
        client.put("/api/settings", json={"checkin_offset_minutes": 45}).status_code
        == 200
    )
    response = client.post(
        f"/api/loads/{load.id}/book",
        json={
            "carrier_mc": "123456",
            "carrier_rate": 1000,
            "customer_rate": 1500,
            "driver_phone": "+15551234567",
        },
    )
    assert response.status_code == 200, response.text
    checkins = (
        db.query(ScheduledCheckIn).filter(ScheduledCheckIn.load_id == load.id).all()
    )
    assert len(checkins) == 2
    assert all(
        (item.send_at - item.scheduled_time).total_seconds() == 45 * 60
        for item in checkins
    )


def test_no_reply_tick_uses_database_alert_window(db, load_data, providers):
    load, _ = load_data
    now = utcnow()
    db.add(BrokerSettings(id=1, no_reply_alert_minutes=15))
    first = ScheduledCheckIn(
        load_id=load.id,
        kind="pickup",
        scheduled_time=now,
        send_at=now,
        checkin_sent_at=now - timedelta(minutes=20),
        checkin_channel="sms",
        driver_contact="+15551234567",
        state="sent",
    )
    db.add(first)
    db.commit()
    run_checkin_tick(db, now, providers["sms"], providers["email"])
    assert first.state == "no_reply"
    db.get(BrokerSettings, 1).no_reply_alert_minutes = 30
    second = ScheduledCheckIn(
        load_id=load.id,
        kind="dropoff",
        scheduled_time=now,
        send_at=now,
        checkin_sent_at=now - timedelta(minutes=20),
        checkin_channel="sms",
        driver_contact="+15551234567",
        state="sent",
    )
    db.add(second)
    db.commit()
    run_checkin_tick(db, now, providers["sms"], providers["email"])
    assert second.state == "sent"


def test_checkin_template_uses_database_company(db, load_data):
    load, _ = load_data
    db.add(BrokerSettings(id=1, broker_company="North Freight"))
    db.commit()
    assert "North Freight" in render_checkin(load, "pickup")
