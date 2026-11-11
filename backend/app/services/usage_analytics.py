from collections import Counter, defaultdict
from datetime import date, datetime, time, timedelta, timezone
from statistics import mean, median
from zoneinfo import ZoneInfo

from fastapi import HTTPException
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.models import (
    Communication,
    CustomerUpdateDraft,
    KofLoad,
    KofMessage,
    UsageEvent,
    UsageMinute,
    User,
    utcnow,
)
from app.services.preferences import get_prefs

FEATURES = {
    "load_created": "Created load",
    "load_edited": "Edited load",
    "load_status_changed": "Changed load status",
    "load_booked": "Booked carrier",
    "checkin_manual_send": "Sent check-in manually",
    "bol_upload_extract": "Uploaded BOL",
    "kof_text_draft": "Drafted KOF text",
    "kof_email_draft": "Drafted KOF email",
    "kof_text_send": "Sent KOF text",
    "kof_email_send": "Sent KOF email",
    "customer_update_approve": "Approved customer update",
    "customer_update_dismiss": "Dismissed customer update",
    "operational_update_dismiss": "Dismissed operational update",
    "operational_send": "Sent operational message",
    "assistant_question": "Asked assistant",
    "assistant_opened": "Opened assistant",
    "suggestion_clicked": "Clicked assistant suggestion",
    "kof_manual_sync": "Started KOF sync",
    "truckstop_post": "Posted load to TruckStop workspace",
    "truckstop_post_text": "Retrieved TruckStop posting text",
    "carrier_verify": "Verified carrier",
    "login_success": "Signed in",
    "outlook_connect": "Connected Outlook",
    "operator_switched": "Switched operator",
}
NON_ACTIONS = {"page_view", "assistant_question_submitted", "llm_error"}


def event_summary(row):
    detail = row.detail if isinstance(row.detail, dict) else {}
    text = FEATURES.get(row.event, row.event.replace("_", " ").capitalize())
    if row.event == "page_view":
        return f"Viewed {row.path or 'page'}"
    if detail.get("order_no") is not None:
        text += f" for order {detail['order_no']}"
    elif detail.get("reference") or detail.get("load_id"):
        text += f" for load {detail.get('reference') or detail['load_id']}"
    return text


def identity(row) -> str:
    return row.operator_name or row.username or "shared login"


def aware(stamp: datetime) -> datetime:
    return stamp.replace(tzinfo=timezone.utc) if stamp.tzinfo is None else stamp


def admin_filter(model):
    return or_(
        model.user_id.is_(None),
        model.user_id.not_in(select(User.id).where(User.role == "admin")),
    )


class Analytics:
    def __init__(
        self, db: Session, period: str, anchor: date | None, exclude_admins: bool
    ):
        self.db = db
        self.zone = ZoneInfo(get_prefs(db).broker_timezone)
        self.now = aware(utcnow())
        self.today = self.now.astimezone(self.zone).date()
        anchor = anchor or self.today
        try:
            if period == "day":
                first, last = anchor, anchor + timedelta(days=1)
            elif period == "week":
                first = anchor - timedelta(days=anchor.weekday())
                last = first + timedelta(days=7)
            else:
                first = anchor.replace(day=1)
                last = (first.replace(day=28) + timedelta(days=4)).replace(day=1)
            self.start = datetime.combine(first, time.min, self.zone).astimezone(
                timezone.utc
            )
            self.end = datetime.combine(last, time.min, self.zone).astimezone(
                timezone.utc
            )
        except (ValueError, OverflowError):
            raise HTTPException(
                422, "Date is outside the supported calendar range"
            ) from None
        self.first, self.last = first, last
        self.exclude_admins = exclude_admins
        self.meta = {
            "period": period,
            "date": anchor.isoformat(),
            "timezone": str(self.zone),
            "start": self.start.astimezone(self.zone).isoformat(),
            "end_exclusive": self.end.astimezone(self.zone).isoformat(),
            "exclude_admins": exclude_admins,
        }

    def query(self, model, stamp):
        query = select(model).where(
            stamp >= self.start, stamp < self.end, stamp <= self.now
        )
        return query.where(admin_filter(model)) if self.exclude_admins else query

    def events(self):
        return list(
            self.db.scalars(
                self.query(UsageEvent, UsageEvent.created_at).order_by(
                    UsageEvent.created_at, UsageEvent.id
                )
            )
        )

    def minutes(self):
        return list(
            self.db.scalars(
                self.query(UsageMinute, UsageMinute.minute).order_by(UsageMinute.minute)
            )
        )

    def local(self, stamp):
        return aware(stamp).astimezone(self.zone).isoformat() if stamp else None

    def people(self):
        minutes, events = self.minutes(), self.events()
        grouped, actions, stamps = (
            defaultdict(list),
            defaultdict(Counter),
            defaultdict(list),
        )
        for row in minutes:
            grouped[identity(row)].append(aware(row.minute))
            stamps[identity(row)].append(aware(row.minute))
        for row in events:
            who = identity(row)
            stamps[who].append(aware(row.created_at))
            if row.event not in NON_ACTIONS:
                actions[who][row.event] += 1
        history_query = select(UsageMinute).where(
            UsageMinute.minute >= self.now - timedelta(days=180),
            UsageMinute.minute <= self.now,
        )
        if self.exclude_admins:
            history_query = history_query.where(admin_filter(UsageMinute))
        history = defaultdict(set)
        for row in self.db.scalars(history_query):
            history[identity(row)].add(aware(row.minute).astimezone(self.zone).date())
        result = []
        for who in sorted(stamps):
            active = grouped[who]
            sessions = []
            for minute in active:
                if not sessions or minute - sessions[-1][-1] > timedelta(minutes=30):
                    sessions.append([minute])
                else:
                    sessions[-1].append(minute)
            durations = [
                (session[-1] - session[0]).total_seconds() / 60 + 1
                for session in sessions
            ]
            cursor = (
                self.today
                if self.today in history[who]
                else self.today - timedelta(days=1)
            )
            streak = 0
            while cursor in history[who]:
                streak += 1
                cursor -= timedelta(days=1)
            result.append(
                {
                    "identity": who,
                    "active_minutes": len(active),
                    "sessions": len(sessions),
                    "first_activity": self.local(min(stamps[who])),
                    "last_activity": self.local(max(stamps[who])),
                    "avg_session_minutes": round(mean(durations), 2)
                    if durations
                    else 0,
                    "days_active": len(
                        {stamp.astimezone(self.zone).date() for stamp in active}
                    ),
                    "current_streak": streak,
                    "actions": sum(actions[who].values()),
                    "action_counts": dict(sorted(actions[who].items())),
                    "chat_questions": actions[who]["assistant_question"],
                }
            )
        return {**self.meta, "people": result}

    def pages(self):
        counts = Counter((identity(row), row.path) for row in self.minutes())
        return {
            **self.meta,
            "pages": [
                {"identity": who, "path": path, "active_minutes": count}
                for (who, path), count in sorted(counts.items())
            ],
        }

    def heatmap(self):
        counts, totals = Counter(), Counter()
        for row in self.minutes():
            stamp = aware(row.minute).astimezone(self.zone)
            counts[identity(row), stamp.weekday(), stamp.hour] += 1
            totals[stamp.weekday(), stamp.hour] += 1
        return {
            **self.meta,
            "cells": [
                {"identity": who, "weekday": day, "hour": hour, "active_minutes": count}
                for (who, day, hour), count in sorted(counts.items())
            ],
            "total": [
                {"weekday": day, "hour": hour, "active_minutes": count}
                for (day, hour), count in sorted(totals.items())
            ],
        }

    def feed(self, who: str | None, limit: int, offset: int):
        query = self.query(UsageEvent, UsageEvent.created_at)
        if who is not None:
            query = query.where(
                func.coalesce(
                    UsageEvent.operator_name, UsageEvent.username, "shared login"
                )
                == who
            )
        total = self.db.scalar(select(func.count()).select_from(query.subquery()))
        rows = self.db.scalars(
            query.order_by(UsageEvent.created_at.desc(), UsageEvent.id.desc())
            .offset(offset)
            .limit(limit)
        )
        items = []
        for row in rows:
            detail = row.detail if isinstance(row.detail, dict) else {}
            items.append(
                {
                    "id": row.id,
                    "identity": identity(row),
                    "event": row.event,
                    "path": row.path,
                    "device": row.device,
                    "time": self.local(row.created_at),
                    "summary": event_summary(row),
                    "detail": detail,
                }
            )
        return {
            **self.meta,
            "items": items,
            "total": total,
            "limit": limit,
            "offset": offset,
            "has_more": offset + len(items) < total,
        }

    def kof_output(self):
        result = {}
        for name in ("booker", "rep"):
            field = getattr(KofLoad, name)
            query = select(
                field,
                func.count(),
                func.sum(KofLoad.price),
                func.sum(KofLoad.cost),
                func.sum(KofLoad.profit),
            ).where(
                KofLoad.is_deleted.is_(False),
                KofLoad.date_of_sale >= self.first,
                KofLoad.date_of_sale < self.last,
            )
            if self.exclude_admins:
                query = query.where(
                    or_(
                        field.is_(None),
                        func.lower(field).not_in(
                            select(func.lower(User.username)).where(
                                User.role == "admin"
                            )
                        ),
                    )
                )
            rows = self.db.execute(query.group_by(field).order_by(field)).all()
            result[name] = [
                {
                    "name": row[0],
                    "loads": row[1],
                    "revenue": round(float(row[2] or 0), 2),
                    "carrier_cost": round(float(row[3] or 0), 2),
                    "profit": round(float(row[4] or 0), 2),
                    "margin_pct": round(float(row[4] or 0) * 100 / float(row[2]), 2)
                    if row[2]
                    else None,
                }
                for row in rows
            ]
        return {**self.meta, **result}

    def response_speed(self):
        values = defaultdict(list)
        missing = 0
        seen = set()
        query = select(UsageEvent).where(
            UsageEvent.event == "customer_update_approve",
            UsageEvent.created_at <= self.now,
        )
        if self.exclude_admins:
            query = query.where(admin_filter(UsageEvent))
        for event in self.db.scalars(query):
            detail = event.detail if isinstance(event.detail, dict) else {}
            draft_id = detail.get("draft_id")
            draft = (
                self.db.get(CustomerUpdateDraft, draft_id)
                if isinstance(draft_id, int)
                else None
            )
            if not draft or not draft.sent_at:
                if self.start <= aware(event.created_at) < self.end:
                    missing += 1
                continue
            if (
                not self.start <= aware(draft.sent_at) < self.end
                or aware(draft.sent_at) > self.now
            ):
                continue
            if draft.id in seen:
                continue
            seen.add(draft.id)
            sources = []
            for ref in draft.source_refs or []:
                if not isinstance(ref, dict) or ref.get("deferred"):
                    continue
                try:
                    sources.append(aware(datetime.fromisoformat(ref["received_at"])))
                except (KeyError, TypeError, ValueError):
                    model = (
                        KofMessage
                        if ref.get("channel") == "sms"
                        else Communication
                        if ref.get("channel") == "email"
                        else None
                    )
                    linked = (
                        self.db.get(model, ref["id"])
                        if model is not None and isinstance(ref.get("id"), int)
                        else None
                    )
                    if linked is not None and (
                        (
                            model is KofMessage
                            and linked.order_no == draft.order_no
                            and linked.direction == "in"
                        )
                        or (
                            model is Communication
                            and linked.kof_order_no == draft.order_no
                            and linked.direction == "inbound"
                        )
                    ):
                        sources.append(aware(linked.created_at))
            source = min(sources) if sources else aware(draft.created_at)
            elapsed = (aware(draft.sent_at) - source).total_seconds()
            if elapsed < 0:
                missing += 1
                continue
            values[identity(event)].append(elapsed)
        return {
            **self.meta,
            "people": [
                {
                    "identity": who,
                    "count": len(seconds),
                    "median_seconds": round(median(seconds), 2),
                    "avg_seconds": round(mean(seconds), 2),
                }
                for who, seconds in sorted(values.items())
            ],
            "unlinked_approval_events": missing,
        }

    def features(self):
        events = defaultdict(list)
        for row in self.events():
            if row.event not in NON_ACTIONS:
                events[row.event].append(row)
        return {
            **self.meta,
            "features": [
                {
                    "feature": name,
                    "label": FEATURES.get(name, name.replace("_", " ").capitalize()),
                    "uses": len(events[name]),
                    "distinct_people": len({identity(row) for row in events[name]}),
                    "last_used": self.local(events[name][-1].created_at)
                    if events[name]
                    else None,
                }
                for name in sorted(set(FEATURES) | set(events))
            ],
        }

    def leaderboard(self):
        profits = Counter()
        for row in self.kof_output()["booker"]:
            if row["name"]:
                profits[row["name"].casefold()] += row["profit"]
        people = [
            {
                "identity": row["identity"],
                "active_minutes": row["active_minutes"],
                "actions": row["actions"],
                "kof_profit": profits.get(row["identity"].casefold()),
            }
            for row in self.people()["people"]
        ]
        for metric in ("active_minutes", "actions", "kof_profit"):
            ordered = sorted(
                people,
                key=lambda row: (
                    row[metric] is None,
                    -(row[metric] or 0),
                    row["identity"],
                ),
            )
            for row in people:
                row[f"{metric}_rank"] = (
                    next(
                        index + 1
                        for index, candidate in enumerate(ordered)
                        if candidate is row
                    )
                    if row[metric] is not None
                    else None
                )
        return {
            **self.meta,
            "people": sorted(people, key=lambda row: row["active_minutes_rank"]),
        }
