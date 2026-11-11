import os
import sqlite3
import subprocess
import sys
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import delete, select

from app import main
from app.models import (
    CustomerUpdateDraft,
    KofLoad,
    ScheduledCheckIn,
    TeamMember,
    UsageEvent,
    UsageMinute,
)
from app.services import usage, usage_analytics
from tests.test_admin import add_user, sign_in_as
from tests.test_assistant import block, fake_provider
from tests.test_customer_updates import ingest
from tests.test_kof_messages import kof_load

SECTIONS = (
    "people",
    "pages",
    "heatmap",
    "feed",
    "kof_output",
    "response_speed",
    "features",
    "leaderboard",
)
NOW = datetime(2026, 11, 9, 18, tzinfo=timezone.utc)


@pytest.fixture
def clock(monkeypatch):
    monkeypatch.setattr(usage, "utcnow", lambda: NOW)
    monkeypatch.setattr(usage_analytics, "utcnow", lambda: NOW)
    monkeypatch.setattr("app.services.usage_report.utcnow", lambda: NOW)


def minute(db, when, who="Tony", user=None, path="/loads", **kwargs):
    row = UsageMinute(
        identity=who,
        minute=when,
        path=path,
        user_id=user.id if user else None,
        username=user.username if user else None,
        operator_name=who,
        device="mobile",
        **kwargs,
    )
    db.add(row)
    return row


def event(db, name, when=NOW, who="Tony", user=None, **kwargs):
    row = UsageEvent(
        event=name,
        created_at=when,
        operator_name=who,
        user_id=user.id if user else None,
        username=user.username if user else None,
        device="mobile",
        **kwargs,
    )
    db.add(row)
    return row


def report(client, section, **params):
    response = client.get(
        f"/api/admin/usage/{section}",
        params={"period": "day", "date": "2026-11-09", **params},
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_heartbeat_idempotent_server_identity_and_last_path(client, db, clock):
    user = add_user(db)
    sign_in_as(client, user)
    member = TeamMember(name="Tony")
    db.add(member)
    db.commit()
    client.post("/api/auth/operator", json={"team_member_id": member.id})
    payload = {
        "path": "/loads/123?customer=private",
        "identity": "forged",
        "device": "desktop",
    }
    for _ in range(2):
        result = client.post(
            "/api/usage/heartbeat",
            json=payload,
            headers={"user-agent": "iPhone Mobile"},
        )
        assert result.status_code == 202 and result.json() == {"accepted": True}
    rows = db.scalars(select(UsageMinute)).all()
    assert len(rows) == 1
    row = rows[0]
    assert (
        row.identity,
        row.operator_name,
        row.user_id,
        row.username,
        row.team_member_id,
        row.path,
        row.device,
    ) == ("Tony", "Tony", user.id, user.username, member.id, "/loads", "mobile")
    assert row.minute.replace(tzinfo=timezone.utc) == NOW.replace(
        second=0, microsecond=0
    )
    other = add_user(db, username="Other")
    sign_in_as(client, other)
    client.post("/api/auth/operator", json={"team_member_id": member.id})
    client.post("/api/usage/heartbeat", json={"path": "/status/99"})
    db.expire_all()
    rows = db.scalars(select(UsageMinute)).all()
    assert len(rows) == 1 and rows[0].path == "/status" and rows[0].user_id == other.id
    client.post("/api/auth/operator", json={"team_member_id": None})
    client.post("/api/usage/heartbeat", json={"path": "/dashboard"})
    assert {r.identity for r in db.scalars(select(UsageMinute))} == {"Tony", "Other"}


@pytest.mark.parametrize(
    "payload",
    [
        None,
        [],
        {},
        {"path": 2},
        {"path": "//host/loads"},
        {"path": "/bad"},
        {"path": "/loads", "extra": "x" * 5000},
    ],
)
def test_bad_heartbeat_is_ignored(client, db, payload):
    response = client.post("/api/usage/heartbeat", json=payload)
    assert response.status_code == 202 and response.json() == {"accepted": False}
    assert not db.scalars(select(UsageMinute)).all()


def test_heartbeat_failure_auth_and_legacy(client, db, monkeypatch):
    assert client.post("/api/usage/heartbeat", json={"path": "/loads"}).json()[
        "accepted"
    ]
    assert db.scalar(select(UsageMinute)).identity == "shared login"
    assert client.post("/api/usage/heartbeat", content="{").json() == {
        "accepted": False
    }

    def unavailable():
        raise RuntimeError("storage unavailable")

    monkeypatch.setattr(usage, "SessionLocal", unavailable)
    assert client.post("/api/usage/heartbeat", json={"path": "/loads"}).json() == {
        "accepted": False
    }
    client.cookies.clear()
    assert (
        client.post("/api/usage/heartbeat", json={"path": "/loads"}).status_code == 401
    )


@pytest.mark.parametrize("section", SECTIONS)
def test_admin_only_and_empty_shapes(client, db, admin_login, section, clock):
    data = report(client, section)
    assert data["timezone"] == "America/Chicago" and data["exclude_admins"] is True
    assert data["start"] == "2026-11-09T00:00:00-06:00"
    assert data["end_exclusive"] == "2026-11-10T00:00:00-06:00"
    sign_in_as(client, add_user(db))
    assert client.get(f"/api/admin/usage/{section}").status_code == 403
    client.cookies.clear()
    assert client.get(f"/api/admin/usage/{section}").status_code == 401


def test_people_sessions_days_streak_and_identity(client, db, admin_login, clock):
    db.execute(delete(UsageEvent))
    base = datetime(2026, 11, 9, 16, tzinfo=timezone.utc)
    for offset in (0, 30, 61):
        minute(db, base + timedelta(minutes=offset))
    minute(db, base - timedelta(days=1))
    event(db, "page_view", base - timedelta(minutes=1), path="/loads")
    event(db, "load_created", base)
    event(db, "assistant_question", base)
    event(db, "assistant_question_submitted", base)
    db.commit()
    who = report(client, "people")["people"][0]
    assert who == {
        "identity": "Tony",
        "active_minutes": 3,
        "sessions": 2,
        "first_activity": "2026-11-09T09:59:00-06:00",
        "last_activity": "2026-11-09T11:01:00-06:00",
        "avg_session_minutes": 16,
        "days_active": 1,
        "current_streak": 2,
        "actions": 2,
        "action_counts": {"load_created": 1, "assistant_question": 1},
        "chat_questions": 1,
    }
    assert report(client, "pages")["pages"] == [
        {"identity": "Tony", "path": "/loads", "active_minutes": 3}
    ]
    event(db, "page_view", who=None, path="/settings")
    event(
        db, "page_view", who=None, user=add_user(db, username="Named"), path="/settings"
    )
    db.commit()
    assert {p["identity"] for p in report(client, "people")["people"]} == {
        "Tony",
        "Named",
        "shared login",
    }


def test_heatmap_dst_week_month_boundaries(client, db, admin_login, clock):
    minute(db, datetime(2026, 11, 1, 6, 30, tzinfo=timezone.utc))
    minute(db, datetime(2026, 11, 1, 7, 30, tzinfo=timezone.utc))
    minute(db, datetime(2026, 11, 2, 6, tzinfo=timezone.utc))
    db.commit()
    data = report(client, "heatmap", date="2026-11-01")
    assert data["start"] == "2026-11-01T00:00:00-05:00"
    assert data["end_exclusive"] == "2026-11-02T00:00:00-06:00"
    assert data["cells"] == [
        {"identity": "Tony", "weekday": 6, "hour": 1, "active_minutes": 2}
    ]
    assert data["total"] == [{"weekday": 6, "hour": 1, "active_minutes": 2}]
    week = report(client, "pages", period="week", date="2026-11-01")
    assert week["start"].startswith("2026-10-26") and week["end_exclusive"].startswith(
        "2026-11-02"
    )
    assert sum(p["active_minutes"] for p in week["pages"]) == 2
    month = report(client, "pages", period="month", date="2026-11-30")
    assert month["start"].startswith("2026-11-01") and month[
        "end_exclusive"
    ].startswith("2026-12-01")
    assert sum(p["active_minutes"] for p in month["pages"]) == 3


def test_feed_pagination_summaries_and_features_zero(client, db, admin_login, clock):
    db.execute(delete(UsageEvent))
    event(db, "customer_update_approve", detail={"order_no": 3425326})
    event(db, "page_view", path="/loads")
    event(db, "load_created", who="Kolby", detail={"load_id": 7, "reference": "BOL-7"})
    db.commit()
    feed = report(client, "feed", identity="Tony", limit=1)
    assert feed["total"] == 2 and feed["has_more"] is True
    assert feed["items"][0]["summary"] == "Viewed /loads"
    second = report(client, "feed", identity="Tony", offset=1, limit=1)
    assert second["items"][0]["summary"] == "Approved customer update for order 3425326"
    assert second["has_more"] is False
    assert report(client, "feed", identity="missing")["items"] == []
    features = {r["feature"]: r for r in report(client, "features")["features"]}
    assert features["kof_email_send"] == {
        "feature": "kof_email_send",
        "label": "Sent KOF email",
        "uses": 0,
        "distinct_people": 0,
        "last_used": None,
    }
    assert (
        features["customer_update_approve"]["uses"]
        == features["customer_update_approve"]["distinct_people"]
        == 1
    )


def test_kof_grouping_profit_matching_and_exclusions(client, db, admin_login, clock):
    for index, (booker, rep, price, cost, profit) in enumerate(
        [
            ("tony", "Rep A", 1000, 700, 300),
            ("Tony", "Rep A", 2000, 1000, 1000),
            (None, "Rep B", 0, 100, -100),
            (admin_login.username, "Rep B", 5000, 1000, 4000),
        ]
    ):
        db.add(
            KofLoad(
                order_no=index + 1,
                booker=booker,
                rep=rep,
                date_of_sale=date(2026, 11, 9),
                price=Decimal(price),
                cost=Decimal(cost),
                profit=Decimal(profit),
            )
        )
    db.add_all(
        [
            KofLoad(
                order_no=10, booker="Tony", date_of_sale=date(2026, 11, 8), profit=999
            ),
            KofLoad(
                order_no=11,
                booker="Tony",
                date_of_sale=date(2026, 11, 9),
                profit=999,
                is_deleted=True,
            ),
            KofLoad(order_no=12, booker="Tony", date_of_sale=None, profit=999),
        ]
    )
    minute(db, NOW)
    minute(db, NOW, who="Kolby")
    event(db, "load_created")
    db.commit()
    data = report(client, "kof_output")
    assert sum(r["loads"] for r in data["booker"]) == 3
    assert next(r for r in data["booker"] if r["name"] is None)["margin_pct"] is None
    rep = next(r for r in data["rep"] if r["name"] == "Rep A")
    assert rep == {
        "name": "Rep A",
        "loads": 2,
        "revenue": 3000,
        "carrier_cost": 1700,
        "profit": 1300,
        "margin_pct": 43.33,
    }
    assert (
        sum(
            r["loads"]
            for r in report(client, "kof_output", exclude_admins="false")["booker"]
        )
        == 4
    )
    people = {r["identity"]: r for r in report(client, "leaderboard")["people"]}
    assert (
        people["Tony"]["kof_profit"] == 1300 and people["Tony"]["kof_profit_rank"] == 1
    )
    assert people["Kolby"]["kof_profit"] is people["Kolby"]["kof_profit_rank"] is None
    assert people["Tony"]["actions_rank"] == 1


def test_exclude_admins_even_when_using_operator(client, db, admin_login, clock):
    db.execute(delete(UsageEvent))
    event(db, "assistant_question", user=admin_login, who="Admin operator")
    minute(db, NOW, user=admin_login, who="Admin operator")
    event(db, "assistant_question", who="Tony")
    minute(db, NOW)
    db.commit()
    for section, key in [
        ("people", "people"),
        ("pages", "pages"),
        ("heatmap", "cells"),
        ("feed", "items"),
        ("leaderboard", "people"),
    ]:
        assert {row["identity"] for row in report(client, section)[key]} == {"Tony"}
        assert {
            row["identity"]
            for row in report(client, section, exclude_admins="false")[key]
        } == {"Tony", "Admin operator"}
    assert (
        next(
            r
            for r in report(client, "features")["features"]
            if r["feature"] == "assistant_question"
        )["uses"]
        == 1
    )
    assert (
        next(
            r
            for r in report(client, "features", exclude_admins="false")["features"]
            if r["feature"] == "assistant_question"
        )["uses"]
        == 2
    )
    assert client.get("/api/admin/usage").json()["totals"]["chat_questions"] == 1
    assert (
        client.get("/api/admin/usage?exclude_admins=false").json()["totals"][
            "chat_questions"
        ]
        == 2
    )


def test_response_speed_source_fallback_and_approver(client, db, admin_login, clock):
    db.execute(delete(UsageEvent))
    db.add(KofLoad(order_no=1))
    for index, (seconds, sources) in enumerate(
        [
            (600, [{"received_at": (NOW - timedelta(seconds=600)).isoformat()}]),
            (1200, []),
            (2400, []),
        ]
    ):
        draft = CustomerUpdateDraft(
            order_no=1,
            summary="Status",
            status="loaded",
            confidence=1,
            subject="Update",
            body="Update",
            state="sent",
            source_refs=sources,
            created_at=NOW - timedelta(seconds=30 if sources else seconds),
            sent_at=NOW,
        )
        db.add(draft)
        db.flush()
        event(
            db,
            "customer_update_approve",
            user=admin_login if index == 2 else None,
            who="Owner" if index == 2 else "Tony",
            detail={"draft_id": draft.id},
        )
    event(db, "customer_update_approve", detail={})
    db.commit()
    data = report(client, "response_speed")
    assert data["people"] == [
        {"identity": "Tony", "count": 2, "median_seconds": 900, "avg_seconds": 900}
    ]
    assert data["unlinked_approval_events"] == 1
    assert len(report(client, "response_speed", exclude_admins="false")["people"]) == 2


def test_retention_and_migration(client, db, clock, monkeypatch, tmp_path):
    minute(db, NOW - timedelta(days=180, minutes=1), who="old")
    minute(db, NOW - timedelta(days=180), who="boundary")
    db.commit()
    monkeypatch.setattr(main, "run_checkin_tick", lambda db: None)
    main._run_tick()
    assert [row.identity for row in db.scalars(select(UsageMinute))] == ["boundary"]
    database = tmp_path / "minutes.db"
    env = dict(os.environ, DATABASE_URL=f"sqlite+pysqlite:///{database}")
    backend = Path(__file__).resolve().parents[1]
    for args in [
        ("upgrade", "head"),
        ("downgrade", "b81e0d6f3295"),
        ("upgrade", "head"),
    ]:
        subprocess.run(
            [sys.executable, "-m", "alembic", *args],
            cwd=backend,
            env=env,
            capture_output=True,
            check=True,
        )
    with sqlite3.connect(database) as conn:
        assert (
            conn.execute("SELECT version_num FROM alembic_version").fetchone()[0]
            == "d03af21982bc"
        )
        conn.execute(
            "INSERT INTO usage_minutes(identity,minute,path,device) VALUES ('Tony','2026-11-09 18:00:00','/loads','mobile')"
        )
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO usage_minutes(identity,minute,path,device) VALUES ('Tony','2026-11-09 18:00:00','/status','desktop')"
            )


def test_missing_feature_events_have_references(client, db, providers, load_data):
    user = add_user(db)
    sign_in_as(client, user)
    created = client.post("/api/loads", json={"reference": "REF-123"})
    assert created.status_code == 201
    load_id = created.json()["id"]
    assert (
        client.patch(f"/api/loads/{load_id}", json={"notes": "edited"}).status_code
        == 200
    )
    assert client.post(f"/api/loads/{load_id}/post").status_code == 200
    assert client.get(f"/api/loads/{load_id}/post-text").status_code == 200
    assert (
        client.post(
            f"/api/loads/{load_id}/status", json={"status": "picked_up"}
        ).status_code
        == 200
    )
    records = {
        row.event: row
        for row in db.scalars(select(UsageEvent).where(UsageEvent.user_id == user.id))
    }
    for name in (
        "load_created",
        "load_edited",
        "load_status_changed",
        "truckstop_post",
        "truckstop_post_text",
    ):
        assert records[name].detail["load_id"] == load_id
        assert records[name].detail["reference"] == "REF-123"
    load, _ = load_data
    checkin = ScheduledCheckIn(
        load_id=load.id,
        kind="pickup",
        scheduled_time=NOW,
        send_at=NOW,
        checkin_channel="sms",
        driver_contact="+15550001111",
    )
    db.add(checkin)
    db.commit()
    assert client.post(f"/api/checkins/{checkin.id}/send-now").status_code == 200
    checkin_event = db.scalar(
        select(UsageEvent).where(UsageEvent.event == "checkin_manual_send")
    )
    assert (
        checkin_event.user_id == user.id and checkin_event.detail["load_id"] == load.id
    )
    kof_load(db)
    draft = ingest(db)
    draft.to_email = "customer@example.com"
    db.commit()
    assert (
        client.post(
            f"/api/customer-updates/{draft.id}/approve", json={"version": draft.version}
        ).status_code
        == 200
    )
    approval = db.scalar(
        select(UsageEvent).where(UsageEvent.event == "customer_update_approve")
    )
    assert (
        approval.detail["draft_id"] == draft.id
        and approval.detail["order_no"] == draft.order_no
    )


def test_assistant_draft_events_without_send(client, db, monkeypatch):
    kof_load(db)
    monkeypatch.setattr(
        "app.routers.assistant.capabilities",
        lambda db: {"sms_live": True, "email_live": True, "assistant_live": True},
    )
    fake_provider(
        monkeypatch,
        [
            type(
                "Response",
                (),
                {
                    "content": [
                        block(
                            type="tool_use",
                            id="t1",
                            name="draft_driver_text",
                            input={
                                "order_no": 90123,
                                "recipient": "carrier",
                                "body": "Status?",
                            },
                        )
                    ]
                },
            )(),
            type(
                "Response", (), {"content": [block(type="text", text="Review draft.")]}
            )(),
        ],
    )
    response = client.post(
        "/api/assistant/chat",
        json={"messages": [{"role": "user", "content": "Text the carrier"}]},
    )
    assert response.status_code == 200
    assert (
        db.scalar(
            select(UsageEvent).where(UsageEvent.event == "kof_text_draft")
        ).detail["order_no"]
        == 90123
    )
    assert not db.scalar(select(UsageEvent).where(UsageEvent.event == "kof_text_send"))


@pytest.mark.parametrize(
    "query",
    ["period=year", "date=bad", "date=9999-12-31&period=month", "limit=0", "offset=-1"],
)
def test_invalid_report_inputs(client, admin_login, query):
    assert client.get(f"/api/admin/usage/feed?{query}").status_code == 422
