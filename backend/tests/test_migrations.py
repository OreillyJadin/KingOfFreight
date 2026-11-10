import os
import subprocess
import sys
import sqlite3


def test_alembic_upgrade_applies_to_sqlite_file(tmp_path):
    database = tmp_path / "migration.db"
    env = dict(os.environ)
    env["DATABASE_URL"] = f"sqlite+pysqlite:///{database}"
    env["BROKER_PASSWORD"] = "migration-test"
    for command in (
        ["upgrade", "head"],
        ["downgrade", "-1"],
        ["upgrade", "head"],
    ):
        subprocess.run(
            [sys.executable, "-m", "alembic", *command],
            cwd=os.path.dirname(os.path.dirname(__file__)),
            env=env,
            check=True,
            capture_output=True,
            text=True,
        )
    assert database.exists()


def test_user_role_migration_backfills_existing_members(tmp_path):
    database = tmp_path / "existing-users.db"
    env = dict(os.environ, DATABASE_URL=f"sqlite+pysqlite:///{database}")
    backend = os.path.dirname(os.path.dirname(__file__))
    subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "e50c91a72bd3"],
        cwd=backend,
        env=env,
        check=True,
        capture_output=True,
    )
    with sqlite3.connect(database) as db:
        db.execute(
            "INSERT INTO users (username, password_version, must_set_password, created_at) VALUES ('Existing', 0, 1, CURRENT_TIMESTAMP)"
        )
    subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=backend,
        env=env,
        check=True,
        capture_output=True,
    )
    with sqlite3.connect(database) as db:
        assert db.execute(
            "SELECT role, is_active, last_login_at FROM users"
        ).fetchone() == ("member", 1, None)
