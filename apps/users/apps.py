"""App configuration for the users app."""

from core.apps import AppConfig


class UsersConfig(AppConfig):
    name = "apps.users"
    label = "users"
    verbose_name = "Users & Accounts"

    def ready(self) -> None:
        # Import signals / side effects here if needed.
        pass
