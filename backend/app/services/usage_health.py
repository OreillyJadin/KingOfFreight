import logging
import hashlib
import time
from collections import Counter, defaultdict, deque
from contextvars import ContextVar
from datetime import timedelta
from threading import Lock

from sqlalchemy import select

from app.db import SessionLocal
from app.models import RequestMetric, KofMessage, KofSyncRun, utcnow
from app.services.usage_analytics import identity, aware
from app.services.capabilities import capabilities
from app.services.usage import record_event

logger = logging.getLogger(__name__)
actor_context = ContextVar("usage_actor", default=None)
_rate_lock = Lock()
_sessions = {}


def accept_client_error(token):
    key = hashlib.sha256(token.encode()).hexdigest()
    now = time.monotonic()
    with _rate_lock:
        for stale in [
            key
            for key, values in _sessions.items()
            if not values or values[-1] <= now - 60
        ]:
            del _sessions[stale]
        if key not in _sessions and len(_sessions) >= 10000:
            return False
        values = _sessions.setdefault(key, deque())
        while values and values[0] <= now - 60:
            values.popleft()
        if len(values) >= 5:
            return False
        values.append(now)
        return True


def record_metric(
    actor, path, method, status, duration_ms, kind="server", message=None
):
    try:
        user_id, username, member_id, operator_name = actor or (None, None, None, None)
        with SessionLocal() as db:
            db.add(
                RequestMetric(
                    user_id=user_id,
                    username=username,
                    team_member_id=member_id,
                    operator_name=operator_name,
                    path=path[:200],
                    method=method[:10],
                    status=status,
                    duration_ms=round(duration_ms, 2),
                    kind=kind,
                    message=message[:1000] if message else None,
                    created_at=utcnow(),
                )
            )
            db.commit()
        return True
    except Exception:
        logger.warning("Request metric recording failed")
        return False


def record_llm_error(operation, error):
    try:
        actor = actor_context.get()
        record_event(
            getattr(actor, "usage_identity", None) or (None, None, None, None),
            "llm_error",
            None,
            "",
            {"operation": operation, "error_type": type(error).__name__},
        )
    except Exception:
        logger.warning("LLM metric recording failed")


def percentile(values, fraction):
    if not values:
        return None
    values = sorted(values)
    point = (len(values) - 1) * fraction
    low = int(point)
    high = min(low + 1, len(values) - 1)
    return round(values[low] + (values[high] - values[low]) * (point - low), 2)


def health_report(analytics):
    db = analytics.db
    metrics = list(
        db.scalars(
            analytics.query(RequestMetric, RequestMetric.created_at).order_by(
                RequestMetric.created_at
            )
        )
    )
    daily, failing, timings = Counter(), Counter(), defaultdict(list)
    client_errors = []
    for row in metrics:
        if row.kind == "client":
            client_errors.append(
                {
                    "id": row.id,
                    "identity": identity(row),
                    "time": analytics.local(row.created_at),
                    "message": row.message,
                    "path": row.path,
                }
            )
        if row.status >= 500 or row.kind == "client":
            daily[
                aware(row.created_at).astimezone(analytics.zone).date().isoformat()
            ] += 1
        if row.kind == "server":
            if row.status >= 500:
                failing[row.method, row.path] += 1
            timings[row.method, row.path].append(row.duration_ms)
    failures = list(
        db.scalars(
            select(KofMessage)
            .where(
                KofMessage.status == "failed",
                KofMessage.created_at >= analytics.start,
                KofMessage.created_at < analytics.end,
                KofMessage.created_at <= analytics.now,
            )
            .order_by(KofMessage.created_at.desc())
        )
    )
    runs = list(
        db.scalars(
            select(KofSyncRun)
            .where(
                KofSyncRun.started_at >= analytics.start,
                KofSyncRun.started_at < analytics.end,
                KofSyncRun.started_at <= analytics.now,
            )
            .order_by(KofSyncRun.started_at.desc())
        )
    )
    last_success = db.scalar(
        select(KofSyncRun)
        .where(KofSyncRun.status == "ok", KofSyncRun.finished_at <= analytics.now)
        .order_by(KofSyncRun.finished_at.desc())
        .limit(1)
    )
    llm = [row for row in analytics.events() if row.event == "llm_error"]
    return {
        **analytics.meta,
        "metric_retention_days": 30,
        "errors_per_day": [
            {
                "date": (analytics.first + timedelta(days=i)).isoformat(),
                "count": daily[(analytics.first + timedelta(days=i)).isoformat()],
            }
            for i in range((analytics.last - analytics.first).days)
        ],
        "failing_endpoints": [
            {"method": method, "path": path, "count": count}
            for (method, path), count in failing.most_common(20)
        ],
        "slowest_endpoints": sorted(
            [
                {
                    "method": method,
                    "path": path,
                    "count": len(values),
                    "p50_ms": percentile(values, 0.5),
                    "p95_ms": percentile(values, 0.95),
                }
                for (method, path), values in timings.items()
            ],
            key=lambda row: -row["p95_ms"],
        )[:20],
        "latency_basis": "Only requests over 2s or with 5xx status are sampled; not all requests",
        "client_errors": list(reversed(client_errors))[:100],
        "client_error_total": len(client_errors),
        "failed_sends": {
            "kof_messages": [
                {
                    "id": row.id,
                    "order_no": row.order_no,
                    "time": analytics.local(row.created_at),
                }
                for row in failures[:100]
            ],
            "kof_message_total": len(failures),
            "communications_status_available": False,
            "attribution_available": False,
        },
        "kof_sync": {
            "last_success": analytics.local(last_success.finished_at)
            if last_success
            else None,
            "freshness_seconds": max(
                0, (analytics.now - aware(last_success.finished_at)).total_seconds()
            )
            if last_success
            else None,
            "failures": sum(row.status == "error" for row in runs),
            "runs": [
                {
                    "id": row.id,
                    "status": row.status,
                    "started_at": analytics.local(row.started_at),
                    "finished_at": analytics.local(row.finished_at),
                }
                for row in runs[:100]
            ],
        },
        "llm_errors": [
            {
                "identity": identity(row),
                "time": analytics.local(row.created_at),
                "detail": row.detail,
            }
            for row in llm[-100:]
        ],
        "llm_error_total": len(llm),
        "integrations": capabilities(db),
        "workspace_metrics_note": "KOF messages and sync runs have no actor IDs; workspace-wide regardless of exclude_admins.",
    }
