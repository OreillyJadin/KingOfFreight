import asyncio
from datetime import date, timedelta
from types import SimpleNamespace

import pytest
from fastapi import Request
from sqlalchemy import select, delete
from starlette.responses import Response

from app import main
from app.integrations.llm import FallbackLlmProvider
from app.models import (
    CustomerUpdateDraft,
    KofLoad,
    KofMessage,
    KofSyncRun,
    RequestMetric,
    TeamMember,
    UsageDaily,
    UsageEvent,
)
from app.services import usage, usage_analytics, usage_health
from tests.test_admin import add_user, sign_in_as
from tests.test_usage_analytics import NOW, event, minute

SECTIONS = (
    "contributions",
    "timeline",
    "trend",
    "live",
    "flows",
    "users_overview",
    "health",
)


@pytest.fixture(autouse=True)
def clock(monkeypatch):
    monkeypatch.setattr(usage, "utcnow", lambda: NOW)
    monkeypatch.setattr(usage_analytics, "utcnow", lambda: NOW)
    monkeypatch.setattr(usage_health, "utcnow", lambda: NOW)
    usage_health._sessions.clear()


def report(client, section, **params):
    result = client.get(
        f"/api/admin/usage/{section}",
        params={"period": "day", "date": "2026-11-09", **params},
    )
    assert result.status_code == 200, result.text
    return result.json()


@pytest.fixture(autouse=True)
def clean_initial_login(client, db):
    db.execute(delete(UsageEvent))
    db.commit()


@pytest.mark.parametrize("section", SECTIONS)
def test_admin_only_and_empty(client, db, section):
    assert client.get(f"/api/admin/usage/{section}").status_code == 403
    admin = add_user(db, role="admin")
    sign_in_as(client, admin)
    data = report(client, section)
    assert data["timezone"] == "America/Chicago" and data["exclude_admins"] is True
    assert data.get("people", data.get("transitions", [])) == []


def test_contributions_dense_history_streaks_archive_and_exclusion(
    client, db, admin_login
):
    minute(db, NOW)
    minute(db, NOW - timedelta(days=1))
    event(db, "load_created", NOW - timedelta(days=2))
    for day in range(5, 9):
        event(db, "assistant_question", NOW - timedelta(days=day))
    event(db, "load_created", user=admin_login, who="Owner")
    minute(db, NOW - timedelta(days=200))
    minute(db, NOW - timedelta(days=200, minutes=1))
    event(db, "load_edited", NOW - timedelta(days=200))
    db.commit()
    usage.prune_usage_events()
    usage.prune_usage_events()
    db.expire_all()
    old = db.scalars(select(UsageDaily)).all()
    assert sum(row.active_minutes for row in old) == 2
    assert sum(row.actions for row in old) == 1
    person = report(client, "contributions")["people"][0]
    assert person["identity"] == "Tony"
    assert len(person["days"]) == 365
    assert person["current_streak"] == 3 and person["longest_streak"] == 4
    assert sum(day["active_minutes"] for day in person["days"]) == 4
    assert len(report(client, "contributions", exclude_admins=False)["people"]) == 2
    assert report(client, "feed", period="day", date="2026-11-07")["total"] == 1


def test_timeline_merges_five_minute_gaps_and_day_timezone(client, db, admin_login):
    for delta in (0, 1, 6, 12):
        minute(db, NOW + timedelta(minutes=delta) - timedelta(hours=1))
    minute(db, NOW - timedelta(hours=13), who="previous-local-day")
    event(db, "customer_update_approve", detail={"order_no": 123})
    db.commit()
    data = report(client, "timeline", period="month")
    assert data["period"] == "day"
    person = data["people"][0]
    assert person["identity"] == "Tony"
    assert [span["active_minutes"] for span in person["spans"]] == [3, 1]
    assert person["actions"][0]["summary"] == "Approved customer update for order 123"
    assert person["spans"][0]["start"].endswith("-06:00")


def test_live_precise_heartbeat_and_last_action(client, db, admin_login):
    minute(
        db,
        NOW - timedelta(minutes=2, seconds=30),
        last_seen_at=NOW - timedelta(seconds=110),
        path="/tracking",
    )
    minute(
        db,
        NOW - timedelta(minutes=3),
        who="idle",
        last_seen_at=NOW - timedelta(seconds=121),
    )
    minute(db, NOW, who="Owner", user=admin_login, last_seen_at=NOW)
    event(db, "load_edited", NOW - timedelta(days=1), detail={"reference": "BOL-1"})
    event(db, "page_view", NOW, path="/loads")
    db.commit()
    rows = report(client, "live")["people"]
    assert len(rows) == 1 and rows[0]["path"] == "/tracking"
    assert (
        rows[0]["device"] == "mobile"
        and rows[0]["last_action"]["event"] == "load_edited"
    )
    assert len(report(client, "live", exclude_admins=False)["people"]) == 2


def test_flows_identity_and_strict_gap(client, db, admin_login):
    base = NOW - timedelta(hours=2)
    for who in ("Tony", "Kolby"):
        event(db, "page_view", base, who=who, path="/loads")
        event(db, "page_view", base + timedelta(minutes=1), who=who, path="/tracking")
        event(db, "page_view", base + timedelta(minutes=31), who=who, path="/status")
    db.commit()
    assert report(client, "flows")["transitions"] == [
        {"from": "/loads", "to": "/tracking", "count": 2}
    ]


def test_trend_categories_weekly_adoption_devices_kof_and_speed(
    client, db, admin_login
):
    minute(db, NOW)
    event(db, "bol_upload_extract")
    event(db, "checkin_manual_send")
    event(db, "customer_update_approve")
    event(db, "assistant_question")
    event(db, "load_edited")
    event(db, "kof_text_send")
    event(db, "kof_manual_sync")
    event(db, "llm_error")
    event(db, "load_edited", who="Owner", user=admin_login)
    db.add(
        KofLoad(
            order_no=1,
            booker="Tony",
            rep="Rep A",
            date_of_sale=date(2026, 11, 9),
            profit=120,
        )
    )
    db.flush()
    draft = CustomerUpdateDraft(
        order_no=1,
        summary="Status",
        status="loaded",
        confidence=1,
        subject="Update",
        body="Update",
        state="sent",
        source_refs=[],
        created_at=NOW - timedelta(minutes=12),
        sent_at=NOW,
    )
    db.add(draft)
    db.flush()
    event(db, "customer_update_approve", detail={"draft_id": draft.id})
    db.commit()
    data = report(client, "trend", days=8, interval="week")
    assert len(data["people"]) == 1
    person = data["people"][0]
    assert person["devices"] == {"mobile": 1}
    assert len(person["series"]) == 2
    assert person["series"][-1]["categories"] == {
        **dict.fromkeys(("bol", "checkins", "chat", "edits", "messages", "sync"), 1),
        "approvals": 2,
        "other": 0,
    }
    assert data["kof"]["booker"][0]["series"][-1]["profit"] == 120
    assert data["kof"]["rep"][0]["name"] == "Rep A"
    assert len(data["feature_adoption"]) == len(data["response_speed"]) == 2
    assert data["response_speed"][-1]["people"][0]["median_seconds"] == 720
    adoption = {
        row["feature"]: row["distinct_people"]
        for row in data["feature_adoption"][-1]["features"]
    }
    assert adoption["bol_upload_extract"] == 1 and adoption["kof_email_send"] == 0


def test_user_overview_includes_inactive_and_never_active_accounts(
    client, db, admin_login
):
    user = add_user(db, username="Never", is_active=False)
    team = TeamMember(name="Never operator", is_active=False)
    active = TeamMember(name="Tony")
    db.add_all([team, active])
    db.flush()
    minute(db, NOW, team_member_id=active.id)
    event(db, "load_edited", team_member_id=active.id)
    db.commit()
    rows = report(client, "users_overview")["users"]
    never = next(row for row in rows if row["kind"] == "user" and row["id"] == user.id)
    assert never["last_seen"] is None and never["is_active"] is False
    assert len(never["sparkline"]) == 7
    operator = next(row for row in rows if row["identity"] == "Tony")
    assert operator["active_minutes_this_week"] == operator["actions_this_week"] == 1
    assert any(row["identity"] == "Never operator" for row in rows)
    assert not any(row["role"] == "admin" for row in rows)
    assert any(
        row["role"] == "admin"
        for row in report(client, "users_overview", exclude_admins=False)["users"]
    )


def test_client_error_validation_truncation_rate_and_attribution(client, db):
    assert client.post("/api/usage/client-error", json=[]).json() == {"accepted": False}
    assert client.post(
        "/api/usage/client-error", json={"message": "oops", "path": "/invalid"}
    ).json() == {"accepted": False}
    for _ in range(5):
        assert client.post(
            "/api/usage/client-error",
            json={"message": "x" * 1100, "path": "/loads/123?secret=yes"},
        ).json() == {"accepted": True}
    assert client.post(
        "/api/usage/client-error", json={"message": "oops", "path": "/loads"}
    ).json() == {"accepted": False}
    rows = db.scalars(select(RequestMetric)).all()
    assert len(rows) == 5 and rows[0].path == "/loads" and len(rows[0].message) == 1000
    client.cookies.clear()
    assert client.post("/api/usage/client-error", json={}).status_code == 401


def test_health_aggregation_and_retention(client, db, admin_login):
    for duration in (2100, 3100, 4100):
        db.add(
            RequestMetric(
                path="/api/loads/{load_id}",
                method="GET",
                status=503,
                duration_ms=duration,
                created_at=NOW,
            )
        )
    db.add(
        RequestMetric(
            path="/loads",
            method="CLIENT",
            kind="client",
            status=0,
            duration_ms=0,
            message="broken",
            created_at=NOW,
        )
    )
    db.add(
        RequestMetric(
            path="/old",
            method="GET",
            status=500,
            duration_ms=1,
            created_at=NOW - timedelta(days=31),
        )
    )
    db.add(
        RequestMetric(
            path="/admin",
            method="GET",
            status=500,
            duration_ms=1,
            user_id=admin_login.id,
            created_at=NOW,
        )
    )
    db.add(
        KofMessage(
            body="not returned", direction="out", status="failed", created_at=NOW
        )
    )
    db.add(
        KofSyncRun(
            kind="manual",
            status="ok",
            started_at=NOW - timedelta(hours=1),
            finished_at=NOW - timedelta(minutes=30),
        )
    )
    db.add(KofSyncRun(kind="manual", status="error", started_at=NOW))
    event(db, "llm_error", detail={"error_type": "ValueError"})
    db.commit()
    data = report(client, "health")
    assert data["errors_per_day"] == [{"date": "2026-11-09", "count": 4}]
    assert data["failing_endpoints"][0]["count"] == 3
    assert data["slowest_endpoints"][0]["p50_ms"] == 3100
    assert data["slowest_endpoints"][0]["p95_ms"] == 4000
    assert data["failed_sends"]["kof_message_total"] == 1
    assert data["kof_sync"]["failures"] == 1
    assert data["kof_sync"]["freshness_seconds"] == 1800
    assert data["llm_error_total"] == 1
    assert data["integrations"]["sms_live"] is False
    usage.prune_usage_events()
    assert db.scalar(select(RequestMetric).where(RequestMetric.path == "/old")) is None


def test_middleware_5xx_slow_unhandled_and_failure_isolation(monkeypatch):
    records = []
    monkeypatch.setattr(main, "record_metric", lambda *args: records.append(args))

    def request():
        req = Request(
            {
                "type": "http",
                "method": "GET",
                "path": "/api/loads/PRIVATE",
                "headers": [],
                "route": SimpleNamespace(path="/api/loads/{load_id}"),
            }
        )
        req.state.usage_identity = (1, "Broker", 2, "Tony")
        return req

    async def failed(req):
        return Response(status_code=503)

    assert asyncio.run(main.request_observability(request(), failed)).status_code == 503
    assert records[0][0] == (1, "Broker", 2, "Tony")
    assert records[0][1] == "/api/loads/{load_id}"
    times = iter([0, 3])
    monkeypatch.setattr(main, "perf_counter", lambda: next(times))

    async def slow(req):
        return Response(status_code=200)

    assert asyncio.run(main.request_observability(request(), slow)).status_code == 200
    assert records[-1][3:5] == (200, 3000)
    monkeypatch.setattr(main, "perf_counter", lambda: 0)

    async def thrown(req):
        raise ValueError("do not store this secret")

    with pytest.raises(ValueError):
        asyncio.run(main.request_observability(request(), thrown))
    assert records[-1][3] == 500

    def broken(*args):
        raise RuntimeError("storage down")

    monkeypatch.setattr(main, "record_metric", broken)
    assert asyncio.run(main.request_observability(request(), failed)).status_code == 503


def test_llm_fallback_records_error_type_without_payload(db):
    class Broken:
        def classify_carrier_update(self, text):
            raise ValueError("secret payload")

    provider = FallbackLlmProvider(Broken())
    provider.classify_carrier_update("loaded")
    row = db.scalar(select(UsageEvent).where(UsageEvent.event == "llm_error"))
    assert row.detail == {
        "operation": "carrier_classification",
        "error_type": "ValueError",
    }
    assert "secret" not in str(row.detail)


def test_metric_persistence_failure_is_isolated(monkeypatch):
    def broken():
        raise RuntimeError("unavailable")

    monkeypatch.setattr(usage_health, "SessionLocal", broken)
    assert usage_health.record_metric(None, "/loads", "GET", 500, 1) is False


def test_invalid_history_range_is_422(client, admin_login):
    assert (
        client.get("/api/admin/usage/contributions?date=0001-01-01").status_code == 422
    )
    assert client.get("/api/admin/usage/trend?days=366").status_code == 422
