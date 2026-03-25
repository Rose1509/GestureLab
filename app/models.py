"""Compatibility shim for prior imports.

Structural refactor only: ORM models now live in `app/models/db_models.py` and are
re-exported by the `app/models` package.
"""

from .models import (  # noqa: F401
    User,
    Lesson,
    Quiz,
    Admin,
    Notification,
    QuizResult,
    ContactSubmission,
    PasswordResetCode,
)
