"""fastapi-admin integration — zero-config dashboard.

Design goals (make the dashboard "just work"):
  * **No Redis required** — falls back to in-memory fakeredis if the
    configured Redis is unreachable, so ``/admin`` works out of the box.
  * **No manual superuser** — a login is auto-created from settings.
  * **No per-model boilerplate** — apps register models in one line (or not
    at all) via ``core.admin``.

The admin is a self-contained sub-application mounted at ``settings.ADMIN_PATH``.
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi_admin.app import app as admin_app
from fastapi_admin.providers.login import UsernamePasswordProvider
from loguru import logger

from config.settings import BASE_DIR, settings
from core.admin import add_link
from core.apps import apps

_LOGO = "https://fastapi.tiangolo.com/img/logo-margin/logo-teal.png"


async def _get_redis():
    """Return an async Redis client, falling back to fakeredis if needed."""
    import redis.asyncio as aioredis

    try:
        client = aioredis.from_url(
            settings.REDIS_URL, decode_responses=True, encoding="utf-8"
        )
        await client.ping()
        logger.info("Admin: connected to Redis at {}", settings.REDIS_URL)
        return client
    except Exception as exc:  # noqa: BLE001 - any connection failure -> fallback
        logger.warning(
            "Admin: Redis unavailable ({}); using in-memory fakeredis "
            "(sessions reset on restart)",
            exc,
        )
        from fakeredis import aioredis as fake

        return fake.FakeRedis(decode_responses=True, encoding="utf-8")


def _register_dashboard_menu() -> None:
    """Add convenience links to the dashboard sidebar."""
    add_link("API Docs", "/docs", icon="fas fa-book", target="_blank")
    add_link("Health", "/health", icon="fas fa-heartbeat", target="_blank")


async def configure_admin() -> None:
    """Configure fastapi-admin once Tortoise is ready.

    Called from the app ``lifespan`` on startup. Wrapped so a failure (e.g.
    genuinely unusable environment) degrades gracefully — the API still runs,
    only ``/admin`` is unavailable.
    """
    try:
        await _configure_admin()
    except Exception as exc:  # noqa: BLE001 - admin is optional in dev
        logger.warning("Admin setup skipped: {}", exc)


async def _configure_admin() -> None:
    from apps.users.models import AdminUser
    from apps.users.services import ensure_admin_user

    # Collect resources: app admin.py modules + auto-registered models,
    # then the dashboard menu links.
    apps.admin_resources()
    _register_dashboard_menu()

    redis = await _get_redis()
    await admin_app.configure(
        logo_url=_LOGO,
        admin_path=settings.ADMIN_PATH,
        template_folders=[str(BASE_DIR / "templates" / "admin")],
        favicon_url="https://fastapi.tiangolo.com/img/favicon.png",
        providers=[
            UsernamePasswordProvider(
                admin_model=AdminUser,
                login_logo_url=_LOGO,
                login_title=settings.ADMIN_TITLE,
            )
        ],
        redis=redis,
    )

    # Seed a superuser so the dashboard is immediately usable. The provider's
    # pre_save signal (registered by configure() above) hashes the password.
    if settings.ADMIN_AUTO_CREATE:
        _, created = await ensure_admin_user(
            settings.ADMIN_USERNAME, settings.ADMIN_PASSWORD
        )
        if created:
            logger.info(
                "Admin: created superuser '{}' (change ADMIN_PASSWORD in prod)",
                settings.ADMIN_USERNAME,
            )

    logger.info("Admin ready at {}", settings.ADMIN_PATH)


def mount_admin(app: FastAPI) -> None:
    """Mount the admin sub-app. Configuration happens in the app lifespan."""
    app.mount(settings.ADMIN_PATH, admin_app)
