import logging
import hashlib
import json
from datetime import timedelta
from zoneinfo import ZoneInfo
from urllib.parse import urlsplit

from fastapi import Request
from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from app.db import SessionLocal
from app.models import UsageEvent, UsageMinute, UsageDaily, RequestMetric, utcnow
from app.services.preferences import get_prefs
from app.services.usage_analytics import aware, NON_ACTIONS

logger = logging.getLogger(__name__)
PAGES = {
    "dashboard",
    "tracking",
    "loads",
    "customers",
    "branches",
    "carriers",
    "sales",
    "inbox",
    "customer-updates",
    "truckstop",
    "status",
    "settings",
    "users",
    "usage",
    "set-password",
}
CLIENT_EVENTS = {
    "page_view",
    "assistant_opened",
    "assistant_question_submitted",
    "suggestion_clicked",
}


def normalize_path(path) -> str | None:
    if not isinstance(path, str) or not path.startswith("/") or path.startswith("//"):
        return None
    try:
        page = urlsplit(path).path.split("/")[1]
    except ValueError:
        return None
    return f"/{page}" if page in PAGES else None


def device_type(user_agent: str) -> str:
    ua = user_agent.lower()
    if (
        "ipad" in ua
        or "tablet" in ua
        or ("android" in ua and "mobile" not in ua)
        or ("macintosh" in ua and "mobile" in ua)
    ):
        return "tablet"
    return (
        "mobile"
        if any(word in ua for word in ("mobile", "iphone", "ipod"))
        else "desktop"
    )


def feature_event(request: Request, event: str, detail: dict | None = None) -> None:
    try:
        if not hasattr(request.state, "usage_events"):
            request.state.usage_events = []
        request.state.usage_events.append((event, detail))
    except Exception:
        logger.warning("Usage event staging failed")


def record_event(
    identity: tuple,
    event: str,
    path: str | None,
    user_agent: str,
    detail: dict | None = None,
) -> bool:
    try:
        user_id, username = identity[:2]
        team_member_id, operator_name = (
            identity[2:] if len(identity) == 4 else (None, None)
        )
        now = utcnow()
        device = device_type(user_agent)
        with SessionLocal() as db:
            if (
                event == "page_view"
                and db.scalar(
                    select(UsageEvent.id)
                    .where(
                        UsageEvent.event == event,
                        UsageEvent.user_id == user_id,
                        UsageEvent.username == username,
                        UsageEvent.team_member_id == team_member_id,
                        UsageEvent.path == path,
                        UsageEvent.device == device,
                        UsageEvent.created_at >= now - timedelta(seconds=5),
                    )
                    .limit(1)
                )
                is not None
            ):
                return False
            db.add(
                UsageEvent(
                    user_id=user_id,
                    username=username,
                    team_member_id=team_member_id,
                    operator_name=operator_name,
                    event=event,
                    path=path,
                    device=device,
                    detail=detail,
                    created_at=now,
                )
            )
            db.commit()
        return True
    except Exception:
        logger.warning("Usage event recording failed")
        return False


def record_heartbeat(identity: tuple, path: str, user_agent: str) -> bool:
    try:
        user_id, username = identity[:2]
        team_member_id, operator_name = (
            identity[2:] if len(identity) == 4 else (None, None)
        )
        values = dict(
            identity=operator_name or username or "shared login",
            minute=utcnow().replace(second=0, microsecond=0),
            last_seen_at=utcnow(),
            path=path,
            user_id=user_id,
            username=username,
            team_member_id=team_member_id,
            operator_name=operator_name,
            device=device_type(user_agent),
        )
        with SessionLocal() as db:
            insert = (
                pg_insert
                if db.get_bind().dialect.name == "postgresql"
                else sqlite_insert
            )
            statement = insert(UsageMinute).values(**values)
            db.execute(
                statement.on_conflict_do_update(
                    index_elements=["identity", "minute"],
                    set_={
                        key: value
                        for key, value in values.items()
                        if key not in {"identity", "minute"}
                    },
                )
            )
            db.commit()
        return True
    except Exception:
        logger.warning("Usage heartbeat recording failed")
        return False


def prune_usage_events() -> None:
    try:
        with SessionLocal() as db:
            zone = ZoneInfo(get_prefs(db).broker_timezone)
            cutoff_day = utcnow().astimezone(zone).date() - timedelta(days=364)
            archives = {}
            for model, field, metric in (
                (UsageMinute, UsageMinute.minute, "active_minutes"),
                (UsageEvent, UsageEvent.created_at, "actions"),
            ):
                for row in db.scalars(
                    select(model).where(field < utcnow() - timedelta(days=180))
                ):
                    day = aware(getattr(row, field.key)).astimezone(zone).date()
                    if day < cutoff_day or (
                        model is UsageEvent and row.event in NON_ACTIONS | {"llm_error"}
                    ):
                        continue
                    actor = {
                        name: getattr(row, name)
                        for name in (
                            "user_id",
                            "username",
                            "team_member_id",
                            "operator_name",
                        )
                    }
                    key = hashlib.sha256(
                        json.dumps([day.isoformat(), actor], sort_keys=True).encode()
                    ).hexdigest()
                    daily = archives.get(key) or db.get(UsageDaily, key)
                    if daily is None:
                        daily = UsageDaily(
                            id=key, day=day, active_minutes=0, actions=0, **actor
                        )
                        db.add(daily)
                    archives[key] = daily
                    stamp = aware(getattr(row, field.key))
                    if daily.last_seen_at is None or stamp > aware(daily.last_seen_at):
                        daily.last_seen_at = stamp
                    setattr(daily, metric, getattr(daily, metric) + 1)
            db.execute(
                delete(UsageDaily)
                .where(UsageDaily.day < cutoff_day)
                .execution_options(synchronize_session=False)
            )
            db.execute(
                delete(RequestMetric)
                .where(RequestMetric.created_at < utcnow() - timedelta(days=30))
                .execution_options(synchronize_session=False)
            )
            db.execute(
                delete(UsageEvent)
                .where(UsageEvent.created_at < utcnow() - timedelta(days=180))
                .execution_options(synchronize_session=False)
            )
            db.execute(
                delete(UsageMinute)
                .where(UsageMinute.minute < utcnow() - timedelta(days=180))
                .execution_options(synchronize_session=False)
            )
            db.commit()
    except Exception:
        logger.warning("Usage event pruning failed")
