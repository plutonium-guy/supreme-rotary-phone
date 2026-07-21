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

## Adding a model, end to end

A worked example: a `blog` app with a `Post` model, from scaffold to live
endpoint and admin listing. Every snippet below was executed against the real
app before being written down.

### 1. Scaffold and register

```bash
python manage.py startapp blog
```

That writes `apps/blog/` with `apps.py`, `models.py`, `schemas.py`,
`services.py`, `views.py` and `admin.py`. Nothing is discovered until the app
is installed:

```python
# config/settings.py
INSTALLED_APPS: list[str] = ["apps.users", "apps.blog"]
```

### 2. Model — `apps/blog/models.py`

```python
from sqlalchemy import Boolean, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from core.models import TimestampedModel


class Post(TimestampedModel):
    __tablename__ = "posts"

    title: Mapped[str] = mapped_column(String(255))
    slug: Mapped[str] = mapped_column(String(255), unique=True)
    body: Mapped[str | None] = mapped_column(Text, nullable=True)
    published: Mapped[bool] = mapped_column(Boolean, default=True)
```

Subclassing `TimestampedModel` supplies `id` (UUID string), `created_at` and
`updated_at`, and puts the table into `Base.metadata` — which is all
`init-db` and Alembic autogenerate need to find it.

### 3. Schemas — `apps/blog/schemas.py`

```python
from pydantic import BaseModel, ConfigDict, Field


class PostCreate(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    slug: str = Field(min_length=1, max_length=255)
    body: str | None = None


class PostOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str          # UUID string, not int
    title: str
    slug: str
    published: bool
```

### 4. Service — `apps/blog/services.py`

All database work goes through `run_db`, one unit of work per call. It commits
when the function returns and rolls back if it raises, so there is no explicit
`session.commit()`.

```python
from sqlalchemy import select
from sqlalchemy.orm import Session

from apps.blog.models import Post
from apps.blog.schemas import PostCreate
from core.db import run_db


class DuplicateSlug(Exception):
    pass


async def create_post(data: PostCreate) -> Post:
    def _work(session: Session) -> Post:
        # Delta will not enforce the unique constraint — check it here
        if session.scalar(select(Post).where(Post.slug == data.slug)):
            raise DuplicateSlug(f"slug '{data.slug}' is taken")
        post = Post(**data.model_dump())
        session.add(post)
        return post

    return await run_db(_work)


async def list_posts(limit: int = 100) -> list[Post]:
    return await run_db(
        lambda s: list(
            s.scalars(select(Post).order_by(Post.created_at.desc()).limit(limit))
        )
    )


async def get_post(post_id: str) -> Post | None:
    return await run_db(lambda s: s.get(Post, post_id))
```

### 5. View — `apps/blog/views.py`

The module-level `router` is what the registry looks for; it is auto-mounted at
`/api/blog`.

```python
from fastapi import APIRouter, HTTPException, status

from apps.blog import services
from apps.blog.schemas import PostCreate, PostOut

router = APIRouter()


@router.post("", response_model=PostOut, status_code=201, operation_id="blog_create")
async def create_post(payload: PostCreate) -> PostOut:
    try:
        post = await services.create_post(payload)
    except services.DuplicateSlug as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    return PostOut.model_validate(post)


@router.get("", response_model=list[PostOut], operation_id="blog_list")
async def list_posts(limit: int = 100) -> list[PostOut]:
    return [PostOut.model_validate(p) for p in await services.list_posts(limit)]
```

### 6. Admin — `apps/blog/admin.py`

```python
from core.admin import register_model

from apps.blog.models import Post

register_model(
    Post,
    list_display=("id", "title", "slug", "published", "created_at"),
    search_fields=("title", "slug"),
    list_filter=("published",),
)
```

Or delete the file — the framework auto-registers every model the app defines.

### 7. Migrate

```bash
pixi run makemigrations --name add_posts
# read migrations/versions/<hash>_add_posts.py before applying
pixi run migrate
```

### Traps worth knowing before you write the second model

**Relationships must be eagerly loaded.** The session closes when `run_db`
returns. `expire_on_commit=False` keeps already-loaded *columns* usable, but
touching an unloaded relationship afterwards raises `DetachedInstanceError`.
Load it inside the unit of work:

```python
from sqlalchemy.orm import selectinload

await run_db(lambda s: s.scalar(select(Post).options(selectinload(Post.author))))
```

**Foreign keys are not enforced.** Declare them — joins and `relationship()`
work normally — but Delta will not reject an orphan row, exactly as with
`unique`.

**Don't split one operation across several `run_db` calls.** Each is a thread
hop and a warehouse round-trip at ~0.2–2s. Fetch-then-update as two calls costs
double; do both inside one `_work`.

**Primary keys are strings.** Path parameters are `post_id: str`, not `int`.
And if you write a custom `ModelAdmin`, subclass `core.admin.ModelAdmin` rather
than fastadmin's `SqlAlchemyModelAdmin`, or you lose the Databricks session
binding and the UUID-to-string PK coercion.

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
