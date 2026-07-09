"""Business logic for the users app (kept out of the view layer).

Views stay thin; all persistence and rules live here so they can be reused
by the CLI, background jobs and tests.
"""

from __future__ import annotations

import bcrypt

from apps.users.models import AdminUser, User
from apps.users.schemas import UserCreate, UserUpdate


def hash_password(raw: str) -> str:
    # bcrypt hard-limits input to 72 bytes; truncate deterministically.
    return bcrypt.hashpw(raw.encode()[:72], bcrypt.gensalt()).decode()


def verify_password(raw: str, hashed: str) -> bool:
    return bcrypt.checkpw(raw.encode()[:72], hashed.encode())


async def create_user(data: UserCreate) -> User:
    return await User.create(
        username=data.username,
        email=data.email,
        full_name=data.full_name,
        hashed_password=hash_password(data.password),
    )


async def list_users(limit: int = 100, offset: int = 0) -> list[User]:
    return await User.all().limit(limit).offset(offset)


async def get_user(user_id: int) -> User | None:
    return await User.get_or_none(id=user_id)


async def update_user(user: User, data: UserUpdate) -> User:
    payload = data.model_dump(exclude_unset=True)
    if payload:
        await user.update_from_dict(payload).save()
    return user


async def delete_user(user: User) -> None:
    await user.delete()


async def ensure_admin_user(
    username: str,
    password: str,
    *,
    email: str | None = None,
    prehash: bool = False,
) -> tuple[AdminUser, bool]:
    """Create the admin superuser if it does not already exist.

    Returns ``(admin, created)``. Pass ``prehash=True`` to bcrypt-hash the
    password before storing (the dashboard's ``authenticate`` verifies with
    bcrypt). ``prehash=False`` stores the raw value — only useful if the
    caller hashes separately.
    """
    existing = await AdminUser.get_or_none(username=username)
    if existing:
        return existing, False
    admin = await AdminUser.create(
        username=username,
        password=hash_password(password) if prehash else password,
        email=email,
    )
    return admin, True
