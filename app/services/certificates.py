"""
Certificate helper logic moved from `app/main.py` (structural refactor only).
"""

from datetime import date
from typing import Optional

from sqlalchemy.orm import Session

from .streaks import _utc_date
from ..models import QuizResult


# -------------------------
# Certificate helpers (perfect score = 10/10 per level)
# -------------------------
CERTIFICATE_LEVELS = ("Beginner", "Intermediate", "Advance")


def _has_perfect_for_level(db: Session, user_id: int, level: str) -> bool:
    """True if user has at least one quiz result for this level with 10/10 (perfect)."""
    from sqlalchemy import and_

    q = db.query(QuizResult).filter(
        and_(
            QuizResult.user_id == user_id,
            QuizResult.quiz_level == level,
            QuizResult.score == 10,
            QuizResult.total_questions == 10,
        )
    ).first()
    return q is not None


def _certificate_achieved_date(db: Session, user_id: int, level: str) -> Optional[date]:
    """Return the date of the most recent 10/10 result for this level, or None."""
    from sqlalchemy import and_, desc

    r = (
        db.query(QuizResult)
        .filter(
            and_(
                QuizResult.user_id == user_id,
                QuizResult.quiz_level == level,
                QuizResult.score == 10,
                QuizResult.total_questions == 10,
            )
        )
        .order_by(desc(QuizResult.taken_at))
        .first()
    )
    if not r or not getattr(r, "taken_at", None):
        return None
    return _utc_date(r.taken_at)


def get_certificates_earned(db: Session, user_id: int) -> list:
    """Return list of level names for which the user has earned a certificate (perfect score)."""
    return [lev for lev in CERTIFICATE_LEVELS if _has_perfect_for_level(db, user_id, lev)]