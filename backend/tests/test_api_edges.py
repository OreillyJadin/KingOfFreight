import base64
import json
from datetime import datetime, timezone
from decimal import Decimal
from zoneinfo import ZoneInfo

from sqlalchemy import select

from app.config import get_settings
from app.models import BolFile, Communication, Load, ScheduledCheckIn, utcnow


def test_auth_public_routes_and_twilio_signature(client, db, load_data, monkeypatch):
    from fastapi.testclient import TestClient

    from app.auth import COOKIE_NAME
    from app.main import app

    unauthorized = TestClient(app)
    assert unauthorized.get("/api/loads").status_code == 401
    assert unauthorized.get("/api/auth/me").status_code == 401
    assert (
        unauthorized.post("/api/auth/login", json={"password": "wrong"}).status_code
        == 401
    )
    assert (
        unauthorized.post(
            "/api/dev/simulate/sms-reply",
            json={"from": "+15551234567", "body": "loaded"},
        ).status_code
        == 401
    )
    assert (
        unauthorized.post(
            "/api/dev/simulate/inbound-email",
            json={"from": "driver@example.com", "subject": "Update", "body": "loaded"},
        ).status_code
        == 401
    )
    assert unauthorized.post("/api/dev/run-tick").status_code == 401
    load, _ = load_data
    assert unauthorized.get(f"/api/track/{load.tracking_token}").status_code == 200
    monkeypatch.setenv("SMS_PROVIDER", "twilio")
    from app.config import get_settings

    get_settings.cache_clear()
    try:
        response = unauthorized.post(
            "/api/webhooks/twilio/sms", data={"From": "+15551234567", "Body": "yes"}
        )
        assert response.status_code == 403
    finally:
        monkeypatch.delenv("SMS_PROVIDER")
        get_settings.cache_clear()
    assert COOKIE_NAME in client.cookies
    assert client.get("/api/auth/me").json() == {
        "authenticated": True,
        "broker_timezone": get_settings().broker_timezone,
    }
    session_cookie = client.cookies.get(COOKIE_NAME)
    assert session_cookie and "test-password" not in session_cookie
    encoded_payload = session_cookie.split(".", 1)[0]
    decoded_payload = base64.urlsafe_b64decode(
        encoded_payload + "=" * (-len(encoded_payload) % 4)
    )
    assert json.loads(decoded_payload) == {"broker": True}


def test_password_change_invalidates_existing_session(monkeypatch):
    from app.auth import create_session, validate_session
    from app.config import get_settings

    monkeypatch.setenv("BROKER_PASSWORD", "password-a")
    get_settings.cache_clear()
    try:
        session_cookie = create_session()
        assert validate_session(session_cookie)
        monkeypatch.setenv("BROKER_PASSWORD", "password-b")
        get_settings.cache_clear()
        assert not validate_session(session_cookie)
    finally:
        get_settings.cache_clear()


def test_frontend_static_serving_has_spa_fallback_without_shadowing_api(tmp_path):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from app.main import mount_frontend

    dist = tmp_path / "dist"
    assets = dist / "assets"
    assets.mkdir(parents=True)
    index_html = "<!doctype html><title>KingOfFreight</title>"
    (dist / "index.html").write_text(index_html)
    (assets / "app.js").write_text("console.log('frontend')")

    test_app = FastAPI()

    @test_app.get("/api/ping")
    def ping():
        return {"ok": True}

    mount_frontend(test_app, dist)
    client = TestClient(test_app)
    assert client.get("/").text == index_html
    assert client.get("/status").text == index_html
    assert client.get("/assets/app.js").text == "console.log('frontend')"
    assert client.get("/api/ping").json() == {"ok": True}
    assert client.get("/api/not-found").status_code == 404


def test_bol_upload_and_create_load(client, db):
    pdf_content = b"%PDF-1.4 fake content"
    response = client.post(
        "/api/bol/upload",
        files={"file": ("Böl of lading 2026.pdf", pdf_content, "application/pdf")},
    )
    assert response.status_code == 200, response.text
    communication = response.json()
    assert (
        communication["tag"] == "bol"
        and communication["extracted"]["notes"] == "mock extraction"
    )
    assert communication["has_attachment"] is True
    assert communication["attachment_filename"] == "Böl of lading 2026.pdf"
    communication_record = db.get(Communication, communication["id"])
    stored_file = db.get(BolFile, communication_record.attachment_file_id)
    assert stored_file.content == pdf_content
    assert stored_file.size_bytes == len(pdf_content)

    downloaded = client.get(f"/api/files/bol/{communication['id']}")
    assert downloaded.content == pdf_content
    assert downloaded.headers["content-type"] == "application/pdf"
    assert (
        downloaded.headers["content-disposition"]
        == 'inline; filename="B_l_of_lading_2026.pdf"'
    )

    assert (
        client.post(
            "/api/bol/upload",
            files={"file": ("not.pdf", b"not pdf", "application/pdf")},
        ).status_code
        == 400
    )
    created = client.post(f"/api/inbox/{communication['id']}/create-load", json={})
    assert created.status_code == 201, created.text
    assert created.json()["reference"] == "TEST-BOL"
    assert created.json()["pickup_city"] == "Chicago"
    assert db.get(Load, created.json()["id"]).bol_source == communication["id"]
    linked = db.get(Communication, communication["id"])
    assert linked.archived and linked.load_id == created.json()["id"]
    load_detail = client.get(f"/api/loads/{created.json()['id']}")
    assert load_detail.status_code == 200, load_detail.text
    attached_communication = next(
        item
        for item in load_detail.json()["communications"]
        if item["id"] == communication["id"]
    )
    assert attached_communication["has_attachment"] is True
    assert attached_communication["attachment_filename"] == "Böl of lading 2026.pdf"


def test_bol_file_endpoint_returns_404_without_a_file(client, db):
    communication = Communication(
        channel="email",
        direction="inbound",
        content="No attachment",
        tag="other",
    )
    db.add(communication)
    db.commit()

    assert client.get(f"/api/files/bol/{communication.id}").status_code == 404
    assert client.get("/api/files/bol/99999").status_code == 404


def test_email_pdf_ingest_stores_bol_file_in_database(db, providers):
    from app.routers.api import _ingest_email_message

    pdf_content = b"%PDF-1.4 email attachment"
    _ingest_email_message(
        db,
        {
            "from": "shipper@example.com",
            "subject": "Bill of lading",
            "body_text": "Attached",
            "pdf_attachments": [("BOL.pdf", pdf_content)],
        },
        providers["llm"],
    )

    communication = db.scalar(select(Communication).where(Communication.tag == "bol"))
    assert communication is not None
    assert communication.has_attachment
    assert communication.attachment_filename == "BOL.pdf"
    stored_file = db.get(BolFile, communication.attachment_file_id)
    assert stored_file.content == pdf_content
    assert stored_file.size_bytes == len(pdf_content)


def test_send_now_resends_no_reply_checkin_and_clears_alert(
    client, db, load_data, providers
):
    load, _ = load_data
    now = utcnow()
    checkin = ScheduledCheckIn(
        load_id=load.id,
        kind="pickup",
        scheduled_time=now,
        send_at=now,
        checkin_sent_at=now,
        checkin_channel="sms",
        driver_contact="+15551234567",
        state="no_reply",
        alert_raised_at=now,
        alert_dismissed_at=now,
    )
    db.add(checkin)
    db.commit()

    response = client.post(f"/api/checkins/{checkin.id}/send-now")

    assert response.status_code == 200, response.text
    assert response.json()["state"] == "sent"
    assert response.json()["checkin_sent_at"]
    assert response.json()["alert_raised_at"] is None
    assert response.json()["alert_dismissed_at"] is None
    assert providers["sms"].sent == [("+15551234567", response.json()["message_text"])]
    communication = db.scalar(
        select(Communication).where(
            Communication.load_id == load.id,
            Communication.direction == "outbound",
            Communication.tag == "checkin",
        )
    )
    assert communication is not None
    assert communication.content == response.json()["message_text"]


def test_send_now_rejects_replied_and_skipped_checkins(
    client, db, load_data, providers
):
    load, _ = load_data
    now = utcnow()
    checkins = [
        ScheduledCheckIn(
            load_id=load.id,
            kind="pickup",
            scheduled_time=now,
            send_at=now,
            checkin_channel="sms",
            driver_contact="+15551234567",
            state=state,
        )
        for state in ("replied", "skipped")
    ]
    db.add_all(checkins)
    db.commit()

    for checkin in checkins:
        response = client.post(f"/api/checkins/{checkin.id}/send-now")
        assert response.status_code == 409
    assert providers["sms"].sent == []


def test_carrier_verify_prefix_and_post_text(client, db, load_data):
    load, _ = load_data
    response = client.post("/api/carriers/verify", json={"mc_number": "MC-123456"})
    assert response.status_code == 200
    assert response.json()["flag"] == "green"
    text = client.get(f"/api/loads/{load.id}/post-text")
    assert text.status_code == 200 and "Chicago, IL to Des Moines, IA" in text.text
    detail = client.get(f"/api/loads/{load.id}")
    assert detail.status_code == 200 and "latest_location_ping" in detail.json()


def test_customer_messages_only_from_approve(client, db, load_data, providers):
    load, _ = load_data
    client.post(f"/api/loads/{load.id}/status", json={"status": "in_transit"})
    client.post(
        f"/api/loads/{load.id}/status", json={"status": "delayed", "note": "traffic"}
    )
    assert providers["email"].sent == []
    assert providers["sms"].sent == []
    assert db.scalars(select(Load)).first().status == "delayed"


def test_bol_create_load_field_overrides(client):
    uploaded = client.post(
        "/api/bol/upload",
        files={"file": ("bol.pdf", b"%PDF-1.4 fake content", "application/pdf")},
    ).json()
    response = client.post(
        f"/api/inbox/{uploaded['id']}/create-load",
        json={
            "reference": "CUSTOM-REF",
            "pickup_city": "Madison",
            "pickup_datetime": "2025-01-02T09:00:00",
            "weight_lbs": 12345,
            "commodity": "Frozen",
            "customer_name": "Override Customer",
            "customer_rate": "2500",
            "driver_name": "Casey",
        },
    )
    assert response.status_code == 201
    load = response.json()
    assert load["status"] == "new"
    assert load["reference"] == "CUSTOM-REF"
    assert load["pickup_city"] == "Madison"
    expected_pickup = datetime(2025, 1, 2, 9).replace(
        tzinfo=ZoneInfo(get_settings().broker_timezone)
    )
    expected_pickup = expected_pickup.astimezone(timezone.utc).replace(tzinfo=None)
    assert datetime.fromisoformat(load["pickup_datetime"]) == expected_pickup
    assert Decimal(load["weight_lbs"]) == Decimal("12345")
    assert load["commodity"] == "Frozen"
    assert load["customer_name"] == "Override Customer"
    assert Decimal(load["customer_rate"]) == Decimal("2500")
    assert load["driver_name"] == "Casey"
