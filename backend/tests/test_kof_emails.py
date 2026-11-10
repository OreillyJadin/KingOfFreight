import pytest
from sqlalchemy import select

from app.integrations.llm import MockLlmProvider
from app.models import Communication, CustomerUpdateDraft, utcnow
from app.routers.api import _ingest_email_message
from app.services.assistant_tools import AssistantTools
from tests.test_kof_messages import kof_load


def test_send_and_reply(client, db, providers):
    load = kof_load(db)
    load.carrier_contact_email = "carrier@example.com"
    load.raw = {"Dispatch Email": "dispatch@example.com"}
    db.commit()
    payload = {
        "recipient": "dispatch",
        "subject": "Status?",
        "body": " Exact preview\nBroker ",
    }
    result = client.post("/api/kof/loads/90123/emails", json=payload)
    assert result.status_code == 200
    subject = result.json()["subject"]
    assert subject == "Order #90123 — Status?"
    assert providers["email"].sent == [
        ("dispatch@example.com", subject, payload["body"])
    ]
    _ingest_email_message(
        db,
        {
            "from": "dispatch@example.com",
            "subject": f"RE: {subject}",
            "body_text": "Driver loaded, will deliver tomorrow",
            "external_id": "reply-1",
            "received_at": utcnow(),
            "pdf_attachments": [],
        },
        MockLlmProvider(),
    )
    inbound = db.scalar(
        select(Communication).where(Communication.external_id == "reply-1")
    )
    assert inbound.kof_order_no == 90123
    assert db.scalar(select(CustomerUpdateDraft)).order_no == 90123
    assert len(client.get("/api/kof/loads/90123/emails").json()) == 2
    assert len(AssistantTools(db).get_load_status("kof", 90123)["emails"]) == 2


def test_draft_and_template_send_nothing(client, db, providers):
    load = kof_load(db)
    load.carrier_contact_email = "pat@example.com"
    db.commit()
    service = AssistantTools(db)
    result = service.draft_dispatcher_email(
        90123, "carrier", "Order #90123 update", "Status and ETA?"
    )
    assert result["sent"] is False
    assert service.actions[0]["to_label"] == "Pat · p…@example.com"
    assert (
        client.get("/api/kof/loads/90123/emails/draft").json()["type"]
        == "send_kof_email"
    )
    assert not providers["email"].sent
    assert not db.scalar(select(Communication))


@pytest.mark.parametrize("address", [None, "invalid", "a@example.com,b@example.com"])
def test_missing_recipient(client, db, providers, address):
    load = kof_load(db)
    load.carrier_contact_email = address
    db.commit()
    result = client.post(
        "/api/kof/loads/90123/emails",
        json={"recipient": "dispatch", "subject": "Update", "body": "Please update"},
    )
    assert result.status_code == 422
    assert "No dispatcher email" in result.json()["detail"]
    assert not providers["email"].sent


def test_auth_and_invalid(client, db, providers):
    kof_load(db)
    for payload in [
        {"recipient": "other", "subject": "X", "body": "X"},
        {"recipient": "carrier", "subject": "X\nBcc: x@y.com", "body": "X"},
        {"recipient": "carrier", "subject": "X", "body": " "},
    ]:
        assert (
            client.post("/api/kof/loads/90123/emails", json=payload).status_code == 422
        )
    client.cookies.clear()
    assert client.get("/api/kof/loads/90123/emails").status_code == 401
    assert (
        client.post(
            "/api/kof/loads/90123/emails",
            json={"recipient": "dispatch", "subject": "X", "body": "X"},
        ).status_code
        == 401
    )


def test_empty_thread_and_delivery_error(client, db, providers, monkeypatch):
    load = kof_load(db)
    load.carrier_contact_email = "pat@example.com"
    db.commit()
    assert client.get("/api/kof/loads/90123/emails").json() == []

    def fail(*args):
        raise RuntimeError("private provider detail")

    monkeypatch.setattr(providers["email"], "send", fail)
    response = client.post(
        "/api/kof/loads/90123/emails",
        json={
            "recipient": "carrier",
            "subject": "Order #90123 update",
            "body": "Status and ETA?",
        },
    )
    assert response.status_code == 502
    assert "private" not in response.text
    assert not db.scalar(select(Communication))
