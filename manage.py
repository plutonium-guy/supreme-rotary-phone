#!/usr/bin/env python
"""Project management CLI — the Django ``manage.py`` of this framework.

Commands:
    runserver [--host --port --reload]   Start the ASGI dev server.
    startapp <name>                      Scaffold a new app under ``apps/``.
    init-db                              Create tables in Databricks from models.
    makemigrations                       Generate an Alembic revision.
    migrate                              Apply Alembic migrations.
    createadmin <username> <password>    Create an admin superuser.
    dbshell                              Check connectivity, print catalog info.
    shell                                REPL with a Databricks session ready.
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
        """SQLAlchemy models for the {name} app (stored in Databricks)."""

        from __future__ import annotations

        from sqlalchemy import String
        from sqlalchemy.orm import Mapped, mapped_column

        from core.models import TimestampedModel


        class {cls}(TimestampedModel):
            __tablename__ = "{name}"

            name: Mapped[str] = mapped_column(String(255))
        '''
    ),
    "schemas.py": dedent(
        '''\
        """Pydantic schemas for the {name} app."""

        from __future__ import annotations

        from pydantic import BaseModel, ConfigDict


        class {cls}Out(BaseModel):
            model_config = ConfigDict(from_attributes=True)

            id: str
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


        @router.get("", operation_id="{name}_index")
        async def index() -> dict[str, str]:
            return {{"app": "{name}"}}
        '''
    ),
    "admin.py": dedent(
        '''\
        """Admin registration for the {name} app (fastadmin).

        One line per model. Delete this file to auto-register every model
        the app defines. See ``core.admin.register_model`` for options.
        """

        from core.admin import register_model

        from apps.{name}.models import {cls}

        register_model({cls}, list_display=("id", "name"), search_fields=("name",))
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
    from config.database import create_all

    create_all()


# --------------------------------------------------------------------------- #
# alembic migration wrappers
# --------------------------------------------------------------------------- #
def _alembic(*alembic_args: str) -> None:
    subprocess.run(
        [sys.executable, "-m", "alembic", *alembic_args], check=True, cwd=BASE_DIR
    )


def cmd_makemigrations(args: argparse.Namespace) -> None:
    _alembic("revision", "--autogenerate", "-m", args.name or "auto")


def cmd_migrate(args: argparse.Namespace) -> None:
    _alembic("upgrade", args.revision)


# --------------------------------------------------------------------------- #
# dbshell — connectivity check
# --------------------------------------------------------------------------- #
def cmd_dbshell(_: argparse.Namespace) -> None:
    from sqlalchemy import text

    from config.settings import settings as s
    from core.db import get_engine

    with get_engine().connect() as conn:
        current = conn.execute(
            text("SELECT current_catalog(), current_schema(), current_user()")
        ).one()
        print(f"Connected to {s.DATABRICKS_SERVER_HOSTNAME}")
        print(f"  catalog={current[0]}  schema={current[1]}  user={current[2]}")
        tables = conn.execute(text("SHOW TABLES")).fetchall()
        print(f"  {len(tables)} table(s): {', '.join(str(t[1]) for t in tables)}")


# --------------------------------------------------------------------------- #
# createadmin
# --------------------------------------------------------------------------- #
def cmd_createadmin(args: argparse.Namespace) -> None:
    from apps.users.services import ensure_admin_user
    from config.database import import_models

    async def _run() -> None:
        import_models()
        # Standalone (no admin app configured), so hash here.
        admin, created = await ensure_admin_user(
            args.username, args.password, email=args.email, prehash=True
        )
        print(f"Admin user '{admin.username}' {'created' if created else 'already exists'}.")

    asyncio.run(_run())


# --------------------------------------------------------------------------- #
# shell
# --------------------------------------------------------------------------- #
def cmd_shell(_: argparse.Namespace) -> None:
    import code

    from sqlalchemy import select

    from config.database import import_models
    from core.db import get_engine, get_session_factory, run_db

    import_models()
    session = get_session_factory()()
    print("Ready: session, select, run_db, engine (+ your models are imported).")
    code.interact(
        local={
            "session": session,
            "select": select,
            "run_db": run_db,
            "engine": get_engine(),
            "asyncio": asyncio,
        }
    )


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

    p = sub.add_parser("init-db", help="Create tables in Databricks from models")
    p.set_defaults(func=cmd_init_db)

    p = sub.add_parser("makemigrations", help="Generate an Alembic revision")
    p.add_argument("--name", default=None)
    p.set_defaults(func=cmd_makemigrations)

    p = sub.add_parser("migrate", help="Apply Alembic migrations")
    p.add_argument("revision", nargs="?", default="head")
    p.set_defaults(func=cmd_migrate)

    p = sub.add_parser("createadmin", help="Create an admin superuser")
    p.add_argument("username")
    p.add_argument("password")
    p.add_argument("--email", default=None)
    p.set_defaults(func=cmd_createadmin)

    p = sub.add_parser("dbshell", help="Check Databricks connectivity")
    p.set_defaults(func=cmd_dbshell)

    p = sub.add_parser("shell", help="REPL with a Databricks session ready")
    p.set_defaults(func=cmd_shell)

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
