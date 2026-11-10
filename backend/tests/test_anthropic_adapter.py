from contextlib import nullcontext
from types import SimpleNamespace
from unittest.mock import MagicMock

import anthropic
import httpx
import pytest

from app.config import get_settings
from app.integrations.llm import (
    AnthropicLlmProvider,
    FallbackLlmProvider,
    MockLlmProvider,
    get_llm_provider,
)
from app.models import AssistantConnection
from app.services.kof_credentials import encrypt_kof_password


class StubMessages:
    def __init__(self):
        self.request = None

    def create(self, **kwargs):
        self.request = kwargs
        return SimpleNamespace(
            content=[
                SimpleNamespace(
                    type="tool_use",
                    name="record_bol_fields",
                    input={
                        "pickup_city": "Chicago",
                        "weight_lbs": 34000,
                        "confidence": 0.8,
                    },
                )
            ]
        )


class StubClient:
    def __init__(self):
        self.messages = StubMessages()


def test_anthropic_bol_uses_pdf_prompt_forced_tool_and_validates():
    client = StubClient()
    provider = AnthropicLlmProvider(client)
    extracted = provider.extract_bol(b"%PDF-1.4 mock", "sample.pdf")
    request = client.messages.request
    assert request["system"].startswith("You are extracting shipment details")
    assert request["tool_choice"] == {"type": "tool", "name": "record_bol_fields"}
    document = request["messages"][0]["content"][0]
    assert document["type"] == "document" and document["source"]["type"] == "base64"
    assert extracted.pickup_city == "Chicago" and extracted.weight_lbs == 34000


@pytest.mark.parametrize(
    "app_key,env_key,expected",
    [
        ("saved-key", "bad-env", "saved-key"),
        ("saved-key", None, "saved-key"),
        (None, "env-key", "env-key"),
        (None, None, None),
    ],
)
def test_provider_resolves_shared_key(db, monkeypatch, app_key, env_key, expected):
    monkeypatch.setattr(get_settings(), "llm_provider", "anthropic")
    monkeypatch.setattr(get_settings(), "anthropic_api_key", env_key)
    monkeypatch.setattr("app.integrations.llm.SessionLocal", lambda: nullcontext(db))
    if app_key:
        db.add(AssistantConnection(id=1, key_encrypted=encrypt_kof_password(app_key)))
        db.commit()
    client = StubClient()
    constructor = MagicMock(return_value=client)
    monkeypatch.setattr("anthropic.Anthropic", constructor)
    provider = get_llm_provider()
    if expected is None:
        assert isinstance(provider, MockLlmProvider)
        constructor.assert_not_called()
    else:
        assert isinstance(provider, FallbackLlmProvider)
        constructor.assert_called_once_with(api_key=expected)
        assert provider.extract_bol(b"%PDF mock", "bol.pdf").pickup_city == "Chicago"
        client.messages.create = lambda **kwargs: SimpleNamespace(
            content=[
                SimpleNamespace(
                    type="tool_use",
                    name="record_status",
                    input={
                        "status": "in_transit",
                        "summary": "Rolling",
                        "confidence": 0.9,
                    },
                )
            ]
        )
        assert provider.parse_reply("Rolling", {}).status == "in_transit"
        constructor.reset_mock()
        AnthropicLlmProvider()
        constructor.assert_called_once_with(api_key=expected)


def test_mock_in_production_does_not_resolve_key(monkeypatch):
    monkeypatch.setattr(get_settings(), "env", "production")
    monkeypatch.setattr(get_settings(), "llm_provider", "mock")
    lookup = MagicMock(side_effect=AssertionError("Must not resolve credentials"))
    monkeypatch.setattr("app.integrations.llm._api_key", lookup)
    assert isinstance(get_llm_provider(), MockLlmProvider)
    lookup.assert_not_called()


@pytest.mark.parametrize("failure", ["auth", "connection", "invalid_tool"])
def test_provider_falls_back_for_bol_and_reply(failure, caplog):
    request = httpx.Request("POST", "https://api.anthropic.com")
    if failure == "auth":
        error = anthropic.AuthenticationError(
            "secret-key", response=httpx.Response(401, request=request), body=None
        )
    elif failure == "connection":
        error = anthropic.APIConnectionError(request=request)
    else:
        error = ValueError("secret-key")
    primary = MagicMock()
    primary.extract_bol.side_effect = error
    primary.parse_reply.side_effect = error
    provider = FallbackLlmProvider(primary)
    extracted = provider.extract_bol(b"%PDF invalid", "fallback.pdf")
    assert extracted.reference == "fallback"
    assert extracted.notes == "mock extraction"
    assert provider.parse_reply("Loaded", {"kind": "pickup"}).status == "picked_up"
    assert provider.parse_reply("", {}).status == "unclear"
    assert "secret-key" not in caplog.text


def test_provider_reads_changed_key_on_next_resolution(db, monkeypatch):
    monkeypatch.setattr(get_settings(), "llm_provider", "anthropic")
    monkeypatch.setattr(get_settings(), "anthropic_api_key", "env-key")
    monkeypatch.setattr("app.integrations.llm.SessionLocal", lambda: nullcontext(db))
    constructor = MagicMock(return_value=StubClient())
    monkeypatch.setattr("anthropic.Anthropic", constructor)
    get_llm_provider()
    constructor.assert_called_with(api_key="env-key")
    db.add(AssistantConnection(id=1, key_encrypted=encrypt_kof_password("new-key")))
    db.commit()
    get_llm_provider()
    constructor.assert_called_with(api_key="new-key")
