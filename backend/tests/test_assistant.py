from types import SimpleNamespace
from unittest.mock import MagicMock

import anthropic
import httpx
import pytest

from app.config import get_settings
from app.models import (
    AssistantConnection,
    Communication,
    KofLoad,
    Load,
    StatusUpdate,
    utcnow,
)
from app.services.assistant_credentials import get_assistant_key
from app.services.assistant_tools import AssistantTools
from app.integrations.kof.client import KofSiteError


@pytest.fixture(autouse=True)
def no_env_key(monkeypatch):
    monkeypatch.setattr(get_settings(), "anthropic_api_key", None)


def test_search_identifiers(db, load_data):
    load, _ = load_data
    db.add_all(
        [
            KofLoad(
                order_no=101,
                po="PO-123",
                raw={"BOL #": "RAW-456"},
                notes_text="BOL NOTE-789 loaded",
            ),
            KofLoad(order_no=102, po="PO-123", is_deleted=True),
            Communication(
                load_id=load.id,
                channel="email",
                direction="inbound",
                extracted={"reference_numbers": {"BOL": "OP-321"}},
            ),
        ]
    )
    db.commit()
    tools = AssistantTools(db)
    for query, field in [
        ("PO-123", "po"),
        ("RAW-456", "raw"),
        ("NOTE-789", "notes_text"),
    ]:
        rows = tools.search_loads(query)["loads"]
        assert len(rows) == 1
        assert rows[0]["source"] == "kof"
        assert field in rows[0]["matched_fields"]
    rows = tools.search_loads("OP-321")["loads"]
    assert rows[0]["source"] == "operational"
    assert rows[0]["exact_identifier_match"]
    assert tools.search_loads("missing")["loads"] == []
    assert tools.search_loads(" ")["loads"] == []


def test_exact_extracted_identifier_ranks_first(db, load_data):
    load, _ = load_data
    db.add(
        Communication(
            load_id=load.id,
            channel="email",
            direction="inbound",
            extracted={"reference_numbers": {"PO": "123"}},
        )
    )
    db.add_all([Load(reference=f"123-partial-{index}") for index in range(25)])
    db.commit()
    result = AssistantTools(db).search_loads("123")["loads"]
    assert result[0]["id"] == load.id
    assert result[0]["exact_identifier_match"]


def test_status_confirmed_and_proposed(db, load_data):
    load, _ = load_data
    db.add_all(
        [
            StatusUpdate(
                load_id=load.id, status="picked_up", source="manual", applied=True
            ),
            StatusUpdate(
                load_id=load.id, status="delivered", source="checkin", applied=False
            ),
        ]
    )
    db.commit()
    result = AssistantTools(db).get_load_status("operational", load.id)
    assert {row["status"]: row["confirmed"] for row in result["status_updates"]} == {
        "picked_up": True,
        "delivered": False,
    }
    assert result["status"] == "posted"
    assert AssistantTools(db).get_load_status("kof", 999) == {"error": "Load not found"}


def test_connection_encrypted_and_app_precedence(client, db, monkeypatch, admin_login):
    assert client.get("/api/assistant/connection").json() == {
        "configured": False,
        "source": None,
    }
    assert client.put(
        "/api/assistant/connection", json={"api_key": "test-app-key"}
    ).json() == {"configured": True, "source": "app"}
    row = db.get(AssistantConnection, 1)
    assert row.key_encrypted != "test-app-key"
    assert "test-app-key" not in row.key_encrypted
    assert get_assistant_key(db) == ("test-app-key", "app")
    assert "test-app-key" not in client.get("/api/assistant/connection").text
    monkeypatch.setattr(get_settings(), "anthropic_api_key", "test-env-key")
    assert get_assistant_key(db) == ("test-app-key", "app")
    assert client.get("/api/assistant/connection").json() == {
        "configured": True,
        "source": "app",
    }
    assert client.put(
        "/api/assistant/connection", json={"api_key": "other"}
    ).json() == {"configured": True, "source": "app"}
    assert get_assistant_key(db) == ("other", "app")
    assert client.delete("/api/assistant/connection").status_code == 204
    assert get_assistant_key(db) == ("test-env-key", "env")
    assert client.get("/api/assistant/connection").json() == {
        "configured": True,
        "source": "env",
    }
    monkeypatch.setattr(get_settings(), "anthropic_api_key", None)
    assert get_assistant_key(db) is None
    assert (
        client.put("/api/assistant/connection", json={"api_key": "   "}).status_code
        == 422
    )


def test_missing_key_and_auth(client):
    payload = {"messages": [{"role": "user", "content": "Where is PO 123?"}]}
    assert client.post("/api/assistant/chat", json=payload).status_code == 503
    client.cookies.clear()
    assert client.post("/api/assistant/chat", json=payload).status_code == 401
    for method in (client.get, client.delete):
        assert method("/api/assistant/connection").status_code == 401
    assert (
        client.put("/api/assistant/connection", json={"api_key": "x"}).status_code
        == 401
    )


def fake_provider(monkeypatch, responses):
    provider = MagicMock()
    provider.__enter__.return_value = provider
    provider.messages.create.side_effect = responses
    monkeypatch.setattr(
        "app.routers.assistant.anthropic.Anthropic", lambda **kwargs: provider
    )
    monkeypatch.setattr(get_settings(), "anthropic_api_key", "fake")
    return provider


def block(**kwargs):
    result = SimpleNamespace(**kwargs)
    result.model_dump = lambda: kwargs
    return result


def test_chat_tool_loop(client, db, monkeypatch):
    db.add(KofLoad(order_no=123, po="TEST-PO", stage="in_transit"))
    db.commit()
    provider = fake_provider(
        monkeypatch,
        [
            SimpleNamespace(
                content=[
                    block(
                        type="tool_use",
                        id="tool1",
                        name="search_loads",
                        input={"query": "TEST-PO"},
                    )
                ]
            ),
            SimpleNamespace(
                content=[
                    block(type="text", text="KOF order #123 is recorded in transit.")
                ]
            ),
        ],
    )
    response = client.post(
        "/api/assistant/chat",
        json={"messages": [{"role": "user", "content": "Did TEST-PO load?"}]},
    )
    assert response.status_code == 200
    assert response.json() == {
        "reply": "KOF order #123 is recorded in transit.",
        "loads": [{"source": "kof", "id": 123, "label": "Order #123"}],
        "actions": [],
    }
    assert provider.messages.create.call_count == 2
    assert "tool_result" in str(provider.messages.create.call_args.kwargs["messages"])
    assert "Broker timezone" in provider.messages.create.call_args.kwargs["system"]


@pytest.mark.parametrize(
    "error_type,status,message,expected",
    [
        (
            anthropic.AuthenticationError,
            401,
            "invalid key",
            "Claude API key was rejected",
        ),
        (anthropic.PermissionDeniedError, 403, "denied", "does not have permission"),
        (anthropic.NotFoundError, 404, "missing", "model '{model}' not available"),
        (anthropic.BadRequestError, 400, "Credit balance is too low", "out of credits"),
        (anthropic.BadRequestError, 400, "Billing issue", "out of credits"),
        (anthropic.BadRequestError, 400, "invalid request", "AI provider"),
        (anthropic.BadRequestError, 400, "", "AI provider"),
        (anthropic.RateLimitError, 429, "slow down", "rate limited"),
        (anthropic.APIConnectionError, None, "", "unreachable"),
        (anthropic.APITimeoutError, None, "", "unreachable"),
        (anthropic.InternalServerError, 500, "failed", "AI provider"),
    ],
)
def test_provider_error(
    client, monkeypatch, caplog, error_type, status, message, expected
):
    request = httpx.Request("POST", "https://api.anthropic.com")
    secret = "secret-key-must-not-leak"
    if status is None:
        error = error_type(request=request)
    else:
        error = error_type(
            message + secret,
            response=httpx.Response(status, request=request),
            body={"error": {"message": message + secret}},
        )
    fake_provider(monkeypatch, [error])
    response = client.post(
        "/api/assistant/chat", json={"messages": [{"role": "user", "content": "hello"}]}
    )
    assert response.status_code == 502
    assert (
        expected.format(model=get_settings().anthropic_model)
        in response.json()["detail"]
    )
    assert secret not in response.text
    assert secret not in caplog.text
    assert f"{error_type.__name__} status={status}" in caplog.text


def test_history_bounds(client):
    assert client.post("/api/assistant/chat", json={"messages": []}).status_code == 422
    assert (
        client.post(
            "/api/assistant/chat",
            json={"messages": [{"role": "user", "content": "a" * 8001}]},
        ).status_code
        == 422
    )


def test_refresh_notes(db, monkeypatch):
    db.add(KofLoad(order_no=123, notes_text="old"))
    db.commit()
    tools = AssistantTools(db)
    monkeypatch.setattr(
        "app.services.assistant_tools.get_kof_credentials", lambda db: None
    )
    assert "credentials" in tools.refresh_kof_notes(123)["error"]
    monkeypatch.setattr(
        "app.services.assistant_tools.get_kof_credentials",
        lambda db: ("user", "pass", "app"),
    )
    client = MagicMock()
    client.__enter__.return_value = client
    client.get_fulltext.side_effect = ["2026-11-09 09:30:00 Carrier - Loaded", ""]
    factory = MagicMock(return_value=client)
    monkeypatch.setattr("app.services.assistant_tools.KofClient", factory)
    result = tools.refresh_kof_notes(123)
    assert "Loaded" in result["notes"][0]["text"]
    assert db.get(KofLoad, 123).notes_text.endswith("Loaded")
    assert factory.call_args.kwargs["timeout"] == (5, 10)
    assert client.get_fulltext.call_count == 2
    client.get_fulltext.side_effect = KofSiteError("timeout")
    assert "timed out" in tools.refresh_kof_notes(123)["error"]
    assert db.get(KofLoad, 123).notes_text.endswith("Loaded")
    assert "not found" in tools.refresh_kof_notes(999)["error"]


def test_list_and_sync(db, load_data):
    db.add(
        KofLoad(
            order_no=123,
            stage="in_transit",
            notes_text=utcnow().strftime("%Y-%m-%d %H:%M:%S") + " Carrier - loaded",
        )
    )
    db.commit()
    tools = AssistantTools(db)
    assert len(tools.list_loads()["loads"]) == 2
    assert tools.list_loads(stage="unknown")["loads"] == []
    assert tools.list_loads(no_update_hours=-1).get("error")
    assert tools.get_sync_status() == {"last_successful_kof_sync_at": None}
