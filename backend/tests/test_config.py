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


def test_production_requires_a_long_non_default_secret():
    import pytest
    from pydantic import ValidationError

    with pytest.raises(
        ValidationError,
        match="SECRET_KEY must be set to a random value of at least 32 characters in production",
    ):
        Settings(
            _env_file=None,
            broker_password="x",
            env="production",
            secret_key="development-secret-change-me",
        )
    with pytest.raises(ValidationError):
        Settings(
            _env_file=None,
            broker_password="x",
            env="production",
            secret_key="x" * 20,
        )
    with pytest.raises(ValidationError):
        Settings(
            _env_file=None,
            broker_password="x",
            env="production",
            secret_key="replace-with-a-long-random-value",
        )

    settings = Settings(
        _env_file=None,
        broker_password="x",
        env="production",
        secret_key="x" * 44,
    )
    assert settings.secret_key == "x" * 44


def test_development_allows_default_secret():
    settings = Settings(
        _env_file=None,
        broker_password="x",
        env="development",
        secret_key="development-secret-change-me",
    )
    assert settings.secret_key == "development-secret-change-me"
