from fastapi.testclient import TestClient
from sqlalchemy import select

from app.auth import COOKIE_NAME, decode_session
from app.config import get_settings
from app.models import User


def test_bootstrap_login_password_setup_gating_and_session_invalidation(
    db, monkeypatch
):
    import app.main as main_module

    app = main_module.app

    monkeypatch.setenv("BOOTSTRAP_USERNAME", "Keaster")
    monkeypatch.setenv("SCHEDULER_ENABLED", "false")
    get_settings.cache_clear()
    settings = get_settings()
    monkeypatch.setattr(main_module, "settings", settings)
    try:
        with TestClient(app) as client:
            user = db.scalar(select(User).where(User.username == "Keaster"))
            assert user is not None
            assert user.password_hash is None
            assert user.must_set_password is True

            login = client.post(
                "/api/auth/login",
                json={"username": "keaster", "password": ""},
            )
            assert login.status_code == 200
            assert login.json() == {
                "authenticated": True,
                "username": "Keaster",
                "must_set_password": True,
            }
            old_cookie = client.cookies.get(COOKIE_NAME)
            assert old_cookie
            session_payload = decode_session(old_cookie)
            assert session_payload is not None
            assert session_payload["uid"] == user.id
            assert session_payload["password_version"] == user.password_version

            me = client.get("/api/auth/me")
            assert me.status_code == 200
            assert me.json() == {
                "authenticated": True,
                "broker_timezone": settings.broker_timezone,
                "username": "Keaster",
                "must_set_password": True,
            }
            assert client.get("/api/loads").status_code == 403
            assert client.get("/api/track/not-a-real-token").status_code == 403
            assert (
                client.post(
                    "/api/auth/set-password", json={"new_password": "short"}
                ).status_code
                == 422
            )

            setup = client.post(
                "/api/auth/set-password",
                json={"new_password": "first-personal-password"},
            )
            assert setup.status_code == 200
            assert setup.json() == {"ok": True}
            assert client.get("/api/loads").status_code == 200
            assert client.post("/api/auth/logout").status_code == 200
            empty_password_login = client.post(
                "/api/auth/login",
                json={"username": "Keaster", "password": ""},
            )
            assert empty_password_login.status_code == 401
            personal_login = client.post(
                "/api/auth/login",
                json={
                    "username": "Keaster",
                    "password": "first-personal-password",
                },
            )
            assert personal_login.status_code == 200

            with TestClient(app) as stale_session:
                stale_session.cookies.set(COOKIE_NAME, old_cookie)
                assert stale_session.get("/api/loads").status_code == 401

                previous_cookie = client.cookies.get(COOKIE_NAME)
                changed = client.post(
                    "/api/auth/change-password",
                    json={
                        "current_password": "first-personal-password",
                        "new_password": "second-personal-password",
                    },
                )
                assert changed.status_code == 200
                assert changed.json() == {"ok": True}
                assert previous_cookie
                stale_session.cookies.set(COOKIE_NAME, previous_cookie)
                assert stale_session.get("/api/loads").status_code == 401

            me = client.get("/api/auth/me")
            assert me.json()["must_set_password"] is False
            assert client.post("/api/auth/logout").json() == {"authenticated": False}
            personal = client.post(
                "/api/auth/login",
                json={
                    "username": "KEASTER",
                    "password": "second-personal-password",
                },
            )
            assert personal.status_code == 200
            assert personal.json()["must_set_password"] is False
            client.post("/api/auth/logout")
            legacy = client.post("/api/auth/login", json={"password": "test-password"})
            assert legacy.status_code == 200
            assert legacy.json() == {
                "authenticated": True,
                "username": None,
                "must_set_password": False,
            }

            db.add(
                User(
                    username="OtherUser",
                    password_hash=None,
                    password_version=0,
                    must_set_password=True,
                )
            )
            db.commit()
            client.post("/api/auth/logout")
            non_bootstrap_empty_login = client.post(
                "/api/auth/login",
                json={"username": "OtherUser", "password": ""},
            )
            assert non_bootstrap_empty_login.status_code == 401
            non_bootstrap_broker_login = client.post(
                "/api/auth/login",
                json={"username": "OtherUser", "password": "test-password"},
            )
            assert non_bootstrap_broker_login.status_code == 200
            assert non_bootstrap_broker_login.json()["must_set_password"] is True
    finally:
        get_settings.cache_clear()


def test_bootstrap_ignores_existing_case_insensitive_username(db):
    from app.auth import ensure_bootstrap_user

    original = User(
        username="Keaster",
        password_hash=None,
        password_version=0,
        must_set_password=True,
    )
    db.add(original)
    db.commit()

    existing = ensure_bootstrap_user(db, "keaster")
    assert existing is not None
    assert existing.id == original.id
    assert db.scalar(select(User).where(User.username == "keaster")) is None


def test_bootstrap_login_matches_configured_username_case_insensitively(
    db, monkeypatch
):
    import app.main as main_module

    monkeypatch.setenv("BOOTSTRAP_USERNAME", "keaster")
    monkeypatch.setenv("SCHEDULER_ENABLED", "false")
    get_settings.cache_clear()
    settings = get_settings()
    monkeypatch.setattr(main_module, "settings", settings)
    db.add(
        User(
            username="Keaster",
            password_hash=None,
            password_version=0,
            must_set_password=True,
        )
    )
    db.commit()
    try:
        with TestClient(main_module.app) as client:
            response = client.post(
                "/api/auth/login",
                json={"username": "KEASTER", "password": "anything"},
            )
            assert response.status_code == 200
            assert response.json()["must_set_password"] is True
    finally:
        get_settings.cache_clear()
