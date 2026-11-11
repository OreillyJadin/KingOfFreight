from collections import Counter
from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import UsageEvent, utcnow
from app.services.preferences import get_prefs
from app.services.usage_analytics import admin_filter, identity


def ranked(counts: Counter) -> list[dict]:
    return [
        {"name": name, "count": count}
        for name, count in sorted(counts.items(), key=lambda pair: (-pair[1], pair[0]))
    ]


def report(db: Session, days: int, exclude_admins: bool = True) -> dict:
    zone = ZoneInfo(get_prefs(db).broker_timezone)
    now = utcnow()
    first_day = now.astimezone(zone).date() - timedelta(days=days - 1)
    start = datetime.combine(first_day, time.min, zone).astimezone(timezone.utc)
    query = select(UsageEvent)
    if exclude_admins:
        query = query.where(admin_filter(UsageEvent))
    rows = db.scalars(
        query.where(
            UsageEvent.created_at >= start, UsageEvent.created_at <= now
        ).order_by(UsageEvent.created_at, UsageEvent.id)
    ).all()
    daily = {
        (first_day + timedelta(days=index)).isoformat(): {
            "users": set(),
            "questions": 0,
        }
        for index in range(days)
    }
    users = {}
    pages, features, devices = Counter(), Counter(), Counter()
    questions = []
    page_views = 0
    for row in rows:
        stamp = row.created_at
        if stamp.tzinfo is None:
            stamp = stamp.replace(tzinfo=timezone.utc)
        stamp = stamp.astimezone(zone)
        key = identity(row)
        day = daily[stamp.date().isoformat()]
        day["users"].add(key)
        user = users.setdefault(
            key,
            {
                "user_id": row.user_id,
                "username": row.username,
                "label": row.operator_name or row.username or "shared login",
                "operator_name": row.operator_name,
                "team_member_id": row.team_member_id,
                "last_seen": None,
                "page_views": 0,
                "questions": 0,
                "pages": Counter(),
                "devices": Counter(),
            },
        )
        user["last_seen"] = stamp.isoformat()
        user["devices"][row.device] += 1
        devices[row.device] += 1
        if row.event == "page_view":
            page_views += 1
            user["page_views"] += 1
            if row.path:
                user["pages"][row.path] += 1
                pages[row.path] += 1
        elif row.event != "assistant_question_submitted":
            features[row.event] += 1
        if row.event == "assistant_question":
            day["questions"] += 1
            user["questions"] += 1
            detail = row.detail if isinstance(row.detail, dict) else {}
            text = detail.get("question", "")
            questions.append(
                {
                    "username": row.username,
                    "user": row.operator_name or row.username or "shared login",
                    "operator_name": row.operator_name,
                    "team_member_id": row.team_member_id,
                    "time": stamp.isoformat(),
                    "text": text[:300] if isinstance(text, str) else "",
                }
            )
    user_rows = []
    for user in users.values():
        top = ranked(user.pop("pages"))
        user["top_page"] = top[0]["name"] if top else None
        user["devices"] = dict(user["devices"])
        user_rows.append(user)
    return {
        "days": days,
        "timezone": str(zone),
        "exclude_admins": exclude_admins,
        "totals": {
            "events": len(rows),
            "active_users": len(users),
            "chat_questions": len(questions),
            "page_views": page_views,
        },
        "daily": [
            {
                "date": date,
                "active_users": len(data["users"]),
                "questions": data["questions"],
            }
            for date, data in daily.items()
        ],
        "users": sorted(
            user_rows,
            key=lambda user: datetime.fromisoformat(user["last_seen"]).timestamp(),
            reverse=True,
        ),
        "top_pages": ranked(pages),
        "top_features": ranked(features),
        "devices": dict(devices),
        "questions": list(reversed(questions[-50:])),
    }
