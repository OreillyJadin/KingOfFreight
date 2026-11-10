import pytest

from app.config import Settings, get_settings
from app.models import AssistantConnection
from app.services.kof_credentials import encrypt_kof_password


def test_default_llm_mode_is_auto_but_tests_use_mock(monkeypatch):
    assert get_settings().llm_provider == "mock"
    monkeypatch.delenv("LLM_PROVIDER")
    assert Settings(_env_file=None).llm_provider == "auto"


@pytest.mark.parametrize(
    "mode,app_key,env_key,expected",
    [
        ("auto", None, None, "mock"),
        ("auto", "saved-secret", None, "anthropic"),
        ("auto", None, "env-secret", "anthropic"),
        ("auto", "saved-secret", "env-secret", "anthropic"),
        ("mock", "saved-secret", "env-secret", "mock"),
        ("anthropic", None, None, "mock"),
        ("anthropic", "saved-secret", None, "anthropic"),
    ],
)
def test_status_reports_llm_selection(
    client, db, monkeypatch, mode, app_key, env_key, expected
):
    settings = get_settings()
    monkeypatch.setattr(settings, "llm_provider", mode)
    monkeypatch.setattr(settings, "anthropic_api_key", env_key)
    monkeypatch.setattr(settings, "sms_provider", "mock")
    for field in ("twilio_account_sid", "twilio_auth_token", "twilio_from_number"):
        monkeypatch.setattr(settings, field, None)
    if app_key:
        db.add(AssistantConnection(id=1, key_encrypted=encrypt_kof_password(app_key)))
        db.commit()
    response = client.get("/api/integrations/status")
    assert response.status_code == 200
    assert response.json() == {
        "llm": expected,
        "sms": "mock",
        "twilio_configured": False,
        "email": "mock",
        "email_account": None,
    }
    assert "secret" not in response.text


@pytest.mark.parametrize(
    "provider,credentials,configured",
    [
        ("twilio", ("sid-secret", "token-secret", "+15555555555"), True),
        ("mock", ("sid-secret", "token-secret", "+15555555555"), True),
        ("twilio", ("sid-secret", None, "+15555555555"), False),
        ("twilio", ("sid-secret", "token-secret", "  "), False),
    ],
)
def test_status_reports_sms_without_contacting_twilio(
    client, monkeypatch, provider, credentials, configured
):
    settings = get_settings()
    monkeypatch.setattr(settings, "sms_provider", provider)
    for field, value in zip(
        ("twilio_account_sid", "twilio_auth_token", "twilio_from_number"), credentials
    ):
        monkeypatch.setattr(settings, field, value)
    response = client.get("/api/integrations/status")
    assert response.status_code == 200
    assert response.json() == {
        "llm": "mock",
        "sms": provider,
        "twilio_configured": configured,
        "email": "mock",
        "email_account": None,
    }
    assert "secret" not in response.text
    assert "+15555555555" not in response.text


def test_status_requires_auth(client):
    client.cookies.clear()
    assert client.get("/api/integrations/status").status_code == 401
