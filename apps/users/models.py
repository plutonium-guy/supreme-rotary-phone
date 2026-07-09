"""Tortoise ORM models for the users app."""

from __future__ import annotations

from tortoise import fields

from core.models import TimestampedModel


class User(TimestampedModel):
    """An application end-user account."""

    username = fields.CharField(max_length=64, unique=True)
    email = fields.CharField(max_length=255, unique=True)
    full_name = fields.CharField(max_length=255, null=True)
    hashed_password = fields.CharField(max_length=255)
    is_active = fields.BooleanField(default=True)

    class Meta:
        table = "users"

    def __str__(self) -> str:
        return self.username


class AdminUser(TimestampedModel):
    """Superuser record backing the admin dashboard login (fastadmin)."""

    username = fields.CharField(max_length=64, unique=True)
    password = fields.CharField(max_length=255)
    email = fields.CharField(max_length=255, null=True)
    avatar = fields.CharField(max_length=255, default="")
    is_superuser = fields.BooleanField(default=True)

    class Meta:
        table = "admin_users"

    def __str__(self) -> str:
        return self.username
