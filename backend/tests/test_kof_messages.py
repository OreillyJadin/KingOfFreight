from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from sqlalchemy import func, select

from app.config import get_settings
from app.models import Communication, KofLoad, KofMessage, ScheduledCheckIn, utcnow
from app.services.assistant_tools import AssistantTools
from app.services.kof_messages import handle_kof_sms, thread
from tests.test_assistant import block, fake_provider

NUMBER = "+15551234567"


def kof_load(db, number=90123, phone="(555) 123-4567", po="PO-789"):
    load = KofLoad(
        order_no=number,
        po=po,
        carrier_contact_phone=phone,
        carrier_contact_name="Pat",
        dispatch_phone="+15559876543",
        dispatch_contact="Dispatch",
        stage="in_transit",
        origin_city="Wichita",
        origin_state="KS",
        dest_city="Dallas",
        dest_state="TX",
    )
    db.add(load)
    db.commit()
    return load


def outbound(db, load, age=1, status="sent", phone=NUMBER):
    row = KofMessage(
        order_no=load.order_no,
        direction="out",
        to_phone=phone,
        body="Order update?",
        status=status,
        created_at=utcnow() - timedelta(hours=age),
    )
    db.add(row)
    db.commit()
    return row


def test_send_exact_body_and_server_resolved_recipient(client, db, providers):
    load = kof_load(db)
    body = " Order #90123, PO PO-789. Wichita KS to Dallas TX. Update?\nJadin / KOF "
    response = client.post(
        f"/api/kof/loads/{load.order_no}/messages",
        json={
            "recipient": "carrier",
            "body": body,
            "phone": "+19999999999",
        },
    )
    assert response.status_code == 200
    assert response.json()["status"] == "sent"
    assert response.json()["body"] == body
    assert providers["sms"].sent == [(NUMBER, body)]
    row = db.get(KofMessage, response.json()["id"])
    assert row.external_id.startswith("sms-")
    assert load.stage == "in_transit"
    response = client.post(
        f"/api/kof/loads/{load.order_no}/messages",
        json={"recipient": "dispatch", "body": "Dispatch update?"},
    )
    assert response.json()["to_phone"] == "+15559876543"
    messages = client.get(f"/api/kof/loads/{load.order_no}/messages").json()
    assert [item["body"] for item in messages] == [body, "Dispatch update?"]


@pytest.mark.parametrize(
    "value", [None, "", "not a phone", "5551234567 ext 12", "+0123456789"]
)
def test_send_missing_or_invalid_phone(client, db, providers, value):
    load = kof_load(db, phone=value)
    response = client.post(
        f"/api/kof/loads/{load.order_no}/messages",
        json={"recipient": "carrier", "body": "Update?"},
    )
    assert response.status_code == 422
    assert providers["sms"].sent == []
    assert db.scalar(select(func.count(KofMessage.id))) == 0


def test_send_errors_are_persisted_and_no_secrets_leak(client, db, providers):
    load = kof_load(db)
    providers["sms"].send = MagicMock(side_effect=RuntimeError("secret-token"))
    response = client.post(
        f"/api/kof/loads/{load.order_no}/messages",
        json={"recipient": "carrier", "body": "Update?"},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "failed"
    assert "secret-token" not in response.text
    assert (
        db.get(KofMessage, response.json()["id"]).error
        == "SMS send failed (RuntimeError)"
    )


def test_send_validation_and_auth(client, db, providers):
    load = kof_load(db)
    path = f"/api/kof/loads/{load.order_no}/messages"
    for payload in (
        {"recipient": "driver", "body": "Update?"},
        {"recipient": "carrier", "body": " "},
        {"recipient": "carrier", "body": "x" * 1601},
    ):
        assert client.post(path, json=payload).status_code == 422
    assert (
        client.post(
            "/api/kof/loads/999/messages", json={"recipient": "carrier", "body": "Hi"}
        ).status_code
        == 404
    )
    load.is_deleted = True
    db.commit()
    assert (
        client.post(path, json={"recipient": "carrier", "body": "Hi"}).status_code
        == 404
    )
    assert providers["sms"].sent == []
    client.cookies.clear()
    assert client.get(path).status_code == 401
    assert (
        client.post(path, json={"recipient": "carrier", "body": "Hi"}).status_code
        == 401
    )


@pytest.mark.parametrize(
    "body,expected,method",
    [
        ("Order 90123 is loaded", 90123, "explicit_order_or_po"),
        ("PO-789 is loaded", 90123, "explicit_order_or_po"),
        ("Order 90124 delivered", 90124, "explicit_order_or_po"),
        ("Loaded", None, "ambiguous"),
        ("190123 loaded", None, "ambiguous"),
        ("90123 and 90124 loaded", None, "explicit_order_or_po"),
    ],
)
def test_kof_matching_explicit_or_ambiguous(db, providers, body, expected, method):
    first = kof_load(db)
    second = kof_load(db, number=90124, po="OTHER")
    outbound(db, first)
    outbound(db, second)
    handle_kof_sms(db, NUMBER, body, "incoming", providers["llm"], "+15550000000")
    row = db.scalar(select(KofMessage).where(KofMessage.direction == "in"))
    assert row.order_no == expected
    assert row.match_method == method
    assert row.status == ("received" if expected else "ambiguous")
    assert row.candidate_order_nos == ([] if expected else [90123, 90124])
    assert row.parsed_status is not None
    assert row.from_phone == NUMBER
    assert first.stage == "in_transit" and second.stage == "in_transit"
    assert db.scalar(select(func.count(Communication.id))) == 0
    handle_kof_sms(db, NUMBER, body, "incoming", providers["llm"])
    assert (
        db.scalar(select(func.count(KofMessage.id)).where(KofMessage.direction == "in"))
        == 1
    )
    if expected is None:
        assert thread(db, first.order_no)[-1]["status"] == "ambiguous"
        assert thread(db, first.order_no)[-1]["confirmed"] is False


def test_single_candidate_and_expired_failed_excluded(db, providers):
    first = kof_load(db)
    second = kof_load(db, number=90124)
    outbound(db, first)
    outbound(db, second, age=73)
    outbound(db, second, status="failed")
    handle_kof_sms(db, "(555) 123-4567", "Loaded", "reply", providers["llm"])
    row = db.scalar(select(KofMessage).where(KofMessage.direction == "in"))
    assert row.order_no == first.order_no
    assert row.match_method == "single_candidate"


def test_no_candidate_preserves_unmatched_behavior(db, providers):
    first = kof_load(db)
    outbound(db, first, age=73)
    handle_kof_sms(db, NUMBER, "Loaded", "reply", providers["llm"])
    assert db.scalar(select(KofMessage.id).where(KofMessage.direction == "in")) is None
    communication = db.scalar(
        select(Communication).where(Communication.external_id == "reply")
    )
    assert communication.load_id is None
    handle_kof_sms(db, NUMBER, "Loaded", "reply", providers["llm"])
    assert db.scalar(select(func.count(Communication.id))) == 1


@pytest.mark.parametrize("explicit", [True, False])
def test_operational_precedence_unless_explicit_kof(
    client, db, providers, load_data, explicit, monkeypatch
):
    monkeypatch.setattr(get_settings(), "sms_provider", "mock")
    operational, _ = load_data
    operational.driver_phone = NUMBER
    operational.status = "booked"
    checkin = ScheduledCheckIn(
        load_id=operational.id,
        kind="pickup",
        scheduled_time=utcnow(),
        send_at=utcnow(),
        checkin_sent_at=utcnow(),
        checkin_channel="sms",
        driver_contact=NUMBER,
        state="sent",
    )
    db.add(checkin)
    load = kof_load(db)
    outbound(db, load)
    body = "Order 90123 loaded" if explicit else "Loaded"
    response = client.post(
        "/api/webhooks/twilio/sms",
        data={
            "From": NUMBER,
            "To": "+15550000000",
            "Body": body,
            "MessageSid": "incoming",
        },
    )
    assert response.status_code == 200
    db.refresh(checkin)
    assert checkin.state == ("sent" if explicit else "replied")
    assert (
        bool(db.scalar(select(KofMessage.id).where(KofMessage.direction == "in")))
        is explicit
    )
    assert (
        client.post(
            "/api/webhooks/twilio/sms",
            data={"From": NUMBER, "Body": body, "MessageSid": "incoming"},
        ).status_code
        == 200
    )
    assert db.scalar(
        select(func.count(KofMessage.id)).where(KofMessage.direction == "in")
    ) == (1 if explicit else 0)


def test_draft_tool_chat_returns_action_and_sends_nothing(
    client, db, providers, monkeypatch
):
    monkeypatch.setattr(
        "app.routers.assistant.capabilities",
        lambda db: {"sms_live": True, "email_live": False, "assistant_live": True},
    )
    load = kof_load(db)
    body = "Order #90123, PO PO-789, Wichita KS to Dallas TX: update? Jadin / KOF"
    provider = fake_provider(
        monkeypatch,
        [
            SimpleNamespace(
                content=[
                    block(
                        type="tool_use",
                        id="draft1",
                        name="draft_driver_text",
                        input={"order_no": 90123, "recipient": "carrier", "body": body},
                    )
                ]
            ),
            SimpleNamespace(
                content=[
                    block(
                        type="text",
                        text="Please review and tap Send. Nothing has been sent.",
                    )
                ]
            ),
        ],
    )
    response = client.post(
        "/api/assistant/chat",
        json={"messages": [{"role": "user", "content": "Text order 90123"}]},
    )
    assert response.status_code == 200
    assert response.json()["actions"] == [
        {
            "type": "send_kof_text",
            "order_no": 90123,
            "recipient": "carrier",
            "to_label": "Pat · …4567",
            "body": body,
        }
    ]
    assert providers["sms"].sent == []
    assert db.scalar(select(func.count(KofMessage.id))) == 0
    assert "Nothing is sent" in provider.messages.create.call_args.kwargs["system"]
    load.carrier_contact_phone = None
    db.commit()
    assert "error" in AssistantTools(db).draft_driver_text(90123, "carrier", body)
    assert "error" in AssistantTools(db).draft_driver_text(999, "carrier", body)
    assert "error" in AssistantTools(db).draft_driver_text(90123, "dispatch", " ")


def test_status_includes_threads_and_unconfirmed_ambiguous_replies(db, providers):
    first = kof_load(db)
    second = kof_load(db, number=90124)
    outbound(db, first)
    outbound(db, second)
    handle_kof_sms(db, NUMBER, "Delivered", "incoming", providers["llm"])
    messages = AssistantTools(db).get_load_status("kof", 90123)["messages"]
    assert [item["direction"] for item in messages] == ["out", "in"]
    assert messages[-1]["status"] == "ambiguous"
    assert messages[-1]["confirmed"] is False
    assert messages[-1]["parsed_status"] is not None


def test_empty_thread_and_bounded_history(client, db):
    load = kof_load(db)
    assert client.get(f"/api/kof/loads/{load.order_no}/messages").json() == []
    assert client.get("/api/kof/loads/999/messages").status_code == 404
    for i in range(12):
        outbound(db, load, age=12 - i)
    messages = AssistantTools(db).get_load_status("kof", load.order_no)["messages"]
    assert len(messages) == 10
    assert [item["id"] for item in messages] == sorted(item["id"] for item in messages)


def test_parse_failure_preserves_inbound(db, providers):
    load = kof_load(db)
    outbound(db, load)
    providers["llm"].parse_reply = MagicMock(side_effect=RuntimeError("secret-token"))
    handle_kof_sms(db, NUMBER, "I'm here", "incoming", providers["llm"])
    row = db.scalar(select(KofMessage).where(KofMessage.direction == "in"))
    assert row.status == "received"
    assert row.parsed_status is None
    assert row.parsed_summary == "Reply recorded; automatic parsing unavailable"
    assert load.stage == "in_transit"
