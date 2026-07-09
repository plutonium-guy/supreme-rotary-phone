"""ASGI entry point.

Run with:  ``uvicorn main:app --reload``  (or ``python manage.py runserver``).
"""

import core  # noqa: F401 - installs the beartype import hook first

from config.app import create_app

app = create_app()
