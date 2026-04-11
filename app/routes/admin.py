from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import desc, or_
from sqlalchemy.orm import Session
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import quote

from ..authentication import validate_email, validate_password, validate_username, hash_password
from ..config.runtime import templates
from ..models import (
    Admin,
    ContactSubmission,
    Lesson,
    Notification,
    Quiz,
    QuizResult,
    User,
)
from ..services.certificates import get_certificates_earned
from ..services.notifications import (
    create_notification_for_all_users,
    create_notification_for_user,
    is_user_also_admin,
)
from ..services.startup import init_admin
from ..services.streaks import compute_streak, get_activity_dates
from ..utils.deps import get_db, require_admin
from ..utils.uploads import save_uploaded_file

router = APIRouter()


def _performance_url_for_user(user_id: int, search_query: Optional[str]) -> str:
    base = f"/dashboard/user/{user_id}/performance"
    if search_query and str(search_query).strip():
        return f"{base}?return_q={quote(search_query.strip())}"
    return base


def _build_dashboard_user_rows(
    db: Session,
    q: Optional[str],
    admin_id: Optional[int],
) -> Tuple[List[Dict[str, Any]], int, str, Optional[str]]:
    """
    Rows for dashboard.html (includes performance_url for each learner).
    user_count is the number of User rows matching the search filter (not counting the synthetic admin row).
    """
    admin_name = "Admin"
    admin_email = None
    admin_last_login_at = None
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

    user_rows: List[Dict[str, Any]] = []
    sq = q.strip() if q and q.strip() else None
    if admin_email:
        if (
            not q
            or not q.strip()
            or (admin_email and q.strip().lower() in admin_email.lower())
            or (admin_name and q.strip().lower() in admin_name.lower())
        ):
            user_rows.append(
                {
                    "id": None,
                    "email": admin_email,
                    "username": admin_name,
                    "role": "Admin",
                    "last_login_at": admin_last_login_at,
                    "is_admin": True,
                    "performance_url": None,
                }
            )

    for u in users:
        if admin_email and u.email and u.email.strip().lower() == admin_email.strip().lower():
            continue
        user_rows.append(
            {
                "id": u.id,
                "email": u.email,
                "username": u.username,
                "role": "User",
                "last_login_at": getattr(u, "last_login_at", None),
                "is_admin": False,
                "performance_url": _performance_url_for_user(u.id, sq),
            }
        )

    user_count = len(users)
    return user_rows, user_count, admin_name, admin_email


def _aggregate_user_performance(
    db: Session, user_id: int
) -> Tuple[List[QuizResult], int, int, int, int, List[str], List[Dict[str, Any]]]:
    """Quiz results (newest first), quizzes_taken, total_points, badges, streak, certificates, per-level rows."""
    results = (
        db.query(QuizResult)
        .filter(QuizResult.user_id == user_id)
        .order_by(desc(QuizResult.taken_at))
        .all()
    )
    quizzes_taken = len(results)
    total_points = sum(r.score for r in results)
    badges = total_points // 20
    activity_dates = get_activity_dates(user_id, db)
    reference = max(activity_dates) if activity_dates else None
    today_utc = datetime.now(timezone.utc).date()
    if reference is None or (today_utc - reference) >= timedelta(days=3):
        current_streak = 0
    else:
        current_streak = compute_streak(activity_dates, reference)
    certificates = get_certificates_earned(db, user_id)

    by_level: Dict[str, Dict[str, Any]] = {}
    for r in results:
        lv = (r.quiz_level or "—").strip() or "—"
        den = r.total_questions or 1
        ratio = r.score / den
        if lv not in by_level:
            by_level[lv] = {
                "level": lv,
                "attempts": 0,
                "best_score": r.score,
                "best_total": r.total_questions or 0,
                "best_ratio": ratio,
                "last_at": r.taken_at,
            }
        row = by_level[lv]
        row["attempts"] += 1
        if r.taken_at and (row["last_at"] is None or r.taken_at > row["last_at"]):
            row["last_at"] = r.taken_at
        if ratio > row["best_ratio"] or (
            ratio == row["best_ratio"] and r.score > row["best_score"]
        ):
            row["best_score"] = r.score
            row["best_total"] = r.total_questions or 0
            row["best_ratio"] = ratio

    level_rows = sorted(by_level.values(), key=lambda x: x["level"].lower())
    return results, quizzes_taken, total_points, badges, current_streak, certificates, level_rows


@router.get("/add_quizzes", response_class=HTMLResponse)
def quizzes_page(request: Request, db: Session = Depends(get_db), _: None = Depends(require_admin)):
    """Admin view to add/edit quizzes."""
    quizzes = db.query(Quiz).all()
    quiz_counts = {}
    for q in quizzes:
        quiz_counts[q.level] = quiz_counts.get(q.level, 0) + 1
    error = request.query_params.get("error")
    return templates.TemplateResponse(
        request,
        "add_quizzes.html",
        {"request": request, "quizzes": quizzes, "quiz_counts": quiz_counts, "error": error},
    )


@router.get("/dashboard", response_class=HTMLResponse)
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
    admin_id = request.session.get("admin_id")
    user_rows, user_count, admin_name, admin_email = _build_dashboard_user_rows(db, q, admin_id)
    lesson_count = db.query(Lesson).count()
    quiz_count = db.query(Quiz).count()
    quiz_attempts_count = db.query(QuizResult).count()

    return templates.TemplateResponse(
        request,
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


@router.get("/dashboard/user/{user_id}/performance", response_class=HTMLResponse)
def user_performance_page(
    request: Request,
    user_id: int,
    return_q: Optional[str] = None,
    db: Session = Depends(get_db),
    _: None = Depends(require_admin),
):
    """Admin view of a learner's quiz performance (same metrics as user profile stats)."""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        return RedirectResponse(url="/dashboard", status_code=303)

    dashboard_back = "/dashboard"
    if return_q and return_q.strip():
        dashboard_back = f"/dashboard?q={quote(return_q.strip())}"

    (
        results,
        quizzes_taken,
        total_points,
        badges,
        current_streak,
        certificates,
        level_rows,
    ) = _aggregate_user_performance(db, user_id)

    admin_name = "Admin"
    aid = request.session.get("admin_id")
    if aid:
        adm = db.query(Admin).filter(Admin.id == aid).first()
        if adm and adm.full_name:
            admin_name = adm.full_name

    recent_limit = 6
    recent = results[:recent_limit]

    return templates.TemplateResponse(
        request,
        "admin_user_performance.html",
        {
            "request": request,
            "admin_name": admin_name,
            "target_user": user,
            "dashboard_back_url": dashboard_back,
            "quizzes_taken": quizzes_taken,
            "total_points": total_points,
            "badges": badges,
            "current_streak": current_streak,
            "certificates": certificates,
            "level_rows": level_rows,
            "recent_results": recent,
            "recent_results_limit": recent_limit,
        },
    )


@router.get("/send_notifications", response_class=HTMLResponse)
def send_notifications_page(
    request: Request, db: Session = Depends(get_db), _: None = Depends(require_admin)
):
    """Admin page to send custom notifications to all users."""
    return templates.TemplateResponse(request, "send_notifications.html", {"request": request})


@router.get("/contact_messages", response_class=HTMLResponse)
def contact_messages_page(
    request: Request, db: Session = Depends(get_db), _: None = Depends(require_admin)
):
    """Admin page to view contact form submissions from the Contact Us page."""
    submissions = db.query(ContactSubmission).order_by(ContactSubmission.created_at.desc()).all()
    admin_name = "Admin"
    admin_id = request.session.get("admin_id")
    if admin_id:
        admin = db.query(Admin).filter(Admin.id == admin_id).first()
        if admin and admin.full_name:
            admin_name = admin.full_name
    qp = request.query_params
    return templates.TemplateResponse(
        request,
        "contact_messages.html",
        {
            "request": request,
            "submissions": submissions,
            "admin_name": admin_name,
            "flash_success": qp.get("success") == "1",
            "flash_notified": qp.get("notified") == "1",
            "flash_error": qp.get("error"),
        },
    )


@router.post("/contact_messages/reply")
def contact_message_reply(
    request: Request,
    submission_id: int = Form(...),
    reply: str = Form(...),
    db: Session = Depends(get_db),
    _: None = Depends(require_admin),
):
    """Save admin reply and notify the submitting user in-app if they have a registered account."""
    body = (reply or "").strip()
    if not body or len(body) > 4000:
        return RedirectResponse(url="/contact_messages?error=invalid", status_code=303)
    sub = db.query(ContactSubmission).filter(ContactSubmission.id == submission_id).first()
    if not sub:
        return RedirectResponse(url="/contact_messages?error=notfound", status_code=303)
    if sub.admin_reply:
        return RedirectResponse(url="/contact_messages?error=already_replied", status_code=303)

    sub.admin_reply = body
    sub.replied_at = datetime.now(timezone.utc)
    db.commit()

    user = db.query(User).filter(User.email.ilike(sub.email.strip())).first()
    notified = False
    if user and not is_user_also_admin(user.id, db):
        title = f"Re: {sub.subject}"[:200]
        create_notification_for_user(
            db=db,
            user_id=user.id,
            title=title,
            message=body,
            notification_type="contact_reply",
            related_id=sub.id,
            is_admin_created=True,
        )
        notified = True

    q = "success=1"
    if notified:
        q += "&notified=1"
    return RedirectResponse(url=f"/contact_messages?{q}", status_code=303)


@router.post("/send_custom_notification")
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
        if len(title) > 50:
            return {"status": "error", "detail": "Title must be 50 characters or less"}
        if len(message) > 200:
            return {"status": "error", "detail": "Message must be 200 characters or less"}
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


@router.get("/admin/recent_notifications")
def get_admin_recent_notifications(
    db: Session = Depends(get_db), _: None = Depends(require_admin)
):
    """Get recent notifications added by admin only (sent from Notifications page), within last 30 days."""

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


@router.get("/admin_profile", response_class=HTMLResponse)
def admin_profile_page(
    request: Request, db: Session = Depends(get_db), _: None = Depends(require_admin)
):
    """Admin profile page with current admin data."""
    admin = db.query(Admin).first()
    if not admin:
        init_admin()
        admin = db.query(Admin).first()

    return templates.TemplateResponse(
        request,
        "admin_profile.html",
        {
            "request": request,
            "admin": admin,
            "error": None,
            "success": None,
            "form_full_name": None,
            "form_username": None,
            "form_email": None,
        },
    )


@router.get("/add_lessons", response_class=HTMLResponse)
def add_lessons_page(
    request: Request, db: Session = Depends(get_db), _: None = Depends(require_admin)
):
    lessons = db.query(Lesson).all()
    error = request.query_params.get("error")
    return templates.TemplateResponse(
        request,
        "add_lessons.html", {"request": request, "lessons": lessons, "error": error}
    )


@router.post("/update_user")
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

    aid = request.session.get("admin_id")
    admin_name = "Admin"
    if aid:
        adm = db.query(Admin).filter(Admin.id == aid).first()
        if adm and adm.full_name:
            admin_name = adm.full_name

    sq = search_query.strip() if search_query and str(search_query).strip() else None

    def _dashboard_error_response(err_msg: str):
        user_rows, user_count, _, admin_email = _build_dashboard_user_rows(db, sq, aid)
        return templates.TemplateResponse(
            request,
            "dashboard.html",
            {
                "request": request,
                "users": user_rows,
                "user_count": user_count,
                "lesson_count": db.query(Lesson).count(),
                "quiz_count": db.query(Quiz).count(),
                "quiz_attempts_count": db.query(QuizResult).count(),
                "user_error": err_msg,
                "admin_name": admin_name,
                "admin_email": admin_email,
                "search_query": sq,
            },
        )

    ok, err = validate_username(username)
    if not ok:
        return _dashboard_error_response(err)
    ok, err = validate_email(email)
    if not ok:
        return _dashboard_error_response(err)
    existing = (
        db.query(User)
        .filter(
            or_(User.email == email, User.username == username),
            User.id != user_id,
        )
        .first()
    )

    if existing:
        user_rows, user_count, _, admin_email = _build_dashboard_user_rows(db, sq, aid)
        lesson_count = db.query(Lesson).count()
        quiz_count = db.query(Quiz).count()
        return templates.TemplateResponse(
            request,
            "dashboard.html",
            {
                "request": request,
                "users": user_rows,
                "user_count": user_count,
                "lesson_count": lesson_count,
                "quiz_count": quiz_count,
                "quiz_attempts_count": db.query(QuizResult).count(),
                "user_error": "Email or username is already in use by another account.",
                "admin_name": admin_name,
                "admin_email": admin_email,
                "search_query": sq,
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


# NOTE: Remaining admin POST routes (`/delete_user`, lesson/quiz CRUD, admin/user profile updates)
# are moved as-is below (structural refactor only).


@router.post("/delete_user")
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


@router.post("/add_lessons")
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
    if not sign_level or not sign_level.strip():
        return RedirectResponse(url=f"/add_lessons?error={quote('Please select a sign level.')}", status_code=303)
    if not name or not name.strip():
        return RedirectResponse(url=f"/add_lessons?error={quote('Please enter a name.')}", status_code=303)
    if not heading or not heading.strip():
        return RedirectResponse(url=f"/add_lessons?error={quote('Please enter a heading.')}", status_code=303)
    if not description or not description.strip():
        return RedirectResponse(url=f"/add_lessons?error={quote('Please enter a description.')}", status_code=303)

    try:
        image_path = await save_uploaded_file(image)
    except ValueError as e:
        return RedirectResponse(url=f"/add_lessons?error={quote(str(e))}", status_code=303)

    lesson = Lesson(
        sign_level=sign_level,
        name=name,
        image=image_path,
        heading=heading,
        description=description,
    )
    db.add(lesson)
    db.commit()
    db.refresh(lesson)

    create_notification_for_all_users(
        db=db,
        title="New Lesson Added",
        message=f"A new {sign_level} lesson '{name}' has been added to Gesture Lab!",
        notification_type="lesson",
        related_id=lesson.id,
    )

    return RedirectResponse(url="/add_lessons?success=lesson_added", status_code=303)


@router.post("/update_lesson")
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
            return RedirectResponse(url=f"/add_lessons?error={quote(str(e))}", status_code=303)
    elif existing_image:
        lesson.image = existing_image

    db.commit()

    create_notification_for_all_users(
        db=db,
        title="Lesson Updated",
        message=f"The lesson '{name}' has been updated!",
        notification_type="update",
        related_id=lesson.id,
    )

    return RedirectResponse(url="/add_lessons?success=lesson_updated", status_code=303)


@router.post("/delete_lesson")
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


@router.post("/add_quiz")
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
            url=f"/add_quizzes?error={quote('Correct option must be 1, 2, 3, or 4.')}",
            status_code=303,
        )

    level_count = db.query(Quiz).filter(Quiz.level == level).count()
    if level_count >= 10:
        return RedirectResponse(
            url=f"/add_quizzes?error={quote(f'Maximum 10 quizzes allowed per level. The {level} level already has {level_count} quizzes.')}",
            status_code=303,
        )

    try:
        question_image_path = (
            await save_uploaded_file(question_image)
            if question_image and question_image.filename
            else None
        )
        opt1_img_path = (
            await save_uploaded_file(option1_image)
            if option1_image and option1_image.filename
            else None
        )
        opt2_img_path = (
            await save_uploaded_file(option2_image)
            if option2_image and option2_image.filename
            else None
        )
        opt3_img_path = (
            await save_uploaded_file(option3_image)
            if option3_image and option3_image.filename
            else None
        )
        opt4_img_path = (
            await save_uploaded_file(option4_image)
            if option4_image and option4_image.filename
            else None
        )
    except ValueError as e:
        return RedirectResponse(url=f"/add_quizzes?error={quote(str(e))}", status_code=303)

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
        related_id=quiz.id,
    )

    return RedirectResponse(url="/add_quizzes?success=quiz_added", status_code=303)


@router.post("/update_quiz")
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
            url=f"/add_quizzes?error={quote('Correct option must be 1, 2, 3, or 4.')}",
            status_code=303,
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
        return RedirectResponse(url=f"/add_quizzes?error={quote(str(e))}", status_code=303)

    quiz.correct_option = correct_option

    db.commit()

    create_notification_for_all_users(
        db=db,
        title="Quiz Updated",
        message=f"A {level} level quiz has been updated!",
        notification_type="update",
        related_id=quiz.id,
    )

    return RedirectResponse(url="/add_quizzes?success=quiz_updated", status_code=303)


@router.post("/delete_quiz")
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


@router.post("/update_admin_profile")
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
    admin = db.query(Admin).first()
    if not admin:
        init_admin()
        admin = db.query(Admin).first()

    # Validation: username max 15, email must contain @
    ok, err = validate_username(username)
    if not ok:
        return templates.TemplateResponse(
            request,
            "admin_profile.html",
            {
                "request": request,
                "admin": admin,
                "error": err,
                "success": None,
                "form_full_name": full_name,
                "form_username": username,
                "form_email": email,
            },
        )
    ok, err = validate_email(email)
    if not ok:
        return templates.TemplateResponse(
            request,
            "admin_profile.html",
            {
                "request": request,
                "admin": admin,
                "error": err,
                "success": None,
                "form_full_name": full_name,
                "form_username": username,
                "form_email": email,
            },
        )
    # Only check for conflict when admin is changing username or email; allow keeping current
    if username != admin.username or email != admin.email:
        existing_user = db.query(User).filter(or_(User.username == username, User.email == email)).first()
        if existing_user:
            return templates.TemplateResponse(
                request,
                "admin_profile.html",
                {
                    "request": request,
                    "admin": admin,
                    "error": "Username or email is already in use by another account.",
                    "success": None,
                    "form_full_name": full_name,
                    "form_username": username,
                    "form_email": email,
                },
            )

    # Validate password if provided (must contain at least one of #, @, $)
    if new_password:
        if new_password != confirm_password:
            return templates.TemplateResponse(
                request,
                "admin_profile.html",
                {
                    "request": request,
                    "admin": admin,
                    "error": "Passwords do not match!",
                    "success": None,
                    "form_full_name": full_name,
                    "form_username": username,
                    "form_email": email,
                },
            )
        ok, err = validate_password(new_password)
        if not ok:
            return templates.TemplateResponse(
                request,
                "admin_profile.html",
                {
                    "request": request,
                    "admin": admin,
                    "error": err,
                    "success": None,
                    "form_full_name": full_name,
                    "form_username": username,
                    "form_email": email,
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
            request,
            "admin_profile.html",
            {
                "request": request,
                "admin": admin,
                "error": None,
                "success": "No changes made. Your profile is already up to date.",
                "form_full_name": None,
                "form_username": None,
                "form_email": None,
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
        request,
        "admin_profile.html",
        {
            "request": request,
            "admin": admin,
            "error": None,
            "success": "Profile updated successfully!",
            "form_full_name": None,
            "form_username": None,
            "form_email": None,
        },
    )

