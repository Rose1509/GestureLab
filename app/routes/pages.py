from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session
from typing import Optional

from ..config.runtime import templates
from ..models import Lesson, Quiz, QuizResult, User
from ..utils.deps import get_db

router = APIRouter()


@router.get("/", response_class=HTMLResponse)
def landing_page(request: Request):
    return templates.TemplateResponse("landing_page.html", {"request": request})


@router.get("/home", response_class=HTMLResponse)
def home_page(request: Request):
    return templates.TemplateResponse("home.html", {"request": request})


@router.get("/about", response_class=HTMLResponse)
def about_us(request: Request):
    return templates.TemplateResponse("about_us.html", {"request": request})


@router.get("/contact", response_class=HTMLResponse)
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


@router.post("/contact", response_class=HTMLResponse)
def contact_us_submit(
    request: Request,
    name: str = Form(""),
    email: str = Form(""),
    subject: str = Form(""),
    message: str = Form(""),
    db: Session = Depends(get_db),
):
    """Validate contact form and save to DB so admin can see it."""
    from ..authentication import (
        validate_contact_email,
        validate_contact_message,
        validate_contact_name,
        validate_subject_word_count,
    )
    from ..models import ContactSubmission

    ok_name, err_name = validate_contact_name(name)
    if not ok_name:
        return templates.TemplateResponse(
            "contact_us.html",
            {
                "request": request,
                "contact_error": err_name,
                "contact_name": name,
                "contact_email": email,
                "contact_subject": subject,
                "contact_message": message,
            },
        )
    ok_email, err_email = validate_contact_email(email)
    if not ok_email:
        return templates.TemplateResponse(
            "contact_us.html",
            {
                "request": request,
                "contact_error": err_email,
                "contact_name": name,
                "contact_email": email,
                "contact_subject": subject,
                "contact_message": message,
            },
        )
    ok_subject, err_subject = validate_subject_word_count(subject)
    if not ok_subject:
        return templates.TemplateResponse(
            "contact_us.html",
            {
                "request": request,
                "contact_error": err_subject,
                "contact_name": name,
                "contact_email": email,
                "contact_subject": subject,
                "contact_message": message,
            },
        )
    ok_message, err_message = validate_contact_message(message)
    if not ok_message:
        return templates.TemplateResponse(
            "contact_us.html",
            {
                "request": request,
                "contact_error": err_message,
                "contact_name": name,
                "contact_email": email,
                "contact_subject": subject,
                "contact_message": message,
            },
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


@router.get("/practice", response_class=HTMLResponse)
def practice_page(request: Request, lesson_id: Optional[int] = None, db: Session = Depends(get_db)):
    """Practice page; if lesson_id is given, show that lesson's image and instructions."""
    lesson = None
    if lesson_id is not None:
        lesson = db.query(Lesson).filter(Lesson.id == lesson_id).first()
    return templates.TemplateResponse("practice.html", {"request": request, "lesson": lesson})


@router.get("/profile", response_class=HTMLResponse)
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
    beginner_results = [r for r in quiz_results if r.quiz_level == "Beginner"]
    intermediate_results = [r for r in quiz_results if r.quiz_level == "Intermediate"]
    advance_results = [r for r in quiz_results if r.quiz_level == "Advance"]

    total_quizzes = len(quiz_results)
    total_points = sum(r.score for r in quiz_results)
    badges = total_points // 20

    # Calculate average scores by level
    beginner_avg = (
        round(sum(r.score for r in beginner_results) / max(len(beginner_results), 1))
        if beginner_results
        else 0
    )
    intermediate_avg = (
        round(sum(r.score for r in intermediate_results) / max(len(intermediate_results), 1))
        if intermediate_results
        else 0
    )
    advance_avg = (
        round(sum(r.score for r in advance_results) / max(len(advance_results), 1))
        if advance_results
        else 0
    )

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


@router.get("/quizzes", response_class=HTMLResponse)
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


@router.get("/beginner", response_class=HTMLResponse)
def beginner_quiz(request: Request, db: Session = Depends(get_db)):
    """
    Beginner quiz page showing only quizzes created in the admin with level 'Beginner'.
    """
    quizzes = db.query(Quiz).filter(Quiz.level == "Beginner").all()
    return templates.TemplateResponse("beginner.html", {"request": request, "quizzes": quizzes})


@router.get("/intermediate", response_class=HTMLResponse)
def intermediate_quiz(request: Request, db: Session = Depends(get_db)):
    """
    Intermediate quiz page showing only quizzes created in the admin with level 'Intermediate'.
    """
    quizzes = db.query(Quiz).filter(Quiz.level == "Intermediate").all()
    return templates.TemplateResponse(
        "intermediate.html", {"request": request, "quizzes": quizzes}
    )


@router.get("/advance", response_class=HTMLResponse)
def advance_quiz(request: Request, db: Session = Depends(get_db)):
    """
    Advance quiz page showing only quizzes created in the admin with level 'Advance'.
    """
    quizzes = db.query(Quiz).filter(Quiz.level == "Advance").all()
    return templates.TemplateResponse("advance.html", {"request": request, "quizzes": quizzes})


@router.get("/lessons", response_class=HTMLResponse)
def lessons_page(request: Request, q: Optional[str] = None, db: Session = Depends(get_db)):
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


@router.get("/intermediatee", response_class=HTMLResponse)
def intermediate_lessons_page(request: Request, db: Session = Depends(get_db)):
    # Fetch only Intermediate level lessons
    lessons = db.query(Lesson).filter(Lesson.sign_level == "Intermediate").all()
    return templates.TemplateResponse(
        "intermediatee.html", {"request": request, "lessons": lessons}
    )


@router.get("/advancee", response_class=HTMLResponse)
def advance_lessons_page(request: Request, db: Session = Depends(get_db)):
    # Fetch only Advance level lessons
    lessons = db.query(Lesson).filter(Lesson.sign_level == "Advance").all()
    return templates.TemplateResponse("advancee.html", {"request": request, "lessons": lessons})


@router.get("/quiz_results", response_class=HTMLResponse)
def quiz_results_page(request: Request, db: Session = Depends(get_db)):
    """
    Show a table of all quiz results for the logged-in user.
    """
    user_id = request.session.get("user_id")
    if not user_id:
        # If not logged in, send to login page
        return RedirectResponse(url="/login", status_code=303)

    try:
        page = int(request.query_params.get("page", "1"))
    except ValueError:
        page = 1
    page = max(1, page)

    per_page = 10

    base_query = (
        db.query(QuizResult)
        .filter(QuizResult.user_id == user_id)
    )
    total_results = base_query.count()

    # Ensure at least one page when user has zero results
    total_pages = max(1, (total_results + per_page - 1) // per_page) if total_results else 1
    page = min(page, total_pages)

    offset = (page - 1) * per_page
    results = (
        base_query.order_by(QuizResult.taken_at.desc())
        .offset(offset)
        .limit(per_page)
        .all()
    )

    has_prev = page > 1
    has_next = page < total_pages

    # Page links (kept compact)
    if total_pages <= 5:
        page_range = list(range(1, total_pages + 1))
    elif page <= 3:
        page_range = [1, 2, 3, total_pages]
    elif page >= total_pages - 2:
        page_range = [1, total_pages - 2, total_pages - 1, total_pages]
    else:
        page_range = [1, page - 1, page, page + 1, total_pages]
    page_range = sorted(set(page_range))

    return templates.TemplateResponse(
        "quiz_results.html",
        {
            "request": request,
            "results": results,
            "current_page": page,
            "total_pages": total_pages,
            "has_prev": has_prev,
            "has_next": has_next,
            "page_range": page_range,
        },
    )


@router.post("/update_user_profile")
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
    from sqlalchemy import or_
    from ..authentication import validate_email, validate_password, validate_username, hash_password
    from ..models import Admin

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
    existing_user = (
        db.query(User)
        .filter(or_(User.username == username, User.email == email), User.id != user_id)
        .first()
    )
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
    if user.username == username and user.email == email and not new_password:
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

