"""Business logic for the users app (kept out of the view layer).

Views stay thin; all persistence and rules live here so they can be reused
by the CLI, background jobs and tests.

Every function funnels through ``core.db.run_db``, which executes one unit of
work in a worker thread (the Databricks driver is synchronous). Keep each unit
whole — a Databricks round-trip costs ~0.2-2s, so splitting one operation
across several ``run_db`` calls multiplies that.
"""

from __future__ import annotations

import bcrypt
from sqlalchemy import select
from sqlalchemy.orm import Session

from apps.users.models import AdminUser, User
from apps.users.schemas import UserCreate, UserUpdate
from core.db import run_db


class DuplicateUser(Exception):
    """Raised when username/email is already taken (Delta won't enforce it)."""


def hash_password(raw: str) -> str:
    # bcrypt hard-limits input to 72 bytes; truncate deterministically.
    return bcrypt.hashpw(raw.encode()[:72], bcrypt.gensalt()).decode()


def verify_password(raw: str, hashed: str) -> bool:
    return bcrypt.checkpw(raw.encode()[:72], hashed.encode())


async def create_user(data: UserCreate) -> User:
    """Create a user, rejecting duplicates.

    Databricks does not enforce UNIQUE, so the check below is advisory: two
    concurrent creates can both pass it and insert duplicate rows.
    """

    def _work(session: Session) -> User:
        clash = session.scalar(
            select(User).where(
                (User.username == data.username) | (User.email == data.email)
            )
        )
        if clash is not None:
            field = "username" if clash.username == data.username else "email"
            raise DuplicateUser(f"A user with this {field} already exists")

        user = User(
            username=data.username,
            email=data.email,
            full_name=data.full_name,
            hashed_password=hash_password(data.password),
        )
        session.add(user)
        return user

    return await run_db(_work)


async def list_users(limit: int = 100, offset: int = 0) -> list[User]:
    def _work(session: Session) -> list[User]:
        stmt = select(User).order_by(User.created_at).limit(limit).offset(offset)
        return list(session.scalars(stmt))

    return await run_db(_work)


async def get_user(user_id: str) -> User | None:
    return await run_db(lambda session: session.get(User, user_id))


async def update_user(user_id: str, data: UserUpdate) -> User | None:
    payload = data.model_dump(exclude_unset=True)

    def _work(session: Session) -> User | None:
        user = session.get(User, user_id)
        if user is None:
            return None
        for key, value in payload.items():
            setattr(user, key, value)
        return user

    return await run_db(_work)


async def delete_user(user_id: str) -> bool:
    """Delete a user. Returns False if it did not exist."""

    def _work(session: Session) -> bool:
        user = session.get(User, user_id)
        if user is None:
            return False
        session.delete(user)
        return True

    return await run_db(_work)


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

    def _work(session: Session) -> tuple[AdminUser, bool]:
        existing = session.scalar(select(AdminUser).where(AdminUser.username == username))
        if existing is not None:
            return existing, False
        admin = AdminUser(
            username=username,
            password=hash_password(password) if prehash else password,
            email=email,
        )
        session.add(admin)
        return admin, True

    return await run_db(_work)
