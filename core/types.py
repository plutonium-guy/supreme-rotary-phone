"""Reusable column types for the Databricks dialect.

Databricks' SQLAlchemy dialect cannot compile ``sqlalchemy.JSON`` at all --
``CreateTable`` raises ``CompileError``. Structured payloads therefore have to
live in a STRING column, which :class:`JSONText` makes transparent.
"""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy import Text
from sqlalchemy.types import TypeDecorator


class JSONText(TypeDecorator):
    """A ``dict``/``list`` column persisted as JSON text.

    Use anywhere you would reach for ``sqlalchemy.JSON``::

        payload: Mapped[dict | None] = mapped_column(JSONText, nullable=True)

    ``default=str`` on the encoder keeps values that JSON cannot represent
    natively (datetimes, Decimals, UUIDs) from raising at write time.
    """

    impl = Text
    cache_ok = True

    def process_bind_param(self, value: Any, dialect: Any) -> str | None:
        if value is None:
            return None
        return json.dumps(value, default=str)

    def process_result_value(self, value: Any, dialect: Any) -> Any:
        if value is None:
            return None
        try:
            return json.loads(value)
        except (TypeError, ValueError):
            # Hand back the raw string rather than None: for audit/log columns,
            # an unparseable value is still evidence and must not be swallowed.
            return value
