"""Admin registration for the users app (fastadmin, Django-style).

``AdminUser`` is the authentication model for the dashboard, so its
``ModelAdmin`` implements ``authenticate`` / ``change_password`` (bcrypt).
``User`` is registered with a one-line generic listing.
"""

from fastadmin import TortoiseModelAdmin, WidgetType, register

from apps.users.models import AdminUser, User
from apps.users.services import hash_password, verify_password
from core.admin import register_model

# End-user accounts — read-mostly listing (hashed_password hidden by default).
register_model(
    User,
    list_display=("id", "username", "email", "is_active", "created_at"),
    search_fields=("username", "email"),
    list_filter=("is_active",),
)


@register(AdminUser)
class AdminUserAdmin(TortoiseModelAdmin):
    """Dashboard superusers + the login authentication backend."""

    list_display = ("id", "username", "email", "is_superuser")
    search_fields = ("username", "email")
    list_filter = ("is_superuser",)
    # Render the password field as a masked input; the base save_model hashes
    # it via change_password on create.
    formfield_overrides = {"password": (WidgetType.PasswordInput, {})}

    async def authenticate(self, username: str, password: str) -> int | None:
        user = await AdminUser.get_or_none(username=username, is_superuser=True)
        if user is None or not verify_password(password, user.password):
            return None
        return user.id

    async def change_password(self, id: int, password: str) -> None:
        user = await AdminUser.get_or_none(id=id)
        if user is None:
            return
        user.password = hash_password(password)
        await user.save(update_fields=["password"])
