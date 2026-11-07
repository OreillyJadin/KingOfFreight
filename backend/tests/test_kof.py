from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import func, select

from app.integrations.kof.catalog import ListDefinition
from app.integrations.kof.client import KofClient, KofLoginError
from app.integrations.kof.mapping import derive_stage, map_load_row
from app.integrations.kof.parser import (
    ParsedList,
    parse_checkbox,
    parse_date,
    parse_local_datetime,
    parse_money,
    parse_phprunner_list,
    parse_row_key_or_order,
    parse_time,
)
from app.models import KofListSnapshot, KofLoad, KofSyncRun
from app.services.kof_sync import (
    SyncStats,
    _master_first_page,
    _order_numbers_descending,
    _upsert_master_rows,
)

FIXTURE = Path(__file__).parent / "fixtures" / "kof_master_synthetic.html"
STAGE_FIXTURE = Path(__file__).parent / "fixtures" / "kof_stage_synthetic.html"


def test_phprunner_parser_maps_synthetic_headers_cells_keys_and_notes():
    parsed = parse_phprunner_list(FIXTURE.read_text())
    assert parsed.row_keys == ["700001", "700002"]
    assert "Order #" in parsed.columns
    assert "Price" in parsed.columns
    first = parsed.rows[0]
    assert first["Order #"] == "700001"
    assert first["Customer"] == "Northwind Demo Co"
    assert first["Price"] == "$1,050.00"
    assert "Synthetic complete note" in first["Notes"]
    assert first["Confirmation Sent"] == "checked"
    assert parsed.rows[1]["Confirmation Sent"] == "unchecked"

    mapped = map_load_row(first, parsed.row_keys[0])
    assert mapped is not None
    assert mapped["order_no"] == 700001
    assert mapped["date_of_sale"] == date(2025, 3, 5)
    assert mapped["pick_at"] == datetime(2025, 3, 6, 14, 49, 39)
    assert mapped["pick_tz"] == "America/Chicago"
    assert mapped["weight"] == Decimal("44000")
    assert mapped["price"] == Decimal("1050.00")
    assert mapped["confirmation_sent"] is True


def test_phprunner_parser_reads_stage_rows_without_edit_links():
    parsed = parse_phprunner_list(STAGE_FIXTURE.read_text())
    assert parsed.columns == ["Order #", "Pick Date", "Customer"]
    assert len(parsed.rows) == 2
    assert parsed.row_keys == [None, None]
    assert [
        parse_row_key_or_order(row, key)
        for row, key in zip(parsed.rows, parsed.row_keys)
    ] == [
        700011,
        700012,
    ]


def test_phprunner_parser_accepts_empty_list_grid():
    parsed = parse_phprunner_list(
        '<table class="rnr-gridtable"><thead></thead><tbody></tbody></table>'
    )
    assert parsed.columns == []
    assert parsed.rows == []


def test_parser_handles_money_dates_times_and_checkbox_values():
    assert parse_money("$1,050.00") == Decimal("1050.00")
    assert parse_money("($50.25)") == Decimal("-50.25")
    assert parse_money("unknown") is None
    assert parse_date("03/05/2025") == date(2025, 3, 5)
    assert parse_date("2025-03-05") == date(2025, 3, 5)
    assert parse_date("not-a-date") is None
    assert parse_time("2:49:39 pm") == time(14, 49, 39)
    assert parse_time("not a time") is None
    assert parse_local_datetime("03/05/2025", "2:49 pm") == datetime(2025, 3, 5, 14, 49)
    assert parse_checkbox("checked") is True
    assert parse_checkbox("unchecked") is False
    assert parse_checkbox("maybe") is None


def test_stage_membership_and_status_precedence():
    assert (
        derive_stage(
            {"Paid": "Yes", "Delivery Status": "Delivered"},
            "awaiting_pickup",
        )
        == "awaiting_pickup"
    )
    assert (
        derive_stage(
            {
                "Paid": "Yes",
                "Billed": "Yes",
                "Delivery Status": "Delivered",
                "Pick Status": "In Transit",
            }
        )
        == "paid"
    )
    assert derive_stage({"Billed": "Yes", "Delivery Status": "Delivered"}) == "billed"
    assert derive_stage({"Delivery Status": "Delivered"}) == "delivered"
    assert derive_stage({"Pick Status": "Picked Up"}) == "in_transit"
    assert derive_stage({}) == "booked"


def test_late_uses_facility_local_appointments_and_unreached_status():
    from app.routers.kof import _is_late

    load = KofLoad(
        order_no=700201,
        stage="awaiting_pickup",
        pick_at=datetime(2025, 3, 1, 8),
        pick_tz="America/Chicago",
        pick_status="Not picked up",
        raw={"Pick Time": "8:00 am"},
    )
    now = datetime(2025, 3, 1, 15, tzinfo=timezone.utc)
    assert _is_late(load, now)

    load.pick_status = "Picked Up"
    assert not _is_late(load, now)

    load.pick_status = "Not picked up"
    load.raw = {}
    assert not _is_late(load, now)


def test_kof_client_does_not_follow_list_redirects():
    class RedirectSession:
        def request(self, method, url, **kwargs):
            assert kwargs["allow_redirects"] is False
            from requests import Response

            response = Response()
            response.status_code = 302
            response.url = url
            response.headers["Location"] = "https://example.test/unexpected"
            return response

    client = KofClient("synthetic-user", "synthetic-password")
    client.session = RedirectSession()
    with pytest.raises(KofLoginError, match="was redirected"):
        client._request("GET", "https://kingsoffreight.com/my_dispatch/list.php")


def test_kof_client_uses_phprunner_order_header_link():
    html = (
        '<table><tr class="rnr-toprow"><th>'
        '<span class="rnr-orderlink" data-href="Master_Record_Sheet_list.php?orderby=dOrder__">'
        "</span>Order #</th></tr></table>"
    )
    assert KofClient.order_number_sort_params(html) == {"orderby": "dOrder__"}


def test_master_first_page_uses_detected_sort_link_to_get_newest_first():
    header = (
        '<table><tr class="rnr-toprow"><th>'
        '<span class="rnr-orderlink" data-href="Master_Record_Sheet_list.php?orderby=dOrder__">'
        "</span>Order #</th></tr></table>"
    )
    ascending = ParsedList(
        ["Order #"],
        [{"Order #": "700001"}, {"Order #": "700002"}],
        [None, None],
    )
    descending = ParsedList(
        ["Order #"],
        [{"Order #": "700002"}, {"Order #": "700001"}],
        [None, None],
    )

    class SortClient:
        def __init__(self):
            self.calls = []

        def get_list_page(self, definition, page, *, page_size, extra_params=None):
            self.calls.append(extra_params)
            return header, descending if extra_params else ascending

        order_number_sort_params = staticmethod(KofClient.order_number_sort_params)

    client = SortClient()
    params, _, parsed = _master_first_page(client)
    assert params == {"orderby": "dOrder__"}
    assert client.calls == [None, {"orderby": "dOrder__"}]
    assert _order_numbers_descending(parsed)


def test_kof_client_logs_into_root_before_reposting_module_hidden_values():
    from requests import Response

    class LoginSession:
        def __init__(self):
            self.calls = []

        def request(self, method, url, **kwargs):
            self.calls.append((method, url, kwargs))
            response = Response()
            response.url = url
            response.headers = {}
            if url.endswith("/Lindex.php") and method == "GET":
                response.status_code = 200
                response._content = (
                    b'<form action="Lindex.php"><input name="csrf" value="root">'
                    b'<input name="txt_uname_email"><input name="txt_password"></form>'
                )
            elif url.endswith("/Lindex.php"):
                response.status_code = 302
                response.headers["Location"] = "/emphome.php"
                response._content = b""
            elif url.endswith("/emphome.php"):
                response.status_code = 200
                response._content = (
                    b'<form action="my_dispatch/login.php">'
                    b'<input type="hidden" name="module_token" value="synthetic">'
                    b"</form>"
                )
            else:
                response.status_code = 302
                response.headers["Location"] = (
                    "/my_dispatch/Master_Record_Sheet_list.php"
                )
                response._content = b""
            return response

    client = KofClient("synthetic-user", "synthetic-password")
    session = LoginSession()
    client.session = session
    client.login_module("my_dispatch")

    assert [
        (method, url.split("kingsoffreight.com")[-1])
        for method, url, _ in session.calls
    ] == [
        ("GET", "/Lindex.php"),
        ("POST", "/Lindex.php"),
        ("GET", "/emphome.php"),
        ("POST", "/my_dispatch/login.php"),
    ]
    assert all(call[2]["allow_redirects"] is False for call in session.calls)
    assert session.calls[1][2]["data"]["txt_uname_email"] == "synthetic-user"
    assert session.calls[3][2]["data"] == {"module_token": "synthetic"}


def test_kof_client_accepts_empty_phprunner_list():
    from requests import Response

    class EmptyListClient(KofClient):
        def login_module(self, _):
            return None

        def _request(self, method, url, **kwargs):
            response = Response()
            response.status_code = 200
            response.url = url
            response._content = (
                b'<table class="rnr-gridtable"><thead></thead><tbody></tbody></table>'
            )
            return response

    client = EmptyListClient("synthetic-user", "synthetic-password")
    _, parsed = client.get_list_page(
        ListDefinition(
            "fax_received",
            "Fax Received",
            "my_dispatch",
            "Fax_Received__list.php",
        )
    )
    assert parsed.columns == []
    assert parsed.rows == []


def test_kof_load_upsert_is_idempotent(db):
    parsed = parse_phprunner_list(FIXTURE.read_text())
    stats = SyncStats()
    first = _upsert_master_rows(db, parsed, {}, set(), stats, set())
    assert first == (2, 2)
    count = db.scalar(select(func.count(KofLoad.order_no)))
    assert count == 2

    second = _upsert_master_rows(db, parsed, {}, set(), SyncStats(), set())
    assert second == (2, 0)
    assert db.scalar(select(func.count(KofLoad.order_no))) == 2


def _seed_kof_load(
    db,
    *,
    order_no: int,
    date_of_sale: date,
    customer: str,
    carrier: str,
    stage: str,
    price: Decimal | None,
    cost: Decimal | None,
    profit: Decimal | None,
    is_deleted: bool = False,
    city: str = "Chicago",
    state: str = "IL",
    equipment: str = "Dry Van",
    on_time: bool | None = True,
) -> KofLoad:
    now = datetime.now(timezone.utc)
    load = KofLoad(
        order_no=order_no,
        date_of_sale=date_of_sale,
        customer=customer,
        carrier=carrier,
        mc="MC 123456",
        origin_city=city,
        origin_state=state,
        dest_city="Des Moines",
        dest_state="IA",
        pick_at=datetime.combine(date.today() - timedelta(days=1), time(8)),
        pick_tz="America/Chicago",
        delivery_at=datetime.combine(date.today() - timedelta(days=1), time(14)),
        drop_tz="America/Chicago",
        equipment=equipment,
        weight=Decimal("44000"),
        price=price,
        cost=cost,
        profit=profit,
        billed_status=None,
        paid_status=None,
        confirmation_sent=True,
        confirmation_received=True,
        confirmation_returned=None,
        pick_status="Picked Up" if stage != "awaiting_pickup" else "Not picked up",
        delivery_status="Not delivered",
        on_time=on_time,
        notes_text="11/06/2026 02:49:39 pm Demo User - Synthetic update",
        log_text="11/06/2026 02:49:39 pm Demo User - Synthetic log entry",
        booker="Demo Booker",
        rep="Demo Rep",
        stage=stage,
        is_deleted=is_deleted,
        raw={"Order #": str(order_no)},
        first_seen_at=now,
        synced_at=now,
    )
    db.add(load)
    return load


def test_kof_api_contract_shapes(client, db, monkeypatch):
    today = date.today()
    _seed_kof_load(
        db,
        order_no=700101,
        date_of_sale=today - timedelta(days=2),
        customer="Synthetic Customer A",
        carrier="Synthetic Carrier A",
        stage="in_transit",
        price=Decimal("1000.00"),
        cost=Decimal("800.00"),
        profit=Decimal("200.00"),
        city="Chicago",
        state="IL",
        on_time=True,
    )
    _seed_kof_load(
        db,
        order_no=700102,
        date_of_sale=today - timedelta(days=5),
        customer="Synthetic Customer B",
        carrier="Synthetic Carrier B",
        stage="awaiting_pickup",
        price=Decimal("1500.00"),
        cost=Decimal("1200.00"),
        profit=Decimal("300.00"),
        city="Madison",
        state="WI",
        equipment="Reefer",
        on_time=None,
    )
    _seed_kof_load(
        db,
        order_no=700103,
        date_of_sale=today - timedelta(days=3),
        customer="Deleted Synthetic Customer",
        carrier="Deleted Synthetic Carrier",
        stage="booked",
        price=Decimal("500.00"),
        cost=Decimal("400.00"),
        profit=Decimal("100.00"),
        is_deleted=True,
    )
    keys = (
        "leads_no_callback",
        "leads_callback",
        "priority_leads",
        "past_due",
        "charge_backs",
        "shipped_30",
        "not_shipped_30",
        "open_live_loads",
    )
    for key in keys:
        db.add(
            KofListSnapshot(
                key=key,
                label=f"Synthetic {key}",
                columns=["Reference", "Customer"],
                rows=[["DEMO-1", "Synthetic Customer"]],
                count=1,
                synced_at=datetime.now(timezone.utc),
            )
        )
    now = datetime.now(timezone.utc)
    db.add(
        KofSyncRun(
            kind="full",
            status="ok",
            started_at=now - timedelta(minutes=1),
            finished_at=now,
            loads_upserted=2,
            counts={"loads_upserted": 2},
        )
    )
    db.commit()

    date_query = f"start={today - timedelta(days=10)}&end={today}"
    summary = client.get(f"/api/kof/summary?{date_query}&interval=month")
    assert summary.status_code == 200, summary.text
    summary_body = summary.json()
    assert set(summary_body) == {"totals", "series", "by_equipment"}
    assert set(summary_body["totals"]) == {
        "loads",
        "revenue",
        "cost",
        "profit",
        "margin_pct",
        "avg_price",
        "avg_cost",
        "avg_profit",
        "on_time_pct",
    }
    assert summary_body["totals"]["loads"] == 2
    assert summary_body["totals"]["revenue"] == 2500
    assert summary_body["totals"]["profit"] == 500
    assert summary_body["totals"]["margin_pct"] == 20
    assert summary_body["totals"]["on_time_pct"] == 100
    assert summary_body["series"][0]["period"].endswith("-01")
    assert set(summary_body["by_equipment"][0]) == {
        "equipment",
        "loads",
        "avg_price",
        "avg_cost",
        "margin_pct",
    }

    lanes = client.get(f"/api/kof/lanes?{date_query}&level=state&min_loads=1&limit=10")
    assert lanes.status_code == 200, lanes.text
    assert set(lanes.json()[0]) == {
        "origin",
        "destination",
        "loads",
        "avg_price",
        "avg_cost",
        "avg_profit",
        "margin_pct",
        "min_cost",
        "max_cost",
        "last_cost",
        "last_date",
    }
    customers = client.get(f"/api/kof/customers?{date_query}")
    assert set(customers.json()[0]) == {
        "customer",
        "loads",
        "revenue",
        "cost",
        "profit",
        "margin_pct",
        "avg_price",
        "last_load_date",
    }
    carriers = client.get(f"/api/kof/carriers?{date_query}")
    assert set(carriers.json()[0]) == {
        "carrier",
        "mc",
        "loads",
        "total_cost",
        "avg_cost",
        "on_time_pct",
        "last_load_date",
        "top_lanes",
    }

    load_list = client.get(f"/api/kof/loads?q=700101&{date_query}&page=1&page_size=50")
    assert load_list.status_code == 200
    assert load_list.json()["total"] == 1
    item = load_list.json()["items"][0]
    assert set(item) == {
        "order_no",
        "date_of_sale",
        "customer",
        "branch",
        "carrier",
        "mc",
        "origin_city",
        "origin_state",
        "dest_city",
        "dest_state",
        "pick_at",
        "pick_tz",
        "delivery_at",
        "drop_tz",
        "equipment",
        "weight",
        "price",
        "cost",
        "profit",
        "stage",
        "billed_status",
        "paid_status",
        "late",
    }
    detail = client.get("/api/kof/loads/700101")
    assert detail.status_code == 200
    detail_body = detail.json()
    assert set(detail_body["shipper"]) == {
        "company",
        "address",
        "city",
        "state",
        "zip",
        "phone",
        "email",
    }
    assert set(detail_body["consignee"]) == set(detail_body["shipper"])
    assert set(detail_body["carrier_contact"]) == {
        "name",
        "phone",
        "email",
        "dispatch_contact",
        "dispatch_phone",
    }
    assert detail_body["notes"][0]["text"] == "Synthetic update"
    assert set(detail_body["log"][0]) == {"at", "text"}
    assert detail_body["raw"] == {"Order #": "700101"}
    assert client.get("/api/kof/loads/999999").status_code == 404

    tracking = client.get("/api/kof/tracking")
    assert tracking.status_code == 200
    assert [stage["key"] for stage in tracking.json()["stages"]] == [
        "awaiting_pickup",
        "in_transit",
        "awaiting_delivery",
    ]
    active = tracking.json()["stages"][1]["loads"][0]
    assert "last_note" in active and "hours_since_update" in active
    sales = client.get("/api/kof/sales")
    assert [item["key"] for item in sales.json()["lists"]] == list(keys)
    assert set(sales.json()["lists"][0]) == {
        "key",
        "label",
        "count",
        "columns",
        "rows",
    }

    monkeypatch.setenv("KOF_USERNAME", "synthetic-user")
    monkeypatch.setenv("KOF_PASSWORD", "synthetic-password")
    from app.config import get_settings

    get_settings.cache_clear()
    try:
        sync_status = client.get("/api/kof/sync")
        assert sync_status.status_code == 200
        sync_body = sync_status.json()
        assert set(sync_body) == {
            "configured",
            "enabled",
            "running",
            "load_count",
            "last_run",
            "last_success_at",
        }
        assert sync_body["configured"] is True
        assert sync_body["load_count"] == 3
        assert set(sync_body["last_run"]) == {
            "id",
            "kind",
            "status",
            "started_at",
            "finished_at",
            "loads_upserted",
            "error",
        }
        from app.routers import kof as kof_router

        monkeypatch.setattr(kof_router, "start_sync", lambda kind: 42)
        started = client.post("/api/kof/sync?kind=full")
        assert started.status_code == 202
        assert started.json() == {"started": True}
        monkeypatch.setattr(kof_router, "start_sync", lambda kind: None)
        assert client.post("/api/kof/sync?kind=incremental").status_code == 409
    finally:
        monkeypatch.delenv("KOF_USERNAME")
        monkeypatch.delenv("KOF_PASSWORD")
        get_settings.cache_clear()
    assert client.post("/api/kof/sync?kind=full").status_code == 400
