"""Django-style ``AppConfig`` and the global application registry.

Each installed app declares an ``AppConfig`` subclass in its ``apps.py``.
The registry discovers them from ``settings.INSTALLED_APPS`` and exposes
their models, routers and admin resources to the rest of the framework.
"""

from __future__ import annotations

import importlib
from dataclasses import dataclass, field

from beartype import beartype
from fastapi import APIRouter
from loguru import logger

from config.settings import settings


class AppConfig:
    """Base class for an app's configuration.

    Subclass it in ``apps/<name>/apps.py`` and set :attr:`name` to the
    dotted package path (e.g. ``"apps.users"``). Override :attr:`label`
    and :attr:`verbose_name` as needed.
    """

    #: Dotted import path of the app package, e.g. ``"apps.users"``.
    name: str = ""
    #: Short unique label; defaults to the last path segment.
    label: str = ""
    #: Human-friendly name shown in the admin.
    verbose_name: str = ""
    #: Whether this app's views are exposed as MCP tools. Set False to opt out.
    expose_mcp: bool = True

    def __init__(self) -> None:
        if not self.name:
            raise ValueError(f"{type(self).__name__}.name must be set")
        self.label = self.label or self.name.rsplit(".", 1)[-1]
        self.verbose_name = self.verbose_name or self.label.replace("_", " ").title()

    @property
    def models_module(self) -> str:
        return f"{self.name}.models"

    def ready(self) -> None:
        """Hook called once the app is loaded. Override for signals etc."""


@dataclass
class _LoadedApp:
    config: AppConfig
    router: APIRouter | None = field(default=None)


class AppRegistry:
    """Loads and caches :class:`AppConfig` instances for installed apps."""

    def __init__(self) -> None:
        self._apps: dict[str, _LoadedApp] = {}
        self._ready = False

    @beartype
    def populate(self, installed_apps: list[str]) -> None:
        if self._ready:
            return
        for dotted in installed_apps:
            config = self._load_config(dotted)
            self._apps[config.label] = _LoadedApp(config=config)
            logger.debug("Registered app '{}' ({})", config.label, config.name)
        for loaded in self._apps.values():
            loaded.config.ready()
        self._ready = True

    def _load_config(self, dotted: str) -> AppConfig:
        module = importlib.import_module(f"{dotted}.apps")
        for attr in vars(module).values():
            if (
                isinstance(attr, type)
                and issubclass(attr, AppConfig)
                and attr is not AppConfig
            ):
                return attr()
        raise ImportError(f"No AppConfig subclass found in {dotted}.apps")

    @property
    def configs(self) -> list[AppConfig]:
        return [loaded.config for loaded in self._apps.values()]

    def get(self, label: str) -> AppConfig:
        return self._apps[label].config

    def models_modules(self) -> list[str]:
        """Return dotted paths of every app's ``models`` module."""
        return [c.models_module for c in self.configs]

    def routers(self) -> list[tuple[str, APIRouter]]:
        """Import each app's ``views`` module and collect its ``router``."""
        collected: list[tuple[str, APIRouter]] = []
        for config in self.configs:
            try:
                views = importlib.import_module(f"{config.name}.views")
            except ModuleNotFoundError:
                continue
            router = getattr(views, "router", None)
            if isinstance(router, APIRouter):
                collected.append((config.label, router))
        return collected

    def admin_resources(self) -> None:
        """Register every app's admin resources.

        If an app ships an ``admin.py`` it is imported for its side effects
        (resources register at import time). Otherwise the framework
        auto-registers a default resource for each model the app defines.
        """
        from core.admin import autoregister_models

        for config in self.configs:
            try:
                importlib.import_module(f"{config.name}.admin")
            except ModuleNotFoundError:
                autoregister_models(config.models_module)


#: Process-wide registry, populated by the app factory at startup.
apps = AppRegistry()


def autodiscover() -> AppRegistry:
    """Populate the global registry from settings and return it."""
    apps.populate(settings.INSTALLED_APPS)
    return apps
