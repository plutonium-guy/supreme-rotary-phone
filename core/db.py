"""Databricks persistence layer (SQLAlchemy 2.0).

Databricks' Python driver is **synchronous** — there is no asyncio DBAPI and
therefore no ``create_async_engine``. Everything here exists to bridge that
gap without blocking the event loop:

``run_db(fn)``
    The API our own code uses. Runs ``fn(session, ...)`` in a worker thread
    with a fresh ``Session``, committing on success. One thread hop per
    logical operation — important, because a Databricks round-trip costs
    ~0.2-2s and per-statement hops would multiply that.

``admin_sessionmaker()``
    Only for **fastadmin**, whose SQLAlchemy backend hard-codes
    ``async with sessionmaker() as session`` and awaits every call. We hand it
    an awaitable facade over a sync ``Session``. A ``Session`` is not
    thread-safe, so each one is pinned to its own single-worker executor and is
    therefore only ever touched from one thread.

Results are fully buffered inside the worker thread before crossing back, so
callers never drive a live cursor from the event-loop thread.
"""

from __future__ import annotations

import asyncio
import functools
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable, TypeVar

from loguru import logger
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from config.settings import settings

T = TypeVar("T")

_engine: Engine | None = None
_session_factory: sessionmaker[Session] | None = None


# --------------------------------------------------------------------------- #
# Engine / session factory (lazy — settings must be loaded first)
# --------------------------------------------------------------------------- #
def get_engine() -> Engine:
    """Return the process-wide Databricks engine, creating it on first use."""
    global _engine
    if _engine is None:
        _engine = create_engine(
            settings.database_url,
            pool_pre_ping=True,
            pool_size=settings.DB_POOL_SIZE,
            max_overflow=settings.DB_MAX_OVERFLOW,
            pool_recycle=settings.DB_POOL_RECYCLE,
            echo=settings.DB_ECHO,
        )
        logger.debug(
            "Databricks engine created (catalog={}, schema={})",
            settings.DATABRICKS_CATALOG,
            settings.DATABRICKS_SCHEMA,
        )
    return _engine


def get_session_factory() -> sessionmaker[Session]:
    global _session_factory
    if _session_factory is None:
        # expire_on_commit=False: re-loading an object after commit would cost
        # another warehouse round-trip, and callers routinely read attributes
        # off returned objects.
        _session_factory = sessionmaker(
            bind=get_engine(), expire_on_commit=False, future=True
        )
    return _session_factory


def dispose_engine() -> None:
    """Close all pooled connections (called on app shutdown)."""
    global _engine, _session_factory
    if _engine is not None:
        _engine.dispose()
        logger.debug("Databricks engine disposed")
    _engine = None
    _session_factory = None


# --------------------------------------------------------------------------- #
# The API application code should use
# --------------------------------------------------------------------------- #
async def run_db(fn: Callable[..., T], *args: Any, **kwargs: Any) -> T:
    """Run ``fn(session, *args, **kwargs)`` in a thread with a fresh Session.

    Commits if ``fn`` returns normally, rolls back if it raises. Keep the whole
    unit of work inside ``fn`` so it costs a single thread hop::

        user = await run_db(lambda s: s.get(User, user_id))
    """

    def _work() -> T:
        with get_session_factory()() as session:
            try:
                result = fn(session, *args, **kwargs)
                session.commit()
                return result
            except Exception:
                session.rollback()
                raise

    return await asyncio.to_thread(_work)


# --------------------------------------------------------------------------- #
# Async facade over a sync Session — required by fastadmin
# --------------------------------------------------------------------------- #
class AsyncSessionFacade:
    """Awaitable proxy for a sync ``Session``, pinned to one worker thread.

    Only the methods fastadmin awaits are wrapped; anything else falls through
    to the underlying Session synchronously (``add``, ``expunge``, ...).
    """

    def __init__(self, session: Session, executor: ThreadPoolExecutor) -> None:
        self._session = session
        self._executor = executor

    async def _call(self, method: str, *args: Any, **kwargs: Any) -> Any:
        loop = asyncio.get_running_loop()
        fn = functools.partial(getattr(self._session, method), *args, **kwargs)
        return await loop.run_in_executor(self._executor, fn)

    # -- reads: buffer inside the worker thread so no live cursor escapes ----
    async def execute(self, *args: Any, **kwargs: Any) -> Any:
        def _run() -> Any:
            # freeze() drains the cursor; calling the FrozenResult yields a
            # fresh Result the caller can still use .scalar()/.all() on.
            return self._session.execute(*args, **kwargs).freeze()

        loop = asyncio.get_running_loop()
        frozen = await loop.run_in_executor(self._executor, _run)
        return frozen()

    async def scalars(self, *args: Any, **kwargs: Any) -> list[Any]:
        def _run() -> list[Any]:
            return list(self._session.scalars(*args, **kwargs))

        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(self._executor, _run)

    async def scalar(self, *args: Any, **kwargs: Any) -> Any:
        return await self._call("scalar", *args, **kwargs)

    async def get(self, *args: Any, **kwargs: Any) -> Any:
        return await self._call("get", *args, **kwargs)

    # -- writes --------------------------------------------------------------
    async def merge(self, *args: Any, **kwargs: Any) -> Any:
        return await self._call("merge", *args, **kwargs)

    async def delete(self, *args: Any, **kwargs: Any) -> Any:
        return await self._call("delete", *args, **kwargs)

    async def flush(self, *args: Any, **kwargs: Any) -> Any:
        return await self._call("flush", *args, **kwargs)

    async def refresh(self, *args: Any, **kwargs: Any) -> Any:
        return await self._call("refresh", *args, **kwargs)

    async def commit(self) -> None:
        await self._call("commit")

    async def rollback(self) -> None:
        await self._call("rollback")

    async def close(self) -> None:
        await self._call("close")

    def __getattr__(self, name: str) -> Any:
        # Non-awaited passthrough (session.add, session.expunge, ...).
        return getattr(self._session, name)


class _AsyncSessionContext:
    """``async with`` wrapper yielding an :class:`AsyncSessionFacade`."""

    def __init__(self) -> None:
        self._executor: ThreadPoolExecutor | None = None
        self._session: Session | None = None

    async def __aenter__(self) -> AsyncSessionFacade:
        # max_workers=1 keeps every statement on this session on one thread.
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="db")
        loop = asyncio.get_running_loop()
        self._session = await loop.run_in_executor(
            self._executor, get_session_factory()
        )
        return AsyncSessionFacade(self._session, self._executor)

    async def __aexit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        assert self._executor is not None
        if self._session is not None:
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(self._executor, self._session.close)
        self._executor.shutdown(wait=False)
        self._executor = None
        self._session = None


def admin_sessionmaker() -> _AsyncSessionContext:
    """Async sessionmaker handed to fastadmin's SQLAlchemy ModelAdmin."""
    return _AsyncSessionContext()
