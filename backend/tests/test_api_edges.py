import base64
import json

from sqlalchemy import select

from app.models import Communication, Load


def test_auth_public_routes_and_twilio_signature(client, db, load_data, monkeypatch):
    from fastapi.testclient import TestClient

    from app.auth import COOKIE_NAME
    from app.main import app

    unauthorized = TestClient(app)
    assert unauthorized.get("/api/loads").status_code == 401
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
    response = client.post(
        "/api/bol/upload",
        files={"file": ("bol.pdf", b"%PDF-1.4 fake content", "application/pdf")},
    )
    assert response.status_code == 200, response.text
    communication = response.json()
    assert (
        communication["tag"] == "bol"
        and communication["extracted"]["notes"] == "mock extraction"
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
    linked = db.get(Communication, communication["id"])
    assert linked.archived and linked.load_id == created.json()["id"]


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
        json={"reference": "CUSTOM-REF", "customer_name": "Override Customer"},
    )
    assert response.status_code == 201
    assert response.json()["reference"] == "CUSTOM-REF"
    assert response.json()["customer_name"] == "Override Customer"
