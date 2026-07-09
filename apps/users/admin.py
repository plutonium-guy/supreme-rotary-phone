"""Admin registration for the users app.

One line per model — see ``core.admin.register_model`` for options
(``label``, ``icon``, ``exclude``, ``fields``). Delete this file entirely
and the framework auto-registers every model the app defines.
"""

from core.admin import register_model

from apps.users.models import AdminUser, User

register_model(User, label="Users", icon="fas fa-user")
register_model(AdminUser, label="Admins", icon="fas fa-user-shield")
