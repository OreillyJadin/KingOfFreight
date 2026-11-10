from contextlib import nullcontext
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from requests.exceptions import ConnectionError
from twilio.base.exceptions import TwilioRestException
from twilio.request_validator import RequestValidator

from app.config import Settings, get_settings
from app.integrations.sms import MockSmsProvider, TwilioSmsProvider, get_sms_provider
from app.models import TwilioConnection
from app.services.twilio_credentials import get_twilio_credentials

SID = "AC" + "a" * 32
TOKEN = "test-secret-token"
FROM = "+15551234567"
PAYLOAD = {"account_sid": SID, "auth_token": TOKEN, "from_number": FROM}
PATH = "/api/integrations/twilio/connection"


@pytest.fixture(autouse=True)
def twilio_settings(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "sms_provider", "auto")
    for field in ("twilio_account_sid", "twilio_auth_token", "twilio_from_number"):
        monkeypatch.setattr(settings, field, None)


def env_credentials(monkeypatch):
    for field, value in zip(
        ("twilio_account_sid", "twilio_auth_token", "twilio_from_number"),
        ("AC" + "b" * 32, "env-secret", "+15559876543"),
    ):
        monkeypatch.setattr(get_settings(), field, value)


def test_connection_precedence_encryption_and_removal(client, db, monkeypatch):
    assert client.get(PATH).json() == {
        "configured": False,
        "source": None,
        "account_sid": None,
        "from_number": None,
        "sms": "mock",
    }
    env_credentials(monkeypatch)
    assert client.get(PATH).json()["source"] == "env"
    response = client.put(PATH, json=PAYLOAD)
    assert response.status_code == 200
    assert response.json() == {
        "configured": True,
        "source": "app",
        "account_sid": "AC…aaaa",
        "from_number": "…4567",
        "sms": "twilio",
    }
    row = db.get(TwilioConnection, 1)
    assert row.token_encrypted != TOKEN and TOKEN not in row.token_encrypted
    assert get_twilio_credentials(db).auth_token == TOKEN
    for secret in (SID, TOKEN, FROM):
        assert secret not in response.text
        assert secret not in client.get(PATH).text
    assert client.get("/api/integrations/status").json()["sms"] == "twilio"
    assert client.get("/api/integrations/status").json()["twilio_configured"] is True
    assert (
        client.put(PATH, json={**PAYLOAD, "auth_token": "replacement"}).status_code
        == 200
    )
    assert get_twilio_credentials(db).auth_token == "replacement"
    assert client.delete(PATH).status_code == 204
    assert get_twilio_credentials(db).source == "env"
    assert client.get(PATH).json()["from_number"] == "…6543"
    for field in ("twilio_account_sid", "twilio_auth_token", "twilio_from_number"):
        monkeypatch.setattr(get_settings(), field, None)
    assert client.get(PATH).json()["configured"] is False


@pytest.mark.parametrize(
    "number", ["5551234567", "+0123456", "+1 5551234567", "+1234567890123456", ""]
)
def test_connection_rejects_invalid_from(client, number):
    assert client.put(PATH, json={**PAYLOAD, "from_number": number}).status_code == 422


def test_connection_rejects_blank_token_and_bad_sid(client):
    assert client.put(PATH, json={**PAYLOAD, "auth_token": "  "}).status_code == 422
    assert (
        client.put(PATH, json={**PAYLOAD, "account_sid": "invalid"}).status_code == 422
    )


@pytest.mark.parametrize(
    "mode,configured,expected",
    [
        ("auto", True, "twilio"),
        ("auto", False, "mock"),
        ("mock", True, "mock"),
        ("twilio", True, "twilio"),
    ],
)
def test_provider_selection_and_current_credentials(
    client, db, monkeypatch, mode, configured, expected
):
    monkeypatch.setattr(get_settings(), "sms_provider", mode)
    monkeypatch.setattr("app.integrations.sms.SessionLocal", lambda: nullcontext(db))
    constructor = MagicMock()
    constructor.return_value.messages.create.return_value = SimpleNamespace(
        sid="message-id"
    )
    monkeypatch.setattr("twilio.rest.Client", constructor)
    if configured:
        assert client.put(PATH, json=PAYLOAD).status_code == 200
    provider = get_sms_provider()
    assert client.get("/api/integrations/status").json()["sms"] == expected
    if expected == "twilio":
        assert isinstance(provider, TwilioSmsProvider)
        constructor.assert_called_with(SID, TOKEN)
        assert provider.send("+15550001111", "test") == "message-id"
        constructor.return_value.messages.create.assert_called_once_with(
            to="+15550001111", from_=FROM, body="test"
        )
        client.put(PATH, json={**PAYLOAD, "auth_token": "replacement"})
        get_sms_provider()
        constructor.assert_called_with(SID, "replacement")
    else:
        assert isinstance(provider, MockSmsProvider)
        constructor.assert_not_called()


def test_auto_ignores_incomplete_env_and_default_is_auto(db, monkeypatch):
    env_credentials(monkeypatch)
    monkeypatch.setattr(get_settings(), "twilio_auth_token", None)
    assert get_twilio_credentials(db) is None
    monkeypatch.setattr("app.integrations.sms.SessionLocal", lambda: nullcontext(db))
    assert isinstance(get_sms_provider(), MockSmsProvider)
    monkeypatch.delenv("SMS_PROVIDER", raising=False)
    assert Settings(_env_file=None).sms_provider == "auto"


@pytest.mark.parametrize("mode", ["auto", "twilio"])
@pytest.mark.parametrize("explicit_url", [True, False])
def test_signed_webhook_uses_public_or_forwarded_url(
    client, monkeypatch, mode, explicit_url
):
    assert client.put(PATH, json=PAYLOAD).status_code == 200
    monkeypatch.setattr(get_settings(), "sms_provider", mode)
    monkeypatch.setattr(
        get_settings(),
        "public_base_url",
        "https://explicit.example" if explicit_url else "",
    )
    path = "/api/webhooks/twilio/sms?source=twilio"
    public_url = f"https://{'explicit' if explicit_url else 'forwarded'}.example{path}"
    data = {"From": "+15550001111", "Body": "Hello", "MessageSid": "incoming-1"}
    headers = {"X-Forwarded-Proto": "https", "X-Forwarded-Host": "forwarded.example"}
    assert client.post(path, data=data, headers=headers).status_code == 403
    headers["X-Twilio-Signature"] = RequestValidator(TOKEN).compute_signature(
        public_url, data
    )
    assert client.post(path, data=data, headers=headers).status_code == 200
    data["Body"] = "Tampered"
    assert client.post(path, data=data, headers=headers).status_code == 403


def test_webhook_uses_host_when_public_url_is_not_explicit(client, monkeypatch):
    client.put(PATH, json=PAYLOAD)
    monkeypatch.delenv("PUBLIC_BASE_URL", raising=False)
    settings = Settings(_env_file=None)
    assert "public_base_url" not in settings.model_fields_set
    monkeypatch.setattr("app.routers.twilio.get_settings", lambda: settings)
    path = "/api/webhooks/twilio/sms"
    data = {"From": "+15550001111", "Body": "Hello"}
    signature = RequestValidator(TOKEN).compute_signature(
        "https://host.example" + path, data
    )
    headers = {
        "Host": "host.example",
        "X-Forwarded-Proto": "https",
        "X-Twilio-Signature": signature,
    }
    assert client.post(path, data=data, headers=headers).status_code == 200


def test_webhook_env_token_then_app_override(client, monkeypatch):
    env_credentials(monkeypatch)
    monkeypatch.setattr(get_settings(), "public_base_url", "https://public.example")
    path = "/api/webhooks/twilio/sms"
    data = {"From": "+15550001111", "Body": "Hello"}
    signature = RequestValidator("env-secret").compute_signature(
        "https://public.example" + path, data
    )
    headers = {"X-Twilio-Signature": signature}
    assert client.post(path, data=data, headers=headers).status_code == 200
    client.put(PATH, json=PAYLOAD)
    assert client.post(path, data=data, headers=headers).status_code == 403


def test_webhook_missing_credentials_with_explicit_twilio_rejects(client, monkeypatch):
    monkeypatch.setattr(get_settings(), "sms_provider", "twilio")
    assert (
        client.post("/api/webhooks/twilio/sms", data={"Body": "Hello"}).status_code
        == 403
    )


def test_test_sms_success_and_validation(client, monkeypatch):
    assert (
        client.post(
            "/api/integrations/twilio/test", json={"to": "+15550001111"}
        ).status_code
        == 503
    )
    assert (
        client.post("/api/integrations/twilio/test", json={"to": "invalid"}).status_code
        == 422
    )
    client.put(PATH, json=PAYLOAD)
    constructor = MagicMock()
    monkeypatch.setattr("twilio.rest.Client", constructor)
    response = client.post("/api/integrations/twilio/test", json={"to": "+15550001111"})
    assert response.json() == {"sent": True}
    constructor.assert_called_once_with(SID, TOKEN)
    assert constructor.return_value.messages.create.call_count == 1
    assert (
        constructor.return_value.messages.create.call_args.kwargs["to"]
        == "+15550001111"
    )


def test_test_sms_redacts_twilio_error(client, monkeypatch):
    client.put(PATH, json=PAYLOAD)
    constructor = MagicMock()
    constructor.return_value.messages.create.side_effect = TwilioRestException(
        400,
        "/messages",
        msg=f"Recipient not verified for {SID} token {TOKEN} from {FROM}",
        code=21608,
    )
    monkeypatch.setattr("twilio.rest.Client", constructor)
    response = client.post("/api/integrations/twilio/test", json={"to": "+15550001111"})
    assert response.status_code == 502
    assert "Recipient not verified" in response.json()["detail"]
    for secret in (SID, TOKEN, FROM):
        assert secret not in response.text
    constructor.return_value.messages.create.side_effect = ConnectionError(TOKEN)
    response = client.post("/api/integrations/twilio/test", json={"to": "+15550001111"})
    assert response.status_code == 502
    assert TOKEN not in response.text


def test_endpoints_require_auth(client):
    client.cookies.clear()
    assert client.get(PATH).status_code == 401
    assert client.put(PATH, json=PAYLOAD).status_code == 401
    assert client.delete(PATH).status_code == 401
    assert (
        client.post(
            "/api/integrations/twilio/test", json={"to": "+15550001111"}
        ).status_code
        == 401
    )
