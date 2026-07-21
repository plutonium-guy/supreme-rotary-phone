"""Database wiring derived from ``INSTALLED_APPS``.

Importing every installed app's ``models`` module is what populates
``Base.metadata`` — the same job Django's app loader does, and what both
``init-db`` and Alembic's autogenerate rely on.
"""

from __future__ import annotations

import importlib

from loguru import logger

from core.apps import autodiscover
from core.models import Base


def import_models() -> None:
    """Import each installed app's models so they register on ``Base.metadata``."""
    registry = autodiscover()
    for dotted in registry.models_modules():
        try:
            importlib.import_module(dotted)
        except ModuleNotFoundError:
            logger.debug("No models module for '{}'", dotted)


def get_metadata():
    """Return the fully-populated SQLAlchemy metadata."""
    import_models()
    return Base.metadata


def create_all() -> None:
    """Create every table in the configured Databricks catalog/schema.

    Delta accepts PRIMARY KEY / UNIQUE clauses but does **not enforce** them,
    so this creates the tables, not the guarantees.
    """
    from core.db import get_engine

    metadata = get_metadata()
    metadata.create_all(bind=get_engine())
    logger.info(
        "Created/verified {} table(s): {}",
        len(metadata.tables),
        ", ".join(sorted(metadata.tables)),
    )
