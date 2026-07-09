#!/usr/bin/env python
"""Project management CLI — the Django ``manage.py`` of this framework.

Commands:
    runserver [--host --port --reload]   Start the ASGI dev server.
    startapp <name>                      Scaffold a new app under ``apps/``.
    init-db                              Create tables from models (dev only).
    makemigrations                       Generate Aerich migrations.
    migrate                              Apply Aerich migrations.
    createadmin <username> <password>    Create a fastapi-admin superuser.
    shell                                Async REPL with Tortoise initialised.
"""

from __future__ import annotations

import argparse
import asyncio
import subprocess
import sys
from textwrap import dedent

import core  # noqa: F401 - install beartype hook before anything else

from config.settings import BASE_DIR, settings

APPS_DIR = BASE_DIR / "apps"


# --------------------------------------------------------------------------- #
# runserver
# --------------------------------------------------------------------------- #
def cmd_runserver(args: argparse.Namespace) -> None:
    import uvicorn

    uvicorn.run(
        "main:app",
        host=args.host or settings.HOST,
        port=args.port or settings.PORT,
        reload=args.reload,
    )


# --------------------------------------------------------------------------- #
# startapp
# --------------------------------------------------------------------------- #
_APP_TEMPLATE: dict[str, str] = {
    "__init__.py": '"""The {name} app."""\n\ndefault_app_config = "apps.{name}.apps.{cls}Config"\n',
    "apps.py": dedent(
        '''\
        """App configuration for the {name} app."""

        from core.apps import AppConfig


        class {cls}Config(AppConfig):
            name = "apps.{name}"
            label = "{name}"
            verbose_name = "{title}"
        '''
    ),
    "models.py": dedent(
        '''\
        """Tortoise ORM models for the {name} app."""

        from __future__ import annotations

        from tortoise import fields

        from core.models import TimestampedModel


        class {cls}(TimestampedModel):
            name = fields.CharField(max_length=255)

            class Meta:
                table = "{name}"
        '''
    ),
    "schemas.py": dedent(
        '''\
        """Pydantic schemas for the {name} app."""

        from __future__ import annotations

        from pydantic import BaseModel, ConfigDict


        class {cls}Out(BaseModel):
            model_config = ConfigDict(from_attributes=True)

            id: int
            name: str
        '''
    ),
    "services.py": '"""Business logic for the {name} app."""\n',
    "views.py": dedent(
        '''\
        """Routes for the {name} app (auto-mounted at /api/{name})."""

        from __future__ import annotations

        from fastapi import APIRouter

        router = APIRouter()


        @router.get("")
        async def index() -> dict[str, str]:
            return {{"app": "{name}"}}
        '''
    ),
    "admin.py": dedent(
        '''\
        """Admin registration for the {name} app.

        One line per model. Delete this file to auto-register every model
        the app defines. See ``core.admin.register_model`` for options.
        """

        from core.admin import register_model

        from apps.{name}.models import {cls}

        register_model({cls}, label="{title}", icon="fas fa-table")
        '''
    ),
}


def cmd_startapp(args: argparse.Namespace) -> None:
    name = args.name.strip().lower()
    if not name.isidentifier():
        sys.exit(f"Invalid app name: {name!r}")
    target = APPS_DIR / name
    if target.exists():
        sys.exit(f"App '{name}' already exists at {target}")

    cls = "".join(part.title() for part in name.split("_"))
    title = name.replace("_", " ").title()
    target.mkdir(parents=True)
    for filename, template in _APP_TEMPLATE.items():
        (target / filename).write_text(template.format(name=name, cls=cls, title=title))

    print(f"Created app '{name}' at {target}")
    print(f"→ Add \"apps.{name}\" to INSTALLED_APPS in config/settings.py")


# --------------------------------------------------------------------------- #
# init-db (dev convenience — generate schemas directly from models)
# --------------------------------------------------------------------------- #
def cmd_init_db(_: argparse.Namespace) -> None:
    from tortoise import Tortoise

    from config.tortoise import TORTOISE_ORM

    async def _run() -> None:
        await Tortoise.init(config=TORTOISE_ORM)
        await Tortoise.generate_schemas()
        await Tortoise.close_connections()
        print("Database schema generated.")

    asyncio.run(_run())


# --------------------------------------------------------------------------- #
# aerich migration wrappers
# --------------------------------------------------------------------------- #
def _aerich(*aerich_args: str) -> None:
    subprocess.run([sys.executable, "-m", "aerich", *aerich_args], check=True)


def cmd_makemigrations(args: argparse.Namespace) -> None:
    if not (BASE_DIR / "migrations").exists():
        _aerich("init", "-t", "config.tortoise.TORTOISE_ORM")
        _aerich("init-db")
    else:
        _aerich("migrate", *(["--name", args.name] if args.name else []))


def cmd_migrate(_: argparse.Namespace) -> None:
    _aerich("upgrade")


# --------------------------------------------------------------------------- #
# createadmin
# --------------------------------------------------------------------------- #
def cmd_createadmin(args: argparse.Namespace) -> None:
    from tortoise import Tortoise

    from apps.users.services import ensure_admin_user
    from config.tortoise import TORTOISE_ORM

    async def _run() -> None:
        await Tortoise.init(config=TORTOISE_ORM)
        await Tortoise.generate_schemas()
        # Standalone (no admin app configured), so hash here.
        admin, created = await ensure_admin_user(
            args.username, args.password, email=args.email, prehash=True
        )
        await Tortoise.close_connections()
        print(f"Admin user '{admin.username}' {'created' if created else 'already exists'}.")

    asyncio.run(_run())


# --------------------------------------------------------------------------- #
# shell
# --------------------------------------------------------------------------- #
def cmd_shell(_: argparse.Namespace) -> None:
    import code

    from tortoise import Tortoise

    from config.tortoise import TORTOISE_ORM

    async def _boot() -> None:
        await Tortoise.init(config=TORTOISE_ORM)

    asyncio.run(_boot())
    code.interact(local={"Tortoise": Tortoise, "asyncio": asyncio})


# --------------------------------------------------------------------------- #
# dispatch
# --------------------------------------------------------------------------- #
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="manage.py", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("runserver", help="Start the ASGI dev server")
    p.add_argument("--host")
    p.add_argument("--port", type=int)
    p.add_argument("--reload", action="store_true", default=True)
    p.set_defaults(func=cmd_runserver)

    p = sub.add_parser("startapp", help="Scaffold a new app")
    p.add_argument("name")
    p.set_defaults(func=cmd_startapp)

    p = sub.add_parser("init-db", help="Generate schema from models (dev)")
    p.set_defaults(func=cmd_init_db)

    p = sub.add_parser("makemigrations", help="Generate Aerich migrations")
    p.add_argument("--name", default=None)
    p.set_defaults(func=cmd_makemigrations)

    p = sub.add_parser("migrate", help="Apply Aerich migrations")
    p.set_defaults(func=cmd_migrate)

    p = sub.add_parser("createadmin", help="Create an admin superuser")
    p.add_argument("username")
    p.add_argument("password")
    p.add_argument("--email", default=None)
    p.set_defaults(func=cmd_createadmin)

    p = sub.add_parser("shell", help="Async REPL with Tortoise initialised")
    p.set_defaults(func=cmd_shell)

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
