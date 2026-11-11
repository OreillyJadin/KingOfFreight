from collections import Counter, defaultdict
from datetime import datetime, time, timedelta, timezone

from sqlalchemy import select, func, or_

from app.models import UsageEvent, UsageMinute, UsageDaily, User, TeamMember, KofLoad
from app.services.usage_analytics import (
    Analytics,
    NON_ACTIONS,
    FEATURES,
    identity,
    aware,
    admin_filter,
    event_summary,
)

CATEGORIES = {
    "bol": {"bol_upload_extract"},
    "checkins": {"checkin_manual_send"},
    "approvals": {
        "customer_update_approve",
        "customer_update_dismiss",
        "operational_update_dismiss",
    },
    "chat": {"assistant_question", "assistant_opened", "suggestion_clicked"},
    "edits": {
        "load_created",
        "load_edited",
        "load_status_changed",
        "load_booked",
        "truckstop_post",
    },
    "messages": {
        "kof_text_draft",
        "kof_email_draft",
        "kof_text_send",
        "kof_email_send",
        "operational_send",
    },
    "sync": {"kof_manual_sync"},
}


def action(row):
    return row.event not in NON_ACTIONS and row.event != "llm_error"


class Visuals(Analytics):
    def window(self, first, last):
        self.first, self.last = first, last
        self.start = datetime.combine(first, time.min, self.zone).astimezone(
            timezone.utc
        )
        self.end = datetime.combine(last, time.min, self.zone).astimezone(timezone.utc)
        self.meta.update(
            start=self.local(self.start), end_exclusive=self.local(self.end)
        )

    def day(self, stamp):
        return aware(stamp).astimezone(self.zone).date()

    def contributions(self, anchor):
        end = min(anchor or self.today, self.today)
        self.window(end - timedelta(days=364), end + timedelta(days=1))
        counts = defaultdict(lambda: defaultdict(Counter))
        archived = select(UsageDaily).where(
            UsageDaily.day >= self.first, UsageDaily.day < self.last
        )
        if self.exclude_admins:
            archived = archived.where(admin_filter(UsageDaily))
        for row in self.db.scalars(archived):
            counts[identity(row)][row.day]["active_minutes"] += row.active_minutes
            counts[identity(row)][row.day]["actions"] += row.actions
        for row in self.minutes():
            counts[identity(row)][self.day(row.minute)]["active_minutes"] += 1
        for row in self.events():
            if action(row):
                counts[identity(row)][self.day(row.created_at)]["actions"] += 1
        people = []
        for who, days in sorted(counts.items()):
            current = longest = run = 0
            daily = []
            for offset in range(365):
                day = self.first + timedelta(days=offset)
                values = days[day]
                count = values["active_minutes"] + values["actions"]
                run = run + 1 if count else 0
                longest = max(longest, run)
                daily.append(
                    {
                        "date": day.isoformat(),
                        "active_minutes": values["active_minutes"],
                        "actions": values["actions"],
                        "count": count,
                    }
                )
            cursor = end if sum(days[end].values()) else end - timedelta(days=1)
            while cursor >= self.first and sum(days[cursor].values()):
                current += 1
                cursor -= timedelta(days=1)
            people.append(
                {
                    "identity": who,
                    "days": daily,
                    "current_streak": current,
                    "longest_streak": longest,
                }
            )
        return {**self.meta, "retention_days": 365, "people": people}

    def timeline(self):
        groups = defaultdict(lambda: {"spans": [], "actions": []})
        for row in self.minutes():
            stamp = aware(row.minute)
            spans = groups[identity(row)]["spans"]
            if spans and stamp - spans[-1]["last"] <= timedelta(minutes=5):
                spans[-1]["last"] = stamp
                spans[-1]["active_minutes"] += 1
            else:
                spans.append({"start": stamp, "last": stamp, "active_minutes": 1})
        for row in self.events():
            if action(row):
                groups[identity(row)]["actions"].append(
                    {
                        "time": self.local(row.created_at),
                        "event": row.event,
                        "summary": event_summary(row),
                    }
                )
        people = []
        for who, values in sorted(groups.items()):
            spans = [
                {
                    "start": self.local(span["start"]),
                    "end_exclusive": self.local(
                        min(span["last"] + timedelta(minutes=1), self.end)
                    ),
                    "active_minutes": span["active_minutes"],
                }
                for span in values["spans"]
            ]
            people.append(
                {"identity": who, "spans": spans, "actions": values["actions"]}
            )
        return {**self.meta, "people": people}

    def live(self):
        last_seen = func.coalesce(UsageMinute.last_seen_at, UsageMinute.minute)
        query = (
            select(UsageMinute)
            .where(last_seen >= self.now - timedelta(minutes=2), last_seen <= self.now)
            .order_by(last_seen)
        )
        if self.exclude_admins:
            query = query.where(admin_filter(UsageMinute))
        latest = {identity(row): row for row in self.db.scalars(query)}
        last_actions = {}
        query = (
            select(UsageEvent)
            .where(UsageEvent.created_at <= self.now)
            .order_by(UsageEvent.created_at, UsageEvent.id)
        )
        if self.exclude_admins:
            query = query.where(admin_filter(UsageEvent))
        for row in self.db.scalars(query):
            if identity(row) in latest and action(row):
                last_actions[identity(row)] = row
        return {
            **self.meta,
            "as_of": self.local(self.now),
            "people": [
                {
                    "identity": who,
                    "path": row.path,
                    "device": row.device,
                    "last_heartbeat": self.local(row.last_seen_at or row.minute),
                    "last_action": {
                        "time": self.local(last_actions[who].created_at),
                        "event": last_actions[who].event,
                        "summary": event_summary(last_actions[who]),
                    }
                    if who in last_actions
                    else None,
                }
                for who, row in sorted(latest.items())
            ],
        }

    def flows(self):
        previous, counts = {}, Counter()
        for row in self.events():
            if row.event != "page_view" or not row.path:
                continue
            who = identity(row)
            before = previous.get(who)
            if (
                before
                and aware(row.created_at) - aware(before.created_at)
                < timedelta(minutes=30)
                and before.path != row.path
            ):
                counts[before.path, row.path] += 1
            previous[who] = row
        return {
            **self.meta,
            "transitions": [
                {"from": a, "to": b, "count": count}
                for (a, b), count in sorted(
                    counts.items(), key=lambda item: (-item[1], item[0])
                )[:20]
            ],
        }

    def users_overview(self):
        today = self.today
        week = today - timedelta(days=today.weekday())
        all_minutes = select(UsageMinute).where(UsageMinute.minute <= self.now)
        all_events = select(UsageEvent).where(UsageEvent.created_at <= self.now)
        archived = select(UsageDaily)
        if self.exclude_admins:
            all_minutes = all_minutes.where(admin_filter(UsageMinute))
            all_events = all_events.where(admin_filter(UsageEvent))
            archived = archived.where(admin_filter(UsageDaily))
        history = list(self.db.scalars(archived))
        minutes, events = (
            list(self.db.scalars(all_minutes)),
            list(self.db.scalars(all_events)),
        )
        rows = []
        for kind, model in (("user", User), ("team_member", TeamMember)):
            for account in self.db.scalars(select(model).order_by(model.id)):
                if kind == "user" and self.exclude_admins and account.role == "admin":
                    continue
                field = "user_id" if kind == "user" else "team_member_id"
                selected_minutes = [
                    r for r in minutes if getattr(r, field) == account.id
                ]
                selected_events = [r for r in events if getattr(r, field) == account.id]
                stamps = [aware(r.minute) for r in selected_minutes] + [
                    aware(r.created_at) for r in selected_events
                ]
                stamps.extend(
                    aware(r.last_seen_at)
                    for r in history
                    if getattr(r, field) == account.id
                    and r.last_seen_at
                    and aware(r.last_seen_at) <= self.now
                )
                if (
                    kind == "user"
                    and account.last_login_at
                    and aware(account.last_login_at) <= self.now
                ):
                    stamps.append(aware(account.last_login_at))
                daily = defaultdict(Counter)
                for row in selected_minutes:
                    daily[self.day(row.minute)]["active_minutes"] += 1
                for row in selected_events:
                    if action(row):
                        daily[self.day(row.created_at)]["actions"] += 1
                rows.append(
                    {
                        "kind": kind,
                        "id": account.id,
                        "identity": account.username
                        if kind == "user"
                        else account.name,
                        "role": account.role if kind == "user" else None,
                        "is_active": account.is_active,
                        "last_seen": self.local(max(stamps)) if stamps else None,
                        "active_minutes_this_week": sum(
                            v["active_minutes"]
                            for d, v in daily.items()
                            if week <= d <= today
                        ),
                        "actions_this_week": sum(
                            v["actions"] for d, v in daily.items() if week <= d <= today
                        ),
                        "sparkline": [
                            {
                                "date": (today - timedelta(days=6 - i)).isoformat(),
                                "active_minutes": daily[today - timedelta(days=6 - i)][
                                    "active_minutes"
                                ],
                                "actions": daily[today - timedelta(days=6 - i)][
                                    "actions"
                                ],
                            }
                            for i in range(7)
                        ],
                    }
                )
        return {**self.meta, "week_start": week.isoformat(), "users": rows}

    def trend(self, anchor, days, interval):
        end = min(anchor or self.today, self.today)
        self.window(end - timedelta(days=days - 1), end + timedelta(days=1))

        def bucket(day):
            return (
                day - timedelta(days=day.weekday()) if interval == "week" else day
            ).isoformat()

        buckets = sorted({bucket(self.first + timedelta(days=i)) for i in range(days)})
        counts, devices, adoption = (
            defaultdict(lambda: defaultdict(Counter)),
            defaultdict(Counter),
            defaultdict(lambda: defaultdict(set)),
        )
        for row in self.minutes():
            who, day = identity(row), self.day(row.minute)
            counts[who][bucket(day)]["active_minutes"] += 1
            devices[who][row.device] += 1
        for row in self.events():
            who, day = identity(row), self.day(row.created_at)
            if action(row):
                values = counts[who][bucket(day)]
                values["actions"] += 1
                category = next(
                    (
                        name
                        for name, features in CATEGORIES.items()
                        if row.event in features
                    ),
                    "other",
                )
                values[category] += 1
                adoption[(day - timedelta(days=day.weekday())).isoformat()][
                    row.event
                ].add(who)
        kof = {}
        for field_name in ("booker", "rep"):
            field = getattr(KofLoad, field_name)
            query = select(KofLoad).where(
                KofLoad.is_deleted.is_(False),
                KofLoad.date_of_sale >= self.first,
                KofLoad.date_of_sale < self.last,
                KofLoad.date_of_sale <= end,
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
            groups = defaultdict(lambda: defaultdict(Counter))
            for row in self.db.scalars(query):
                values = groups[getattr(row, field_name)][bucket(row.date_of_sale)]
                values["loads"] += 1
                values["profit"] += float(row.profit or 0)
            kof[field_name] = [
                {
                    "name": name,
                    "series": [
                        {
                            "date": b,
                            "loads": values[b]["loads"],
                            "profit": round(values[b]["profit"], 2),
                        }
                        for b in buckets
                    ],
                }
                for name, values in sorted(
                    groups.items(), key=lambda item: item[0] or ""
                )
            ]
        speeds = []
        saved = self.first, self.last, self.start, self.end, dict(self.meta)
        first_week = self.first - timedelta(days=self.first.weekday())
        cursor = first_week
        while cursor < saved[1]:
            self.window(
                max(cursor, saved[0]), min(cursor + timedelta(days=7), saved[1])
            )
            speeds.append(
                {"week": cursor.isoformat(), "people": self.response_speed()["people"]}
            )
            cursor += timedelta(days=7)
        self.first, self.last, self.start, self.end, self.meta = saved
        return {
            **self.meta,
            "interval": interval,
            "event_retention_days": 180,
            "people": [
                {
                    "identity": who,
                    "series": [
                        {
                            "date": b,
                            "active_minutes": values[b]["active_minutes"],
                            "actions": values[b]["actions"],
                            "categories": {
                                key: values[b][key] for key in (*CATEGORIES, "other")
                            },
                        }
                        for b in buckets
                    ],
                    "devices": dict(devices[who]),
                }
                for who, values in sorted(counts.items())
            ],
            "device_basis": "active_minutes",
            "kof": kof,
            "feature_adoption": [
                {
                    "week": week,
                    "features": [
                        {
                            "feature": feature,
                            "distinct_people": len(adoption[week][feature]),
                        }
                        for feature in sorted(FEATURES)
                    ],
                }
                for week in sorted(
                    {
                        (
                            self.first
                            + timedelta(days=i)
                            - timedelta(days=(self.first + timedelta(days=i)).weekday())
                        ).isoformat()
                        for i in range(days)
                    }
                )
            ],
            "response_speed": speeds,
        }
