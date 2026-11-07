from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
import re
import threading
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import SessionLocal
from app.integrations.kof.catalog import (
    BRANCHES_LIST,
    CUSTOMERS_LIST,
    DELETED_LIST,
    MASTER_LIST,
    SALES_LISTS,
    STAGE_LISTS,
    ListDefinition,
)
from app.integrations.kof.client import KofClient, KofLoginError, KofSiteError
from app.integrations.kof.mapping import (
    MAPPED_SOURCE_LABELS,
    derive_stage,
    map_load_row,
)
from app.integrations.kof.parser import (
    ParsedList,
    parse_date,
    parse_first,
    parse_money,
    parse_row_key_or_order,
    strip_more_suffix,
)
from app.models import (
    KofBranch,
    KofCustomer,
    KofListSnapshot,
    KofLoad,
    KofSyncRun,
    utcnow,
)

PAGE_SIZE = 500
MAX_PAGES = 100
MAX_FULLTEXT_LOADS_PER_SYNC = 60
FULLTEXT_STAGES = ("confirmation", "awaiting_pickup", "in_transit", "awaiting_delivery")
_SYNC_LOCK = threading.Lock()


@dataclass
class SyncStats:
    loads_upserted: int = 0
    changed_rows: int = 0
    master_pages: int = 0
    list_counts: dict[str, int] = field(default_factory=dict)
    unparseable: dict[str, int] = field(
        default_factory=lambda: {
            "price": 0,
            "cost": 0,
            "date_of_sale": 0,
            "pick_date": 0,
            "delivery_date": 0,
        }
    )
    fulltext_loads_considered: int = 0
    fulltext_loads_fetched: int = 0
    fulltext_fields_fetched: int = 0
    fulltext_errors: int = 0
    mapped_labels: set[str] = field(default_factory=set)
    raw_only_labels: set[str] = field(default_factory=set)
    duration_seconds: float = 0

    def as_dict(self) -> dict[str, Any]:
        return {
            "loads_upserted": self.loads_upserted,
            "changed_rows": self.changed_rows,
            "master_pages": self.master_pages,
            "list_counts": self.list_counts,
            "unparseable": self.unparseable,
            "fulltext_loads_considered": self.fulltext_loads_considered,
            "fulltext_loads_fetched": self.fulltext_loads_fetched,
            "fulltext_fields_fetched": self.fulltext_fields_fetched,
            "fulltext_errors": self.fulltext_errors,
            "mapped_labels": sorted(self.mapped_labels),
            "raw_only_labels": sorted(self.raw_only_labels),
            "duration_seconds": self.duration_seconds,
        }


@dataclass(frozen=True)
class FetchedList:
    definition: ListDefinition
    columns: list[str]
    rows: list[dict[str, str]]
    row_keys: list[str | None]


def _normalized_label(label: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", label.lower())


def _count_parse_errors(row: dict[str, str], stats: SyncStats) -> None:
    value = parse_first(row, ("Price", "Revenue"))
    if value and parse_money(value) is None:
        stats.unparseable["price"] += 1
    value = parse_first(row, ("Cost", "Carrier Cost"))
    if value and parse_money(value) is None:
        stats.unparseable["cost"] += 1
    for key, labels in (
        ("date_of_sale", ("Date Of Sale", "Date of Sale", "Sale Date")),
        ("pick_date", ("Pick Date", "Pickup Date")),
        ("delivery_date", ("Delivery Date", "Drop Date")),
    ):
        value = parse_first(row, labels)
        if value and parse_date(value) is None:
            stats.unparseable[key] += 1


def _fetch_all_list(
    client: KofClient,
    definition: ListDefinition,
    *,
    page_params: dict[str, str] | None = None,
) -> FetchedList:
    columns: list[str] = []
    rows: list[dict[str, str]] = []
    row_keys: list[str | None] = []
    for _, _, parsed in client.iter_list_pages(
        definition,
        page_size=PAGE_SIZE,
        max_pages=MAX_PAGES,
        first_page_params=page_params,
    ):
        if not columns:
            columns = parsed.columns
        rows.extend(parsed.rows)
        row_keys.extend(parsed.row_keys)
    return FetchedList(definition, columns, rows, row_keys)


def _fetch_small_lists(
    client: KofClient, stats: SyncStats
) -> tuple[dict[str, str], set[int], dict[str, FetchedList]]:
    membership: dict[str, str] = {}
    deleted: set[int] = set()
    fetched: dict[str, FetchedList] = {}

    for stage, definition in STAGE_LISTS:
        result = _fetch_all_list(client, definition)
        fetched[definition.key] = result
        stats.list_counts[definition.key] = len(result.rows)
        for row, row_key in zip(result.rows, result.row_keys, strict=True):
            order_no = parse_row_key_or_order(row, row_key)
            if order_no is not None:
                membership.setdefault(str(order_no), stage)

    result = _fetch_all_list(client, DELETED_LIST)
    fetched[DELETED_LIST.key] = result
    stats.list_counts[DELETED_LIST.key] = len(result.rows)
    for row, row_key in zip(result.rows, result.row_keys, strict=True):
        order_no = parse_row_key_or_order(row, row_key)
        if order_no is not None:
            deleted.add(order_no)

    for definition in SALES_LISTS:
        result = _fetch_all_list(client, definition)
        fetched[definition.key] = result
        stats.list_counts[definition.key] = len(result.rows)

    for definition in (CUSTOMERS_LIST, BRANCHES_LIST):
        result = _fetch_all_list(client, definition)
        fetched[definition.key] = result
        stats.list_counts[definition.key] = len(result.rows)

    return membership, deleted, fetched


def _row_name(row: dict[str, str], columns: Iterable[str]) -> str | None:
    names = ("Customer", "Customer Name", "Company", "Name") if columns else ()
    return parse_first(row, names)


def _save_snapshot(db: Session, result: FetchedList, now: datetime) -> None:
    snapshot_rows = [
        [row.get(column, "") for column in result.columns] for row in result.rows
    ]
    snapshot = db.get(KofListSnapshot, result.definition.key)
    if snapshot is None:
        snapshot = KofListSnapshot(key=result.definition.key)
        db.add(snapshot)
    snapshot.label = result.definition.label
    snapshot.columns = result.columns
    snapshot.rows = snapshot_rows
    snapshot.count = len(snapshot_rows)
    snapshot.synced_at = now


def _upsert_directory_lists(
    db: Session, fetched: dict[str, FetchedList], now: datetime
) -> None:
    for definition, model, key_field in (
        (CUSTOMERS_LIST, KofCustomer, "customer_key"),
        (BRANCHES_LIST, KofBranch, "branch_key"),
    ):
        result = fetched[definition.key]
        for row, row_key in zip(result.rows, result.row_keys, strict=True):
            name = _row_name(row, result.columns)
            key = row_key or name
            if not key:
                continue
            record = db.get(model, key)
            if record is None:
                record = model(**{key_field: key})
                db.add(record)
            record.name = name
            record.raw = row
            record.synced_at = now


def _refresh_stage_membership(
    db: Session, membership: dict[str, str], deleted: set[int], now: datetime
) -> set[int]:
    changed: set[int] = set()
    for load in db.scalars(select(KofLoad)):
        stage = membership.get(str(load.order_no)) or derive_stage(
            load.raw,
            billed_status=load.billed_status,
            paid_status=load.paid_status,
            invoice_no=load.invoice_no,
        )
        is_deleted = load.order_no in deleted
        if load.stage != stage or load.is_deleted != is_deleted:
            changed.add(load.order_no)
            load.stage = stage
            load.is_deleted = is_deleted
            load.synced_at = now
    return changed


def _upsert_master_rows(
    db: Session,
    parsed: ParsedList,
    membership: dict[str, str],
    deleted: set[int],
    stats: SyncStats,
    stage_changes: set[int],
) -> tuple[int, int]:
    now = utcnow()
    page_upserted = 0
    page_changed = 0
    for label in parsed.columns:
        if _normalized_label(label) in MAPPED_SOURCE_LABELS:
            stats.mapped_labels.add(label)
        else:
            stats.raw_only_labels.add(label)

    for row, row_key in zip(parsed.rows, parsed.row_keys, strict=True):
        _count_parse_errors(row, stats)
        candidate = parse_row_key_or_order(row, row_key)
        if candidate is None:
            continue
        data = map_load_row(
            row,
            row_key,
            membership_stage=membership.get(str(candidate)),
            is_deleted=candidate in deleted,
            synced_at=now,
        )
        if data is None:
            continue
        current = db.get(KofLoad, candidate)
        changed = current is None or candidate in stage_changes
        if current is None:
            current = KofLoad(**data)
            db.add(current)
            changed = True
        else:
            for key, value in data.items():
                if key != "synced_at" and getattr(current, key) != value:
                    changed = True
                setattr(current, key, value)
        page_upserted += 1
        if changed:
            page_changed += 1
    db.commit()
    stats.loads_upserted += page_upserted
    stats.changed_rows += page_changed
    return page_upserted, page_changed


def _refresh_active_fulltext(db: Session, client: KofClient, stats: SyncStats) -> None:
    get_fulltext = getattr(client, "get_fulltext", None)
    if not callable(get_fulltext):
        return
    loads = db.scalars(
        select(KofLoad)
        .where(
            KofLoad.is_deleted.is_(False),
            KofLoad.stage.in_(FULLTEXT_STAGES),
        )
        .order_by(KofLoad.order_no.desc())
        .limit(MAX_FULLTEXT_LOADS_PER_SYNC)
    ).all()
    stats.fulltext_loads_considered = len(loads)
    for load in loads:
        raw = dict(load.raw or {})
        fetched_for_load = False
        for label, attribute in (("Notes", "notes_text"), ("log", "log_text")):
            matching_labels = {
                "notes": {"notes", "notescomments"},
                "log": {"log", "loadlog"},
            }[label.lower()]
            preview = next(
                (
                    value
                    for raw_label, value in raw.items()
                    if _normalized_label(raw_label) in matching_labels
                ),
                None,
            )
            try:
                text = get_fulltext(load.order_no, label)
            except KofSiteError:
                stats.fulltext_errors += 1
                if preview is not None:
                    setattr(load, attribute, strip_more_suffix(preview) or "")
                if fetched_for_load:
                    stats.fulltext_loads_fetched += 1
                db.commit()
                return
            if text is None:
                if preview is not None:
                    setattr(load, attribute, strip_more_suffix(preview) or "")
                continue
            cleaned = strip_more_suffix(text) or ""
            setattr(load, attribute, cleaned)
            stats.fulltext_fields_fetched += 1
            fetched_for_load = True
        if fetched_for_load:
            stats.fulltext_loads_fetched += 1
    db.commit()


def _order_numbers_descending(parsed: ParsedList) -> bool:
    numbers = [
        number
        for row, row_key in zip(parsed.rows, parsed.row_keys, strict=True)
        if (number := parse_row_key_or_order(row, row_key)) is not None
    ]
    return all(left >= right for left, right in zip(numbers, numbers[1:]))


def _master_first_page(
    client: KofClient,
) -> tuple[dict[str, str], str, ParsedList]:
    params: dict[str, str] = {}
    html, parsed = client.get_list_page(MASTER_LIST, page=1, page_size=PAGE_SIZE)
    detected = client.order_number_sort_params(html)
    if not parsed.rows:
        raise KofSiteError("Master Record Sheet returned no load rows")
    if _order_numbers_descending(parsed):
        return params, html, parsed
    if detected != params:
        html, parsed = client.get_list_page(
            MASTER_LIST,
            page=1,
            page_size=PAGE_SIZE,
            extra_params=detected,
        )
        params = detected
    if not parsed.rows:
        raise KofSiteError("Master Record Sheet returned no load rows")
    if _order_numbers_descending(parsed):
        return params, html, parsed
    raise KofSiteError("Could not verify newest-first ordering for Master Record Sheet")


def _iter_master_pages(
    client: KofClient,
    sort_params: dict[str, str],
    first_html: str,
    first_page: ParsedList,
    *,
    full: bool,
) -> Iterable[tuple[int, str, ParsedList]]:
    yield 1, first_html, first_page
    if len(first_page.rows) < PAGE_SIZE:
        return
    max_pages = MAX_PAGES if full else 2
    for page in range(2, max_pages + 1):
        html, parsed = client.get_list_page(
            MASTER_LIST,
            page,
            page_size=PAGE_SIZE,
            extra_params=sort_params,
        )
        yield page, html, parsed
        if len(parsed.rows) < PAGE_SIZE:
            return
    if full:
        raise KofSiteError("Master Record Sheet exceeded the pagination safety limit")


def sync_with_client(
    db: Session,
    client: KofClient,
    kind: str,
    *,
    capture_dir: str | Path | None = None,
) -> SyncStats:
    if kind not in {"full", "incremental"}:
        raise ValueError("Sync kind must be full or incremental")
    stats = SyncStats()
    if capture_dir is not None:
        client.capture_dir = Path(capture_dir)

    membership, deleted, fetched = _fetch_small_lists(client, stats)
    now = utcnow()
    _upsert_directory_lists(db, fetched, now)
    for definition in SALES_LISTS:
        _save_snapshot(db, fetched[definition.key], now)
    stage_changes = _refresh_stage_membership(db, membership, deleted, now)
    db.commit()

    sort_params, first_html, first_page = _master_first_page(client)
    master_pages = _iter_master_pages(
        client,
        sort_params,
        first_html,
        first_page,
        full=kind == "full",
    )
    for page, _, parsed in master_pages:
        stats.master_pages += 1
        _, changed = _upsert_master_rows(
            db, parsed, membership, deleted, stats, stage_changes
        )
        if kind == "incremental" and page == 1 and changed == 0:
            break
        if kind == "incremental" and page == 2:
            break
    _refresh_active_fulltext(db, client, stats)
    return stats


def _sync_error_message(error: Exception) -> str:
    if isinstance(error, KofLoginError):
        return str(error)
    if isinstance(error, KofSiteError):
        return str(error)
    return f"Sync failed ({type(error).__name__})"


def _execute_sync_run(
    run_id: int, kind: str, capture_dir: str | Path | None = None
) -> None:
    started = datetime.now(timezone.utc)
    db = SessionLocal()
    try:
        settings = get_settings()
        with KofClient(
            settings.kof_username or "",
            settings.kof_password or "",
            settings.kof_base_url,
            capture_dir=capture_dir,
        ) as client:
            stats = sync_with_client(db, client, kind)
        stats.duration_seconds = (datetime.now(timezone.utc) - started).total_seconds()
        run = db.get(KofSyncRun, run_id)
        if run is not None:
            run.status = "ok"
            run.finished_at = datetime.now(timezone.utc)
            run.loads_upserted = stats.loads_upserted
            run.counts = stats.as_dict()
            run.error = None
            db.commit()
    except Exception as exc:
        db.rollback()
        run = db.get(KofSyncRun, run_id)
        if run is not None:
            run.status = "error"
            run.finished_at = datetime.now(timezone.utc)
            run.error = _sync_error_message(exc)
            db.commit()
    finally:
        db.close()
        _SYNC_LOCK.release()


def start_sync(kind: str, *, capture_dir: str | Path | None = None) -> int | None:
    settings = get_settings()
    if not settings.kof_username or not settings.kof_password:
        raise ValueError("KOF sync credentials are not configured")
    if not _SYNC_LOCK.acquire(blocking=False):
        return None
    db = SessionLocal()
    try:
        active = db.scalar(
            select(KofSyncRun.id).where(KofSyncRun.status == "running").limit(1)
        )
        if active is not None:
            _SYNC_LOCK.release()
            return None
        run = KofSyncRun(
            kind=kind,
            status="running",
            started_at=datetime.now(timezone.utc),
            loads_upserted=0,
            counts={},
        )
        db.add(run)
        db.commit()
        db.refresh(run)
        worker = threading.Thread(
            target=_execute_sync_run,
            args=(run.id, kind, capture_dir),
            name=f"kof-sync-{run.id}",
            daemon=True,
        )
        worker.start()
        return run.id
    except IntegrityError:
        db.rollback()
        _SYNC_LOCK.release()
        return None
    except Exception:
        db.rollback()
        _SYNC_LOCK.release()
        raise
    finally:
        db.close()


def run_scheduled_kof_sync() -> None:
    settings = get_settings()
    if (
        not settings.kof_sync_enabled
        or not settings.kof_username
        or not settings.kof_password
    ):
        return
    now = datetime.now(timezone.utc)
    kind = "incremental"
    if now.hour == settings.kof_full_sync_hour_utc:
        with SessionLocal() as db:
            successful_full_today = db.scalar(
                select(KofSyncRun.id)
                .where(
                    KofSyncRun.kind == "full",
                    KofSyncRun.status == "ok",
                    KofSyncRun.started_at
                    >= now.replace(hour=0, minute=0, second=0, microsecond=0),
                )
                .limit(1)
            )
        if successful_full_today is None:
            kind = "full"
    try:
        start_sync(kind)
    except ValueError:
        return
