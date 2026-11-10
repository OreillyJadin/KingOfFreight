from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock

import anthropic
import httpx
import pytest
from sqlalchemy import func, select

from app.integrations.llm import (
    AnthropicLlmProvider,
    FallbackLlmProvider,
    MockLlmProvider,
)
from app.models import (
    Communication,
    CustomerContact,
    CustomerUpdateDraft,
    KofCustomer,
    KofLoad,
    KofMessage,
    utcnow,
)
from app.routers.api import _ingest_email_message
from app.services.assistant_tools import AssistantTools
from app.services.customer_updates import detect_update, recipient
from app.services.kof_messages import handle_kof_sms
from tests.test_kof_messages import kof_load, outbound, NUMBER


def ingest(
    db,
    text="Driver did get reloaded, will deliver first thing tomorrow",
    external="mail-1",
    received=None,
    llm=None,
):
    _ingest_email_message(
        db,
        {
            "from": "carrier@example.com",
            "subject": "Order #90123",
            "body_text": text,
            "external_id": external,
            "received_at": received or utcnow(),
            "pdf_attachments": [],
        },
        llm or MockLlmProvider(),
    )
    return db.scalar(
        select(CustomerUpdateDraft).where(CustomerUpdateDraft.state == "pending")
    )


@pytest.mark.parametrize(
    "text,status",
    [
        ("Driver loaded", "loaded"),
        ("Picked up", "picked_up"),
        ("En route", "in_transit"),
        ("Traffic delay", "delayed"),
        ("Delivered", "delivered"),
        ("not loaded", "delayed"),
    ],
)
def test_mock_classifies_updates(text, status):
    result = MockLlmProvider().classify_carrier_update(text)
    assert result.is_update and result.status == status
    assert 0 <= result.confidence <= 1


@pytest.mark.parametrize(
    "text",
    [
        "",
        "Thanks for the invoice",
        "Is the driver loaded?",
        "Any update?\nOn Monday wrote:\nDriver loaded",
    ],
)
def test_mock_ignores_empty_unrelated_and_questions(text):
    assert not MockLlmProvider().classify_carrier_update(text).is_update


def test_mock_eta_and_negation():
    provider = MockLlmProvider()
    assert (
        provider.classify_carrier_update(
            "Reloaded, delivering first thing tomorrow"
        ).eta
        == "first thing tomorrow"
    )
    assert (
        provider.classify_carrier_update("Driver didn't get loaded").status == "delayed"
    )


def test_anthropic_forced_tool_and_fallback():
    client = MagicMock()
    client.messages.create.return_value = SimpleNamespace(
        content=[
            SimpleNamespace(
                type="tool_use",
                name="record_carrier_update",
                input={
                    "is_update": True,
                    "status": "loaded",
                    "eta": "tomorrow morning",
                    "summary": "Reloaded",
                    "confidence": 0.9,
                },
            )
        ]
    )
    provider = AnthropicLlmProvider(client)
    assert provider.classify_carrier_update("Reloaded").eta == "tomorrow morning"
    assert client.messages.create.call_args.kwargs["tool_choice"] == {
        "type": "tool",
        "name": "record_carrier_update",
    }
    client.messages.create.return_value = SimpleNamespace(content=[])
    assert (
        FallbackLlmProvider(provider).classify_carrier_update("Driver loaded").is_update
    )
    provider.classify_carrier_update = MagicMock(
        side_effect=ValueError("invalid response")
    )
    assert (
        FallbackLlmProvider(provider).classify_carrier_update("Driver delivered").status
        == "delivered"
    )
    provider.classify_carrier_update = MagicMock(
        side_effect=anthropic.APIConnectionError(
            request=httpx.Request("POST", "https://api.anthropic.com")
        )
    )
    assert (
        FallbackLlmProvider(provider).classify_carrier_update("En route").status
        == "in_transit"
    )


def test_email_creates_draft_time_lane_signature_no_send(client, db, providers):
    load = kof_load(db)
    when = utcnow() - timedelta(hours=2)
    row = ingest(db, received=when)
    assert row.order_no == load.order_no and row.to_email == ""
    assert row.subject == "Update on Order #90123 (PO PO-789)"
    assert "Wichita, KS → Dallas, TX" in row.body
    assert "tomorrow" in row.body and "carrier reported at" in row.body
    assert row.source_refs[0]["received_at"] == when.isoformat()
    assert row.source_refs[0]["channel"] == "email"
    assert providers["email"].sent == []
    assert client.get("/api/customer-updates").json()["count"] == 1
    ingest(db)
    assert db.scalar(select(func.count(CustomerUpdateDraft.id))) == 1


def test_sms_match_creates_draft_ambiguous_does_not(db):
    load = kof_load(db)
    outbound(db, load)
    handle_kof_sms(db, NUMBER, "Order 90123 loaded", "sms-1", MockLlmProvider())
    row = db.scalar(select(CustomerUpdateDraft))
    assert row.source_refs[0]["channel"] == "sms"
    assert db.get(KofMessage, row.source_refs[0]["id"]).status == "received"
    other = kof_load(db, number=90124, po="OTHER")
    outbound(db, other)
    handle_kof_sms(db, NUMBER, "delivered", "sms-2", MockLlmProvider())
    assert db.scalar(select(func.count(CustomerUpdateDraft.id))) == 1


def test_refresh_keeps_edited_to_and_rejects_stale_approval(client, db):
    kof_load(db)
    row = ingest(db)
    old_version = row.version
    response = client.patch(
        f"/api/customer-updates/{row.id}",
        json={
            "version": row.version,
            "to_email": "chosen@example.com",
            "subject": "Edited",
            "body": "Edited body",
        },
    )
    assert response.status_code == 200
    ingest(db, "Driver delayed by traffic", "mail-2", utcnow() + timedelta(minutes=1))
    db.refresh(row)
    assert row.to_email == "chosen@example.com"
    assert "traffic" in row.body and row.status == "delayed"
    assert len(row.source_refs) == 2
    assert db.scalar(select(func.count(CustomerUpdateDraft.id))) == 1
    assert (
        client.post(
            f"/api/customer-updates/{row.id}/approve", json={"version": old_version}
        ).status_code
        == 409
    )
    assert (
        client.patch(
            f"/api/customer-updates/{row.id}",
            json={
                "version": old_version,
                "to_email": "stale@example.com",
                "subject": "Old",
                "body": "Old",
            },
        ).status_code
        == 409
    )


def test_recipient_discovery_and_approved_contact_remembered(client, db, providers):
    load = kof_load(db)
    load.customer = "Customer Co"
    load.shipper_email = "warehouse@example.com"
    load.consignee_email = "receiver@example.com"
    load.raw = {"Customer Email": "load-contact@example.com"}
    db.add(
        KofCustomer(
            customer_key="cust-1",
            name="Customer Co",
            raw={"Email": "directory@example.com"},
        )
    )
    db.commit()
    assert recipient(db, load) == "load-contact@example.com"
    load.raw = {}
    db.commit()
    assert recipient(db, load) == "directory@example.com"
    row = ingest(db)
    edited = client.patch(
        f"/api/customer-updates/{row.id}",
        json={
            "version": row.version,
            "to_email": "approved@example.com",
            "subject": " Exact subject ",
            "body": " Exact body\nwith newline ",
        },
    ).json()
    url = f"/api/customer-updates/{row.id}/approve"
    approved = client.post(url, json={"version": edited["version"]})
    assert approved.status_code == 200 and approved.json()["state"] == "sent"
    assert client.post(url, json={"version": edited["version"]}).status_code == 200
    assert providers["email"].sent == [
        ("approved@example.com", " Exact subject ", " Exact body\nwith newline ")
    ]
    communication = db.scalar(
        select(Communication).where(Communication.direction == "outbound")
    )
    assert (
        communication.kof_order_no == 90123
        and communication.content == " Exact body\nwith newline "
    )
    assert db.get(CustomerContact, "kof:cust-1").email == "approved@example.com"
    new = ingest(db, "Delivered", "new-mail")
    assert new.to_email == "approved@example.com" and new.id != row.id


def test_blank_and_invalid_email_dismiss_empty_queue_auth(client, db):
    kof_load(db)
    assert client.get("/api/customer-updates").json()["count"] == 0
    row = ingest(db)
    assert (
        client.post(
            f"/api/customer-updates/{row.id}/approve", json={"version": row.version}
        ).status_code
        == 422
    )
    assert (
        client.patch(
            f"/api/customer-updates/{row.id}",
            json={
                "version": row.version,
                "to_email": "a@example.com,b@example.com",
                "subject": "x",
                "body": "x",
            },
        ).status_code
        == 422
    )
    response = client.post(
        f"/api/customer-updates/{row.id}/dismiss", json={"version": row.version}
    )
    assert response.status_code == 200 and response.json()["state"] == "dismissed"
    assert client.get("/api/customer-updates").json()["count"] == 0
    client.cookies.clear()
    assert client.get("/api/customer-updates").status_code == 401
    for method, path, body in [
        (
            "PATCH",
            f"/{row.id}",
            {"version": 1, "to_email": "", "subject": "x", "body": "x"},
        ),
        ("POST", f"/{row.id}/approve", {"version": 1}),
        ("POST", f"/{row.id}/dismiss", {"version": 1}),
    ]:
        assert (
            client.request(
                method, "/api/customer-updates" + path, json=body
            ).status_code
            == 401
        )


def test_ingestion_survives_classifier_failure_and_unrelated_mail(db, caplog):
    kof_load(db)
    llm = MockLlmProvider()
    llm.classify_carrier_update = MagicMock(
        side_effect=RuntimeError("secret-do-not-log")
    )
    assert ingest(db, llm=llm) is None
    assert db.scalar(select(func.count(Communication.id))) == 1
    assert "secret-do-not-log" not in caplog.text
    assert ingest(db, "Invoice attached", "non-update") is None
    load = db.get(KofLoad, 90123)
    outbound(db, load)
    handle_kof_sms(db, NUMBER, "loaded", "sms-fail", llm)
    assert db.scalar(select(KofMessage).where(KofMessage.external_id == "sms-fail"))


def test_failure_is_not_retried_and_new_updates_survive_inflight(client, db, providers):
    kof_load(db)
    row = ingest(db)
    row.to_email = "customer@example.com"
    db.commit()

    def send(*args):
        ingest(db, "Driver delivered", "during-send", utcnow() + timedelta(minutes=1))
        return "sent-during-update"

    providers["email"].send = MagicMock(side_effect=send)
    response = client.post(
        f"/api/customer-updates/{row.id}/approve", json={"version": row.version}
    )
    assert response.status_code == 200
    next_draft = db.scalar(
        select(CustomerUpdateDraft).where(CustomerUpdateDraft.state == "pending")
    )
    assert next_draft.id != row.id and next_draft.status == "delivered"
    next_draft.to_email = "customer@example.com"
    db.commit()
    providers["email"].send = MagicMock(side_effect=RuntimeError("secret"))
    response = client.post(
        f"/api/customer-updates/{next_draft.id}/approve",
        json={"version": next_draft.version},
    )
    assert response.status_code == 502 and "secret" not in response.text
    assert (
        client.post(
            f"/api/customer-updates/{next_draft.id}/approve",
            json={"version": next_draft.version},
        ).status_code
        == 409
    )
    assert providers["email"].send.call_count == 1


def test_assistant_queue_and_order_evidence(db):
    kof_load(db)
    ingest(db)
    service = AssistantTools(db)
    result = service.list_pending_customer_updates()
    assert result["count"] == 1 and result["queue_url"] == "/customer-updates"
    assert (
        service.get_load_status("kof", 90123)["pending_customer_update"]["order_no"]
        == 90123
    )


def test_older_update_does_not_replace_newest(db):
    kof_load(db)
    row = ingest(db, "Driver delivered")
    detect_update(
        db,
        90123,
        "sms",
        99,
        "Driver loaded",
        utcnow() - timedelta(hours=1),
        MockLlmProvider(),
    )
    db.refresh(row)
    assert row.status == "delivered" and len(row.source_refs) == 2
