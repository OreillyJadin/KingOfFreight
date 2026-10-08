from datetime import timedelta

from sqlalchemy import select

from app.integrations.llm import MockLlmProvider
from app.models import (
    Communication,
    Load,
    LocationPing,
    ScheduledCheckIn,
    StatusUpdate,
    utcnow,
)
from app.services.checkins import handle_driver_reply, run_checkin_tick


def test_book_contact_checks_checkins_and_pending_draft(client, db, load_data):
    load, carrier = load_data
    body = {
        "carrier_mc": "MC-123456",
        "carrier_rate": "1200",
        "customer_rate": "1600",
        "driver_name": "Casey",
        "driver_phone": "(555) 123-4567",
    }
    no_contact = {**body}
    no_contact.pop("driver_phone")
    assert client.post(f"/api/loads/{load.id}/book", json=no_contact).status_code == 422
    response = client.post(f"/api/loads/{load.id}/book", json=body)
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "booked"
    checkins = db.scalars(
        select(ScheduledCheckIn).where(ScheduledCheckIn.load_id == load.id)
    ).all()
    assert len(checkins) == 2
    assert all(
        abs((checkin.send_at - checkin.scheduled_time).total_seconds() - 3600) < 1
        for checkin in checkins
    )
    assert {checkin.checkin_channel for checkin in checkins} == {"sms"}
    assert all(checkin.driver_contact == "+15551234567" for checkin in checkins)
    assert load.driver_phone == "+15551234567"
    update = db.scalar(select(StatusUpdate).where(StatusUpdate.load_id == load.id))
    assert (
        update.status == "booked"
        and update.state == "pending_approval"
        and update.applied
    )
    assert not db.scalars(
        select(Communication).where(Communication.direction == "outbound")
    ).all()


def test_book_requires_verified_or_non_red_unless_override(client, db, load_data):
    load, carrier = load_data
    carrier.verified_at = None
    db.commit()
    payload = {
        "carrier_mc": carrier.mc_number,
        "carrier_rate": 900,
        "customer_rate": 1200,
        "driver_email": "d@x.test",
    }
    assert client.post(f"/api/loads/{load.id}/book", json=payload).status_code == 422
    carrier.verified_at = utcnow()
    carrier.flag = "red"
    db.commit()
    assert client.post(f"/api/loads/{load.id}/book", json=payload).status_code == 422
    payload["override_red_flag"] = True
    response = client.post(f"/api/loads/{load.id}/book", json=payload)
    assert response.status_code == 200
    assert "override" in response.json()["notes"].lower()


def test_book_per_load_offset_and_email_channel(client, db, load_data):
    load, _ = load_data
    payload = {
        "carrier_mc": "123456",
        "carrier_rate": "1000",
        "customer_rate": "1500",
        "dispatcher_email": "dispatcher@example.com",
        "checkin_offset_minutes": 25,
        "checkin_channel": "email",
    }
    response = client.post(f"/api/loads/{load.id}/book", json=payload)
    assert response.status_code == 200
    checks = db.scalars(
        select(ScheduledCheckIn).where(ScheduledCheckIn.load_id == load.id)
    ).all()
    assert len(checks) == 2
    assert all(
        (item.send_at - item.scheduled_time).total_seconds() == 25 * 60
        for item in checks
    )
    assert all(
        item.checkin_channel == "email"
        and item.driver_contact == "dispatcher@example.com"
        for item in checks
    )


def test_checkin_tick_due_skip_and_no_reply(client, db, load_data, providers):
    load, _ = load_data
    now = utcnow()
    due = ScheduledCheckIn(
        load_id=load.id,
        kind="pickup",
        scheduled_time=now,
        send_at=now - timedelta(minutes=1),
        checkin_channel="sms",
        driver_contact="+15551234567",
        state="scheduled",
    )
    future = ScheduledCheckIn(
        load_id=load.id,
        kind="dropoff",
        scheduled_time=now,
        send_at=now + timedelta(minutes=10),
        checkin_channel="sms",
        driver_contact="+15551234567",
        state="scheduled",
    )
    db.add_all([due, future])
    db.commit()
    run_checkin_tick(db, now, providers["sms"], providers["email"])
    run_checkin_tick(db, now, providers["sms"], providers["email"])
    assert len(providers["sms"].sent) == 1
    assert due.state == "sent" and future.state == "scheduled"
    run_checkin_tick(
        db, now + timedelta(minutes=31), providers["sms"], providers["email"]
    )
    assert due.state == "no_reply" and due.alert_raised_at is not None
    load.status = "picked_up"
    skipped = ScheduledCheckIn(
        load_id=load.id,
        kind="pickup",
        scheduled_time=now,
        send_at=now - timedelta(minutes=1),
        checkin_channel="sms",
        driver_contact="+15551234567",
        state="scheduled",
    )
    db.add(skipped)
    db.commit()
    run_checkin_tick(db, now + timedelta(hours=1), providers["sms"], providers["email"])
    assert skipped.state == "skipped"


def test_delayed_load_does_not_skip_pickup_checkin(db, load_data, providers):
    load, _ = load_data
    load.status = "delayed"
    now = utcnow()
    checkin = ScheduledCheckIn(
        load_id=load.id,
        kind="pickup",
        scheduled_time=now,
        send_at=now - timedelta(seconds=1),
        checkin_channel="sms",
        driver_contact="+15551234567",
        state="scheduled",
    )
    db.add(checkin)
    db.commit()
    run_checkin_tick(db, now, providers["sms"], providers["email"])
    assert checkin.state == "sent"


def test_checkin_tick_continues_after_sms_failure(db, load_data, providers):
    load, _ = load_data
    now = utcnow()
    failed = ScheduledCheckIn(
        load_id=load.id,
        kind="pickup",
        scheduled_time=now,
        send_at=now - timedelta(minutes=1),
        checkin_channel="sms",
        driver_contact="+15550000001",
        state="scheduled",
    )
    succeeds = ScheduledCheckIn(
        load_id=load.id,
        kind="dropoff",
        scheduled_time=now,
        send_at=now - timedelta(minutes=1),
        checkin_channel="sms",
        driver_contact="+15550000002",
        state="scheduled",
    )
    db.add_all([failed, succeeds])
    db.commit()

    class PartiallyFailingSms:
        def __init__(self):
            self.sent = []

        def send(self, to, body):
            if to == failed.driver_contact:
                raise RuntimeError("simulated Twilio failure")
            self.sent.append(to)
            return "sent"

    sms = PartiallyFailingSms()
    run_checkin_tick(db, now, sms, providers["email"])
    assert failed.state == "scheduled"
    assert succeeds.state == "sent"
    assert sms.sent == [succeeds.driver_contact]


def test_alerts_exclude_checkins_passed_by_current_load_status(client, db, load_data):
    load, _ = load_data
    load.status = "picked_up"
    pickup = ScheduledCheckIn(
        load_id=load.id,
        kind="pickup",
        scheduled_time=utcnow(),
        send_at=utcnow(),
        checkin_channel="sms",
        driver_contact="+15551234567",
        state="no_reply",
        alert_raised_at=utcnow(),
    )
    dropoff = ScheduledCheckIn(
        load_id=load.id,
        kind="dropoff",
        scheduled_time=utcnow(),
        send_at=utcnow(),
        checkin_channel="sms",
        driver_contact="+15551234567",
        state="no_reply",
        alert_raised_at=utcnow(),
    )
    db.add_all([pickup, dropoff])
    db.commit()

    alerts = client.get("/api/alerts").json()
    assert {alert["id"] for alert in alerts} == {dropoff.id}

    load.status = "delivered"
    db.commit()
    assert client.get("/api/alerts").json() == []


def test_reply_matching_approval_and_unmatched(client, db, load_data, providers):
    load, _ = load_data
    load.status = "booked"
    load.driver_phone = "+15551234567"
    checkin = ScheduledCheckIn(
        load_id=load.id,
        kind="pickup",
        scheduled_time=utcnow(),
        send_at=utcnow(),
        checkin_sent_at=utcnow(),
        checkin_channel="sms",
        driver_contact=load.driver_phone,
        state="no_reply",
        alert_raised_at=utcnow(),
    )
    db.add(checkin)
    db.commit()
    handle_driver_reply(
        db, "(555) 123-4567", "Loaded", "sms", "incoming-1", providers["llm"]
    )
    db.refresh(checkin)
    assert checkin.state == "replied" and checkin.alert_dismissed_at is not None
    assert load.status == "booked"
    update = db.scalar(select(StatusUpdate).where(StatusUpdate.load_id == load.id))
    assert update and update.applied is False
    response = client.post(
        f"/api/status-updates/{update.id}/approve",
        json={"body": "Broker reviewed: loaded.", "channel": "email"},
    )
    assert response.status_code == 200, response.text
    assert db.get(Load, load.id).status == "picked_up"
    assert providers["email"].sent == [
        (
            "customer@example.com",
            update.customer_message_subject,
            "Broker reviewed: loaded.",
        )
    ]
    logged = db.scalar(
        select(Communication).where(Communication.tag == "customer_update")
    )
    assert logged and logged.direction == "outbound"
    handle_driver_reply(
        db, "unmatched@example.com", "hello", "email", "incoming-2", providers["llm"]
    )
    unmatched = db.scalar(
        select(Communication).where(Communication.external_id == "incoming-2")
    )
    assert unmatched.load_id is None and unmatched.tag == "other"


def test_unclear_reply_is_alert_not_status_update(client, db, load_data, providers):
    load, _ = load_data
    providers["llm"].status = "unclear"
    load.driver_email = "driver@example.com"
    checkin = ScheduledCheckIn(
        load_id=load.id,
        kind="pickup",
        scheduled_time=utcnow(),
        send_at=utcnow(),
        checkin_sent_at=utcnow(),
        checkin_channel="email",
        driver_contact=load.driver_email,
        state="sent",
    )
    db.add(checkin)
    db.commit()
    handle_driver_reply(
        db, "DRIVER@example.com", "Call me", "email", llm=providers["llm"]
    )
    assert not db.scalars(
        select(StatusUpdate).where(StatusUpdate.load_id == load.id)
    ).all()
    assert checkin.alert_dismissed_at is None
    assert client.get("/api/alerts").json()[0]["id"] == checkin.id


def test_manual_status_templates_and_replaces_pending_without_sending(
    client, db, load_data, providers
):
    load, _ = load_data
    response = client.post(f"/api/loads/{load.id}/status", json={"status": "picked_up"})
    assert response.status_code == 200
    no_eta = response.json()["customer_message_preview"]
    assert "Current ETA" not in no_eta
    assert "Hi Alex," in no_eta
    response = client.post(
        f"/api/loads/{load.id}/status",
        json={"status": "picked_up", "eta": "2025-10-09T15:00:00-05:00"},
    )
    assert "Current ETA:" in response.json()["customer_message_preview"]
    delayed = client.post(
        f"/api/loads/{load.id}/status", json={"status": "delayed", "note": ""}
    ).json()
    assert "behind. I'll send" in delayed["customer_message_preview"]
    assert "  " not in delayed["customer_message_preview"]
    updates = db.scalars(
        select(StatusUpdate).where(StatusUpdate.load_id == load.id)
    ).all()
    assert [update.state for update in updates].count("pending_approval") == 1
    assert not providers["email"].sent and not providers["sms"].sent


def test_tracking_public_rate_limit_and_internal_only(client, db, load_data, providers):
    load, _ = load_data
    assert client.get("/api/track/bad").status_code == 404
    view = client.get(f"/api/track/{load.tracking_token}")
    assert view.status_code == 200
    assert (
        "customer_email" not in view.text
        and "rate" not in view.text
        and "customer_phone" not in view.text
    )
    first = client.post(
        f"/api/track/{load.tracking_token}/ping", json={"lat": 41, "lng": -93}
    )
    second = client.post(
        f"/api/track/{load.tracking_token}/ping", json={"lat": 42, "lng": -94}
    )
    assert first.json() == {"stored": True}
    assert second.json() == {"stored": False}
    assert len(db.scalars(select(LocationPing)).all()) == 1
    assert not db.scalars(select(StatusUpdate)).all()
    assert not providers["email"].sent and not providers["sms"].sent


def test_mock_reply_marks_attention_independently_of_status():
    llm = MockLlmProvider()
    breakdown = llm.parse_reply("Truck breakdown", {"kind": "pickup"})
    assert breakdown.status == "delayed" and breakdown.needs_broker_attention
    call_me = llm.parse_reply("Call me", {"kind": "pickup"})
    assert call_me.status == "unclear" and call_me.needs_broker_attention
