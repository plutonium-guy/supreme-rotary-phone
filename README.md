# fastAPI_api

A small FastAPI framework laid out like a Django project: a central
`config/` (settings + app factory), a `core/` runtime, and pluggable
**apps** under `apps/`. Batteries: **SQLAlchemy 2.0 on Databricks**,
**Alembic** migrations, **fastadmin** (Django-style admin, no Redis),
**beartype** (runtime type-checking) and **loguru**.

> **Databricks is the only datastore.** There is no SQLite/Postgres fallback —
> the app will refuse to start without warehouse credentials. Read
> [Living with Databricks](#living-with-databricks) before building on this;
> a lakehouse is not a drop-in OLTP database and the differences are load-bearing.

## Layout

```
config/            project configuration (Django's settings + wsgi)
  settings.py      pydantic-settings; holds INSTALLED_APPS + Databricks config
  app.py           create_app() factory: logging → apps → ORM → admin
  database.py      imports app models, builds metadata, create_all()
  admin.py         fastadmin mounting/configuration (JWT-cookie auth)
  logging.py       loguru + stdlib interception
core/              framework internals
  __init__.py      installs the beartype import hook for apps/core/config
  apps.py          AppConfig + AppRegistry (autodiscovery)
  db.py            engine, run_db(), and the async facade fastadmin needs
  models.py        Base + TimestampedModel (UUID pk, created_at/updated_at)
  admin.py         register_model() + the ModelAdmin base
apps/              installed applications, one package each
  users/           sample app
    apps.py        AppConfig
    models.py      SQLAlchemy models
    schemas.py     Pydantic in/out
    services.py    business logic (thin views)
    views.py       APIRouter -> auto-mounted at /api/users
    admin.py       fastadmin ModelAdmin registration
migrations/        Alembic environment + versions
manage.py          CLI: runserver / startapp / migrations / createadmin / shell
main.py            ASGI entry point (uvicorn main:app)
```

## Design pattern (Django parallels)

| Django                         | Here                                    |
|--------------------------------|-----------------------------------------|
| `settings.py` / `INSTALLED_APPS` | `config/settings.py`                  |
| `AppConfig` in `apps.py`       | `core.apps.AppConfig` subclass          |
| app autodiscovery / registry   | `core.apps.AppRegistry`                 |
| `models.py`                    | `apps/<app>/models.py` (SQLAlchemy)     |
| `views.py` + `urls.py`         | `apps/<app>/views.py` (`router`)        |
| `admin.py` / `ModelAdmin`      | `apps/<app>/admin.py` (fastadmin)       |
| `manage.py`                    | `manage.py`                             |
| `makemigrations` / `migrate`   | Alembic wrappers in `manage.py`         |

Every app router is auto-mounted at `/api/<label>`; every app's models are
imported into `Base.metadata`; every app's admin resources are imported at
admin-configuration time.

## Quickstart

```bash
pixi install
cp .env.example .env          # then fill in your Databricks credentials

pixi run dbshell              # verify connectivity first
pixi run initdb               # create tables in the configured catalog/schema
pixi run runserver            # http://127.0.0.1:8000  (docs at /docs)
```

`.env` needs at minimum, from your SQL warehouse's *Connection details* tab:

```
DATABRICKS_SERVER_HOSTNAME=dbc-xxxx.cloud.databricks.com
DATABRICKS_HTTP_PATH=/sql/1.0/warehouses/xxxxxxxx
DATABRICKS_TOKEN=dapi...
DATABRICKS_CATALOG=main
DATABRICKS_SCHEMA=default
```

## Living with Databricks

Databricks is an OLAP lakehouse. It stores the data fine, but four differences
shape how this framework is written — worth understanding before you extend it.

**1. Primary keys are client-generated UUID strings.**
Databricks has no sequences and no `INSERT ... RETURNING`, so a server-side id
could never be read back after insert. `TimestampedModel.id` is a
`String(36)` filled in by Python (`core.models.new_id`). Ids in URLs and
payloads are strings, not ints.

**2. Constraints are not enforced.** Delta accepts `PRIMARY KEY` / `UNIQUE` /
`FOREIGN KEY` as *informational only* — and the SQLAlchemy dialect drops
unique constraints from the DDL outright. **The database will not reject a
duplicate.** Uniqueness must be enforced in code:

```python
clash = session.scalar(select(User).where(User.username == name))
if clash is not None:
    raise DuplicateUser(...)
```

That check is racy under concurrency — two simultaneous requests can both pass
it. If you need a hard guarantee, you need a different store for that table.

**3. The driver is synchronous.** There is no asyncio DBAPI for Databricks, so
no `create_async_engine`. All DB work goes through `core.db.run_db`, which
runs one unit of work in a worker thread:

```python
from core.db import run_db

async def get_user(user_id: str) -> User | None:
    return await run_db(lambda s: s.get(User, user_id))
```

Keep each unit of work inside a single `run_db` call. A warehouse round-trip
costs ~0.2–2s, so splitting one operation across several calls multiplies that.

**4. Timestamps need the dialect's `TIMESTAMP`.** The dialect maps generic
`DateTime` to `TIMESTAMP_NTZ` and strips `tzinfo` on read, even with
`timezone=True`. Use `from databricks.sqlalchemy import TIMESTAMP`, as
`core.models` does.

Expect admin pages to take a beat: each list view is several warehouse queries.

### Admin dashboard

Start the server and open **http://127.0.0.1:8000/admin**, log in with
**`admin` / `admin`**.

- **No Redis, no external services.** [fastadmin](https://github.com/vsdudakov/fastadmin)
  keeps its session in a signed JWT http-only cookie (`ADMIN_SECRET_KEY`).
- **Superuser auto-created** on startup from `ADMIN_USERNAME` /
  `ADMIN_PASSWORD` (change these in `.env` for anything real; set
  `ADMIN_AUTO_CREATE=false` to disable). Auth is handled by the
  `AdminUser` `ModelAdmin` (`authenticate` / `change_password`, bcrypt).
- **Models show up automatically.** Each app registers its models in one line
  in `apps/<app>/admin.py`:

  ```python
  from core.admin import register_model
  from apps.blog.models import Post

  register_model(Post, list_display=("id", "title", "created_at"),
                 search_fields=("title",))
  ```

  …or **delete `admin.py`** entirely and the framework auto-registers every
  model the app defines (secret columns like `password` are hidden by default).
  For full control, subclass `core.admin.ModelAdmin` — not fastadmin's
  `SqlAlchemyModelAdmin` directly, or you lose the Databricks session binding
  and the UUID-to-string PK coercion (see `apps/users/admin.py`).

Create additional superusers from the CLI any time:

```bash
python manage.py createadmin alice s3cretpw --email alice@x.com
```

## Add an app

```bash
python manage.py startapp blog
# add "apps.blog" to INSTALLED_APPS in config/settings.py
python manage.py makemigrations --name add_blog
python manage.py migrate
```

## Migrations (Alembic)

`migrations/env.py` builds the connection from `config.settings` and takes
`target_metadata` from `config.database.get_metadata()`, so migrations and the
app always agree. Autogenerate needs a live warehouse connection — there is no
offline mode.

`compare_type` is off: Delta has no `ALTER COLUMN TYPE`, so type-change
autodetection would only emit migrations that cannot run.

## Notes

- **beartype** is installed as an import hook in `core/__init__.py`, so any
  module imported after `core` is runtime type-checked — import `core` first
  (both `main.py` and `manage.py` do).
- **loguru** captures stdlib logging (uvicorn/sqlalchemy) via an intercept
  handler; logs stream to stderr and rotate into `logs/app.log`.
- With `DEBUG=true` the app runs `create_all()` on every boot. That is several
  warehouse round-trips per start — turn it off and use migrations for anything
  beyond local iteration.
