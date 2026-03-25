"""
Models package.

Exports SQLAlchemy ORM models for compatibility with the prior `from .models import ...` imports.
"""

from .db_models import (  # noqa: F401
    User,
    Lesson,
    Quiz,
    Admin,
    Notification,
    QuizResult,
    ContactSubmission,
    PasswordResetCode,
)

