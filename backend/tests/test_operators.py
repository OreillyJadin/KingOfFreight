import os
import sqlite3
import subprocess
import sys

import pytest
from sqlalchemy import select

from app.auth import COOKIE_NAME, decode_session
from app.models import UsageEvent
from tests.test_admin import add_user, sign_in_as


def member(client, name="Tony"):
    result = client.post("/api/team-members", json={"name": name})
    assert result.status_code == 201
    return result.json()


@pytest.mark.parametrize("named", [False, True])
def test_selection_me_clear_logout_and_permissions(client, db, named):
    if named:
        user = add_user(db)
        client.cookies.clear()
        assert (
            client.post(
                "/api/auth/login",
                json={"username": user.username, "password": "personal-password"},
            ).status_code
            == 200
        )
    assert client.get("/api/auth/me").json()["operator"] is None
    assert client.get("/api/auth/me").json()["team_members_exist"] is False
    tony = member(client)
    assert client.get("/api/auth/me").json()["team_members_exist"] is True
    before = decode_session(client.cookies.get(COOKIE_NAME))
    response = client.post("/api/auth/operator", json={"team_member_id": tony["id"]})
    assert response.status_code == 200
    assert response.json()["operator"] == {"id": tony["id"], "name": "Tony"}
    after = decode_session(client.cookies.get(COOKIE_NAME))
    assert after["team_member_id"] == tony["id"]
    assert (after["uid"], after["role"], after["password_version"]) == (
        before["uid"],
        before["role"],
        before["password_version"],
    )
    assert client.get("/api/auth/me").json()["operator"]["name"] == "Tony"
    assert client.get("/api/admin/usage").status_code == 403
    assert (
        client.post("/api/auth/operator", json={"team_member_id": None}).json()[
            "operator"
        ]
        is None
    )
    assert decode_session(client.cookies.get(COOKIE_NAME))["team_member_id"] is None
    assert (
        client.post(
            "/api/auth/operator", json={"team_member_id": tony["id"]}
        ).status_code
        == 200
    )
    assert client.post("/api/auth/logout").status_code == 200
    assert client.get("/api/auth/me").status_code == 401
    assert (
        client.post("/api/auth/login", json={"password": "test-password"}).status_code
        == 200
    )
    assert client.get("/api/auth/me").json()["operator"] is None


def test_manage_team_and_inactive_selection(client, db):
    tony = member(client)
    assert client.get("/api/team-members").json()[0]["name"] == "Tony"
    assert client.post("/api/team-members", json={"name": " tOnY "}).status_code == 409
    assert client.post("/api/team-members", json={"name": "  "}).status_code == 422
    assert client.post("/api/team-members", json={"name": "x" * 121}).status_code == 422
    assert (
        client.post(
            "/api/auth/operator", json={"team_member_id": tony["id"]}
        ).status_code
        == 200
    )
    assert (
        client.patch(
            f"/api/team-members/{tony['id']}", json={"name": "Tony Updated"}
        ).status_code
        == 200
    )
    assert client.get("/api/auth/me").json()["operator"]["name"] == "Tony Updated"
    member(client, "Kolby")
    assert (
        client.patch(
            f"/api/team-members/{tony['id']}", json={"name": "kolby"}
        ).status_code
        == 409
    )
    assert (
        client.patch(
            f"/api/team-members/{tony['id']}", json={"is_active": False}
        ).status_code
        == 200
    )
    assert client.get("/api/auth/me").json()["operator"] is None
    assert (
        client.post(
            "/api/auth/operator", json={"team_member_id": tony["id"]}
        ).status_code
        == 422
    )
    assert (
        client.post("/api/auth/operator", json={"team_member_id": 9999}).status_code
        == 422
    )
    assert (
        client.post("/api/auth/operator", json={"team_member_id": True}).status_code
        == 422
    )
    assert (
        client.patch("/api/team-members/9999", json={"is_active": False}).status_code
        == 404
    )
    assert (
        client.patch(
            f"/api/team-members/{tony['id']}", json={"is_active": True}
        ).status_code
        == 200
    )
    client.cookies.clear()
    for path, body in [
        ("/api/auth/operator", {"team_member_id": None}),
        ("/api/team-members", {"name": "No auth"}),
    ]:
        assert client.post(path, json=body).status_code == 401
    assert client.get("/api/team-members").status_code == 401


def test_operator_attribution_report_and_snapshots(client, db, admin_login):
    tony = member(client)
    kolby = member(client, "Kolby")
    for who in (tony, kolby):
        assert (
            client.post(
                "/api/auth/operator", json={"team_member_id": who["id"]}
            ).status_code
            == 200
        )
        assert (
            client.post(
                "/api/usage/events", json={"event": "page_view", "path": "/loads"}
            ).json()["accepted"]
            is True
        )
        assert (
            client.post(
                "/api/assistant/chat",
                json={
                    "messages": [
                        {"role": "user", "content": f"Question from {who['name']}"}
                    ]
                },
            ).status_code
            == 503
        )
    events = db.scalars(
        select(UsageEvent)
        .where(UsageEvent.event == "assistant_question")
        .order_by(UsageEvent.id)
    ).all()
    assert [
        (event.team_member_id, event.operator_name, event.user_id) for event in events
    ] == [(tony["id"], "Tony", admin_login.id), (kolby["id"], "Kolby", admin_login.id)]
    switches = db.scalars(
        select(UsageEvent)
        .where(UsageEvent.event == "operator_switched")
        .order_by(UsageEvent.id)
    ).all()
    assert [event.operator_name for event in switches] == ["Tony", "Kolby"]
    client.patch(
        f"/api/team-members/{tony['id']}", json={"name": "Renamed", "is_active": False}
    )
    data = client.get("/api/admin/usage?exclude_admins=false").json()
    people = {user["label"]: user for user in data["users"]}
    assert people["Tony"]["questions"] == people["Kolby"]["questions"] == 1
    assert people["Tony"]["page_views"] == people["Kolby"]["page_views"] == 1
    assert {question["user"] for question in data["questions"]} == {"Tony", "Kolby"}
    assert data["questions"][0]["operator_name"] == "Kolby"
    assert (
        client.post("/api/auth/operator", json={"team_member_id": None}).status_code
        == 200
    )
    assert (
        client.post(
            "/api/usage/events", json={"event": "page_view", "path": "/loads"}
        ).json()["accepted"]
        is True
    )
    data = client.get("/api/admin/usage?exclude_admins=false").json()
    assert any(user["label"] == admin_login.username for user in data["users"])


def test_operator_survives_password_rotation(client, db):
    user = add_user(db)
    sign_in_as(client, user)
    tony = member(client)
    client.post("/api/auth/operator", json={"team_member_id": tony["id"]})
    result = client.post(
        "/api/auth/change-password",
        json={
            "current_password": "personal-password",
            "new_password": "changed-password",
        },
    )
    assert result.status_code == 200
    assert client.get("/api/auth/me").json()["operator"]["name"] == "Tony"


def test_migration_seeds_team_and_preserves_usage(tmp_path):
    database = tmp_path / "operators.db"
    env = dict(os.environ, DATABASE_URL=f"sqlite+pysqlite:///{database}")
    backend = os.path.dirname(os.path.dirname(__file__))

    def migrate(*args):
        subprocess.run(
            [sys.executable, "-m", "alembic", *args],
            cwd=backend,
            env=env,
            check=True,
            capture_output=True,
            text=True,
        )

    migrate("upgrade", "a70d9c5e2184")
    with sqlite3.connect(database) as conn:
        conn.execute(
            "INSERT INTO usage_events(event,device,created_at) VALUES ('page_view','mobile','2026-11-10')"
        )
    migrate("upgrade", "head")
    with sqlite3.connect(database) as conn:
        assert conn.execute("SELECT name FROM team_members ORDER BY id").fetchall() == [
            ("Scotti",),
            ("Tony",),
            ("Kolby",),
        ]
        assert conn.execute(
            "SELECT operator_name,team_member_id FROM usage_events"
        ).fetchone() == (None, None)
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO team_members(name,is_active,created_at) VALUES ('TONY',1,'2026-11-10')"
            )
    migrate("downgrade", "-1")
    migrate("upgrade", "head")
