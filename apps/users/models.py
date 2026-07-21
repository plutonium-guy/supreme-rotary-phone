"""SQLAlchemy models for the users app (stored in Databricks).

``unique=True`` below is emitted into the DDL but Delta treats key constraints
as *informational only* — it will not reject a duplicate. Uniqueness is
enforced in ``services.py`` with a read-before-write check.
"""

from __future__ import annotations

from sqlalchemy import Boolean, String
from sqlalchemy.orm import Mapped, mapped_column

from core.models import TimestampedModel


class User(TimestampedModel):
    """An application end-user account."""

    __tablename__ = "users"

    username: Mapped[str] = mapped_column(String(64), unique=True)
    email: Mapped[str] = mapped_column(String(255), unique=True)
    full_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    hashed_password: Mapped[str] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    def __str__(self) -> str:
        return self.username


class AdminUser(TimestampedModel):
    """Superuser record backing the admin dashboard login (fastadmin)."""

    __tablename__ = "admin_users"

    username: Mapped[str] = mapped_column(String(64), unique=True)
    password: Mapped[str] = mapped_column(String(255))
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    avatar: Mapped[str] = mapped_column(String(255), default="")
    is_superuser: Mapped[bool] = mapped_column(Boolean, default=True)

    def __str__(self) -> str:
        return self.username
