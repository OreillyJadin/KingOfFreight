import os
import subprocess
import sys


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
