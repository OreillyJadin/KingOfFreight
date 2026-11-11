from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from sqlalchemy import delete, select

from app import main
from app.models import KofConnection, UsageEvent, utcnow
from app.services import usage
from app.services.kof_credentials import encrypt_kof_password
from tests.test_admin import add_user, sign_in_as
from tests.test_assistant import block, fake_provider
from tests.test_customer_updates import ingest
from tests.test_kof_messages import kof_load


def rows(db, event=None):
    query = select(UsageEvent).order_by(UsageEvent.id)
    if event:
        query = query.where(UsageEvent.event == event)
    return list(db.scalars(query))


def test_record_attribution_normalization_and_dedup(client, db):
    member = add_user(db)
    sign_in_as(client, member)
    headers = {"user-agent": "Mozilla iPhone Mobile"}
    body = {
        "event": "page_view",
        "path": "/loads/12345?po=private#notes",
        "user_id": 999,
        "username": "spoof",
        "device": "desktop",
        "detail": {"secret": "do not store"},
    }
    assert client.post("/api/usage/events", json=body, headers=headers).json() == {
        "accepted": True
    }
    assert client.post("/api/usage/events", json=body, headers=headers).json() == {
        "accepted": False
    }
    event = rows(db, "page_view")[0]
    assert (event.user_id, event.username, event.path, event.device, event.detail) == (
        member.id,
        member.username,
        "/loads",
        "mobile",
        None,
    )
    event.created_at = utcnow() - timedelta(seconds=6)
    db.commit()
    assert (
        client.post("/api/usage/events", json=body, headers=headers).json()["accepted"]
        is True
    )
    assert len(rows(db, "page_view")) == 2


def test_legacy_attribution_is_null(client, db):
    assert (
        client.post(
            "/api/usage/events",
            json={"event": "assistant_opened", "path": "/dashboard"},
        ).status_code
        == 202
    )
    event = rows(db, "assistant_opened")[0]
    assert event.user_id is None and event.username is None
    client.cookies.clear()
    assert (
        client.post(
            "/api/usage/events", json={"event": "page_view", "path": "/loads"}
        ).status_code
        == 401
    )


@pytest.mark.parametrize(
    "body",
    [
        None,
        [],
        1,
        "bad",
        {},
        {"event": []},
        {"event": "assistant_question", "path": "/loads"},
        {"event": "page_view", "path": 123},
        {"event": "page_view", "path": "https://example.com/loads"},
        {"event": "page_view", "path": "/unknown/123"},
        {"event": "page_view", "path": "//example.com/loads"},
        {"event": "page_view", "path": "/loads", "extra": "x" * 5000},
    ],
)
def test_bad_event_input_is_ignored_without_failing(client, db, body):
    response = client.post("/api/usage/events", json=body)
    assert response.status_code == 202 and response.json() == {"accepted": False}
    assert not rows(db, "page_view")


def test_malformed_json_and_storage_failure_never_break_requests(
    client, db, monkeypatch, caplog
):
    assert (
        client.post(
            "/api/usage/events",
            content="{",
            headers={"Content-Type": "application/json"},
        ).status_code
        == 202
    )

    def unavailable():
        raise RuntimeError("analytics storage unavailable")

    monkeypatch.setattr(usage, "SessionLocal", unavailable)
    response = client.post(
        "/api/usage/events", json={"event": "page_view", "path": "/loads"}
    )
    assert response.status_code == 202 and response.json() == {"accepted": False}
    assert (
        client.post("/api/auth/login", json={"password": "test-password"}).status_code
        == 200
    )
    assert client.get("/api/loads").status_code == 200
    assert "Usage event recording failed" in caplog.text


@pytest.mark.parametrize(
    "ua,expected",
    [
        ("iPhone Mobile", "mobile"),
        ("Android Mobile", "mobile"),
        ("iPad", "tablet"),
        ("Android 13", "tablet"),
        ("Macintosh Mobile", "tablet"),
        ("Windows NT", "desktop"),
        ("", "desktop"),
    ],
)
def test_device_classification(ua, expected):
    assert usage.device_type(ua) == expected


def test_admin_usage_permissions_and_empty_result(client, db):
    sign_in_as(client, add_user(db))
    assert client.get("/api/admin/usage").status_code == 403


def test_empty_usage_and_range_validation(client, db, admin_login):
    db.execute(delete(UsageEvent))
    db.commit()
    result = client.get("/api/admin/usage?days=7")
    assert result.status_code == 200
    data = result.json()
    assert data["totals"] == {
        "events": 0,
        "active_users": 0,
        "chat_questions": 0,
        "page_views": 0,
    }
    assert len(data["daily"]) == 7 and all(
        day["active_users"] == 0 for day in data["daily"]
    )
    assert (
        data["users"]
        == data["questions"]
        == data["top_pages"]
        == data["top_features"]
        == []
    )
    assert data["devices"] == {}
    assert client.get("/api/admin/usage?days=30").json()["days"] == 30
    assert client.get("/api/admin/usage?days=90").json()["days"] == 90
    assert client.get("/api/admin/usage?days=invalid").status_code == 422


def test_aggregation_timezone_boundaries_and_shared_bucket(
    client, db, admin_login, monkeypatch
):
    member = add_user(db)
    db.execute(delete(UsageEvent))
    now = datetime(2026, 11, 10, 2, tzinfo=timezone.utc)
    monkeypatch.setattr("app.services.usage_report.utcnow", lambda: now)
    start = datetime(2026, 11, 3, 6, tzinfo=timezone.utc)

    def event(who, name, when, path=None, device="mobile", detail=None):
        db.add(
            UsageEvent(
                user_id=who.id if who else None,
                username=who.username if who else None,
                event=name,
                path=path,
                device=device,
                created_at=when,
                detail=detail,
            )
        )

    event(member, "page_view", start, "/loads")
    event(member, "page_view", datetime(2026, 11, 9, 1, tzinfo=timezone.utc), "/loads")
    event(
        member,
        "assistant_question",
        datetime(2026, 11, 9, 2, tzinfo=timezone.utc),
        detail={"question": "Did the order load?", "tools": ["get_load_status"]},
    )
    event(None, "page_view", now - timedelta(hours=1), "/settings", "tablet")
    event(admin_login, "suggestion_clicked", now, device="desktop")
    event(member, "page_view", start - timedelta(seconds=1), "/inbox")
    event(member, "page_view", now + timedelta(seconds=1), "/inbox")
    db.commit()
    data = client.get("/api/admin/usage?days=7&exclude_admins=false").json()
    assert data["timezone"] == "America/Chicago"
    assert data["totals"] == {
        "events": 5,
        "active_users": 3,
        "chat_questions": 1,
        "page_views": 3,
    }
    assert data["devices"] == {"mobile": 3, "tablet": 1, "desktop": 1}
    assert data["top_pages"] == [
        {"name": "/loads", "count": 2},
        {"name": "/settings", "count": 1},
    ]
    by_user = next(user for user in data["users"] if user["user_id"] == member.id)
    assert (by_user["page_views"], by_user["questions"], by_user["top_page"]) == (
        2,
        1,
        "/loads",
    )
    assert by_user["devices"] == {"mobile": 3}
    assert any(user["label"] == "shared login" for user in data["users"])
    by_day = {day["date"]: day for day in data["daily"]}
    assert by_day["2026-11-08"]["questions"] == 1
    assert by_day["2026-11-09"]["active_users"] == 2
    assert data["questions"][0]["time"] == "2026-11-08T20:00:00-06:00"
    assert data["questions"][0]["text"] == "Did the order load?"


def test_recent_questions_limited_to_50(client, db, admin_login):
    now = utcnow()
    for index in range(60):
        db.add(
            UsageEvent(
                user_id=admin_login.id,
                username=admin_login.username,
                event="assistant_question",
                device="desktop",
                detail={"question": str(index)},
                created_at=now - timedelta(minutes=60 - index),
            )
        )
    db.commit()
    data = client.get("/api/admin/usage?exclude_admins=false").json()
    assert data["totals"]["chat_questions"] == 60
    assert len(data["questions"]) == 50
    assert data["questions"][0]["text"] == "59"
    assert data["questions"][-1]["text"] == "10"


def test_chat_records_one_question_and_tool_names(client, db, monkeypatch):
    user = add_user(db)
    sign_in_as(client, user)
    fake_provider(
        monkeypatch,
        [
            SimpleNamespace(
                content=[
                    block(
                        type="tool_use",
                        id="t1",
                        name="search_loads",
                        input={"query": "123"},
                    )
                ]
            ),
            SimpleNamespace(content=[block(type="text", text="No load found.")]),
        ],
    )
    question = "x" * 400
    response = client.post(
        "/api/assistant/chat",
        json={
            "messages": [
                {"role": "user", "content": "Earlier question"},
                {"role": "assistant", "content": "Earlier answer"},
                {"role": "user", "content": question},
            ]
        },
    )
    assert response.status_code == 200
    event = rows(db, "assistant_question")[0]
    assert (event.user_id, event.username) == (user.id, user.username)
    assert event.detail == {
        "question": "x" * 300,
        "tools": ["search_loads"],
        "status_code": 200,
    }
    assert len(rows(db, "assistant_question")) == 1


def test_failed_chat_question_still_counted(client, db):
    assert (
        client.post(
            "/api/assistant/chat",
            json={"messages": [{"role": "user", "content": "A question"}]},
        ).status_code
        == 503
    )
    assert rows(db, "assistant_question")[0].detail["status_code"] == 503


def test_login_bol_send_and_idempotent_approval_events(client, db, providers):
    assert rows(db, "login_success")[0].username is None
    load = kof_load(db)
    load.carrier_contact_email = "carrier@example.com"
    db.commit()
    assert (
        client.post(
            "/api/bol/upload",
            files={"file": ("fixture.pdf", b"%PDF fixture", "application/pdf")},
        ).status_code
        == 200
    )
    assert len(rows(db, "bol_upload_extract")) == 1
    assert (
        client.post(
            "/api/kof/loads/90123/emails",
            json={"recipient": "carrier", "subject": "Update", "body": "Status?"},
        ).status_code
        == 200
    )
    assert len(rows(db, "kof_email_send")) == 1
    assert (
        client.post(
            "/api/kof/loads/90123/messages",
            json={"recipient": "carrier", "body": "Status?"},
        ).json()["status"]
        == "sent"
    )
    assert len(rows(db, "kof_text_send")) == 1
    draft = ingest(db)
    draft.to_email = "customer@example.com"
    db.commit()
    body = {"version": draft.version}
    assert (
        client.post(f"/api/customer-updates/{draft.id}/approve", json=body).status_code
        == 200
    )
    assert (
        client.post(f"/api/customer-updates/{draft.id}/approve", json=body).status_code
        == 200
    )
    assert len(rows(db, "customer_update_approve")) == 1


def test_pruning_cutoff_and_scheduler_hook(client, db, monkeypatch):
    now = utcnow()
    monkeypatch.setattr(usage, "utcnow", lambda: now)
    db.add_all(
        [
            UsageEvent(
                event="old",
                device="desktop",
                created_at=now - timedelta(days=180, seconds=1),
            ),
            UsageEvent(
                event="boundary", device="desktop", created_at=now - timedelta(days=180)
            ),
        ]
    )
    db.commit()
    monkeypatch.setattr(main, "run_checkin_tick", lambda db: None)
    main._run_tick()
    assert not rows(db, "old") and len(rows(db, "boundary")) == 1


def test_sync_dismiss_and_operational_feature_events(
    client, db, monkeypatch, load_data
):
    db.add(
        KofConnection(
            id=1,
            username="fixture",
            password_encrypted=encrypt_kof_password("fixture-password"),
        )
    )
    db.commit()
    monkeypatch.setattr("app.routers.kof.start_sync", lambda kind: 1)
    assert client.post("/api/kof/sync?kind=full").status_code == 202
    assert rows(db, "kof_manual_sync")[0].detail["kind"] == "full"
    kof_load(db)
    draft = ingest(db)
    body = {"version": draft.version}
    assert (
        client.post(f"/api/customer-updates/{draft.id}/dismiss", json=body).status_code
        == 200
    )
    assert (
        client.post(f"/api/customer-updates/{draft.id}/dismiss", json=body).status_code
        == 200
    )
    assert len(rows(db, "customer_update_dismiss")) == 1
    load, _ = load_data
    load.driver_phone = "+15550001111"
    db.commit()
    assert client.post(f"/api/loads/{load.id}/send-tracking-link").status_code == 200
    assert rows(db, "operational_send")[0].detail["action"] == "tracking_link"


def test_pruning_failure_is_swallowed(monkeypatch, caplog):
    def unavailable():
        raise RuntimeError("storage unavailable")

    monkeypatch.setattr(usage, "SessionLocal", unavailable)
    usage.prune_usage_events()
    assert "Usage event pruning failed" in caplog.text
