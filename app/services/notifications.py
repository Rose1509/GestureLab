"""
Notification helper logic moved from `app/main.py` (structural refactor only).
"""

from typing import Optional

from sqlalchemy.orm import Session

from ..models import Admin, Notification, User


def is_user_also_admin(user_id: int, db: Session) -> bool:
    """Return True if this user's email matches an admin (so we don't send system notifications to admins)."""
    user = db.query(User).filter(User.id == user_id).first()
    if not user or not user.email:
        return False
    admin = db.query(Admin).filter(Admin.email.ilike(user.email.strip())).first()
    return admin is not None


def create_notification_for_all_users(
    db: Session,
    title: str,
    message: str,
    notification_type: str,
    related_id: Optional[int] = None,
    is_admin_created: bool = False,
    admin_batch_id: Optional[str] = None,
):
    """Create a notification for all users when admin adds/updates lessons or quizzes (or sends from Notifications page)."""
    try:
        all_users = db.query(User).all()
        for user in all_users:
            notification = Notification(
                user_id=user.id,
                title=title,
                message=message,
                notification_type=notification_type,
                related_id=related_id,
                is_read=False,
                is_admin_created=is_admin_created,
                admin_batch_id=admin_batch_id,
            )
            db.add(notification)
        db.commit()
    except Exception as e:
        print(f"Error creating notifications: {e}")
        db.rollback()


def create_notification_for_user(
    db: Session,
    user_id: int,
    title: str,
    message: str,
    notification_type: str,
    related_id: Optional[int] = None,
):
    """Create a notification for a single user (e.g. quiz completed, points earned, badge unlocked). Only for non-admin users for system messages."""
    try:
        notification = Notification(
            user_id=user_id,
            title=title,
            message=message,
            notification_type=notification_type,
            related_id=related_id,
            is_read=False,
            is_admin_created=False,
            admin_batch_id=None,
        )
        db.add(notification)
        db.commit()
    except Exception as e:
        print(f"Error creating user notification: {e}")
        db.rollback()
