"""Shared declarative base and abstract models (Django's abstract base models).

**Primary keys are client-generated UUID strings, not autoincrement integers.**
Databricks has no sequences and no ``INSERT ... RETURNING``, so a
server-generated id could never be read back after an insert. Generating the
id in Python before the insert sidesteps that entirely and keeps
``session.get(Model, obj.id)`` working right after a flush.

Timestamps are likewise populated Python-side rather than with a server
default, for the same reason. They use the dialect's ``TIMESTAMP`` rather than
``DateTime(timezone=True)``: the dialect maps generic ``DateTime`` to
``TIMESTAMP_NTZ`` and strips ``tzinfo`` on read, whatever ``timezone=True``
says.
"""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from databricks.sqlalchemy import TIMESTAMP
from sqlalchemy import String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Declarative base shared by every app's models."""


def new_id() -> str:
    """Generate a primary key. Client-side because Databricks can't return one."""
    return str(uuid4())


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class TimestampedModel(Base):
    """Abstract base adding a UUID ``id`` plus ``created_at`` / ``updated_at``."""

    __abstract__ = True

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP, default=utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP, default=utcnow, onupdate=utcnow, nullable=False
    )

    def __str__(self) -> str:  # pragma: no cover - display helper
        return f"<{type(self).__name__} id={self.id}>"
