"""Django-``admin.site.register`` style helpers for **fastadmin**.

fastadmin already uses the Django admin idiom (``ModelAdmin`` subclasses with
``list_display`` etc.). These helpers let an app register a model with one
line, or register nothing and get a sensible default::

    from core.admin import register_model
    from apps.blog.models import Post

    register_model(Post, list_display=("id", "title", "created_at"))

For full control, subclass ``fastadmin.TortoiseModelAdmin`` yourself and call
``fastadmin.register(Model)`` — see ``apps/users/admin.py``.
"""

from __future__ import annotations

import importlib
import inspect

from fastadmin import TortoiseModelAdmin, register_admin_model_class
from loguru import logger
from tortoise.models import Model as TortoiseModel

#: Column names never shown/edited in the dashboard (secrets).
HIDDEN_FIELDS: set[str] = {"password", "hashed_password"}

#: Guard against registering the same model twice across reloads.
_registered: set[str] = set()


def _visible_columns(model: type[TortoiseModel], exclude: set[str]) -> list[str]:
    return [name for name in model._meta.fields_db_projection if name not in exclude]


def register_model(
    model: type[TortoiseModel],
    *,
    list_display: tuple[str, ...] | None = None,
    search_fields: tuple[str, ...] = (),
    list_filter: tuple[str, ...] = (),
    exclude: tuple[str, ...] = (),
    admin_base: type[TortoiseModelAdmin] = TortoiseModelAdmin,
    **attrs,
) -> type[TortoiseModelAdmin] | None:
    """Register ``model`` with a generated ``TortoiseModelAdmin``.

    ``list_display`` defaults to every concrete column minus :data:`HIDDEN_FIELDS`
    and ``exclude``. Secret columns are also kept out of the edit form. Extra
    ``ModelAdmin`` attributes can be passed as keyword arguments.
    Returns the generated admin class (or ``None`` if already registered).
    """
    if model.__name__ in _registered:
        return None

    hidden = HIDDEN_FIELDS | set(exclude)
    display = list_display or tuple(_visible_columns(model, hidden))

    admin_cls = type(
        f"{model.__name__}Admin",
        (admin_base,),
        {
            "list_display": display,
            "search_fields": search_fields,
            "list_filter": list_filter,
            "exclude": tuple(hidden),
            **attrs,
        },
    )
    register_admin_model_class(admin_cls, [model])
    _registered.add(model.__name__)
    logger.debug("Admin: registered model '{}'", model.__name__)
    return admin_cls


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
