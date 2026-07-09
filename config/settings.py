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

    # --- fastapi-admin --------------------------------------------------
    REDIS_URL: str = "redis://localhost:6379/0"
    ADMIN_PATH: str = "/admin"
    ADMIN_TITLE: str = "fastAPI_api Admin"
    # A superuser is auto-created on startup from these so the dashboard is
    # usable immediately (no manual ``createadmin`` step). Change in prod.
    ADMIN_USERNAME: str = "admin"
    ADMIN_PASSWORD: str = "admin"
    ADMIN_AUTO_CREATE: bool = True

    # --- Logging --------------------------------------------------------
    LOG_LEVEL: str = "DEBUG"
    LOG_DIR: Path = BASE_DIR / "logs"


@lru_cache
def get_settings() -> Settings:
    """Return the singleton settings instance."""
    return Settings()


settings = get_settings()
