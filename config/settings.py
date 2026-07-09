"""Central project settings, à la Django's ``settings.py``.

All configuration is read from the environment (``.env`` supported) via
``pydantic-settings`` so the same code runs in dev, test and prod.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BASE_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- Core -----------------------------------------------------------
    PROJECT_NAME: str = "fastAPI_api"
    DEBUG: bool = True
    SECRET_KEY: str = "change-me-in-production"

    HOST: str = "127.0.0.1"
    PORT: int = 8000

    # --- Installed apps (Django-style) ----------------------------------
    # Each entry is an importable package under ``apps/`` that exposes an
    # ``AppConfig`` in its ``apps.py``. Order matters for router mounting.
    INSTALLED_APPS: list[str] = [
        "apps.users",
    ]

    # --- Database (Tortoise ORM) ----------------------------------------
    # Any Tortoise-supported URL. Defaults to sqlite for zero-config dev.
    DATABASE_URL: str = f"sqlite://{BASE_DIR / 'db.sqlite3'}"

    # --- Admin dashboard (fastadmin — no Redis) -------------------------
    ADMIN_PREFIX: str = "admin"  # mounted at /<ADMIN_PREFIX>
    ADMIN_SITE_NAME: str = "fastAPI_api Admin"
    # ORM model (by class name) used for admin authentication + its username
    # field. Its ModelAdmin must implement ``authenticate``/``change_password``.
    ADMIN_USER_MODEL: str = "AdminUser"
    ADMIN_USER_MODEL_USERNAME_FIELD: str = "username"
    # Secret for signing the admin session JWT. Defaults to SECRET_KEY.
    ADMIN_SECRET_KEY: str = ""
    # A superuser is auto-created on startup from these so the dashboard is
    # usable immediately (no manual ``createadmin`` step). Change in prod.
    ADMIN_USERNAME: str = "admin"
    ADMIN_PASSWORD: str = "admin"
    ADMIN_AUTO_CREATE: bool = True

    @property
    def admin_path(self) -> str:
        return f"/{self.ADMIN_PREFIX.strip('/')}"

    @property
    def admin_secret(self) -> str:
        return self.ADMIN_SECRET_KEY or self.SECRET_KEY

    # --- Logging --------------------------------------------------------
    LOG_LEVEL: str = "DEBUG"
    LOG_DIR: Path = BASE_DIR / "logs"


@lru_cache
def get_settings() -> Settings:
    """Return the singleton settings instance."""
    return Settings()


settings = get_settings()
