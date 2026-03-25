"""
Streak helper logic moved from `app/main.py` (structural refactor only).
"""

from datetime import date, timedelta, timezone

from sqlalchemy.orm import Session

from ..models import QuizResult


def _utc_date(dt):
    """Return the calendar date in UTC for a datetime (aware or naive)."""
    if dt is None:
        return None
    if getattr(dt, "tzinfo", None) is not None:
        return dt.astimezone(timezone.utc).date()
    # Naive: assume UTC (e.g. from DB without TZ)
    return dt.date() if hasattr(dt, "date") else dt


def get_activity_dates(user_id: int, db: Session):
    """Return set of calendar dates (UTC) on which the user took at least one quiz."""
    results = db.query(QuizResult).filter(QuizResult.user_id == user_id).all()
    dates = set()
    for r in results:
        raw = getattr(r, "taken_at", None)
        d = _utc_date(raw)
        if d is not None:
            dates.add(d)
    return dates


def compute_streak(activity_dates: set, reference_date: date) -> int:
    """Count how many consecutive days (ending at reference_date) the user has at least one quiz."""
    if not activity_dates or reference_date not in activity_dates:
        return 0
    count = 0
    d = reference_date
    while d in activity_dates:
        count += 1
        d -= timedelta(days=1)
    return count

