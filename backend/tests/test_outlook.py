import time
from contextlib import contextmanager
from datetime import datetime, timezone
from urllib.parse import parse_qs, urlsplit
from unittest.mock import MagicMock

import httpx
import pytest
from sqlalchemy import func, select

from app.auth import COOKIE_NAME, create_session
from app.config import Settings, get_settings
from app.integrations.email import (
    MockEmailProvider,
    OutlookEmailProvider,
    get_email_provider,
    resolve_email_mode,
)
from app.models import (
    BolFile,
    Communication,
    EmailPollState,
    KofLoad,
    OutlookApp,
    OutlookConnection,
    User,
)
from app.routers.api import _ingest_email_message
from app.services.kof_credentials import decrypt_kof_password, encrypt_kof_password
from app.services.outlook import CONSENT_ERROR, access_token, credentials

CLIENT_ID = "11111111-1111-1111-1111-111111111111"


@pytest.fixture(autouse=True)
def no_env(monkeypatch):
    for name in (
        "outlook_client_id",
        "outlook_client_secret",
        "graph_client_id",
        "graph_client_secret",
        "graph_mailbox",
        "graph_tenant_id",
    ):
        monkeypatch.setattr(get_settings(), name, None)


def app_credentials(db):
    db.add(
        OutlookApp(
            id=1,
            client_id=CLIENT_ID,
            secret_encrypted=encrypt_kof_password("app-secret"),
        )
    )
    db.commit()


def connected(db):
    app_credentials(db)
    row = OutlookConnection(
        id=1,
        token_encrypted=encrypt_kof_password("old-refresh"),
        email="scotti@company.com",
        name="Scotti",
        needs_reconnect=False,
    )
    db.add(row)
    db.commit()
    return row


def reply(payload, status=200):
    return httpx.Response(
        status,
        json=payload,
        request=httpx.Request("POST", "https://microsoft.example/test"),
    )


def begin(client):
    response = client.get("/api/email/oauth/start", follow_redirects=False)
    assert response.status_code == 302
    return parse_qs(urlsplit(response.headers["location"]).query)["state"][0]


def test_credentials_encryption_precedence_disconnect_and_auth(client, db, monkeypatch):
    monkeypatch.setattr(get_settings(), "outlook_client_id", CLIENT_ID)
    monkeypatch.setattr(get_settings(), "outlook_client_secret", "env-secret")
    assert credentials(db).source == "env"
    response = client.put(
        "/api/email/connection",
        json={"client_id": CLIENT_ID, "client_secret": "app-secret"},
    )
    assert response.status_code == 200
    assert response.json()["source"] == "app"
    row = db.get(OutlookApp, 1)
    assert row.secret_encrypted != "app-secret"
    assert decrypt_kof_password(row.secret_encrypted) == "app-secret"
    assert credentials(db).secret == "app-secret"
    assert "app-secret" not in client.get("/api/email/connection").text
    db.add(
        OutlookConnection(
            id=1,
            token_encrypted=encrypt_kof_password("refresh"),
            email="s@company.com",
            name="S",
        )
    )
    db.commit()
    assert client.delete("/api/email/account").status_code == 204
    assert db.get(OutlookConnection, 1) is None
    assert db.get(OutlookApp, 1) is not None
    assert client.delete("/api/email/connection").status_code == 204
    assert credentials(db).source == "env"
    client.cookies.clear()
    for method, path, kwargs in (
        ("get", "/api/email/connection", {}),
        ("get", "/api/email/oauth/start", {}),
        ("get", "/api/email/oauth/callback", {}),
        (
            "put",
            "/api/email/connection",
            {"json": {"client_id": CLIENT_ID, "client_secret": "x"}},
        ),
        ("delete", "/api/email/account", {}),
    ):
        assert getattr(client, method)(path, **kwargs).status_code == 401


def test_start_scopes_prompt_redirect_uri_and_lax_cookies(client, db, monkeypatch):
    app_credentials(db)
    settings = get_settings()
    monkeypatch.setattr(
        settings, "public_base_url", "https://kingoffreight.onrender.com"
    )
    settings.model_fields_set.add("public_base_url")
    response = client.get("/api/email/oauth/start", follow_redirects=False)
    target = urlsplit(response.headers["location"])
    assert target.path == "/common/oauth2/v2.0/authorize"
    query = parse_qs(target.query)
    assert query["scope"] == ["offline_access User.Read Mail.Read Mail.Send"]
    assert query["prompt"] == ["select_account"]
    assert query["redirect_uri"] == [
        "https://kingoffreight.onrender.com/api/email/oauth/callback"
    ]
    assert "SameSite=lax" in response.headers["set-cookie"]
    client.base_url = "https://testserver"
    login = client.post("/api/auth/login", json={"password": "test-password"})
    assert "SameSite=lax" in login.headers["set-cookie"]
    assert "HttpOnly" in login.headers["set-cookie"]
    assert (
        client.get("/api/email/connection").json()["redirect_uri"]
        == query["redirect_uri"][0]
    )


def test_forwarded_redirect_and_missing_config(client, monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "public_base_url", "")
    response = client.get(
        "/api/email/connection",
        headers={
            "X-Forwarded-Proto": "https",
            "X-Forwarded-Host": "kingoffreight.onrender.com",
        },
    )
    assert (
        response.json()["redirect_uri"]
        == "https://kingoffreight.onrender.com/api/email/oauth/callback"
    )
    assert response.json()["status"] == "not_set_up"
    assert (
        "Save the Azure"
        in parse_qs(
            urlsplit(
                client.get("/api/email/oauth/start", follow_redirects=False).headers[
                    "location"
                ]
            ).query
        )["reason"][0]
    )


@pytest.mark.parametrize(
    "invalid", ["tampered", "expired", "session", "missing_cookie"]
)
def test_state_validation(client, db, monkeypatch, invalid):
    app_credentials(db)
    state = begin(client)
    post = MagicMock()
    monkeypatch.setattr("app.routers.outlook.httpx.post", post)
    if invalid == "tampered":
        state += "tamper"
    elif invalid == "expired":
        future = time.time() + 601
        monkeypatch.setattr("itsdangerous.timed.time.time", lambda: future)
    elif invalid == "session":
        client.cookies.set(COOKIE_NAME, create_session(uid=999, password_version=1))
        # Keep a valid, different legacy session so authentication succeeds.
        client.cookies.set(COOKIE_NAME, create_session(password_version=10))
    else:
        client.cookies.delete("outlook_oauth_state")
    response = client.get(
        "/api/email/oauth/callback",
        params={"state": state, "code": "code"},
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert (
        "could not be verified"
        in parse_qs(urlsplit(response.headers["location"]).query)["reason"][0]
    )
    post.assert_not_called()


def test_code_exchange_encrypted_token_and_account(client, db, monkeypatch):
    app_credentials(db)
    state = begin(client)
    post = MagicMock(
        return_value=reply(
            {"access_token": "access-secret", "refresh_token": "refresh-secret"}
        )
    )
    get = MagicMock(
        return_value=reply(
            {
                "mail": None,
                "userPrincipalName": "scotti@company.com",
                "displayName": "Scotti",
            }
        )
    )
    monkeypatch.setattr("app.routers.outlook.httpx.post", post)
    monkeypatch.setattr("app.routers.outlook.httpx.get", get)
    response = client.get(
        "/api/email/oauth/callback",
        params={"state": state, "code": "auth-code"},
        follow_redirects=False,
    )
    assert response.headers["location"] == "/settings?outlook=connected"
    token = db.get(OutlookConnection, 1)
    assert token.email == "scotti@company.com" and token.name == "Scotti"
    assert token.token_encrypted != "refresh-secret"
    assert decrypt_kof_password(token.token_encrypted) == "refresh-secret"
    assert post.call_args.kwargs["data"]["grant_type"] == "authorization_code"
    assert get.call_args.args[0].endswith("/me")
    assert "secret" not in client.get("/api/email/connection").text
    assert "outlook_oauth_state" not in client.cookies


@pytest.mark.parametrize("code", [65001, 90094, 90095])
def test_consent_errors_are_actionable_without_provider_text(
    client, db, monkeypatch, code
):
    app_credentials(db)
    state = begin(client)
    monkeypatch.setattr(
        "app.routers.outlook.httpx.post",
        lambda *a, **kw: reply(
            {
                "error": "invalid_grant",
                "error_description": f"AADSTS{code}: secret-value",
                "error_codes": [code],
            },
            400,
        ),
    )
    response = client.get(
        "/api/email/oauth/callback",
        params={"state": state, "code": "code"},
        follow_redirects=False,
    )
    assert parse_qs(urlsplit(response.headers["location"]).query)["reason"] == [
        CONSENT_ERROR
    ]
    assert "secret-value" not in response.headers["location"]
    assert db.get(OutlookConnection, 1) is None


def test_oauth_denial_and_network_errors(client, db, monkeypatch):
    app_credentials(db)
    state = begin(client)
    response = client.get(
        "/api/email/oauth/callback",
        params={
            "state": state,
            "error": "access_denied",
            "error_description": "AADSTS90094 secret",
        },
        follow_redirects=False,
    )
    assert parse_qs(urlsplit(response.headers["location"]).query)["reason"] == [
        CONSENT_ERROR
    ]
    state = begin(client)
    monkeypatch.setattr(
        "app.routers.outlook.httpx.post",
        MagicMock(side_effect=httpx.ConnectError("secret")),
    )
    response = client.get(
        "/api/email/oauth/callback",
        params={"state": state, "code": "code"},
        follow_redirects=False,
    )
    assert "unreachable" in response.headers["location"]
    assert "secret" not in response.headers["location"]


def test_refresh_rotation_and_needs_reconnect(client, db, monkeypatch):
    row = connected(db)
    post = MagicMock(
        return_value=reply({"access_token": "access", "refresh_token": "rotated"})
    )
    monkeypatch.setattr("app.services.outlook.httpx.post", post)
    assert access_token(db) == "access"
    assert decrypt_kof_password(row.token_encrypted) == "rotated"
    assert post.call_args.kwargs["data"]["refresh_token"] == "old-refresh"
    post.return_value = reply(
        {"error": "invalid_grant", "error_description": "refresh-secret"}, 400
    )
    with pytest.raises(ValueError, match="revoked"):
        access_token(db)
    assert row.needs_reconnect
    assert client.get("/api/email/connection").json()["status"] == "needs_reconnect"
    assert client.get("/api/integrations/status").json()["email_account"][
        "needs_reconnect"
    ]
    post.reset_mock()
    with pytest.raises(ValueError, match="Connect Outlook"):
        access_token(db)
    post.assert_not_called()


def test_auto_selection_and_factory(db, monkeypatch):
    monkeypatch.delenv("EMAIL_PROVIDER")
    assert Settings(_env_file=None).email_provider == "auto"
    monkeypatch.setattr(get_settings(), "email_provider", "auto")

    @contextmanager
    def session():
        yield db

    monkeypatch.setattr("app.integrations.email.SessionLocal", session)
    assert resolve_email_mode(db) == "mock"
    assert isinstance(get_email_provider(), MockEmailProvider)
    for key in (
        "graph_tenant_id",
        "graph_client_id",
        "graph_client_secret",
        "graph_mailbox",
    ):
        monkeypatch.setattr(get_settings(), key, "configured")
    assert resolve_email_mode(db) == "graph"
    row = connected(db)
    assert resolve_email_mode(db) == "outlook"
    assert isinstance(get_email_provider(), OutlookEmailProvider)
    row.needs_reconnect = True
    db.commit()
    assert resolve_email_mode(db) == "graph"
    monkeypatch.setattr(get_settings(), "email_provider", "mock")
    assert resolve_email_mode(db) == "mock"
    monkeypatch.setattr(get_settings(), "email_provider", "graph")
    assert resolve_email_mode(db) == "graph"


def test_delegated_send_poll_pagination_and_durable_watermark(db, monkeypatch):
    connected(db)

    @contextmanager
    def session():
        yield db

    monkeypatch.setattr("app.integrations.email.SessionLocal", session)
    monkeypatch.setattr(
        "app.services.outlook.httpx.post",
        lambda *a, **kw: reply({"access_token": "access", "refresh_token": "rotated"}),
    )
    provider = OutlookEmailProvider("scotti@company.com")
    get = MagicMock(
        side_effect=[
            reply(
                {
                    "value": [
                        {
                            "id": "one",
                            "subject": "Order 3425326",
                            "body": {"content": "Loaded"},
                            "receivedDateTime": "2026-11-10T10:00:00Z",
                        }
                    ],
                    "@odata.nextLink": "https://graph.microsoft.com/v1.0/me/mailFolders/inbox/messages?$skiptoken=x",
                }
            ),
            reply({"value": []}),
        ]
    )
    monkeypatch.setattr("app.integrations.email.httpx.get", get)
    before = datetime.now(timezone.utc)
    assert provider.fetch_new_messages()[0]["subject"] == "Order 3425326"
    query = get.call_args_list[0].kwargs["params"]["$filter"]
    since = datetime.fromisoformat(
        query.split(" gt ")[1].split(" and ")[0].replace("Z", "+00:00")
    )
    assert abs((before - since).total_seconds() - 86400) < 2
    assert db.get(EmailPollState, provider.poll_key) is None
    provider.commit_poll()
    assert db.get(EmailPollState, provider.poll_key) is not None
    get.side_effect = None
    get.return_value = reply({"value": []})
    recreated = OutlookEmailProvider("scotti@company.com")
    recreated.fetch_new_messages()
    assert "mailFolders/inbox/messages" in get.call_args.args[0]
    later_since = datetime.fromisoformat(
        get.call_args.kwargs["params"]["$filter"]
        .split(" gt ")[1]
        .split(" and ")[0]
        .replace("Z", "+00:00")
    )
    assert abs((before - later_since).total_seconds() - 60) < 2
    post = MagicMock(side_effect=[reply({"access_token": "access"}), reply({}, 202)])
    monkeypatch.setattr("app.integrations.email.httpx.post", post)
    assert recreated.send("driver@carrier.com", "Order update", "Hello").startswith(
        "graph-"
    )
    assert post.call_args.args[0] == "https://graph.microsoft.com/v1.0/me/sendMail"


@pytest.mark.parametrize(
    "subject,body,pdfs,expected",
    [
        ("Lunch?", "Personal mail", [], None),
        ("MC 123456 available", "Nothing about a known load", [], None),
        ("Payroll", "Private", [("payroll.pdf", b"%PDF secret")], None),
        ("Rate Confirmation for Order # 3425326", "Carrier booked", [], 3425326),
        ("PO PO-123 update", "Loaded", [], 3425326),
        ("Order 13425326", "Not the same order", [], None),
        ("Deleted order 555", "Loaded", [], None),
    ],
)
def test_only_load_related_mail_persisted_with_kof_link(
    db, providers, subject, body, pdfs, expected
):
    db.add_all(
        [KofLoad(order_no=3425326, po="PO-123"), KofLoad(order_no=555, is_deleted=True)]
    )
    db.commit()
    _ingest_email_message(
        db,
        {
            "from": "dispatch@carrier.com",
            "subject": subject,
            "body_text": body,
            "external_id": "mail1",
            "pdf_attachments": pdfs,
        },
        providers["llm"],
    )
    row = db.scalar(select(Communication))
    if expected:
        assert row.kof_order_no == expected
        assert row.subject == subject and row.content == body
        _ingest_email_message(db, {"external_id": "mail1"}, providers["llm"])
        assert db.scalar(select(func.count(Communication.id))) == 1
    else:
        assert row is None
        assert db.scalar(select(func.count(BolFile.id))) == 0


def test_known_operational_reference_and_bol_only(db, providers, load_data):
    load, _ = load_data
    _ingest_email_message(
        db,
        {
            "subject": f"Update {load.reference}",
            "body_text": "Loaded",
            "from": "dispatch@example.com",
        },
        providers["llm"],
    )
    assert db.scalar(select(Communication)).load_id == load.id
    _ingest_email_message(
        db,
        {
            "subject": "Bill of lading",
            "body_text": "Attached",
            "pdf_attachments": [("BOL.pdf", b"%PDF test")],
        },
        providers["llm"],
    )
    assert (
        db.scalar(
            select(Communication).where(Communication.tag == "bol")
        ).attachment_file.content
        == b"%PDF test"
    )


def test_callback_password_setup_exception_remains_authenticated(client, db):
    user = User(username="setup-user", must_set_password=True, password_version=0)
    db.add(user)
    db.commit()
    client.cookies.clear()
    client.cookies.set(COOKIE_NAME, create_session(user.id, user.password_version))
    assert (
        client.get("/api/email/oauth/start", follow_redirects=False).status_code == 403
    )
    assert (
        client.get("/api/email/oauth/callback", follow_redirects=False).status_code
        == 303
    )
