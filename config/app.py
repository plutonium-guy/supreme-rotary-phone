"""Application factory — the single entry point that assembles the API.

``create_app`` mirrors Django's ``get_wsgi_application``: it configures
logging, discovers installed apps, mounts every app router, wires the ORM
and the admin, then returns a ready-to-serve ``FastAPI`` instance.

Startup/shutdown is driven by a single ``lifespan`` (the modern ASGI way);
we deliberately avoid ``@app.on_event`` because passing ``lifespan`` to
FastAPI disables those handlers.
"""

from __future__ import annotations

from contextlib import asynccontextmanager

import asyncio

from fastapi import FastAPI
from loguru import logger

from config.admin import configure_admin, mount_admin
from config.database import create_all, import_models
from config.logging import configure_logging
from config.settings import settings
from core.apps import autodiscover
from core.db import dispose_engine


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting '{}' (debug={})", settings.PROJECT_NAME, settings.DEBUG)

    # Populate Base.metadata before anything touches the ORM.
    import_models()
    if settings.DEBUG:
        # Convenience only. Prefer Alembic migrations; creating tables costs
        # several warehouse round-trips on every boot.
        await asyncio.to_thread(create_all)

    try:
        await configure_admin()
        yield
    finally:
        await asyncio.to_thread(dispose_engine)
        logger.info("Shutting down '{}'", settings.PROJECT_NAME)


def create_app() -> FastAPI:
    configure_logging()

    app = FastAPI(
        title=settings.PROJECT_NAME,
        debug=settings.DEBUG,
        lifespan=lifespan,
    )

    # Discover installed apps and mount their routers under /api/<label>.
    registry = autodiscover()
    for label, router in registry.routers():
        app.include_router(router, prefix=f"/api/{label}", tags=[label])
        logger.debug("Mounted router for app '{}'", label)

    mount_admin(app)

    @app.get("/health", tags=["system"])
    async def health() -> dict[str, str]:
        return {"status": "ok", "project": settings.PROJECT_NAME}

    return app
