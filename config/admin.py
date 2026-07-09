"""Admin dashboard integration (fastadmin) — no Redis.

fastadmin reads its configuration from environment variables at import time,
so we export them from ``settings`` *before* importing the package. Sessions
are signed JWTs in an http-only cookie (``ADMIN_SECRET_KEY``); there is no
Redis or other external dependency.
"""

from __future__ import annotations

import os

from fastapi import FastAPI
from loguru import logger

from config.settings import settings

# --- Export settings -> env for fastadmin (must precede its import) ---------
os.environ["ADMIN_PREFIX"] = settings.ADMIN_PREFIX
os.environ["ADMIN_SITE_NAME"] = settings.ADMIN_SITE_NAME
os.environ["ADMIN_USER_MODEL"] = settings.ADMIN_USER_MODEL
os.environ["ADMIN_USER_MODEL_USERNAME_FIELD"] = settings.ADMIN_USER_MODEL_USERNAME_FIELD
os.environ["ADMIN_SECRET_KEY"] = settings.admin_secret

from fastadmin import fastapi_app as admin_app  # noqa: E402  (env set above)

from core.apps import apps  # noqa: E402


def mount_admin(app: FastAPI) -> None:
    """Mount the fastadmin sub-app. Configuration happens in the app lifespan."""
    app.mount(settings.admin_path, admin_app)


async def configure_admin() -> None:
    """Register admin resources and seed a superuser (runs on startup).

    Wrapped so a failure degrades gracefully — the API keeps running, only the
    dashboard is unavailable.
    """
    try:
        # Import each app's admin.py (registers resources) or auto-register.
        apps.admin_resources()

        if settings.ADMIN_AUTO_CREATE:
            from apps.users.services import ensure_admin_user

            _, created = await ensure_admin_user(
                settings.ADMIN_USERNAME, settings.ADMIN_PASSWORD, prehash=True
            )
            if created:
                logger.info(
                    "Admin: created superuser '{}' (change ADMIN_PASSWORD in prod)",
                    settings.ADMIN_USERNAME,
                )

        logger.info("Admin ready at {}", settings.admin_path)
    except Exception as exc:  # noqa: BLE001 - admin is optional in dev
        logger.warning("Admin setup skipped: {}", exc)
