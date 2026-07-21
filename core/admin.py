"""Django-``admin.site.register`` style helpers for **fastadmin** (SQLAlchemy).

fastadmin already uses the Django admin idiom (``ModelAdmin`` subclasses with
``list_display`` etc.). These helpers let an app register a model with one
line, or register nothing and get a sensible default::

    from core.admin import register_model
    from apps.blog.models import Post

    register_model(Post, list_display=("id", "title", "created_at"))

For full control, subclass :class:`ModelAdmin` below and call
``fastadmin.register(Model)`` — see ``apps/users/admin.py``. Always inherit
from :class:`ModelAdmin` rather than ``SqlAlchemyModelAdmin`` directly, so the
Databricks sessionmaker is attached.
"""

from __future__ import annotations

import importlib
import inspect
from typing import Any
from uuid import UUID

from fastadmin import SqlAlchemyModelAdmin, register_admin_model_class
from loguru import logger

from core.db import admin_sessionmaker
from core.models import Base

#: Column names never shown/edited in the dashboard (secrets).
HIDDEN_FIELDS: set[str] = {"password", "hashed_password"}

#: Guard against registering the same model twice across reloads.
_registered: set[str] = set()


class ModelAdmin(SqlAlchemyModelAdmin):
    """Base ModelAdmin bound to the Databricks session facade.

    Two impedance mismatches are handled here:

    * fastadmin awaits every session call, but the Databricks driver is sync —
      ``admin_sessionmaker`` bridges that (see ``core.db``).
    * fastadmin treats primary keys as ``int`` or ``uuid.UUID`` and hands back
      ``UUID`` instances, but our PKs are ``String(36)`` columns. Binding a
      ``UUID`` object to a STRING column fails, so ids are coerced below.
    """

    db_session_maker = staticmethod(admin_sessionmaker)

    @staticmethod
    def _pk(value: Any) -> Any:
        return str(value) if isinstance(value, UUID) else value

    async def orm_get_obj(self, id: Any) -> Any:
        return await super().orm_get_obj(self._pk(id))

    async def orm_save_obj(self, id: Any, payload: dict) -> Any:
        return await super().orm_save_obj(self._pk(id) if id else id, payload)

    async def orm_delete_obj(self, id: Any) -> None:
        return await super().orm_delete_obj(self._pk(id))


def _visible_columns(model: type[Base], exclude: set[str]) -> list[str]:
    return [c.key for c in model.__table__.columns if c.key not in exclude]


def register_model(
    model: type[Base],
    *,
    list_display: tuple[str, ...] | None = None,
    search_fields: tuple[str, ...] = (),
    list_filter: tuple[str, ...] = (),
    exclude: tuple[str, ...] = (),
    admin_base: type[SqlAlchemyModelAdmin] = ModelAdmin,
    **attrs,
) -> type[SqlAlchemyModelAdmin] | None:
    """Register ``model`` with a generated ``ModelAdmin``.

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
    register_admin_model_class(
        admin_cls, [model], sqlalchemy_sessionmaker=admin_sessionmaker
    )
    _registered.add(model.__name__)
    logger.debug("Admin: registered model '{}'", model.__name__)
    return admin_cls


def autoregister_models(models_module_path: str) -> None:
    """Register every concrete model *defined in* the given models module."""
    module = importlib.import_module(models_module_path)
    for obj in vars(module).values():
        if (
            inspect.isclass(obj)
            and issubclass(obj, Base)
            and obj.__module__ == module.__name__
            and hasattr(obj, "__table__")
        ):
            register_model(obj)
