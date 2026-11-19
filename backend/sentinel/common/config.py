"""Application configuration loaded from environment variables.

All secrets come from the environment; nothing sensitive has a usable default
outside of the local development template.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="SENTINEL_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- Persistence -----------------------------------------------------
    database_url: str = Field(
        default="postgresql+psycopg://sentinel:sentinel@localhost:5432/sentinel"
    )

    # --- Core API --------------------------------------------------------
    app_env: str = "development"
    debug: bool = False
    secret_key: str = "dev-only-secret-key-change-me"
    session_cookie_name: str = "sentinel_session"
    csrf_cookie_name: str = "sentinel_csrf"
    session_ttl_seconds: int = 60 * 60 * 24 * 7
    secure_cookies: bool = False
    trusted_hosts: list[str] = Field(default_factory=lambda: ["*"])
    cors_origins: list[str] = Field(default_factory=list)

    # --- Rate limits -----------------------------------------------------
    login_rate_limit_per_minute: int = 10
    ingestion_rate_limit_per_minute: int = 600

    # --- Detection rule defaults (documented in docs/architecture.md) ----
    failed_login_burst_threshold: int = 5
    failed_login_burst_window_seconds: int = 120
    failed_login_burst_severity: str = "high"

    high_request_volume_threshold: int = 101
    high_request_volume_window_seconds: int = 60
    high_request_volume_severity: str = "medium"

    repeated_access_denial_threshold: int = 10
    repeated_access_denial_window_seconds: int = 300
    repeated_access_denial_severity: str = "medium"

    # --- Detector --------------------------------------------------------
    detector_poll_interval_seconds: float = 1.0
    detector_batch_size: int = 50
    detector_max_attempts: int = 5

    # --- Demo ------------------------------------------------------------
    demo_mode: bool = True
    demo_api_base_url: str = "http://demo:9000"

    @field_validator("cors_origins", "trusted_hosts", mode="before")
    @classmethod
    def _split_csv(cls, value: object) -> object:
        if isinstance(value, str):
            stripped = value.strip()
            if not stripped:
                return []
            return [item.strip() for item in stripped.split(",") if item.strip()]
        return value

    @property
    def is_production(self) -> bool:
        return self.app_env.lower() in {"production", "prod"}

    def public_base_url(self) -> str:
        return "https://localhost:8443" if self.is_production else "http://localhost:8080"


@lru_cache
def get_settings() -> Settings:
    return Settings()
