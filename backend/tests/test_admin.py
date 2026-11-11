import pytest
from sqlalchemy import select

from app.auth import (
    COOKIE_NAME,
    create_session,
    decode_session,
    hash_password,
    password_hash_matches,
)
from app.models import User


def sign_in_as(client, user):
    client.cookies.clear()
    client.cookies.set(
        COOKIE_NAME, create_session(user.id, user.password_version, user.role)
    )


def add_user(db, username="Broker", role="member", **kwargs):
    user = User(
        username=username,
        role=role,
        password_hash=hash_password("personal-password"),
        must_set_password=False,
        **kwargs,
    )
    db.add(user)
    db.commit()
    return user


def test_claim_creates_first_admin_and_blocks_legacy_login(client, db):
    assert client.get("/api/auth/me").json()["can_claim_admin"] is True
    response = client.post(
        "/api/admin/claim", json={"username": " Owner ", "password": "owner-password"}
    )
    assert response.status_code == 200
    assert response.json()["username"] == "Owner"
    assert response.json()["role"] == "admin"
    assert "password_hash" not in response.text
    user = db.scalar(select(User).where(User.username == "Owner"))
    assert password_hash_matches("owner-password", user.password_hash)
    assert not user.must_set_password
    assert user.last_login_at is not None
    payload = decode_session(client.cookies.get(COOKIE_NAME))
    assert payload["uid"] == user.id
    assert payload["role"] == "admin"
    me = client.get("/api/auth/me").json()
    assert me["role"] == "admin" and me["can_claim_admin"] is False
    assert (
        client.post(
            "/api/admin/claim",
            json={"username": "Second", "password": "other-password"},
        ).status_code
        == 409
    )
    client.post("/api/auth/logout")
    legacy = client.post("/api/auth/login", json={"password": "test-password"})
    assert legacy.status_code == 401
    assert legacy.json()["detail"] == "Sign in with your username"
    assert (
        client.post(
            "/api/auth/login", json={"username": "owner", "password": "owner-password"}
        ).status_code
        == 200
    )
    assert client.get("/api/admin/users").status_code == 200


def test_claim_requires_legacy_auth_and_valid_unique_credentials(client, db):
    member = add_user(db)
    sign_in_as(client, member)
    body = {"username": "Owner", "password": "owner-password"}
    assert client.post("/api/admin/claim", json=body).status_code == 403
    client.cookies.clear()
    assert client.post("/api/admin/claim", json=body).status_code == 401
    client.post("/api/auth/login", json={"password": "test-password"})
    assert (
        client.post("/api/admin/claim", json={**body, "password": "short"}).status_code
        == 422
    )
    assert (
        client.post("/api/admin/claim", json={**body, "username": "   "}).status_code
        == 422
    )
    assert (
        client.post("/api/admin/claim", json={**body, "username": "broker"}).status_code
        == 409
    )
    assert client.get("/api/auth/me").json()["can_claim_admin"] is True


DEV_ENDPOINTS = [
    ("put", "/api/assistant/connection", {"api_key": "secret"}),
    ("delete", "/api/assistant/connection", None),
    (
        "put",
        "/api/integrations/twilio/connection",
        {
            "account_sid": "AC" + "a" * 32,
            "auth_token": "secret",
            "from_number": "+15550001111",
        },
    ),
    ("delete", "/api/integrations/twilio/connection", None),
    ("post", "/api/integrations/twilio/test", {"to": "+15550001111"}),
    (
        "put",
        "/api/email/connection",
        {
            "client_id": "11111111-1111-1111-1111-111111111111",
            "client_secret": "secret",
        },
    ),
    ("delete", "/api/email/connection", None),
    (
        "put",
        "/api/kof/connection",
        {"username": "external-user", "password": "external-password"},
    ),
    ("delete", "/api/kof/connection", None),
    ("get", "/api/admin/users", None),
    ("post", "/api/admin/users", {"username": "New", "password": "temp-password"}),
    ("patch", "/api/admin/users/999", {"role": "admin"}),
    ("post", "/api/admin/users/999/reset-password", {"password": "temp-password"}),
]


@pytest.mark.parametrize("method,path,body", DEV_ENDPOINTS)
@pytest.mark.parametrize("identity", ["legacy", "member"])
def test_admin_endpoints_forbid_members_and_legacy(
    client, db, method, path, body, identity
):
    if identity == "member":
        sign_in_as(client, add_user(db))
    kwargs = {"json": body} if body is not None else {}
    assert getattr(client, method)(path, **kwargs).status_code == 403


def test_member_status_and_mailbox_endpoints_remain_available(client, db):
    sign_in_as(client, add_user(db))
    for path in (
        "/api/settings",
        "/api/integrations/status",
        "/api/email/connection",
        "/api/kof/connection",
        "/api/kof/sync",
    ):
        assert client.get(path).status_code == 200
    assert (
        client.put(
            "/api/settings", json={"broker_timezone": "America/Denver"}
        ).status_code
        == 200
    )
    assert client.delete("/api/email/account").status_code == 204
    assert (
        client.get("/api/email/oauth/start", follow_redirects=False).status_code == 303
    )
    assert client.post("/api/kof/sync").status_code != 403


def test_user_creation_listing_password_setup_and_last_login(client, db, admin_login):
    response = client.post(
        "/api/admin/users",
        json={"username": " NewBroker ", "password": "temporary-password"},
    )
    assert response.status_code == 201
    created = response.json()
    assert created["role"] == "member" and created["is_active"] is True
    assert created["must_set_password"] is True and created["last_login_at"] is None
    assert "password" not in created and "password_hash" not in created
    assert (
        client.post(
            "/api/admin/users",
            json={"username": "newbroker", "password": "temporary-password"},
        ).status_code
        == 409
    )
    assert (
        client.post(
            "/api/admin/users", json={"username": "", "password": "short"}
        ).status_code
        == 422
    )
    assert (
        client.post(
            "/api/admin/users",
            json={
                "username": "Other",
                "password": "temporary-password",
                "role": "owner",
            },
        ).status_code
        == 422
    )
    assert len(client.get("/api/admin/users").json()) == 2
    response = client.post(
        "/api/auth/login",
        json={"username": "newbroker", "password": "temporary-password"},
    )
    assert response.status_code == 200 and response.json()["must_set_password"] is True
    assert client.get("/api/loads").status_code == 403
    assert (
        client.post(
            "/api/auth/set-password", json={"new_password": "new-personal-password"}
        ).status_code
        == 200
    )
    assert client.get("/api/loads").status_code == 200
    user = db.get(User, created["id"])
    assert user.last_login_at is not None
    assert user.must_set_password is False
    sign_in_as(client, admin_login)
    listed = next(
        item for item in client.get("/api/admin/users").json() if item["id"] == user.id
    )
    assert listed["last_login_at"] is not None


def test_reset_password_invalidates_sessions(client, db, admin_login):
    member = add_user(db)
    old_version = member.password_version
    response = client.post(
        f"/api/admin/users/{member.id}/reset-password",
        json={"password": "replacement-temp"},
    )
    assert response.status_code == 200 and response.json()["must_set_password"] is True
    assert member.password_version == old_version + 1
    client.cookies.clear()
    client.cookies.set(COOKIE_NAME, create_session(member.id, old_version))
    assert client.get("/api/auth/me").status_code == 401
    assert (
        client.post(
            "/api/auth/login",
            json={"username": member.username, "password": "personal-password"},
        ).status_code
        == 401
    )
    assert (
        client.post(
            "/api/auth/login",
            json={"username": member.username, "password": "replacement-temp"},
        ).json()["must_set_password"]
        is True
    )


def test_inactive_login_and_session_rejected_and_reactivation(client, db, admin_login):
    member = add_user(db)
    old_token = create_session(member.id, member.password_version)
    assert (
        client.patch(
            f"/api/admin/users/{member.id}", json={"is_active": False}
        ).status_code
        == 200
    )
    client.cookies.clear()
    client.cookies.set(COOKIE_NAME, old_token)
    assert client.get("/api/auth/me").status_code == 401
    assert (
        client.post(
            "/api/auth/login",
            json={"username": member.username, "password": "personal-password"},
        ).status_code
        == 401
    )
    sign_in_as(client, admin_login)
    assert (
        client.patch(
            f"/api/admin/users/{member.id}", json={"is_active": True}
        ).status_code
        == 200
    )
    client.cookies.clear()
    client.cookies.set(COOKIE_NAME, old_token)
    assert client.get("/api/auth/me").status_code == 401
    assert (
        client.post(
            "/api/auth/login",
            json={"username": member.username, "password": "personal-password"},
        ).status_code
        == 200
    )


def test_last_active_admin_guard_and_role_changes(client, db, admin_login):
    add_user(db, username="InactiveAdmin", role="admin", is_active=False)
    path = f"/api/admin/users/{admin_login.id}"
    assert client.patch(path, json={"role": "member"}).status_code == 409
    assert client.patch(path, json={"is_active": False}).status_code == 409
    member = add_user(db)
    assert (
        client.patch(
            f"/api/admin/users/{member.id}", json={"role": "admin"}
        ).status_code
        == 200
    )
    assert client.patch(path, json={"role": "member"}).status_code == 200
    assert client.get("/api/auth/me").json()["role"] == "member"
    assert client.get("/api/admin/users").status_code == 403
    sign_in_as(client, member)
    assert client.patch(path, json={"is_active": False}).status_code == 200


def test_missing_users_and_invalid_updates(client, admin_login):
    assert (
        client.patch("/api/admin/users/999", json={"role": "member"}).status_code == 404
    )
    assert (
        client.post(
            "/api/admin/users/999/reset-password",
            json={"password": "temporary-password"},
        ).status_code
        == 404
    )
    assert (
        client.patch(
            f"/api/admin/users/{admin_login.id}", json={"role": "owner"}
        ).status_code
        == 422
    )
    assert (
        client.post(
            f"/api/admin/users/{admin_login.id}/reset-password",
            json={"password": "short"},
        ).status_code
        == 422
    )


def test_session_role_is_not_authoritative(client, db):
    member = add_user(db)
    client.cookies.clear()
    client.cookies.set(
        COOKIE_NAME, create_session(member.id, member.password_version, "admin")
    )
    assert client.get("/api/auth/me").json()["role"] == "member"
    assert client.get("/api/admin/users").status_code == 403
