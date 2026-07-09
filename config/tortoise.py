"""Tortoise ORM configuration derived from ``INSTALLED_APPS``.

``TORTOISE_ORM`` is consumed both by the running app (``RegisterTortoise`` in
the lifespan) and by Aerich for migrations, so ``manage.py`` and ``aerich.ini``
stay in sync.
"""

from __future__ import annotations

from core.apps import autodiscover
from config.settings import settings


def build_tortoise_config() -> dict:
    """Assemble the Tortoise config dict from the installed apps."""
    registry = autodiscover()
    # Every app's models live in the "models" Tortoise app namespace, plus
    # aerich's own migration bookkeeping models.
    model_modules = registry.models_modules() + ["aerich.models"]
    return {
        "connections": {"default": settings.DATABASE_URL},
        "apps": {
            "models": {
                "models": model_modules,
                "default_connection": "default",
            }
        },
        "use_tz": True,
        "timezone": "UTC",
    }


TORTOISE_ORM = build_tortoise_config()
