"""Django-``admin.site.register`` style helpers for fastapi-admin.

Instead of writing a full ``Model`` resource class per model, an app can do::

    from core.admin import register_model
    from apps.blog.models import Post

    register_model(Post, icon="fas fa-newspaper")

or write no ``admin.py`` at all — :func:`autoregister_models` builds a
sensible default resource for every model the app defines.
"""

from __future__ import annotations

import importlib
import inspect

from fastapi_admin.app import app as admin_app
from fastapi_admin.resources import Link, Model
from loguru import logger
from tortoise.models import Model as TortoiseModel

#: Column names never shown in the dashboard (secrets).
HIDDEN_FIELDS: set[str] = {"password", "hashed_password"}

#: Guard against registering the same model twice across reloads.
_registered: set[str] = set()


def register_model(
    model: type[TortoiseModel],
    *,
    label: str | None = None,
    icon: str = "fas fa-table",
    exclude: tuple[str, ...] = (),
    fields: list[str] | None = None,
) -> type[Model] | None:
    """Register ``model`` with the admin using sensible defaults.

    Field list defaults to every concrete column minus :data:`HIDDEN_FIELDS`
    and ``exclude``. Returns the generated resource class (or ``None`` if the
    model was already registered).
    """
    if model.__name__ in _registered:
        return None

    hide = HIDDEN_FIELDS | set(exclude)
    field_names = fields or [
        name for name in model._meta.fields_db_projection if name not in hide
    ]

    resource = type(
        f"{model.__name__}Resource",
        (Model,),
        {
            "label": label or f"{model.__name__}s",
            "model": model,
            "icon": icon,
            "page_title": label or model.__name__,
            "fields": list(field_names),
        },
    )
    admin_app.register(resource)
    _registered.add(model.__name__)
    logger.debug("Admin: registered model '{}'", model.__name__)
    return resource


def add_link(label: str, url: str, *, icon: str = "fas fa-link", target: str = "_self") -> None:
    """Add a top-level menu link to the dashboard sidebar."""
    resource = type(
        f"{label.replace(' ', '')}Link",
        (Link,),
        {"label": label, "url": url, "icon": icon, "target": target},
    )
    admin_app.register(resource)


def autoregister_models(models_module_path: str) -> None:
    """Register every concrete model *defined in* the given models module."""
    module = importlib.import_module(models_module_path)
    for obj in vars(module).values():
        if (
            inspect.isclass(obj)
            and issubclass(obj, TortoiseModel)
            and obj.__module__ == module.__name__
            and not obj._meta.abstract
        ):
            register_model(obj)
