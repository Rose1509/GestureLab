from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session
from sqlalchemy import or_
from typing import Optional
import os
import secrets
import hashlib
import smtplib
from datetime import datetime, timedelta, timezone

from authlib.integrations.starlette_client import OAuthError

from ..authentication import (
    hash_password,
    verify_password,
    validate_email,
    validate_password,
    validate_username,
)
from ..database import SessionLocal
from ..models import Admin, PasswordResetCode, User
from ..utils.deps import get_db
from ..config.runtime import (
    templates,
    oauth,
    GOOGLE_OAUTH_ENABLED,
    _google_settings,
    _render_login,
    _session_secret,
)

router = APIRouter()


@router.get("/login", response_class=HTMLResponse)
def login_form(request: Request):
    logout_success = request.query_params.get("logout_success")
    register_success = request.query_params.get("register_success")
    return templates.TemplateResponse(
        request,
        "login.html",
        {
            "request": request,
            "error": None,
            "logout_success": logout_success,
            "register_success": register_success,
        },
    )


@router.get("/auth/google/login")
async def auth_google_login(request: Request):
    if not GOOGLE_OAUTH_ENABLED:
        return _render_login(
            request,
            error="Google sign-in is not configured. Please set GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET in .env.",
        )

    redirect_uri = (_google_settings.get("redirect_uri") or "").strip()
    if not redirect_uri:
        redirect_uri = str(request.url_for("auth_google_callback"))
    return await oauth.google.authorize_redirect(request, redirect_uri)


async def _auth_google_callback_impl(request: Request):
    if not GOOGLE_OAUTH_ENABLED:
        return _render_login(
            request,
            error="Google sign-in is not configured. Please set GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET in .env.",
        )

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
        userinfo = None
        try:
            userinfo = await oauth.google.parse_id_token(request, token)
        except Exception:
            pass
        if not userinfo:
            resp = await oauth.google.get(
                "https://openidconnect.googleapis.com/v1/userinfo", token=token
            )
            userinfo = resp.json() if resp else None
    except OAuthError as e:
        db.close()
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
            req = getattr(e, "request", None)
            if req is not None:
                try:
                    print(f"[WARN] Google sign-in failing URL: {getattr(req, 'url', None)}")
                except Exception:
                    pass
            try:
                print(
                    f"[WARN] Google OAuth redirect_uri: {_google_settings.get('redirect_uri') or 'auto'}"
                )
            except Exception:
                pass
        except Exception:
            pass
        return _render_login(
            request, error=f"Google sign-in failed ({type(e).__name__}). Please try again."
        )

    if not userinfo:
        db.close()
        return _render_login(request, error="Google sign-in failed (no profile).")

    google_sub = (userinfo.get("sub") or userinfo.get("id") or "").strip()
    email = (userinfo.get("email") or "").strip()
    name = (userinfo.get("name") or "").strip()

    if not email:
        db.close()
        return _render_login(request, error="Google sign-in failed (no email).")

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

    user = None
    if google_sub:
        user = db.query(User).filter(User.google_id == google_sub).first()
    if not user:
        user = db.query(User).filter(User.email == email).first()

    if not user:
        base = (name or email.split("@", 1)[0]).strip() or "user"
        base = base[:25]
        candidate = base
        suffix = 0
        while db.query(User).filter(User.username == candidate).first() is not None:
            suffix += 1
            tail = str(suffix)
            candidate = (base[: max(1, 25 - (len(tail) + 1))] + "_" + tail)[:25]

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
        if google_sub and not getattr(user, "google_id", None):
            user.google_id = google_sub
            try:
                db.commit()
            except Exception:
                db.rollback()

    try:
        user_id = int(user.id)
    except Exception:
        user_id = None

    try:
        user.last_login_at = datetime.now(timezone.utc)
        db.commit()
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
        return _render_login(
            request,
            error="Google sign-in failed (could not load account). Please try again.",
        )

    request.session["user_id"] = user_id
    request.session["is_admin"] = False
    return RedirectResponse(url="/home?login_success=1", status_code=303)


@router.get("/auth/google/callback", name="auth_google_callback")
async def auth_google_callback(request: Request):
    return await _auth_google_callback_impl(request)


@router.get("/auth/google")
async def auth_google_callback_alias(request: Request):
    return await _auth_google_callback_impl(request)


@router.get("/forgot-password", response_class=HTMLResponse)
def forgot_password_form(request: Request):
    return templates.TemplateResponse(
        request,
        "forgot_password.html",
        {"request": request, "error": None, "success": None, "stage": "request", "email": ""},
    )


@router.get("/register", response_class=HTMLResponse)
def register_form(request: Request):
    return templates.TemplateResponse(request, "register.html", {"request": request, "error": None})


@router.get("/logout")
def logout(request: Request):
    """Logout route - clears session and redirects to login."""
    request.session.clear()
    return RedirectResponse(url="/login?logout_success=1", status_code=303)


@router.post("/register")
def register_submit(
    request: Request,
    email: str = Form(...),
    username: str = Form(...),
    password: str = Form(...),
    confirm_password: str = Form(...),
    db: Session = Depends(get_db),
):
    ok, err = validate_username(username)
    if not ok:
        return templates.TemplateResponse(request, "register.html", {"request": request, "error": err})
    ok, err = validate_email(email)
    if not ok:
        return templates.TemplateResponse(request, "register.html", {"request": request, "error": err})
    ok, err = validate_password(password)
    if not ok:
        return templates.TemplateResponse(request, "register.html", {"request": request, "error": err})

    if password != confirm_password:
        return templates.TemplateResponse(
            request,
            "register.html", {"request": request, "error": "Passwords do not match!"}
        )

    admin = db.query(Admin).first()
    if admin:
        if username.lower() == admin.username.lower() or email.lower() == admin.email.lower():
            return templates.TemplateResponse(
                request,
                "register.html", {"request": request, "error": "This username or email is reserved!"}
            )

    existing_user = (
        db.query(User).filter(or_(User.username == username, User.email == email)).first()
    )
    if existing_user:
        return templates.TemplateResponse(
            request,
            "register.html", {"request": request, "error": "Username or email already exists!"}
        )

    user = User(email=email, username=username, password=hash_password(password))
    db.add(user)
    db.commit()

    return RedirectResponse(url="/login?register_success=1", status_code=303)


@router.post("/forgot-password", response_class=HTMLResponse)
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
            request,
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
        dev_show = (os.getenv("DEV_SHOW_RESET_CODE") or "").strip().lower() in (
            "1",
            "true",
            "yes",
            "on",
        )
        if dev_show:
            return None

        sender_email = (os.getenv("EMAIL_ADDRESS") or "").strip()
        app_password = (os.getenv("EMAIL_PASSWORD") or "").strip()

        if not sender_email or not app_password:
            return "Email service not configured. Please set EMAIL_ADDRESS and EMAIL_PASSWORD in .env."

        app_name = (os.getenv("APP_NAME") or "").strip() or "GestureLab"
        subject = f"{app_name} Password Reset Code"
        body = f"Your password reset code is: {reset_code}\nIt expires in 10 minutes.\n"

        from email.mime.text import MIMEText

        msg = MIMEText(body)
        msg["Subject"] = subject
        msg["From"] = sender_email
        msg["To"] = to_email

        try:
            with smtplib.SMTP("smtp.gmail.com", 587, timeout=15) as server:
                server.starttls()
                server.login(sender_email, app_password)
                server.send_message(msg)
            return None
        except smtplib.SMTPAuthenticationError as e:
            print(f"SMTPAuthenticationError: {e}")
            return "Gmail authentication failed. Make sure EMAIL_PASSWORD is a valid Gmail App Password for this account."
        except smtplib.SMTPConnectError as e:
            print(f"SMTPConnectError: {e}")
            return "Could not connect to Gmail SMTP server. Check your internet connection."
        except smtplib.SMTPRecipientsRefused as e:
            print(f"SMTPRecipientsRefused: {e}")
            return "Email address was rejected by the mail server. Check the email you entered."
        except Exception as e:
            print(f"SMTP send failed: {type(e).__name__}: {e}")
            return "Failed to send email. Please try again later."

    email = (email or "").strip()
    ok, err = validate_email(email)
    if not ok:
        return _render("request", error=err, success=None, email_value=email)

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

        dev_show = (os.getenv("DEV_SHOW_RESET_CODE") or "").strip().lower() in (
            "1",
            "true",
            "yes",
            "on",
        )
        success_msg = "Code sent to your email."
        if dev_show:
            success_msg = f"Dev mode: your reset code is {reset_code} (expires in 10 minutes)."

        return _render("verify", error=None, success=success_msg, email_value=email)

    if action_norm == "verify":
        code_value = (code or "").strip()
        if not code_value:
            return _render("verify", error="Please enter the code.", success=None, email_value=email)
        if not new_password or not confirm_password:
            return _render(
                "verify",
                error="Please enter and confirm your new password.",
                success=None,
                email_value=email,
            )
        okp, errp = validate_password(new_password)
        if not okp:
            return _render("verify", error=errp, success=None, email_value=email)
        if new_password != confirm_password:
            return _render(
                "verify", error="Passwords do not match!", success=None, email_value=email
            )

        now = datetime.now(timezone.utc)
        latest = (
            db.query(PasswordResetCode)
            .filter(PasswordResetCode.email == email)
            .order_by(PasswordResetCode.created_at.desc())
            .first()
        )
        if not latest or latest.used_at is not None:
            return _render(
                "verify",
                error="Invalid code. Please request a new one.",
                success=None,
                email_value=email,
            )
        if latest.expires_at <= now:
            return _render(
                "verify",
                error="Code expired. Please request a new one.",
                success=None,
                email_value=email,
            )
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
            return _render(
                "verify",
                error="Could not update password. Please try again.",
                success=None,
                email_value=email,
            )

        return _render(
            "request",
            error=None,
            success="Password updated successfully. You can now log in.",
            email_value="",
        )

    return _render("request", error="Invalid request.", success=None, email_value=email)


@router.post("/login")
def login_submit(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db),
):
    ok, err = validate_email(email)
    if not ok:
        return _render_login(request, error=err)

    admin = db.query(Admin).first()
    if admin and admin.email and email.strip().lower() == admin.email.strip().lower():
        if not verify_password(password, admin.password):
            return _render_login(request, error="Incorrect password")
        try:
            now = datetime.now(timezone.utc)
            admin.last_login_at = now
            shadow_user = db.query(User).filter(User.email == admin.email).first()
            if shadow_user:
                shadow_user.last_login_at = now
            db.commit()
        except Exception:
            db.rollback()
        request.session["admin_id"] = admin.id
        request.session["is_admin"] = True
        return RedirectResponse(url="/dashboard", status_code=303)

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
