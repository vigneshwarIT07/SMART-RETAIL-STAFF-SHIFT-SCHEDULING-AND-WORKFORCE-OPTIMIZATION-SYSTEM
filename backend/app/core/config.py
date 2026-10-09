"""Application configuration.

All settings are read from environment variables (or a local ``.env`` file)
using ``pydantic-settings``. Nothing sensitive has a usable default: in
``production`` the application refuses to start with placeholder secrets.
"""

from __future__ import annotations

import secrets
from functools import lru_cache
from typing import List

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Values that are obviously placeholders. They are rejected in production.
_PLACEHOLDER_SECRETS = {
    "CHANGE_ME_development_only_secret_key",
    "CHANGE_ME",
    "changeme",
    "secret",
    "CHANGE_ME_development_only_secret_key_please_replace",
}


class Settings(BaseSettings):
    """Typed application settings loaded from the environment."""

    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # --- Application ---------------------------------------------------
    app_name: str = "Retail Staff Shift Scheduling Platform"
    environment: str = "development"
    debug: bool = False

    # --- Database ------------------------------------------------------
    database_url: str = (
        "postgresql+psycopg://postgres:postgres@localhost:5432/retail_scheduling"
    )
    db_echo: bool = False
    db_pool_size: int = 5
    db_max_overflow: int = 10

    # --- JWT -----------------------------------------------------------
    jwt_secret_key: str = "CHANGE_ME_development_only_secret_key"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60

    # --- URLs / CORS ----------------------------------------------------
    frontend_url: str = "http://localhost:5173"
    backend_url: str = "http://localhost:8000"
    extra_cors_origins: List[str] = Field(default_factory=list)

    # --- Bootstrap manager ---------------------------------------------
    manager_email: str = "manager@example.com"

    # --- Attendance rules ----------------------------------------------
    attendance_grace_minutes: int = 10
    missing_clockout_grace_minutes: int = 120

    # --- Scheduling business rules -------------------------------------
    max_weekly_hours: int = 40
    min_rest_hours_between_shifts: int = 11
    max_consecutive_work_days: int = 6
    overtime_warning_hours: int = 36
    min_employee_status_warning_hours: int = 32

    # --- Email ----------------------------------------------------------
    email_host: str = ""
    email_port: int = 587
    email_username: str = ""
    email_password: str = ""
    email_from: str = ""
    email_use_tls: bool = True

    # --- Rate limiting (per-process, in-memory) -------------------------
    rate_limit_enabled: bool = True
    rate_limit_login_attempts: int = 5
    rate_limit_window_seconds: int = 60

    # --- Pagination -----------------------------------------------------
    default_page_size: int = 20
    max_page_size: int = 100

    # ------------------------------------------------------------------
    # Validators
    # ------------------------------------------------------------------
    @field_validator("extra_cors_origins", mode="before")
    @classmethod
    def _split_origins(cls, value: object) -> object:
        """Allow comma-separated origins in a single environment variable."""
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value

    # ------------------------------------------------------------------
    # Derived helpers
    # ------------------------------------------------------------------
    @property
    def is_production(self) -> bool:
        """True when running with ``ENVIRONMENT=production``."""
        return self.environment.strip().lower() == "production"

    @property
    def cors_origins(self) -> List[str]:
        """Browser origins permitted to call the API.

        Only the explicitly configured frontend origin (plus any extras) are
        allowed. A wildcard is never returned.
        """
        origins = [self.frontend_url.strip()]
        origins.extend(self.extra_cors_origins)
        # Preserve order while removing duplicates and blanks.
        return list(dict.fromkeys(origin for origin in origins if origin))

    @property
    def email_enabled(self) -> bool:
        """True only when enough configuration exists to attempt delivery.

        The system is fully usable when this is False: messages are still
        rendered and stored as notifications, and ``/api/health`` reports the
        disabled state honestly.
        """
        return bool(self.email_host.strip() and self.email_from.strip())

    @property
    def api_prefix(self) -> str:
        """URL prefix shared by every router."""
        return "/api"

    def validate_production_secrets(self) -> None:
        """Abort startup when production is configured with unsafe values.

        Raises:
            RuntimeError: if a placeholder secret or default URL is present in
                production.
        """
        if not self.is_production:
            return

        problems = []
        if self.jwt_secret_key in _PLACEHOLDER_SECRETS:
            problems.append("JWT_SECRET_KEY is still a placeholder value")
        elif len(self.jwt_secret_key) < 32:
            problems.append("JWT_SECRET_KEY is shorter than 32 characters")
        if self.jwt_secret_key == self.jwt_secret_key.strip():  # pragma: no cover
            pass
        if "localhost" in self.frontend_url or "127.0.0.1" in self.frontend_url:
            problems.append("FRONTEND_URL still points at localhost")
        if "localhost" in self.database_url or "127.0.0.1" in self.database_url:
            problems.append("DATABASE_URL still points at localhost")

        if problems:
            detail = "; ".join(problems)
            raise RuntimeError(
                "Refusing to start in production with unsafe configuration: "
                f"{detail}. See .env.example and README section 9."
            )

    @classmethod
    def generate_secret(cls) -> str:
        """Return a fresh URL-safe secret suitable for JWT signing."""
        return secrets.token_urlsafe(64)


@lru_cache
def get_settings() -> Settings:
    """Return the process-wide settings singleton.

    The result is cached so that environment parsing happens once. Tests can
    call ``get_settings.cache_clear()`` after changing the environment.
    """
    return Settings()


settings = get_settings()