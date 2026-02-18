# app/models.py

from sqlalchemy import Column, Integer, String, Text, Boolean, DateTime
from datetime import datetime, timezone
from .database import Base, engine  # import engine from database.py

class User(Base):
    __tablename__ = "register"  # match your PostgreSQL table

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(255), unique=True, index=True, nullable=False)
    username = Column(String(50), unique=True, index=True, nullable=False)
    password = Column(String(255), nullable=False)
    google_id = Column(String(255), nullable=True, unique=True, index=True)

class Lesson(Base):
    __tablename__ = "lessons"

    id = Column(Integer, primary_key=True, index=True)
    sign_level = Column(String(50), nullable=False)  # Basic, Intermediate, Advance
    name = Column(String(100), nullable=False)
    image = Column(String(500), nullable=False)  # URL or path to image
    heading = Column(String(200), nullable=False)
    description = Column(Text, nullable=False)  # Can be longer text with multiple steps


class Quiz(Base):
    __tablename__ = "quizzes"

    id = Column(Integer, primary_key=True, index=True)
    level = Column(String(50), nullable=False)  # Beginner, Intermediate, Advance
    # Question text/image are optional so that a quiz can be image-only or text-only
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

    correct_option = Column(Integer, nullable=False)  # 1–4


class Admin(Base):
    __tablename__ = "admin"

    id = Column(Integer, primary_key=True, index=True)
    full_name = Column(String(100), nullable=False)
    username = Column(String(50), unique=True, nullable=False)
    email = Column(String(255), unique=True, nullable=False)
    password = Column(String(255), nullable=False)


class Notification(Base):
    __tablename__ = "notifications"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, nullable=False)  # User receiving the notification
    title = Column(String(200), nullable=False)  # e.g., "New Lesson Added"
    message = Column(Text, nullable=False)  # Full message text
    notification_type = Column(String(50), nullable=False)  # "lesson", "quiz", "update"
    related_id = Column(Integer, nullable=True)  # ID of lesson/quiz that triggered notification
    is_read = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime(timezone=True),default=lambda: datetime.now(timezone.utc),nullable=False
)



# QuizResult: stores each user's quiz attempt and score
class QuizResult(Base):
    __tablename__ = "quiz_results"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, nullable=False)
    # `quiz_id` is optional because the UI submits a quiz "attempt" for a level that
    # can contain multiple question rows from the `quizzes` table.
    quiz_id = Column(Integer, nullable=True)
    quiz_level = Column(String(50), nullable=True)  # Beginner, Intermediate, Advance
    score = Column(Integer, nullable=False)
    total_questions = Column(Integer, nullable=False)
    taken_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)

Base.metadata.create_all(bind=engine)
