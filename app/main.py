"""Main FastAPI application for Gesture Lab (routing, auth, quizzes, practice API)."""
import os
import json
import uuid
import secrets
import hashlib
import smtplib
from email.message import EmailMessage
from datetime import date, timedelta, timezone, datetime
from typing import Optional
from urllib.parse import quote

from fastapi import FastAPI, Request, Form, Depends, File, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware
from sqlalchemy.orm import Session
from sqlalchemy import or_

from dotenv import load_dotenv

from .database import SessionLocal, ensure_schema
from .models import User, Lesson, Quiz, Admin, Notification, QuizResult, ContactSubmission, PasswordResetCode
from .authentication import hash_password, verify_password, validate_username, validate_password, validate_email, validate_contact_email, validate_subject_word_count, validate_contact_name, validate_contact_message
from .certificate import generate_certificate_pdf
from . import sign_model

# -------------------------
# Paths (from config; project root = BASE_DIR)
# -------------------------
from .config import BASE_DIR, STATIC_DIR, IMAGES_DIR, TEMPLATES_DIR

# -------------------------
# Google OAuth (Authlib)
# -------------------------
from authlib.integrations.starlette_client import OAuth, OAuthError

# Load .env from multiple locations so credentials are found however the app is run
_env_paths = [
    os.path.join(BASE_DIR, ".env"),
    os.path.join(os.getcwd(), ".env"),
    ".env",
]
for _p in _env_paths:
    _res = load_dotenv(_p)
    if _res:
        break
# Also use dotenv's default discovery (current dir and parents)
load_dotenv()


# -------------------------
# FastAPI app
# -------------------------
app = FastAPI()
_session_secret = (os.getenv("SESSION_SECRET_KEY") or "").strip() or "your-secret-key-change-in-production"
app.add_middleware(SessionMiddleware, secret_key=_session_secret)

# Create images directory if it doesn't exist
os.makedirs(IMAGES_DIR, exist_ok=True)

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
templates = Jinja2Templates(directory=TEMPLATES_DIR)

def _load_google_oauth_settings() -> dict:
    """
    Load Google OAuth settings from env vars or `credentials.json`.

    Supported env vars:
      - GOOGLE_CLIENT_ID
      - GOOGLE_CLIENT_SECRET
      - GOOGLE_OAUTH_REDIRECT_URI (optional)
    """
    client_id = (os.getenv("GOOGLE_CLIENT_ID") or "").strip()
    client_secret = (os.getenv("GOOGLE_CLIENT_SECRET") or "").strip()
    redirect_uri = (os.getenv("GOOGLE_OAUTH_REDIRECT_URI") or "").strip()

    # Fallback to credentials.json (common for local/dev), but ONLY if env vars are not in use.
    # If the user set only one of GOOGLE_CLIENT_ID/GOOGLE_CLIENT_SECRET, do NOT mix with
    # credentials.json (it would create mismatched credentials and fail with invalid_client).
    env_has_any = bool(client_id or client_secret or redirect_uri)
    if (not env_has_any) and os.path.exists(os.path.join(BASE_DIR, "credentials.json")):
        try:
            with open(os.path.join(BASE_DIR, "credentials.json"), "r", encoding="utf-8") as f:
                raw = json.load(f)
            web = raw.get("web") or {}
            client_id = client_id or (web.get("client_id") or "").strip()
            client_secret = client_secret or (web.get("client_secret") or "").strip()
            if not redirect_uri:
                uris = web.get("redirect_uris") or []
                if uris:
                    redirect_uri = str(uris[0]).strip()
        except Exception:
            pass

    return {
        "client_id": client_id,
        "client_secret": client_secret,
        "redirect_uri": redirect_uri,
    }


_google_settings = _load_google_oauth_settings()
oauth = OAuth()
GOOGLE_OAUTH_ENABLED = bool(_google_settings.get("client_id") and _google_settings.get("client_secret"))
if GOOGLE_OAUTH_ENABLED:
    oauth.register(
        name="google",
        client_id=_google_settings["client_id"],
        client_secret=_google_settings["client_secret"],
        server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
        client_kwargs={"scope": "openid email profile"},
    )


def _render_login(request: Request, error: Optional[str] = None) -> HTMLResponse:
    return templates.TemplateResponse(
        "login.html",
        {"request": request, "error": error},
    )


# -------------------------
# Initialize default admin if none exists
# -------------------------
def init_admin():
    """Create default admin account if it doesn't exist."""
    db = SessionLocal()
    try:
        admin = db.query(Admin).first()
        if not admin:
            default_admin = Admin(
                full_name="Rose Khatiwada",
                username="Rose",
                email="rkc123@gmail.com",
                password=hash_password("Rose@123")
            )
            db.add(default_admin)
            db.commit()
            print("Default admin account created: username='Rose', password='Rose@123'")
    except Exception as e:
        print(f"Error initializing admin: {e}")
        db.rollback()
    finally:
        db.close()

@app.on_event("startup")
def on_startup() -> None:
    try:
        # Create all tables defined in models
        from .database import Base, engine
        Base.metadata.create_all(bind=engine)
        print("[OK] Database tables created")
        
        # Ensure DB schema matches models for local/dev databases (no migrations in repo)
        ensure_schema()
        # Create default admin account if missing
        init_admin()
        print("[OK] Database schema and admin initialization completed successfully")
    except Exception as e:
        print(f"[WARN] Warning during startup: {e}")
        print("App will continue, but database operations may fail until the database is available")


# -------------------------
# Admin upload validation (lessons / quizzes)
# -------------------------
ALLOWED_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp"}
ALLOWED_IMAGE_CONTENT_TYPES = {"image/jpeg", "image/png", "image/gif", "image/webp"}
MAX_IMAGE_SIZE_BYTES = 5 * 1024 * 1024  # 5 MB
UPLOAD_VALIDATION_MESSAGE = "Image must be JPG, PNG, GIF or WebP and under 5 MB."


def validate_uploaded_image(file: UploadFile, content: bytes) -> None:
    """Raise ValueError with UPLOAD_VALIDATION_MESSAGE if file is invalid."""
    if len(content) > MAX_IMAGE_SIZE_BYTES:
        raise ValueError(UPLOAD_VALIDATION_MESSAGE)
    ext = os.path.splitext(file.filename or "")[1].lower()
    content_type = (file.content_type or "").strip().lower().split(";")[0]
    if ext not in ALLOWED_IMAGE_EXTENSIONS or content_type not in ALLOWED_IMAGE_CONTENT_TYPES:
        raise ValueError(UPLOAD_VALIDATION_MESSAGE)


# -------------------------
# Helper function to save uploaded file
# -------------------------
async def save_uploaded_file(file: UploadFile) -> str:
    """Save uploaded file and return the relative path. Validates type and size (max 5 MB)."""
    content = await file.read()
    validate_uploaded_image(file, content)

    # Generate unique filename
    file_ext = os.path.splitext(file.filename)[1] if file.filename else ".jpg"
    if file_ext.lower() not in ALLOWED_IMAGE_EXTENSIONS:
        file_ext = ".jpg"
    unique_filename = f"{uuid.uuid4()}{file_ext}"
    file_path = os.path.join(IMAGES_DIR, unique_filename)

    with open(file_path, "wb") as buffer:
        buffer.write(content)

    await file.seek(0)
    return f"/static/images/{unique_filename}"

# -------------------------
# Notification Helper
# -------------------------
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


# -------------------------
# Streak helpers (daily activity: at least one quiz per day)
# -------------------------
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


@app.exception_handler(AdminRequiredRedirect)
def admin_required_redirect_handler(request: Request, exc: AdminRequiredRedirect):
    return RedirectResponse(url=exc.url, status_code=exc.status_code)


# -------------------------
# GET Routes
# -------------------------
@app.get("/", response_class=HTMLResponse)
def landing_page(request: Request):
    return templates.TemplateResponse("landing_page.html", {"request": request})

@app.get("/home", response_class=HTMLResponse)
def home_page(request: Request):
    return templates.TemplateResponse("home.html", {"request": request})

@app.get("/login", response_class=HTMLResponse)
def login_form(request: Request):
    logout_success = request.query_params.get("logout_success")
    register_success = request.query_params.get("register_success")
    return templates.TemplateResponse(
        "login.html",
        {"request": request, "error": None, "logout_success": logout_success, "register_success": register_success},
    )

@app.get("/auth/google/login")
async def auth_google_login(request: Request):
    if not GOOGLE_OAUTH_ENABLED:
        return _render_login(
            request,
            error="Google sign-in is not configured. Please set GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET in .env.",
        )

    # Prefer explicit env redirect (helps when running behind tunnels/proxies).
    redirect_uri = (_google_settings.get("redirect_uri") or "").strip()
    if not redirect_uri:
        # Default to our callback endpoint.
        redirect_uri = str(request.url_for("auth_google_callback"))
    return await oauth.google.authorize_redirect(request, redirect_uri)


async def _auth_google_callback_impl(request: Request):
    if not GOOGLE_OAUTH_ENABLED:
        return _render_login(
            request,
            error="Google sign-in is not configured. Please set GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET in .env.",
        )

    # If Google sent an error directly to our callback, surface it.
    qp = request.query_params
    if qp.get("error"):
        err = qp.get("error") or "oauth_error"
        desc = qp.get("error_description") or qp.get("error_reason") or ""
        msg = f"Google sign-in error: {err}"
        if desc:
            msg = f"{msg}. {desc}"
        return _render_login(request, error=msg)

    db = SessionLocal()
    try:
        token = await oauth.google.authorize_access_token(request)
        # Prefer OIDC ID token parsing; fallback to userinfo.
        userinfo = None
        try:
            userinfo = await oauth.google.parse_id_token(request, token)
        except Exception:
            pass
        if not userinfo:
            # Some environments end up resolving "userinfo" to a relative "/userinfo" URL.
            # Use the well-known absolute OIDC userinfo endpoint to avoid UnsupportedProtocol.
            resp = await oauth.google.get("https://openidconnect.googleapis.com/v1/userinfo", token=token)
            userinfo = resp.json() if resp else None
    except OAuthError as e:
        db.close()
        # Authlib's OAuthError may include useful details.
        detail = ""
        try:
            if getattr(e, "description", None):
                detail = str(e.description)
            elif getattr(e, "error", None):
                detail = str(e.error)
            elif getattr(e, "message", None):
                detail = str(e.message)
        except Exception:
            detail = ""
        try:
            print(f"[WARN] Google OAuthError: {repr(e)}")
        except Exception:
            pass
        if detail:
            return _render_login(request, error=f"Google sign-in failed: {detail}")
        return _render_login(request, error="Google sign-in failed. Please try again.")
    except Exception as e:
        db.close()
        try:
            print(f"[WARN] Google sign-in exception: {type(e).__name__}: {e}")
            # httpx exceptions often include the failing request URL
            req = getattr(e, "request", None)
            if req is not None:
                try:
                    print(f"[WARN] Google sign-in failing URL: {getattr(req, 'url', None)}")
                except Exception:
                    pass
            # Also log what redirect_uri we attempted (should always include scheme)
            try:
                print(f"[WARN] Google OAuth redirect_uri: {_google_settings.get('redirect_uri') or 'auto'}")
            except Exception:
                pass
        except Exception:
            pass
        # Don't leak secrets; show type + generic text. (Exception message is usually safe but keep conservative.)
        return _render_login(request, error=f"Google sign-in failed ({type(e).__name__}). Please try again.")

    if not userinfo:
        db.close()
        return _render_login(request, error="Google sign-in failed (no profile).")

    google_sub = (userinfo.get("sub") or userinfo.get("id") or "").strip()
    email = (userinfo.get("email") or "").strip()
    name = (userinfo.get("name") or "").strip()

    if not email:
        db.close()
        return _render_login(request, error="Google sign-in failed (no email).")

    # If the email matches the single admin, treat as admin login.
    admin = db.query(Admin).first()
    if admin and admin.email and email.lower() == admin.email.strip().lower():
        try:
            now = datetime.now(timezone.utc)
            admin.last_login_at = now
            shadow_user = db.query(User).filter(User.email == admin.email).first()
            if shadow_user:
                shadow_user.last_login_at = now
            db.commit()
        except Exception:
            db.rollback()
        finally:
            db.close()
        request.session["admin_id"] = admin.id
        request.session["is_admin"] = True
        return RedirectResponse(url="/dashboard", status_code=303)

    # Normal user flow: find by google_id first, then email.
    user = None
    if google_sub:
        user = db.query(User).filter(User.google_id == google_sub).first()
    if not user:
        user = db.query(User).filter(User.email == email).first()

    if not user:
        # Create a unique username from name/email localpart.
        base = (name or email.split("@", 1)[0]).strip() or "user"
        # Keep it compatible with existing validation (max 25 in authentication.py).
        base = base[:25]
        candidate = base
        suffix = 0
        while db.query(User).filter(User.username == candidate).first() is not None:
            suffix += 1
            tail = str(suffix)
            candidate = (base[: max(1, 25 - (len(tail) + 1))] + "_" + tail)[:25]

        # Password is required by DB schema even for Google users.
        random_pw = secrets.token_urlsafe(24)
        user = User(
            email=email,
            username=candidate,
            password=hash_password(random_pw),
            google_id=google_sub or None,
        )
        db.add(user)
        try:
            db.commit()
            db.refresh(user)
        except Exception:
            db.rollback()
            db.close()
            return _render_login(request, error="Could not create account. Please try again.")
    else:
        # Link google_id if missing and provided.
        if google_sub and not getattr(user, "google_id", None):
            user.google_id = google_sub
            try:
                db.commit()
            except Exception:
                db.rollback()

    # Capture user_id before closing the session. SQLAlchemy expires attributes on commit
    # by default, which can make `user.id` trigger a refresh after the session is closed.
    try:
        user_id = int(user.id)
    except Exception:
        user_id = None

    try:
        user.last_login_at = datetime.now(timezone.utc)
        db.commit()
        # Ensure we have a stable id even after commit/expire.
        if user_id is None:
            db.refresh(user)
            user_id = int(user.id)
    except Exception:
        db.rollback()
        if user_id is None:
            try:
                db.refresh(user)
                user_id = int(user.id)
            except Exception:
                user_id = None
    finally:
        db.close()

    if user_id is None:
        return _render_login(request, error="Google sign-in failed (could not load account). Please try again.")

    request.session["user_id"] = user_id
    request.session["is_admin"] = False
    return RedirectResponse(url="/home?login_success=1", status_code=303)


@app.get("/auth/google/callback", name="auth_google_callback")
async def auth_google_callback(request: Request):
    return await _auth_google_callback_impl(request)


# Backwards-compatible alias (some existing setups use this path)
@app.get("/auth/google")
async def auth_google_callback_alias(request: Request):
    return await _auth_google_callback_impl(request)

@app.get("/forgot-password", response_class=HTMLResponse)
def forgot_password_form(request: Request):
    return templates.TemplateResponse(
        "forgot_password.html",
        {"request": request, "error": None, "success": None, "stage": "request", "email": ""},
    )

@app.get("/register", response_class=HTMLResponse)
def register_form(request: Request):
    return templates.TemplateResponse("register.html", {"request": request, "error": None})

@app.get("/about", response_class=HTMLResponse)
def about_us(request: Request):
    return templates.TemplateResponse("about_us.html", {"request": request})

@app.get("/contact", response_class=HTMLResponse)
def contact_us(request: Request):
    contact_success = request.query_params.get("contact_success") == "1"
    return templates.TemplateResponse(
        "contact_us.html",
        {
            "request": request,
            "contact_success": contact_success,
            "contact_error": None,
            "contact_name": "",
            "contact_email": "",
            "contact_subject": "",
            "contact_message": "",
        },
    )

@app.post("/contact", response_class=HTMLResponse)
def contact_us_submit(
    request: Request,
    name: str = Form(""),
    email: str = Form(""),
    subject: str = Form(""),
    message: str = Form(""),
    db: Session = Depends(get_db),
):
    """Validate contact form and save to DB so admin can see it."""
    ok_name, err_name = validate_contact_name(name)
    if not ok_name:
        return templates.TemplateResponse(
            "contact_us.html",
            {"request": request, "contact_error": err_name, "contact_name": name, "contact_email": email, "contact_subject": subject, "contact_message": message},
        )
    ok_email, err_email = validate_contact_email(email)
    if not ok_email:
        return templates.TemplateResponse(
            "contact_us.html",
            {"request": request, "contact_error": err_email, "contact_name": name, "contact_email": email, "contact_subject": subject, "contact_message": message},
        )
    ok_subject, err_subject = validate_subject_word_count(subject)
    if not ok_subject:
        return templates.TemplateResponse(
            "contact_us.html",
            {"request": request, "contact_error": err_subject, "contact_name": name, "contact_email": email, "contact_subject": subject, "contact_message": message},
        )
    ok_message, err_message = validate_contact_message(message)
    if not ok_message:
        return templates.TemplateResponse(
            "contact_us.html",
            {"request": request, "contact_error": err_message, "contact_name": name, "contact_email": email, "contact_subject": subject, "contact_message": message},
        )
    submission = ContactSubmission(
        name=name.strip(),
        email=email.strip(),
        subject=subject.strip(),
        message=message.strip(),
    )
    db.add(submission)
    db.commit()
    return RedirectResponse(url="/contact?contact_success=1", status_code=303)

@app.get("/practice", response_class=HTMLResponse)
def practice_page(request: Request, lesson_id: Optional[int] = None, db: Session = Depends(get_db)):
    """Practice page; if lesson_id is given, show that lesson's image and instructions."""
    lesson = None
    if lesson_id is not None:
        lesson = db.query(Lesson).filter(Lesson.id == lesson_id).first()
    return templates.TemplateResponse("practice.html", {"request": request, "lesson": lesson})

@app.get("/profile", response_class=HTMLResponse)
def profile_page(request: Request, db: Session = Depends(get_db)):
    """
    User profile page showing current user's login details and progress.
    """
    user_id = request.session.get("user_id")
    if not user_id:
        return RedirectResponse(url="/login", status_code=303)
    
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        return RedirectResponse(url="/login", status_code=303)
    
    # Fetch user progress data
    quiz_results = db.query(QuizResult).filter(QuizResult.user_id == user_id).all()
    
    # Calculate level-wise stats
    beginner_results = [r for r in quiz_results if r.quiz_level == 'Beginner']
    intermediate_results = [r for r in quiz_results if r.quiz_level == 'Intermediate']
    advance_results = [r for r in quiz_results if r.quiz_level == 'Advance']
    
    total_quizzes = len(quiz_results)
    total_points = sum(r.score for r in quiz_results)
    badges = total_points // 20
    
    # Calculate average scores by level
    beginner_avg = round(sum(r.score for r in beginner_results) / max(len(beginner_results), 1)) if beginner_results else 0
    intermediate_avg = round(sum(r.score for r in intermediate_results) / max(len(intermediate_results), 1)) if intermediate_results else 0
    advance_avg = round(sum(r.score for r in advance_results) / max(len(advance_results), 1)) if advance_results else 0
    
    # Determine current level based on total points
    if total_points < 50:
        current_level = "Beginner"
    elif total_points < 100:
        current_level = "Intermediate"
    else:
        current_level = "Advanced"
    
    return templates.TemplateResponse(
        "profile.html",
        {
            "request": request,
            "user": user,
            "error": None,
            "success": None,
            "total_quizzes": total_quizzes,
            "total_points": total_points,
            "badges": badges,
            "current_level": current_level,
            "beginner_count": len(beginner_results),
            "intermediate_count": len(intermediate_results),
            "advance_count": len(advance_results),
            "beginner_avg": beginner_avg,
            "intermediate_avg": intermediate_avg,
            "advance_avg": advance_avg,
        },
    )

@app.get("/add_quizzes", response_class=HTMLResponse)
def quizzes_page(request: Request, db: Session = Depends(get_db), _: None = Depends(require_admin)):
    """Admin view to add/edit quizzes."""
    quizzes = db.query(Quiz).all()
    error = request.query_params.get("error")
    return templates.TemplateResponse(
        "add_quizzes.html",
        {"request": request, "quizzes": quizzes, "error": error},
    )


@app.get("/quizzes", response_class=HTMLResponse)
def public_quizzes_page(request: Request, db: Session = Depends(get_db)):
    """
    Public quizzes listing page showing all quizzes created via the admin panel.
    """
    quizzes = db.query(Quiz).all()

    # Count quizzes per level so the public list stays in sync with admin-added quizzes
    beginner_count = sum(1 for q in quizzes if q.level == "Beginner")
    intermediate_count = sum(1 for q in quizzes if q.level == "Intermediate")
    advance_count = sum(1 for q in quizzes if q.level == "Advance")

    return templates.TemplateResponse(
        "quizzes.html",
        {
            "request": request,
            "quizzes": quizzes,
            "beginner_count": beginner_count,
            "intermediate_count": intermediate_count,
            "advance_count": advance_count,
        },
    )

@app.get("/beginner", response_class=HTMLResponse)
def beginner_quiz(request: Request, db: Session = Depends(get_db)):
    """
    Beginner quiz page showing only quizzes created in the admin with level 'Beginner'.
    """
    quizzes = db.query(Quiz).filter(Quiz.level == "Beginner").all()
    return templates.TemplateResponse(
        "beginner.html",
        {"request": request, "quizzes": quizzes},
    )

@app.get("/intermediate", response_class=HTMLResponse)
def intermediate_quiz(request: Request, db: Session = Depends(get_db)):
    """
    Intermediate quiz page showing only quizzes created in the admin with level 'Intermediate'.
    """
    quizzes = db.query(Quiz).filter(Quiz.level == "Intermediate").all()
    return templates.TemplateResponse(
        "intermediate.html",
        {"request": request, "quizzes": quizzes},
    )

@app.get("/advance", response_class=HTMLResponse)
def advance_quiz(request: Request, db: Session = Depends(get_db)):
    """
    Advance quiz page showing only quizzes created in the admin with level 'Advance'.
    """
    quizzes = db.query(Quiz).filter(Quiz.level == "Advance").all()
    return templates.TemplateResponse(
        "advance.html",
        {"request": request, "quizzes": quizzes},
    )

@app.get("/lessons", response_class=HTMLResponse)
def lessons_page(
    request: Request,
    q: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """
    Basic level lessons page with optional search by lesson name.
    """
    lessons_query = db.query(Lesson).filter(Lesson.sign_level == "Basic")
    if q and q.strip():
        term = f"%{q.strip()}%"
        lessons_query = lessons_query.filter(Lesson.name.ilike(term))

    lessons = lessons_query.all()
    return templates.TemplateResponse(
        "lessons.html",
        {
            "request": request,
            "lessons": lessons,
            "search_query": q.strip() if q and q.strip() else "",
        },
    )

@app.get("/intermediatee", response_class=HTMLResponse)
def intermediate_lessons_page(request: Request, db: Session = Depends(get_db)):
    # Fetch only Intermediate level lessons
    lessons = db.query(Lesson).filter(Lesson.sign_level == "Intermediate").all()
    return templates.TemplateResponse("intermediatee.html", {"request": request, "lessons": lessons})

@app.get("/advancee", response_class=HTMLResponse)
def advance_lessons_page(request: Request, db: Session = Depends(get_db)):
    # Fetch only Advance level lessons
    lessons = db.query(Lesson).filter(Lesson.sign_level == "Advance").all()
    return templates.TemplateResponse("advancee.html", {"request": request, "lessons": lessons})


@app.get("/dashboard", response_class=HTMLResponse)
def dashboard_page(
    request: Request,
    q: Optional[str] = None,
    db: Session = Depends(get_db),
    _: None = Depends(require_admin),
):
    """
    Admin dashboard showing basic stats and user list.
    Optional query param 'q' filters users by username or email (case-insensitive).
    """
    admin_name = "Admin"
    admin_email = None
    admin_last_login_at = None
    admin_id = request.session.get("admin_id")
    if admin_id:
        admin = db.query(Admin).filter(Admin.id == admin_id).first()
        if admin and admin.full_name:
            admin_name = admin.full_name
        if admin and admin.email:
            admin_email = admin.email
        if admin and getattr(admin, "last_login_at", None):
            admin_last_login_at = admin.last_login_at

    users_query = db.query(User)
    if q and q.strip():
        term = f"%{q.strip()}%"
        users_query = users_query.filter(
            or_(
                User.username.ilike(term),
                User.email.ilike(term),
            )
        )
    users = users_query.all()

    # Build rows for the "User Management" table (include admin too).
    user_rows = []
    if admin_email:
        if not q or not q.strip() or (admin_email and q.strip().lower() in admin_email.lower()) or (admin_name and q.strip().lower() in admin_name.lower()):
            user_rows.append(
                {
                    "id": None,
                    "email": admin_email,
                    "username": admin_name,
                    "role": "Admin",
                    "last_login_at": admin_last_login_at,
                    "is_admin": True,
                }
            )

    for u in users:
        if admin_email and u.email and u.email.strip().lower() == admin_email.strip().lower():
            # avoid duplicate row if admin email also exists in register table
            continue
        user_rows.append(
            {
                "id": u.id,
                "email": u.email,
                "username": u.username,
                "role": "User",
                "last_login_at": getattr(u, "last_login_at", None),
                "is_admin": False,
            }
        )

    # User count stays as "registered users" (register table)
    user_count = len(users)
    lesson_count = db.query(Lesson).count()
    quiz_count = db.query(Quiz).count()
    quiz_attempts_count = db.query(QuizResult).count()

    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "users": user_rows,
            "user_count": user_count,
            "lesson_count": lesson_count,
            "quiz_count": quiz_count,
            "quiz_attempts_count": quiz_attempts_count,
            "user_error": None,
            "admin_name": admin_name,
            "admin_email": admin_email,
            "search_query": q.strip() if q and q.strip() else None,
        },
    )

# -------------------------
# Notification Routes
# -------------------------
@app.get("/send_notifications", response_class=HTMLResponse)
def send_notifications_page(request: Request, db: Session = Depends(get_db), _: None = Depends(require_admin)):
    """Admin page to send custom notifications to all users."""
    return templates.TemplateResponse("send_notifications.html", {"request": request})


@app.get("/contact_messages", response_class=HTMLResponse)
def contact_messages_page(request: Request, db: Session = Depends(get_db), _: None = Depends(require_admin)):
    """Admin page to view contact form submissions from the Contact Us page."""
    submissions = (
        db.query(ContactSubmission)
        .order_by(ContactSubmission.created_at.desc())
        .all()
    )
    admin_name = "Admin"
    admin_id = request.session.get("admin_id")
    if admin_id:
        admin = db.query(Admin).filter(Admin.id == admin_id).first()
        if admin and admin.full_name:
            admin_name = admin.full_name
    return templates.TemplateResponse(
        "contact_messages.html",
        {"request": request, "submissions": submissions, "admin_name": admin_name},
    )


@app.post("/send_custom_notification")
def send_custom_notification(
    request: Request,
    notification_type: str = Form(...),
    title: str = Form(...),
    message: str = Form(...),
    db: Session = Depends(get_db),
    _: None = Depends(require_admin),
):
    """Handle custom notification submission from admin."""
    import uuid
    try:
        if not title or not message or not notification_type:
            return {"status": "error", "detail": "All fields are required"}
        if len(title) > 200:
            return {"status": "error", "detail": "Title must be 200 characters or less"}
        if len(message) > 1000:
            return {"status": "error", "detail": "Message must be 1000 characters or less"}
        admin_batch_id = str(uuid.uuid4())
        create_notification_for_all_users(
            db=db,
            title=title,
            message=message,
            notification_type=notification_type,
            related_id=None,
            is_admin_created=True,
            admin_batch_id=admin_batch_id,
        )
        return {"status": "success", "detail": "Notification sent to all users"}
    except Exception as e:
        return {"status": "error", "detail": str(e)}


@app.get("/admin/recent_notifications")
def get_admin_recent_notifications(db: Session = Depends(get_db), _: None = Depends(require_admin)):
    """Get recent notifications added by admin only (sent from Notifications page), within last 30 days."""
    from datetime import datetime, timedelta
    thirty_days_ago = datetime.utcnow() - timedelta(days=30)
    notifications = (
        db.query(Notification)
        .filter(
            Notification.created_at >= thirty_days_ago,
            Notification.is_admin_created == True,
            Notification.admin_batch_id.isnot(None),
        )
        .order_by(Notification.created_at.desc())
        .limit(500)
    ).all()
    # One row per user per batch; dedupe by admin_batch_id (show one per batch)
    by_batch = {}
    for notif in notifications:
        if notif.admin_batch_id and notif.admin_batch_id not in by_batch:
            by_batch[notif.admin_batch_id] = notif
    # Return most recent 10 batches
    unique_list = list(by_batch.values())[:10]
    return {
        "notifications": [
            {
                "id": n.id,
                "admin_batch_id": n.admin_batch_id,
                "title": n.title,
                "message": n.message,
                "notification_type": n.notification_type,
                "created_at": n.created_at.isoformat() if n.created_at else None,
            }
            for n in unique_list
        ]
    }


@app.get("/admin_profile", response_class=HTMLResponse)
def admin_profile_page(request: Request, db: Session = Depends(get_db), _: None = Depends(require_admin)):
    """Admin profile page with current admin data."""
    admin = db.query(Admin).first()
    if not admin:
        # If no admin exists, create default one
        init_admin()
        admin = db.query(Admin).first()
    
    return templates.TemplateResponse(
        "admin_profile.html",
        {
            "request": request,
            "admin": admin,
            "error": None,
            "success": None
        }
    )

@app.get("/add_lessons", response_class=HTMLResponse)
def add_lessons_page(request: Request, db: Session = Depends(get_db), _: None = Depends(require_admin)):
    lessons = db.query(Lesson).all()
    error = request.query_params.get("error")
    return templates.TemplateResponse(
        "add_lessons.html", {"request": request, "lessons": lessons, "error": error}
    )


@app.get("/logout")
def logout(request: Request):
    """Logout route - clears session and redirects to login."""
    request.session.clear()
    return RedirectResponse(url="/login?logout_success=1", status_code=303)

# -------------------------
# Notification Routes
# -------------------------
@app.get("/api/notifications")
def get_notifications(request: Request, db: Session = Depends(get_db)):
    """Get all unread notifications for the logged-in user."""
    user_id = request.session.get("user_id")
    if not user_id:
        return {"notifications": [], "unread_count": 0}
    
    notifications = db.query(Notification).filter(
        Notification.user_id == user_id
    ).order_by(Notification.created_at.desc()).limit(10).all()
    
    unread_count = db.query(Notification).filter(
        Notification.user_id == user_id,
        Notification.is_read == False
    ).count()
    
    return {
        "notifications": [
            {
                "id": n.id,
                "title": n.title,
                "message": n.message,
                "type": n.notification_type,
                "is_read": n.is_read,
                "created_at": n.created_at.isoformat() if n.created_at else None
            }
            for n in notifications
        ],
        "unread_count": unread_count
    }


@app.post("/api/notifications/{notification_id}/read")
def mark_notification_as_read(notification_id: int, db: Session = Depends(get_db)):
    """Mark a notification as read."""
    notification = db.query(Notification).filter(Notification.id == notification_id).first()
    if notification:
        notification.is_read = True
        db.commit()
    return {"status": "success"}


@app.post("/api/notifications/read-all")
def mark_all_notifications_as_read(request: Request, db: Session = Depends(get_db)):
    """Mark all notifications as read for logged-in user."""
    user_id = request.session.get("user_id")
    if user_id:
        db.query(Notification).filter(
            Notification.user_id == user_id,
            Notification.is_read == False
        ).update({Notification.is_read: True})
        db.commit()
    return {"status": "success"}


@app.delete("/api/notifications/{notification_id}/delete")
def delete_notification(notification_id: int, db: Session = Depends(get_db)):
    """Delete a notification."""
    notification = db.query(Notification).filter(Notification.id == notification_id).first()
    if notification:
        db.delete(notification)
        db.commit()
    return {"status": "success"}

# -------------------------
# POST Register
# -------------------------
@app.post("/register")
def register_submit(
    request: Request,
    email: str = Form(...),
    username: str = Form(...),
    password: str = Form(...),
    confirm_password: str = Form(...),
    db: Session = Depends(get_db)
):
    # Validation: username (max 15), password (must have #/@/$), email (must have @)
    ok, err = validate_username(username)
    if not ok:
        return templates.TemplateResponse("register.html", {"request": request, "error": err})
    ok, err = validate_email(email)
    if not ok:
        return templates.TemplateResponse("register.html", {"request": request, "error": err})
    ok, err = validate_password(password)
    if not ok:
        return templates.TemplateResponse("register.html", {"request": request, "error": err})

    # Password match check
    if password != confirm_password:
        return templates.TemplateResponse(
            "register.html", {"request": request, "error": "Passwords do not match!"}
        )

    # Prevent anyone from registering with admin username/email
    admin = db.query(Admin).first()
    if admin:
        if username.lower() == admin.username.lower() or email.lower() == admin.email.lower():
            return templates.TemplateResponse(
                "register.html",
                    {"request": request, "error": "This username or email is reserved!"}
        )

    # Check if username or email exists
    existing_user = db.query(User).filter(or_(User.username == username, User.email == email)).first()
    if existing_user:
        return templates.TemplateResponse(
            "register.html", {"request": request, "error": "Username or email already exists!"}
        )

    # Create normal user
    user = User(email=email, username=username, password=hash_password(password))
    db.add(user)
    db.commit()

    return RedirectResponse(url="/login?register_success=1", status_code=303)

# -------------------------
# POST Forgot Password
# -------------------------
@app.post("/forgot-password", response_class=HTMLResponse)
def forgot_password_submit(
    request: Request,
    email: str = Form(...),
    action: str = Form("request"),
    code: Optional[str] = Form(None),
    new_password: Optional[str] = Form(None),
    confirm_password: Optional[str] = Form(None),
    db: Session = Depends(get_db),
):
    def _render(stage: str, *, error: Optional[str], success: Optional[str], email_value: str):
        return templates.TemplateResponse(
            "forgot_password.html",
            {
                "request": request,
                "error": error,
                "success": success,
                "stage": stage,
                "email": email_value,
            },
        )

    def _hash_code(raw_code: str) -> str:
        secret = (os.getenv("RESET_CODE_SECRET") or "").strip() or _session_secret
        h = hashlib.sha256()
        h.update((secret + ":" + raw_code.strip()).encode("utf-8"))
        return h.hexdigest()

    def _send_code(to_email: str, reset_code: str) -> Optional[str]:
        smtp_host = (os.getenv("SMTP_HOST") or "").strip()
        smtp_port = int((os.getenv("SMTP_PORT") or "587").strip() or "587")
        smtp_user = (os.getenv("SMTP_USER") or "").strip()
        smtp_password = (os.getenv("SMTP_PASSWORD") or "").strip()
        smtp_from = (os.getenv("SMTP_FROM") or smtp_user).strip()
        # NOTE: We never display OTP on the page. Email must send successfully.
        if not smtp_host or not smtp_user or not smtp_password or not smtp_from:
            return "Email service not configured. Please set real SMTP_* values in .env."

        msg = EmailMessage()
        app_name = (os.getenv("APP_NAME") or "").strip() or "GestureLab"
        msg["Subject"] = f"{app_name} Password Reset Code"
        msg["From"] = smtp_from
        msg["To"] = to_email
        msg.set_content(
            f"Your password reset code is: {reset_code}\n"
            "It expires in 10 minutes.\n"
        )

        try:
            # Match common Gmail setups:
            # - Port 465: implicit TLS via SMTP_SSL
            # - Port 587: STARTTLS
            if smtp_port == 465:
                with smtplib.SMTP_SSL(smtp_host, smtp_port, timeout=15) as server:
                    server.login(smtp_user, smtp_password)
                    server.send_message(msg)
            else:
                with smtplib.SMTP(smtp_host, smtp_port, timeout=15) as server:
                    server.starttls()
                    server.login(smtp_user, smtp_password)
                    server.send_message(msg)
            return None
        except smtplib.SMTPAuthenticationError as e:
            # Most common with Gmail: using normal password instead of App Password, or 2FA not enabled.
            print(f"SMTPAuthenticationError: {e}")
            return "Gmail authentication failed (535). Use a Gmail App Password for this exact SMTP_USER account (no spaces), or use a different email provider/account."
        except smtplib.SMTPConnectError as e:
            print(f"SMTPConnectError: {e}")
            return "Could not connect to SMTP server. Check SMTP_HOST/SMTP_PORT and your internet connection (or set DEV_SHOW_RESET_CODE=1 to test locally)."
        except smtplib.SMTPRecipientsRefused as e:
            print(f"SMTPRecipientsRefused: {e}")
            return "Email address was rejected by the mail server. Check the email you entered."
        except Exception as e:
            print(f"SMTP send failed: {type(e).__name__}: {e}")
            return f"Failed to send email ({type(e).__name__}). Check your SMTP_* settings and try again (or set DEV_SHOW_RESET_CODE=1 to test locally)."

    email = (email or "").strip()
    ok, err = validate_email(email)
    if not ok:
        return _render("request", error=err, success=None, email_value=email)

    # allow both user and admin reset via same flow
    user = db.query(User).filter(User.email == email).first()
    admin = db.query(Admin).filter(Admin.email == email).first()
    if not user and not admin:
        return _render("request", error="Email not found.", success=None, email_value=email)

    action_norm = (action or "request").strip().lower()
    if action_norm in ("request", "resend"):
        reset_code = f"{secrets.randbelow(1_000_000):06d}"
        expires_at = datetime.now(timezone.utc) + timedelta(minutes=10)
        pr = PasswordResetCode(email=email, code_hash=_hash_code(reset_code), expires_at=expires_at)
        db.add(pr)
        db.commit()

        send_err = _send_code(email, reset_code)
        if send_err:
            return _render("request", error=send_err, success=None, email_value=email)

        return _render("verify", error=None, success="Code sent to your email.", email_value=email)

    if action_norm == "verify":
        code_value = (code or "").strip()
        if not code_value:
            return _render("verify", error="Please enter the code.", success=None, email_value=email)
        if not new_password or not confirm_password:
            return _render("verify", error="Please enter and confirm your new password.", success=None, email_value=email)
        okp, errp = validate_password(new_password)
        if not okp:
            return _render("verify", error=errp, success=None, email_value=email)
        if new_password != confirm_password:
            return _render("verify", error="Passwords do not match!", success=None, email_value=email)

        now = datetime.now(timezone.utc)
        latest = (
            db.query(PasswordResetCode)
            .filter(PasswordResetCode.email == email)
            .order_by(PasswordResetCode.created_at.desc())
            .first()
        )
        if not latest or latest.used_at is not None:
            return _render("verify", error="Invalid code. Please request a new one.", success=None, email_value=email)
        if latest.expires_at <= now:
            return _render("verify", error="Code expired. Please request a new one.", success=None, email_value=email)
        if latest.code_hash != _hash_code(code_value):
            return _render("verify", error="Incorrect code.", success=None, email_value=email)

        try:
            if user:
                user.password = hash_password(new_password)
            if admin:
                admin.password = hash_password(new_password)
            latest.used_at = now
            db.commit()
        except Exception:
            db.rollback()
            return _render("verify", error="Could not update password. Please try again.", success=None, email_value=email)

        return _render("request", error=None, success="Password updated successfully. You can now log in.", email_value="")

    return _render("request", error="Invalid request.", success=None, email_value=email)


# -------------------------
# POST Login
# -------------------------
@app.post("/login")
def login_submit(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db)
):
    # Validation: email must contain @
    ok, err = validate_email(email)
    if not ok:
        return _render_login(request, error=err)
    # Admin check (email + password)
    admin = db.query(Admin).first()
    if admin and admin.email and email.strip().lower() == admin.email.strip().lower():
        if not verify_password(password, admin.password):
            return _render_login(request, error="Incorrect password")
        try:
            now = datetime.now(timezone.utc)
            admin.last_login_at = now
            # If the admin email also exists in the user table, mirror it so it shows in the dashboard list.
            shadow_user = db.query(User).filter(User.email == admin.email).first()
            if shadow_user:
                shadow_user.last_login_at = now
            db.commit()
        except Exception:
            db.rollback()
        request.session["admin_id"] = admin.id
        request.session["is_admin"] = True
        return RedirectResponse(url="/dashboard", status_code=303)

    # Normal user check (email + password)
    user = db.query(User).filter(User.email == email).first()
    if not user:
        return _render_login(request, error="User not found")

    if not verify_password(password, user.password):
        return _render_login(request, error="Incorrect password")

    try:
        user.last_login_at = datetime.now(timezone.utc)
        db.commit()
    except Exception:
        db.rollback()

    request.session["user_id"] = user.id
    request.session["is_admin"] = False
    return RedirectResponse(url="/home?login_success=1", status_code=303)


# -------------------------
# POST Update User (Admin)
# -------------------------
@app.post("/update_user")
def update_user_submit(
    request: Request,
    user_id: int = Form(...),
    email: str = Form(...),
    username: str = Form(...),
    search_query: Optional[str] = Form(None),
    db: Session = Depends(get_db),
    _: None = Depends(require_admin),
):
    """
    Allow admin to update a user's email and username.
    """
    def get_users_for_dashboard(db_session, q=None):
        users_query = db_session.query(User)
        if q and str(q).strip():
            term = f"%{q.strip()}%"
            users_query = users_query.filter(
                or_(User.username.ilike(term), User.email.ilike(term))
            )
        return users_query.all()

    # Validation: username max 15, email must contain @
    admin_name = "Admin"
    aid = request.session.get("admin_id")
    if aid:
        adm = db.query(Admin).filter(Admin.id == aid).first()
        if adm and adm.full_name:
            admin_name = adm.full_name
    ok, err = validate_username(username)
    if not ok:
        users = get_users_for_dashboard(db, search_query)
        return templates.TemplateResponse(
            "dashboard.html",
            {
                "request": request,
                "users": users,
                "user_count": len(users),
                "lesson_count": db.query(Lesson).count(),
                "quiz_count": db.query(Quiz).count(),
                "quiz_attempts_count": db.query(QuizResult).count(),
                "user_error": err,
                "admin_name": admin_name,
                "search_query": search_query.strip() if search_query and search_query.strip() else None,
            },
        )
    ok, err = validate_email(email)
    if not ok:
        users = get_users_for_dashboard(db, search_query)
        return templates.TemplateResponse(
            "dashboard.html",
            {
                "request": request,
                "users": users,
                "user_count": len(users),
                "lesson_count": db.query(Lesson).count(),
                "quiz_count": db.query(Quiz).count(),
                "quiz_attempts_count": db.query(QuizResult).count(),
                "user_error": err,
                "admin_name": admin_name,
                "search_query": search_query.strip() if search_query and search_query.strip() else None,
            },
        )
    # Check if the new email/username is already used by another user
    existing = (
        db.query(User)
        .filter(
            or_(User.email == email, User.username == username),
            User.id != user_id,
        )
        .first()
    )

    if existing:
        users = get_users_for_dashboard(db, search_query)
        user_count = len(users)
        lesson_count = db.query(Lesson).count()
        quiz_count = db.query(Quiz).count()
        return templates.TemplateResponse(
            "dashboard.html",
            {
                "request": request,
                "users": users,
                "user_count": user_count,
                "lesson_count": lesson_count,
                "quiz_count": quiz_count,
                "quiz_attempts_count": db.query(QuizResult).count(),
                "user_error": "Email or username is already in use by another account.",
                "admin_name": admin_name,
                "search_query": search_query.strip() if search_query and search_query.strip() else None,
            },
        )

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        redirect_url = "/dashboard"
        if search_query and str(search_query).strip():
            redirect_url = f"/dashboard?q={quote(search_query.strip())}"
        return RedirectResponse(url=redirect_url, status_code=303)

    user.email = email
    user.username = username
    db.commit()

    redirect_url = "/dashboard"
    if search_query and str(search_query).strip():
        redirect_url = f"/dashboard?q={quote(search_query.strip())}"
    return RedirectResponse(url=redirect_url, status_code=303)


# -------------------------
# POST Delete User (Admin)
# -------------------------
@app.post("/delete_user")
def delete_user_submit(
    request: Request,
    user_id: int = Form(...),
    search_query: Optional[str] = Form(None),
    db: Session = Depends(get_db),
    _: None = Depends(require_admin),
):
    """
    Allow admin to delete a user account.
    Prevents deletion of the hard-coded admin (Rose).
    """
    user = db.query(User).filter(User.id == user_id).first()
    if user:
        # Don't allow deleting if username/email matches admin
        admin = db.query(Admin).first()
        if admin:
            if not (user.username == admin.username or user.email == admin.email):
                db.delete(user)
                db.commit()
        else:
            db.delete(user)
            db.commit()

    redirect_url = "/dashboard?delete_success=user"
    if search_query and str(search_query).strip():
        redirect_url = f"/dashboard?q={quote(search_query.strip())}&delete_success=user"
    return RedirectResponse(url=redirect_url, status_code=303)

# -------------------------
# POST Add Lesson
# -------------------------
@app.post("/add_lessons")
async def add_lesson_submit(
    request: Request,
    sign_level: str = Form(...),
    name: str = Form(...),
    image: UploadFile = File(...),
    heading: str = Form(...),
    description: str = Form(...),
    db: Session = Depends(get_db),
    _: None = Depends(require_admin),
):
    try:
        image_path = await save_uploaded_file(image)
    except ValueError as e:
        return RedirectResponse(
            url=f"/add_lessons?error={quote(str(e))}", status_code=303
        )

    lesson = Lesson(
        sign_level=sign_level,
        name=name,
        image=image_path,
        heading=heading,
        description=description
    )
    db.add(lesson)
    db.commit()
    db.refresh(lesson)

    create_notification_for_all_users(
        db=db,
        title="New Lesson Added",
        message=f"A new {sign_level} lesson '{name}' has been added to Gesture Lab!",
        notification_type="lesson",
        related_id=lesson.id
    )

    return RedirectResponse(url="/add_lessons?success=lesson_added", status_code=303)

# -------------------------
# POST Save Quiz Result
# -------------------------
@app.post("/api/quiz_result")
def save_quiz_result(
    request: Request,
    quiz_id: Optional[int] = Form(None),
    quiz_level: Optional[str] = Form(None),
    score: int = Form(...),
    total_questions: int = Form(...),
    db: Session = Depends(get_db)
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
        total_questions=total_questions
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

# -------------------------
# GET User Stats for Dashboard
# -------------------------
@app.get("/api/user_stats")
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


# -------------------------
# GET Certificate PDF Download
# -------------------------
@app.post("/api/predict-sign")
async def predict_sign(frame: UploadFile = File(..., alias="frame"), target: Optional[str] = Form(None)):
    """
    Accept a single image (webcam frame), run the sign language CNN, return predicted letter and confidence.
    Expects multipart form with field 'frame' containing an image file (e.g. image/jpeg, image/png).
    """
    if not frame.content_type or not frame.content_type.startswith("image/"):
        return {"letter": None, "confidence": 0.0, "error": "Invalid image type"}
    try:
        data = await frame.read()
    except Exception as e:
        return {"letter": None, "confidence": 0.0, "error": str(e)}
    if len(data) > MAX_IMAGE_SIZE_BYTES:
        return {"letter": None, "confidence": 0.0, "error": "Image too large (max 5 MB)"}
    if not data:
        return {"letter": None, "confidence": 0.0, "error": "Empty image"}
    try:
        from io import BytesIO
        from PIL import Image
        img = Image.open(BytesIO(data)).copy()
    except Exception as e:
        return {"letter": None, "confidence": 0.0, "error": f"Image open failed: {e}"}
    labels, probs = sign_model.predict_proba(img)
    if labels is None or probs is None:
        err = sign_model.get_load_error()
        return {"letter": None, "confidence": 0.0, "error": err or "Prediction failed"}

    idx = int(probs.argmax()) if probs.size else 0
    letter = labels[idx] if idx < len(labels) else None
    confidence = float(probs[idx]) if probs.size and idx < probs.size else 0.0

    target_conf = None
    target_label = None
    if target:
        raw_target = target.strip()
        # Extract the LAST A-Z letter from whatever lesson.name contains
        # e.g. "B", "Letter B", "B - Basics" -> "B"
        import re
        letters = re.findall(r"[A-Za-z]", raw_target)
        target_label = letters[-1].upper() if letters else raw_target.upper()

        lookup = {str(l).strip().upper(): i for i, l in enumerate(labels)}
        ti = lookup.get(target_label)
        if ti is not None and ti < probs.size:
            target_conf = float(probs[ti])

    return {
        "letter": letter,
        "confidence": round(confidence, 4),
        "target": target_label,
        "target_confidence": round(target_conf, 4) if target_conf is not None else None,
    }


@app.get("/api/certificate/{level}/download")
def download_certificate(
    level: str,
    request: Request,
    db: Session = Depends(get_db),
):
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


# -------------------------
# GET All Quiz Results (User)
# -------------------------
@app.get("/quiz_results", response_class=HTMLResponse)
def quiz_results_page(request: Request, db: Session = Depends(get_db)):
    """
    Show a table of all quiz results for the logged-in user.
    """
    user_id = request.session.get("user_id")
    if not user_id:
        # If not logged in, send to login page
        return RedirectResponse(url="/login", status_code=303)

    results = (
        db.query(QuizResult)
        .filter(QuizResult.user_id == user_id)
        .order_by(QuizResult.taken_at.desc())
        .all()
    )

    return templates.TemplateResponse(
        "quiz_results.html",
        {
            "request": request,
            "results": results,
        },
    )

# -------------------------
# POST Update Lesson
# -------------------------
@app.post("/update_lesson")
async def update_lesson_submit(
    request: Request,
    lesson_id: int = Form(...),
    sign_level: str = Form(...),
    name: str = Form(...),
    image: Optional[UploadFile] = File(None),
    existing_image: Optional[str] = Form(None),
    heading: str = Form(...),
    description: str = Form(...),
    db: Session = Depends(get_db),
    _: None = Depends(require_admin),
):
    # Find lesson by ID
    lesson = db.query(Lesson).filter(Lesson.id == lesson_id).first()
    if not lesson:
        return RedirectResponse(url="/add_lessons", status_code=303)
    
    # Update lesson fields
    lesson.sign_level = sign_level
    lesson.name = name
    lesson.heading = heading
    lesson.description = description
    
    if image and image.filename:
        try:
            image_path = await save_uploaded_file(image)
            lesson.image = image_path
        except ValueError as e:
            return RedirectResponse(
                url=f"/add_lessons?error={quote(str(e))}", status_code=303
            )
    elif existing_image:
        lesson.image = existing_image

    db.commit()

    create_notification_for_all_users(
        db=db,
        title="Lesson Updated",
        message=f"The lesson '{name}' has been updated!",
        notification_type="update",
        related_id=lesson.id
    )

    return RedirectResponse(url="/add_lessons?success=lesson_updated", status_code=303)

# -------------------------
# POST Delete Lesson
# -------------------------
@app.post("/delete_lesson")
def delete_lesson_submit(
    request: Request,
    lesson_id: int = Form(...),
    db: Session = Depends(get_db),
    _: None = Depends(require_admin),
):
    # Find and delete lesson
    lesson = db.query(Lesson).filter(Lesson.id == lesson_id).first()
    if lesson:
        db.delete(lesson)
        db.commit()
    
    return RedirectResponse(url="/add_lessons?delete_success=lesson", status_code=303)


# -------------------------
# POST Add Quiz
# -------------------------
@app.post("/add_quiz")
async def add_quiz_submit(
    request: Request,
    level: str = Form(...),
    # Question text/image are optional
    question_text: Optional[str] = Form(None),
    question_image: Optional[UploadFile] = File(None),
    option1_text: Optional[str] = Form(None),
    option2_text: Optional[str] = Form(None),
    option3_text: Optional[str] = Form(None),
    option4_text: Optional[str] = Form(None),
    option1_image: Optional[UploadFile] = File(None),
    option2_image: Optional[UploadFile] = File(None),
    option3_image: Optional[UploadFile] = File(None),
    option4_image: Optional[UploadFile] = File(None),
    correct_option: int = Form(...),
    db: Session = Depends(get_db),
    _: None = Depends(require_admin),
):
    if correct_option not in (1, 2, 3, 4):
        return RedirectResponse(
            url=f"/add_quizzes?error={quote('Correct option must be 1, 2, 3, or 4.')}", status_code=303
        )
    try:
        question_image_path = await save_uploaded_file(question_image) if question_image and question_image.filename else None
        opt1_img_path = await save_uploaded_file(option1_image) if option1_image and option1_image.filename else None
        opt2_img_path = await save_uploaded_file(option2_image) if option2_image and option2_image.filename else None
        opt3_img_path = await save_uploaded_file(option3_image) if option3_image and option3_image.filename else None
        opt4_img_path = await save_uploaded_file(option4_image) if option4_image and option4_image.filename else None
    except ValueError as e:
        return RedirectResponse(
            url=f"/add_quizzes?error={quote(str(e))}", status_code=303
        )

    quiz = Quiz(
        level=level,
        # Store empty string as None for question_text to align with nullable column
        question_text=question_text if question_text else None,
        question_image=question_image_path,
        option1_text=option1_text,
        option2_text=option2_text,
        option3_text=option3_text,
        option4_text=option4_text,
        option1_image=opt1_img_path,
        option2_image=opt2_img_path,
        option3_image=opt3_img_path,
        option4_image=opt4_img_path,
        correct_option=correct_option,
    )
    db.add(quiz)
    db.commit()
    db.refresh(quiz)
    
    create_notification_for_all_users(
        db=db,
        title="New Quiz Added",
        message=f"A new {level} level quiz has been added to Gesture Lab!",
        notification_type="quiz",
        related_id=quiz.id
    )

    return RedirectResponse(url="/add_quizzes?success=quiz_added", status_code=303)


# -------------------------
# POST Update Quiz
# -------------------------
@app.post("/update_quiz")
async def update_quiz_submit(
    request: Request,
    quiz_id: int = Form(...),
    level: str = Form(...),
    # Question text/image are optional
    question_text: Optional[str] = Form(None),
    question_image: Optional[UploadFile] = File(None),
    existing_question_image: Optional[str] = Form(None),
    option1_text: Optional[str] = Form(None),
    option2_text: Optional[str] = Form(None),
    option3_text: Optional[str] = Form(None),
    option4_text: Optional[str] = Form(None),
    option1_image: Optional[UploadFile] = File(None),
    option2_image: Optional[UploadFile] = File(None),
    option3_image: Optional[UploadFile] = File(None),
    option4_image: Optional[UploadFile] = File(None),
    existing_option1_image: Optional[str] = Form(None),
    existing_option2_image: Optional[str] = Form(None),
    existing_option3_image: Optional[str] = Form(None),
    existing_option4_image: Optional[str] = Form(None),
    correct_option: int = Form(...),
    db: Session = Depends(get_db),
    _: None = Depends(require_admin),
):
    if correct_option not in (1, 2, 3, 4):
        return RedirectResponse(
            url=f"/add_quizzes?error={quote('Correct option must be 1, 2, 3, or 4.')}", status_code=303
        )
    quiz = db.query(Quiz).filter(Quiz.id == quiz_id).first()
    if not quiz:
        return RedirectResponse(url="/add_quizzes", status_code=303)

    quiz.level = level
    quiz.question_text = question_text if question_text else None

    try:
        if question_image and question_image.filename:
            quiz.question_image = await save_uploaded_file(question_image)
        else:
            quiz.question_image = existing_question_image

        quiz.option1_text = option1_text
        quiz.option2_text = option2_text
        quiz.option3_text = option3_text
        quiz.option4_text = option4_text

        if option1_image and option1_image.filename:
            quiz.option1_image = await save_uploaded_file(option1_image)
        else:
            quiz.option1_image = existing_option1_image

        if option2_image and option2_image.filename:
            quiz.option2_image = await save_uploaded_file(option2_image)
        else:
            quiz.option2_image = existing_option2_image

        if option3_image and option3_image.filename:
            quiz.option3_image = await save_uploaded_file(option3_image)
        else:
            quiz.option3_image = existing_option3_image

        if option4_image and option4_image.filename:
            quiz.option4_image = await save_uploaded_file(option4_image)
        else:
            quiz.option4_image = existing_option4_image
    except ValueError as e:
        return RedirectResponse(
            url=f"/add_quizzes?error={quote(str(e))}", status_code=303
        )

    quiz.correct_option = correct_option

    db.commit()

    create_notification_for_all_users(
        db=db,
        title="Quiz Updated",
        message=f"A {level} level quiz has been updated!",
        notification_type="update",
        related_id=quiz.id
    )

    return RedirectResponse(url="/add_quizzes?success=quiz_updated", status_code=303)


# -------------------------
# POST Delete Quiz
# -------------------------
@app.post("/delete_quiz")
def delete_quiz_submit(
    request: Request,
    quiz_id: int = Form(...),
    db: Session = Depends(get_db),
    _: None = Depends(require_admin),
):
    quiz = db.query(Quiz).filter(Quiz.id == quiz_id).first()
    if quiz:
        db.delete(quiz)
        db.commit()

    return RedirectResponse(url="/add_quizzes?delete_success=quiz", status_code=303)


# -------------------------
# POST Update Admin Profile
# -------------------------
@app.post("/update_admin_profile")
def update_admin_profile_submit(
    request: Request,
    full_name: str = Form(...),
    username: str = Form(...),
    email: str = Form(...),
    new_password: Optional[str] = Form(None),
    confirm_password: Optional[str] = Form(None),
    db: Session = Depends(get_db),
    _: None = Depends(require_admin),
):
    """
    Allow admin to update their profile information.
    """
    # Get the admin account (there should only be one)
    admin = db.query(Admin).first()
    if not admin:
        # If no admin exists, create default one
        init_admin()
        admin = db.query(Admin).first()
    
    # Validation: username max 15, email must contain @
    ok, err = validate_username(username)
    if not ok:
        return templates.TemplateResponse(
            "admin_profile.html",
            {"request": request, "admin": admin, "error": err, "success": None},
        )
    ok, err = validate_email(email)
    if not ok:
        return templates.TemplateResponse(
            "admin_profile.html",
            {"request": request, "admin": admin, "error": err, "success": None},
        )
    # Only check for conflict when admin is changing username or email; allow keeping current
    if username != admin.username or email != admin.email:
        existing_user = db.query(User).filter(
            or_(User.username == username, User.email == email)
        ).first()
        if existing_user:
            return templates.TemplateResponse(
                "admin_profile.html",
                {
                    "request": request,
                    "admin": admin,
                    "error": "Username or email is already in use by another account.",
                    "success": None,
                },
            )

    # Validate password if provided (must contain at least one of #, @, $)
    if new_password:
        if new_password != confirm_password:
            return templates.TemplateResponse(
                "admin_profile.html",
                {
                    "request": request,
                    "admin": admin,
                    "error": "Passwords do not match!",
                    "success": None,
                },
            )
        ok, err = validate_password(new_password)
        if not ok:
            return templates.TemplateResponse(
                "admin_profile.html",
                {
                    "request": request,
                    "admin": admin,
                    "error": err,
                    "success": None,
                },
            )

    # If nothing actually changed and no new password, show a different message
    if (
        full_name == admin.full_name
        and username == admin.username
        and email == admin.email
        and not new_password
    ):
        return templates.TemplateResponse(
            "admin_profile.html",
            {
                "request": request,
                "admin": admin,
                "error": None,
                "success": "No changes made. Your profile is already up to date.",
            },
        )
    
    # Update admin fields
    admin.full_name = full_name
    admin.username = username
    admin.email = email
    
    # Only update password if a new one was provided
    if new_password:
        admin.password = hash_password(new_password)
    
    db.commit()
    
    return templates.TemplateResponse(
        "admin_profile.html",
        {
            "request": request,
            "admin": admin,
            "error": None,
            "success": "Profile updated successfully!",
        },
    )


# -------------------------
# POST Update User Profile
# -------------------------
@app.post("/update_user_profile")
def update_user_profile_submit(
    request: Request,
    username: str = Form(...),
    email: str = Form(...),
    new_password: Optional[str] = Form(None),
    confirm_password: Optional[str] = Form(None),
    db: Session = Depends(get_db),
):
    """
    Allow user to update their profile information.
    """
    user_id = request.session.get("user_id")
    if not user_id:
        return RedirectResponse(url="/login", status_code=303)
    
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        return RedirectResponse(url="/login", status_code=303)
    
    # Validation: username max 15, email must contain @
    ok, err = validate_username(username)
    if not ok:
        return templates.TemplateResponse(
            "profile.html",
            {"request": request, "user": user, "error": err, "success": None},
        )
    ok, err = validate_email(email)
    if not ok:
        return templates.TemplateResponse(
            "profile.html",
            {"request": request, "user": user, "error": err, "success": None},
        )
    # Check if new username or email conflicts with another user
    existing_user = db.query(User).filter(
        or_(User.username == username, User.email == email),
        User.id != user_id
    ).first()
    if existing_user:
        return templates.TemplateResponse(
            "profile.html",
            {
                "request": request,
                "user": user,
                "error": "Username or email is already in use by another account.",
                "success": None,
            },
        )
    
    # Check if username/email conflicts with admin
    admin = db.query(Admin).first()
    if admin:
        if username.lower() == admin.username.lower() or email.lower() == admin.email.lower():
            return templates.TemplateResponse(
                "profile.html",
                {
                    "request": request,
                    "user": user,
                    "error": "This username or email is reserved.",
                    "success": None,
                },
            )
    
    # Validate password if provided (must contain at least one of #, @, $)
    if new_password:
        if new_password != confirm_password:
            return templates.TemplateResponse(
                "profile.html",
                {
                    "request": request,
                    "user": user,
                    "error": "Passwords do not match!",
                    "success": None,
                },
            )
        ok, err = validate_password(new_password)
        if not ok:
            return templates.TemplateResponse(
                "profile.html",
                {
                    "request": request,
                    "user": user,
                    "error": err,
                    "success": None,
                },
            )

    # If nothing changed and no new password, show no-changes message
    if (
        user.username == username
        and user.email == email
        and not new_password
    ):
        return templates.TemplateResponse(
            "profile.html",
            {
                "request": request,
                "user": user,
                "error": None,
                "success": "No changes made. Your profile is already up to date.",
            },
        )

    # Update user fields
    user.username = username
    user.email = email
    
    # Only update password if a new one was provided
    if new_password:
        user.password = hash_password(new_password)
    
    db.commit()
    
    return templates.TemplateResponse(
        "profile.html",
        {
            "request": request,
            "user": user,
            "error": None,
            "success": "Profile updated successfully!",
        },
    )
