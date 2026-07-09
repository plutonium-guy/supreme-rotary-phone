"""Shared abstract models for all apps (like Django's abstract base models)."""

from __future__ import annotations

from tortoise import fields
from tortoise.models import Model


class TimestampedModel(Model):
    """Abstract base adding auto-managed ``created_at`` / ``updated_at``."""

    id = fields.IntField(primary_key=True)
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    class Meta:
        abstract = True

    def __str__(self) -> str:  # pragma: no cover - display helper
        return f"<{type(self).__name__} id={self.id}>"
