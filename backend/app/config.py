from functools import lru_cache
from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=Path(__file__).resolve().parents[2] / ".env",
        extra="ignore",
        case_sensitive=False,
    )

    database_url: str = "postgresql+psycopg://freight:freight@localhost:5432/freight"
    broker_password: str
    secret_key: str = "development-secret-change-me"
    broker_name: str = "Freight Broker"
    broker_company: str = "Freight Brokerage"
    broker_timezone: str = "America/Chicago"
    public_base_url: str = "http://localhost:8000"
    cors_origins: str = "http://localhost:5173"
    checkin_offset_minutes: int = 60
    no_reply_alert_minutes: int = 30
    checkin_default_channel: str = "sms"
    scheduler_enabled: bool = True
    scheduler_interval_seconds: int = 60
    sms_provider: str = "mock"
    twilio_account_sid: str | None = None
    twilio_auth_token: str | None = None
    twilio_from_number: str | None = None
    email_provider: str = "mock"
    graph_tenant_id: str | None = None
    graph_client_id: str | None = None
    graph_client_secret: str | None = None
    graph_mailbox: str | None = None
    llm_provider: str = "mock"
    anthropic_api_key: str | None = None
    anthropic_model: str = "claude-sonnet-4-5"
    fmcsa_provider: str = "mock"
    fmcsa_webkey: str | None = None
    upload_dir: str = "./data/uploads"
    env: str = "development"

    @field_validator(
        "sms_provider",
        "email_provider",
        "llm_provider",
        "fmcsa_provider",
        "checkin_default_channel",
    )
    @classmethod
    def normalize_mode(cls, value: str) -> str:
        return value.lower()

    @property
    def cors_origin_list(self) -> list[str]:
        return [
            origin.strip() for origin in self.cors_origins.split(",") if origin.strip()
        ]


@lru_cache
def get_settings() -> Settings:
    return Settings()
