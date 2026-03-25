"""
Dependency helpers moved from `app/main.py` (structural refactor only).
"""

from fastapi import Request
from fastapi.responses import RedirectResponse

from ..database import SessionLocal


# -------------------------
# DB Dependency
# -------------------------
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# -------------------------
# Admin-only dependency (redirect to login if not admin)
# -------------------------
class AdminRequiredRedirect(Exception):
    """Raised when admin auth is required but session is not admin. Handled by redirecting to login."""

    def __init__(self, url: str = "/login", status_code: int = 303):
        self.url = url
        self.status_code = status_code


def require_admin(request: Request) -> None:
    """Dependency: redirect to login if the request session is not an admin."""
    if not request.session.get("admin_id") or not request.session.get("is_admin"):
        raise AdminRequiredRedirect()


def admin_required_redirect_handler(request: Request, exc: AdminRequiredRedirect):
    return RedirectResponse(url=exc.url, status_code=exc.status_code)

