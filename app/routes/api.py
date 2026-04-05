from datetime import datetime, timedelta, timezone
from typing import Optional
from urllib.parse import quote

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import Response
from sqlalchemy.orm import Session

from ..certificates import generate_certificate_pdf
from ..models import Notification, QuizResult, User
from ..services.certificates import (
    CERTIFICATE_LEVELS,
    _certificate_achieved_date,
    _has_perfect_for_level,
    get_certificates_earned,
)
from ..services.notifications import (
    create_notification_for_user,
    is_user_also_admin,
)
from ..services.streaks import compute_streak, get_activity_dates
from ..utils.deps import get_db

router = APIRouter()


@router.get("/api/notifications")
def get_notifications(request: Request, db: Session = Depends(get_db)):
    """Get all unread notifications for the logged-in user."""
    user_id = request.session.get("user_id")
    if not user_id:
        return {"notifications": [], "unread_count": 0}

    notifications = (
        db.query(Notification)
        .filter(Notification.user_id == user_id)
        .order_by(Notification.created_at.desc())
        .limit(10)
        .all()
    )

    unread_count = (
        db.query(Notification)
        .filter(Notification.user_id == user_id, Notification.is_read == False)
        .count()
    )

    return {
        "notifications": [
            {
                "id": n.id,
                "title": n.title,
                "message": n.message,
                "type": n.notification_type,
                "is_read": n.is_read,
                "created_at": n.created_at.isoformat() if n.created_at else None,
            }
            for n in notifications
        ],
        "unread_count": unread_count,
    }


@router.post("/api/notifications/{notification_id}/read")
def mark_notification_as_read(notification_id: int, db: Session = Depends(get_db)):
    """Mark a notification as read."""
    notification = db.query(Notification).filter(Notification.id == notification_id).first()
    if notification:
        notification.is_read = True
        db.commit()
    return {"status": "success"}


@router.post("/api/notifications/read-all")
def mark_all_notifications_as_read(request: Request, db: Session = Depends(get_db)):
    """Mark all notifications as read for logged-in user."""
    user_id = request.session.get("user_id")
    if user_id:
        db.query(Notification).filter(
            Notification.user_id == user_id, Notification.is_read == False
        ).update({Notification.is_read: True})
        db.commit()
    return {"status": "success"}


@router.delete("/api/notifications/{notification_id}/delete")
def delete_notification(notification_id: int, db: Session = Depends(get_db)):
    """Delete a notification."""
    notification = db.query(Notification).filter(Notification.id == notification_id).first()
    if notification:
        db.delete(notification)
        db.commit()
    return {"status": "success"}


@router.post("/api/quiz_result")
def save_quiz_result(
    request: Request,
    quiz_id: Optional[int] = Form(None),
    quiz_level: Optional[str] = Form(None),
    score: int = Form(...),
    total_questions: int = Form(...),
    db: Session = Depends(get_db),
):
    """Save a user's quiz result."""
    user_id = request.session.get("user_id")
    if not user_id:
        return {"status": "error", "detail": "User not logged in"}

    if quiz_id is None and not quiz_level:
        return {"status": "error", "detail": "quiz_id or quiz_level is required"}

    if total_questions < 1 or total_questions > 100:
        return {"status": "error", "detail": "total_questions must be between 1 and 100"}
    if score < 0 or score > total_questions:
        return {"status": "error", "detail": "score must be between 0 and total_questions"}

    # Points & badges before this attempt
    results_before = db.query(QuizResult).filter(QuizResult.user_id == user_id).all()
    total_points_before = sum(r.score for r in results_before)
    badges_before = total_points_before // 20

    # Streak state before saving this quiz
    activity_dates_before = get_activity_dates(user_id, db)
    reference_old = max(activity_dates_before) if activity_dates_before else None
    old_streak = compute_streak(activity_dates_before, reference_old) if reference_old else 0

    quiz_result = QuizResult(
        user_id=user_id,
        quiz_id=quiz_id,
        quiz_level=quiz_level,
        score=score,
        total_questions=total_questions,
    )
    db.add(quiz_result)
    db.commit()
    db.refresh(quiz_result)

    total_points_after = total_points_before + score
    badges_after = total_points_after // 20
    badge_just_unlocked = badges_after > badges_before
    level_name = quiz_level or "Quiz"

    # Recompute activity dates after inserting this quiz result
    activity_dates_after = get_activity_dates(user_id, db)
    today_utc = datetime.now(timezone.utc).date()
    if activity_dates_after:
        new_date = max(activity_dates_after)
        new_streak = compute_streak(activity_dates_after, new_date)
    else:
        new_date = today_utc
        new_streak = 1

    # Flags control which streak notifications we send
    streak_continued = False
    streak_broken = False
    streak_milestone = False
    if reference_old is None:
        pass
    elif new_date == reference_old:
        new_streak = old_streak
    elif new_date == reference_old + timedelta(days=1):
        streak_continued = True
        if new_streak in (7, 30):
            streak_milestone = True
    else:
        streak_broken = old_streak > 0

    # System notifications (quiz completed, points, badge, streak) go only to regular users, not to admins
    user_is_admin = is_user_also_admin(user_id, db)
    create_notification_for_user(
        db,
        user_id,
        title="Quiz completed!",
        message=f"You completed the {level_name} quiz and earned {score} point(s). Your total is now {total_points_after} points.",
        notification_type="quiz",
        related_id=quiz_result.id,
    )
    if not user_is_admin:
        if score > 0:
            create_notification_for_user(
                db,
                user_id,
                title="Points earned!",
                message=f"You earned {score} point(s) from the {level_name} quiz. Total points: {total_points_after}.",
                notification_type="update",
                related_id=quiz_result.id,
            )
        if badge_just_unlocked:
            create_notification_for_user(
                db,
                user_id,
                title="New badge unlocked!",
                message=f"You earned a new badge! You now have {badges_after} badge(s). Keep it up!",
                notification_type="update",
                related_id=quiz_result.id,
            )
        if streak_continued:
            create_notification_for_user(
                db,
                user_id,
                title="Streak continued!",
                message=f"You're on a {new_streak}-day streak! Keep it up!",
                notification_type="update",
                related_id=quiz_result.id,
            )
        if streak_broken:
            create_notification_for_user(
                db,
                user_id,
                title="Streak reset",
                message="Your streak was reset. Start again today!",
                notification_type="update",
                related_id=quiz_result.id,
            )
        if streak_milestone:
            create_notification_for_user(
                db,
                user_id,
                title="Milestone streak!",
                message=f"Amazing! You've reached a {new_streak}-day streak!",
                notification_type="update",
                related_id=quiz_result.id,
            )

    return {
        "status": "success",
        "quiz_result_id": quiz_result.id,
        "total_points_after": total_points_after,
        "badges_after": badges_after,
        "badge_just_unlocked": badge_just_unlocked,
        "quiz_level": level_name,
        "current_streak": new_streak,
        "streak_continued": streak_continued,
        "streak_broken": streak_broken,
        "streak_milestone": streak_milestone,
        "certificate_earned": score == 10 and total_questions == 10,
        "certificate_level": level_name if (score == 10 and total_questions == 10) else None,
    }


@router.get("/api/user_stats")
def get_user_stats(request: Request, db: Session = Depends(get_db)):
    """Return total points, badges, quizzes taken, streak, and progress for the logged-in user."""
    user_id = request.session.get("user_id")
    if not user_id:
        return {"status": "error", "detail": "User not logged in"}
    results = db.query(QuizResult).filter(QuizResult.user_id == user_id).all()
    quizzes_taken = len(results)
    total_points = sum(r.score for r in results)
    badges = total_points // 20
    points_in_chunk = total_points % 20
    points_to_next_badge = 20 - points_in_chunk if points_in_chunk else 20
    if badges == 0:
        badge_tier = "bronze"
    elif badges == 1:
        badge_tier = "bronze"
    elif 2 <= badges <= 3:
        badge_tier = "silver"
    else:
        badge_tier = "gold"
    activity_dates = get_activity_dates(user_id, db)
    reference = max(activity_dates) if activity_dates else None
    today_utc = datetime.now(timezone.utc).date()
    # If user hasn't done a quiz for 3 days, streak is ended and reset to 0
    if reference is None or (today_utc - reference) >= timedelta(days=3):
        current_streak = 0
    else:
        current_streak = compute_streak(activity_dates, reference)
    certificates_earned = get_certificates_earned(db, user_id)
    return {
        "status": "success",
        "quizzes_taken": quizzes_taken,
        "total_points": total_points,
        "badges": badges,
        "points_in_chunk": points_in_chunk,
        "points_to_next_badge": points_to_next_badge,
        "badge_tier": badge_tier,
        "current_streak": current_streak,
        "certificates_earned": certificates_earned,
    }


@router.get("/api/certificate/{level}/download")
def download_certificate(level: str, request: Request, db: Session = Depends(get_db)):
    """Generate and return a PDF certificate for the given level if the user has earned it (perfect score)."""
    user_id = request.session.get("user_id")
    if not user_id:
        return {"status": "error", "detail": "User not logged in"}
    level_normalized = level.strip()
    if level_normalized not in CERTIFICATE_LEVELS:
        return {"status": "error", "detail": "Invalid level"}
    if not _has_perfect_for_level(db, user_id, level_normalized):
        return {"status": "error", "detail": "Certificate not earned for this level"}
    user = db.query(User).filter(User.id == user_id).first()
    user_name = user.username if user else "Learner"
    achieved_date = _certificate_achieved_date(db, user_id, level_normalized)
    if not achieved_date:
        achieved_date = datetime.now(timezone.utc).date()
    try:
        pdf_bytes = generate_certificate_pdf(user_name, level_normalized, achieved_date)
    except Exception:
        return {"status": "error", "detail": "Certificate generation failed"}
    safe_name = quote(level_normalized.replace(" ", "_"))
    filename = f"GestureLab_Certificate_{safe_name}.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )

