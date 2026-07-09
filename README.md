# fastAPI_api

A small FastAPI framework laid out like a Django project: a central
`config/` (settings + app factory), a `core/` runtime, and pluggable
**apps** under `apps/`. Batteries: **Tortoise ORM**, **Aerich** migrations,
**fastadmin** (Django-style admin, no Redis), **beartype** (runtime
type-checking) and **loguru**.

## Layout

```
config/            project configuration (Django's settings + wsgi)
  settings.py      pydantic-settings; holds INSTALLED_APPS
  app.py           create_app() factory: logging → apps → ORM → admin
  tortoise.py      TORTOISE_ORM built from INSTALLED_APPS (also used by Aerich)
  admin.py         fastadmin mounting/configuration (JWT-cookie auth)
  logging.py       loguru + stdlib interception
core/              framework internals
  __init__.py      installs the beartype import hook for apps/core/config
  apps.py          AppConfig + AppRegistry (autodiscovery)
  models.py        TimestampedModel abstract base
apps/              installed applications, one package each
  users/           sample app
    apps.py        AppConfig
    models.py      Tortoise models
    schemas.py     Pydantic in/out
    services.py    business logic (thin views)
    views.py       APIRouter -> auto-mounted at /api/users
    admin.py       fastadmin ModelAdmin registration
manage.py          CLI: runserver / startapp / migrations / createadmin / shell
main.py            ASGI entry point (uvicorn main:app)
```

## Design pattern (Django parallels)

| Django                         | Here                                    |
|--------------------------------|-----------------------------------------|
| `settings.py` / `INSTALLED_APPS` | `config/settings.py`                  |
| `AppConfig` in `apps.py`       | `core.apps.AppConfig` subclass          |
| app autodiscovery / registry   | `core.apps.AppRegistry`                 |
| `models.py`                    | `apps/<app>/models.py` (Tortoise)       |
| `views.py` + `urls.py`         | `apps/<app>/views.py` (`router`)        |
| `admin.py` / `ModelAdmin`      | `apps/<app>/admin.py` (fastadmin)       |
| `manage.py`                    | `manage.py`                             |
| `makemigrations` / `migrate`   | Aerich wrappers in `manage.py`          |

Every app router is auto-mounted at `/api/<label>`; every app's models are
collected into the Tortoise `models` namespace; every app's admin resources
are imported at admin-configuration time.

## Quickstart

```bash
pixi install                 # installs deps into the pixi env
cp .env.example .env         # optional; sqlite works out of the box

pixi run init-db             # create tables from models (dev)
pixi run runserver           # http://127.0.0.1:8000  (docs at /docs)
```

### Admin dashboard — zero config

Just start the server and open **http://127.0.0.1:8000/admin**, log in with
**`admin` / `admin`**. No extra steps:

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
  For full control, subclass `fastadmin.TortoiseModelAdmin` and use
  `@fastadmin.register(Model)` directly (see `apps/users/admin.py`).

Create additional superusers from the CLI any time:

```bash
python manage.py createadmin alice s3cretpw --email alice@x.com
```

## Add an app

```bash
python manage.py startapp blog
# add "apps.blog" to INSTALLED_APPS in config/settings.py
python manage.py makemigrations
python manage.py migrate
```

## Migrations (Aerich)

`config.tortoise.TORTOISE_ORM` is the single source of truth shared by the
app and Aerich, so `makemigrations` bootstraps Aerich on first run and emits
migrations thereafter; `migrate` applies them.

## Notes

- **beartype** is installed as an import hook in `core/__init__.py`, so any
  module imported after `core` is runtime type-checked — import `core` first
  (both `main.py` and `manage.py` do).
- **loguru** captures stdlib logging (uvicorn/tortoise) via an intercept
  handler; logs stream to stderr and rotate into `logs/app.log`.
