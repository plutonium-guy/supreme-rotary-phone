"""Admin registration for the users app (fastadmin, Django-style).

``AdminUser`` is the authentication model for the dashboard, so its
``ModelAdmin`` implements ``authenticate`` / ``change_password`` (bcrypt).
``User`` is registered with a one-line generic listing.
"""

from uuid import UUID

from fastadmin import WidgetType, register
from sqlalchemy import select
from sqlalchemy.orm import Session

from apps.users.models import AdminUser, User
from apps.users.services import hash_password, verify_password
from core.admin import ModelAdmin, register_model
from core.db import run_db

# End-user accounts — read-mostly listing (hashed_password hidden by default).
register_model(
    User,
    list_display=("id", "username", "email", "is_active", "created_at"),
    search_fields=("username", "email"),
    list_filter=("is_active",),
)


@register(AdminUser)
class AdminUserAdmin(ModelAdmin):
    """Dashboard superusers + the login authentication backend."""

    list_display = ("id", "username", "email", "is_superuser")
    search_fields = ("username", "email")
    list_filter = ("is_superuser",)
    # Render the password field as a masked input; the base save_model hashes
    # it via change_password on create.
    formfield_overrides = {"password": (WidgetType.PasswordInput, {})}

    async def authenticate(self, username: str, password: str) -> UUID | None:
        def _work(session: Session) -> AdminUser | None:
            return session.scalar(
                select(AdminUser).where(
                    AdminUser.username == username,
                    AdminUser.is_superuser.is_(True),
                )
            )

        user = await run_db(_work)
        if user is None or not verify_password(password, user.password):
            return None
        # fastadmin rejects any id that is not int|UUID (api/service.py), and
        # our PKs are String(36); hand it a real UUID. It stringifies the value
        # back into the session JWT, which matches the stored column.
        return UUID(user.id)

    async def change_password(self, id: UUID | str, password: str) -> None:
        def _work(session: Session) -> None:
            user = session.get(AdminUser, str(id))
            if user is not None:
                user.password = hash_password(password)

        await run_db(_work)
