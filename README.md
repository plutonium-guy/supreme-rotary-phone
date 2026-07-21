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
cp .env.example .env          # then fill it in — see Databricks setup below

pixi run dbshell              # verify connectivity first
pixi run initdb               # create tables in the configured catalog/schema
pixi run runserver            # http://127.0.0.1:8000  (docs at /docs)
```

## Databricks setup

You need four things: a **SQL warehouse** to execute queries, a **token** to
authenticate, a **catalog + schema** to hold the tables, and **grants** on that
schema. Roughly ten minutes end to end.

### 1. Get a SQL warehouse

In the workspace sidebar switch to **SQL**, open **SQL Warehouses**, and either
pick an existing warehouse or **Create SQL warehouse**.

Prefer a **Serverless** warehouse if your workspace offers one. Warehouses stop
when idle and must resume on the next query; serverless resumes in seconds,
while classic/pro can take a few minutes. Since this app's *first* query
happens during startup, a cold classic warehouse makes it look hung.

Open the warehouse → **Connection details** tab. Copy:

| Field on that tab | `.env` key |
|---|---|
| Server hostname | `DATABRICKS_SERVER_HOSTNAME` |
| HTTP path       | `DATABRICKS_HTTP_PATH` |

The hostname goes in **without** the `https://` prefix.

### 2. Create an access token

Top-right avatar → **Settings** → **Developer** → **Access tokens** →
**Manage** → **Generate new token**. Copy it immediately; it is shown once.
That value is `DATABRICKS_TOKEN`.

Tokens inherit *your* permissions and expire. For anything beyond local
development, authenticate as a **service principal** with OAuth (M2M) instead
and give it only the grants in step 4 — a personal token in a deployed service
means the service loses access when you do.

### 3. Pick a catalog and schema

Unity Catalog names tables `catalog.schema.table`. Give the app its own schema
rather than dropping tables into `main.default`. In the SQL editor:

```sql
CREATE SCHEMA IF NOT EXISTS main.fastapi_app;
```

Then set `DATABRICKS_CATALOG=main` and `DATABRICKS_SCHEMA=fastapi_app`.

### 4. Grant permissions

The identity from step 2 needs enough to create and use tables. As a
catalog/schema owner or metastore admin:

```sql
GRANT USE CATALOG ON CATALOG main TO `you@example.com`;
GRANT USE SCHEMA, CREATE TABLE, SELECT, MODIFY
  ON SCHEMA main.fastapi_app TO `you@example.com`;
```

Substitute the service principal's application ID for the email when using
OAuth. `CREATE TABLE` is what `init-db` and Alembic need; `MODIFY` covers
INSERT/UPDATE/DELETE.

### 5. Fill in `.env` and verify

```
DATABRICKS_SERVER_HOSTNAME=dbc-xxxxxxxx-xxxx.cloud.databricks.com
DATABRICKS_HTTP_PATH=/sql/1.0/warehouses/xxxxxxxxxxxxxxxx
DATABRICKS_TOKEN=dapi...
DATABRICKS_CATALOG=main
DATABRICKS_SCHEMA=fastapi_app
```

```bash
pixi run dbshell
```

This is the first thing that touches the warehouse, so run it before the
server. On success it prints the catalog, schema, authenticated user and the
tables it can see. Then:

```bash
pixi run initdb      # CREATE TABLE ... USING DELTA for every model
pixi run runserver
```

If the credentials are absent or incomplete the app refuses to start with an
explicit message naming the missing keys — there is no silent fallback.

### Authenticating another way

`DATABASE_URL` overrides the five settings above with a full SQLAlchemy URL,
which is the escape hatch for OAuth, custom connector arguments, or anything
the five fields don't express:

```
DATABASE_URL=databricks://token:dapi...@host?http_path=/sql/1.0/warehouses/xxx&catalog=main&schema=fastapi_app
```

### Troubleshooting

| Symptom | Cause |
|---|---|
| First query hangs 1–5 min, then succeeds | Warehouse was stopped and is resuming. Use serverless, or pre-start it |
| `Databricks is not configured — set ...` | `.env` missing keys; the message names them |
| 403 / `PERMISSION_DENIED` on `initdb` | Missing `CREATE TABLE` on the schema (step 4) |
| `TABLE_OR_VIEW_NOT_FOUND` | `initdb` not run, or `DATABRICKS_SCHEMA` points somewhere else |
| `Invalid access token` | Token expired or was copied truncated — regenerate |
| Schema doesn't exist | `CREATE SCHEMA` from step 3 — the app creates tables, never schemas |

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

## Admin dashboard

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
