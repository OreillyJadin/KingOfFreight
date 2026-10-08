from app.config import Settings, get_settings


def test_database_url_adds_psycopg_driver_only_when_missing():
    assert (
        Settings(
            database_url="postgres://db.example/freight", broker_password="x"
        ).database_url
        == "postgresql+psycopg://db.example/freight"
    )
    assert (
        Settings(
            database_url="postgresql://db.example/freight", broker_password="x"
        ).database_url
        == "postgresql+psycopg://db.example/freight"
    )
    assert (
        Settings(
            database_url="postgresql+asyncpg://db.example/freight",
            broker_password="x",
        ).database_url
        == "postgresql+asyncpg://db.example/freight"
    )
    assert (
        Settings(database_url="sqlite:///db.sqlite", broker_password="x").database_url
        == "sqlite:///db.sqlite"
    )


def test_render_external_url_is_default_when_public_url_is_unset(monkeypatch):
    monkeypatch.delenv("PUBLIC_BASE_URL", raising=False)
    monkeypatch.setenv("RENDER_EXTERNAL_URL", "https://freight.onrender.com")
    settings = Settings(_env_file=None, broker_password="x")
    assert settings.public_base_url == "https://freight.onrender.com"
    get_settings.cache_clear()
