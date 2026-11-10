from types import SimpleNamespace

import pytest
from sqlalchemy import func, select

from app.config import Settings, get_settings
from app.integrations.email import MockEmailProvider, get_email_provider
from app.integrations.sms import MockSmsProvider, get_sms_provider
from app.main import app
from app.models import (
    Communication,
    KofMessage,
    OutlookConnection,
    ScheduledCheckIn,
    utcnow,
)
from app.routers.assistant import available_tools
from app.services.capabilities import capabilities
from app.services.checkins import run_checkin_tick
from tests.test_assistant import block, fake_provider
from tests.test_customer_updates import ingest
from tests.test_kof_messages import kof_load


@pytest.mark.parametrize("env", ["production", "development"])
def test_mock_send_safety(client, db, load_data, monkeypatch, env):
    monkeypatch.setattr(get_settings(), "env", env)
    app.dependency_overrides[get_sms_provider] = lambda: MockSmsProvider()
    app.dependency_overrides[get_email_provider] = lambda: MockEmailProvider()
    load = kof_load(db)
    load.carrier_contact_email = "dispatch@example.com"
    draft = ingest(db)
    draft.to_email = "customer@example.com"
    operational, _ = load_data
    checkin = ScheduledCheckIn(
        load_id=operational.id,
        kind="pickup",
        scheduled_time=utcnow(),
        driver_contact="+15551234567",
        checkin_channel="sms",
        send_at=utcnow(),
        state="scheduled",
    )
    db.add(checkin)
    db.commit()
    before = db.scalar(select(func.count(Communication.id)))
    requests = [
        (
            "/api/kof/loads/90123/messages",
            {"recipient": "carrier", "body": "Update?"},
            "Texting",
        ),
        (
            "/api/kof/loads/90123/emails",
            {"recipient": "dispatch", "subject": "Update", "body": "Update?"},
            "Email",
        ),
        (
            f"/api/customer-updates/{draft.id}/approve",
            {"version": draft.version},
            "Email",
        ),
        (f"/api/checkins/{checkin.id}/send-now", {}, "Texting"),
    ]
    for path, payload, label in requests:
        result = client.post(path, json=payload)
        assert result.status_code == (409 if env == "production" else 200), result.text
        if env == "production":
            assert result.json()["detail"] == f"{label} isn't connected yet"
    db.refresh(draft)
    db.refresh(checkin)
    if env == "production":
        assert draft.state == "pending" and draft.send_started_at is None
        assert checkin.state == "scheduled" and checkin.checkin_sent_at is None
        assert db.scalar(select(func.count(Communication.id))) == before
        assert not db.scalar(select(KofMessage))
    else:
        assert draft.state == "sent" and checkin.state == "sent"


@pytest.mark.parametrize(
    "email,sms", [(False, False), (True, False), (False, True), (True, True)]
)
def test_assistant_tool_and_prompt_gating(client, db, monkeypatch, email, sms):
    caps = {"email_live": email, "sms_live": sms, "assistant_live": True}
    monkeypatch.setattr("app.routers.assistant.capabilities", lambda db: caps)
    names = {tool["name"] for tool in available_tools(caps)}
    assert ("draft_driver_text" in names) == sms
    assert ("draft_dispatcher_email" in names) == email
    assert ("list_pending_customer_updates" in names) == email
    provider = fake_provider(
        monkeypatch,
        [
            SimpleNamespace(
                content=[
                    block(
                        type="tool_use",
                        id="blocked",
                        name="draft_dispatcher_email",
                        input={
                            "order_no": 90123,
                            "recipient": "dispatch",
                            "subject": "Update",
                            "body": "Update?",
                        },
                    )
                ]
            ),
            SimpleNamespace(content=[block(type="text", text="Check KOF notes.")]),
        ],
    )
    response = client.post(
        "/api/assistant/chat",
        json={"messages": [{"role": "user", "content": "Contact carrier"}]},
    )
    assert response.status_code == 200
    args = provider.messages.create.call_args.kwargs
    assert {tool["name"] for tool in args["tools"]} == names
    assert ("draft_driver_text" in args["system"]) == sms
    assert ("draft_dispatcher_email" in args["system"]) == email
    if not email and not sms:
        assert "cannot contact carriers or customers yet" in args["system"]
        assert response.json()["actions"] == []


def test_email_capabilities(db, monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "email_provider", "auto")
    for field in (
        "graph_tenant_id",
        "graph_client_id",
        "graph_client_secret",
        "graph_mailbox",
    ):
        monkeypatch.setattr(settings, field, None)
    assert not capabilities(db)["email_live"]
    account = OutlookConnection(
        id=1,
        email="broker@example.com",
        name="Broker",
        token_encrypted="encrypted",
        needs_reconnect=False,
    )
    db.add(account)
    db.commit()
    assert capabilities(db)["email_live"]
    account.needs_reconnect = True
    db.commit()
    assert not capabilities(db)["email_live"]
    for field in (
        "graph_tenant_id",
        "graph_client_id",
        "graph_client_secret",
        "graph_mailbox",
    ):
        monkeypatch.setattr(settings, field, "configured")
    assert capabilities(db)["email_live"]
    monkeypatch.setattr(settings, "email_provider", "mock")
    assert not capabilities(db)["email_live"]


def test_app_env_alias(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("SECRET_KEY", "test-production-secret-at-least-32-characters")
    assert Settings(_env_file=None).env == "production"


@pytest.mark.parametrize("channel", ["sms", "email"])
def test_tick_skips_disconnected_channel_once_per_tick(
    db, load_data, providers, monkeypatch, caplog, channel
):
    monkeypatch.setattr(get_settings(), "env", "production")
    monkeypatch.setattr(
        "app.services.checkins.capabilities",
        lambda db: {"sms_live": channel != "sms", "email_live": channel != "email"},
    )
    load, _ = load_data
    rows = [
        ScheduledCheckIn(
            load_id=load.id,
            kind="pickup",
            scheduled_time=utcnow(),
            send_at=utcnow(),
            driver_contact="+15551234567" if channel == "sms" else "driver@example.com",
            checkin_channel=channel,
            state="scheduled",
        )
        for _ in range(2)
    ]
    db.add_all(rows)
    db.commit()
    run_checkin_tick(db, sms=providers["sms"], email=providers["email"])
    assert not providers["sms"].sent and not providers["email"].sent
    assert not db.scalar(select(Communication))
    for row in rows:
        db.refresh(row)
        assert row.state == "scheduled" and row.checkin_sent_at is None
    records = [
        record for record in caplog.records if record.name == "app.services.checkins"
    ]
    assert len(records) == 1
    assert (
        records[0].getMessage()
        == "Skipped 2 scheduled check-ins: channel not connected"
    )
    assert records[0].exc_info is None
