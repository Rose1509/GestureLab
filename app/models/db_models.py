# app/models/db_models.py
#
# ORM models: `User` maps to PostgreSQL `register`; `Admin` maps to `admin`.

from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, Integer, String, Text

from ..database import Base


class User(Base):
    __tablename__ = "register"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(255), unique=True, index=True, nullable=False)
    username = Column(String(50), unique=True, index=True, nullable=False)
    password = Column(String(255), nullable=False)
    google_id = Column(String(255), nullable=True, unique=True, index=True)
    last_login_at = Column(DateTime(timezone=True), nullable=True)


class Lesson(Base):
    __tablename__ = "lessons"

    id = Column(Integer, primary_key=True, index=True)
    sign_level = Column(String(50), nullable=False)  # Basic, Intermediate, Advance
    name = Column(String(100), nullable=False)
    image = Column(String(500), nullable=False)
    heading = Column(String(200), nullable=False)
    description = Column(Text, nullable=False)


class Quiz(Base):
    __tablename__ = "quizzes"

    id = Column(Integer, primary_key=True, index=True)
    level = Column(String(50), nullable=False)
    question_text = Column(Text, nullable=True)
    question_image = Column(String(500), nullable=True)

    option1_text = Column(String(255), nullable=True)
    option2_text = Column(String(255), nullable=True)
    option3_text = Column(String(255), nullable=True)
    option4_text = Column(String(255), nullable=True)

    option1_image = Column(String(500), nullable=True)
    option2_image = Column(String(500), nullable=True)
    option3_image = Column(String(500), nullable=True)
    option4_image = Column(String(500), nullable=True)

    correct_option = Column(Integer, nullable=False)


class Admin(Base):
    __tablename__ = "admin"

    id = Column(Integer, primary_key=True, index=True)
    full_name = Column(String(100), nullable=False)
    username = Column(String(50), unique=True, nullable=False)
    email = Column(String(255), unique=True, nullable=False)
    password = Column(String(255), nullable=False)
    last_login_at = Column(DateTime(timezone=True), nullable=True)


class PasswordResetCode(Base):
    __tablename__ = "password_reset_codes"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(255), index=True, nullable=False)
    code_hash = Column(String(64), nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    used_at = Column(DateTime(timezone=True), nullable=True)


class Notification(Base):
    __tablename__ = "notifications"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, nullable=False)
    title = Column(String(200), nullable=False)
    message = Column(Text, nullable=False)
    notification_type = Column(String(50), nullable=False)
    related_id = Column(Integer, nullable=True)
    is_read = Column(Boolean, default=False, nullable=False)
    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    is_admin_created = Column(Boolean, default=False, nullable=False)
    admin_batch_id = Column(String(100), nullable=True)


class ContactSubmission(Base):
    __tablename__ = "contact_submissions"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    email = Column(String(255), nullable=False)
    subject = Column(String(500), nullable=False)
    message = Column(Text, nullable=False)
    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )


class QuizResult(Base):
    __tablename__ = "quiz_results"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, nullable=False)
    quiz_id = Column(Integer, nullable=True)
    quiz_level = Column(String(50), nullable=True)
    score = Column(Integer, nullable=False)
    total_questions = Column(Integer, nullable=False)
    taken_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
