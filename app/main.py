# app/main.py

import os
import uuid
from typing import Optional

from fastapi import FastAPI, Request, Form, Depends, File, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware
from sqlalchemy.orm import Session
from sqlalchemy import or_

from .database import SessionLocal
from .models import User, Lesson, Quiz, Admin
from .authentication import hash_password, verify_password

# -------------------------
# FastAPI app
# -------------------------
app = FastAPI()
app.add_middleware(SessionMiddleware, secret_key="your-secret-key-change-in-production")

# -------------------------
# Paths for static and templates
# -------------------------
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATIC_DIR = os.path.join(BASE_DIR, "static")
IMAGES_DIR = os.path.join(STATIC_DIR, "images")
TEMPLATES_DIR = os.path.join(BASE_DIR, "Frontend")

# Create images directory if it doesn't exist
os.makedirs(IMAGES_DIR, exist_ok=True)

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
templates = Jinja2Templates(directory=TEMPLATES_DIR)


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

# Initialize admin on startup
init_admin()


# -------------------------
# Helper function to save uploaded file
# -------------------------
async def save_uploaded_file(file: UploadFile) -> str:
    """Save uploaded file and return the relative path"""
    # Generate unique filename
    file_ext = os.path.splitext(file.filename)[1] if file.filename else ".jpg"
    unique_filename = f"{uuid.uuid4()}{file_ext}"
    file_path = os.path.join(IMAGES_DIR, unique_filename)

    # Save file
    content = await file.read()
    with open(file_path, "wb") as buffer:
        buffer.write(content)

    # Reset file pointer for potential reuse
    await file.seek(0)

    # Return relative path for database storage
    return f"/static/images/{unique_filename}"

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
    return templates.TemplateResponse("login.html", {"request": request, "error": None})

@app.get("/register", response_class=HTMLResponse)
def register_form(request: Request):
    return templates.TemplateResponse("register.html", {"request": request, "error": None})

@app.get("/about", response_class=HTMLResponse)
def about_us(request: Request):
    return templates.TemplateResponse("about_us.html", {"request": request})

@app.get("/contact", response_class=HTMLResponse)
def contact_us(request: Request):
    return templates.TemplateResponse("contact_us.html", {"request": request})


@app.get("/practice", response_class=HTMLResponse)
def practice_page(request: Request):
    return templates.TemplateResponse("practice.html", {"request": request})


@app.get("/profile", response_class=HTMLResponse)
def profile_page(request: Request, db: Session = Depends(get_db)):
    """
    User profile page showing current user's login details.
    """
    user_id = request.session.get("user_id")
    if not user_id:
        return RedirectResponse(url="/login", status_code=303)
    
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        return RedirectResponse(url="/login", status_code=303)
    
    return templates.TemplateResponse(
        "profile.html",
        {
            "request": request,
            "user": user,
            "error": None,
            "success": None,
        },
    )

@app.get("/add_quizzes", response_class=HTMLResponse)
def quizzes_page(request: Request, db: Session = Depends(get_db)):
    """Admin view to add/edit quizzes."""
    quizzes = db.query(Quiz).all()
    return templates.TemplateResponse(
        "add_quizzes.html",
        {"request": request, "quizzes": quizzes},
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
def lessons_page(request: Request, db: Session = Depends(get_db)):
    # Fetch only Basic level lessons
    lessons = db.query(Lesson).filter(Lesson.sign_level == "Basic").all()
    return templates.TemplateResponse("lessons.html", {"request": request, "lessons": lessons})

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
def dashboard_page(request: Request, db: Session = Depends(get_db)):
    """
    Admin dashboard showing basic stats and user list.
    """
    users = db.query(User).all()
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
            "user_error": None,
        },
    )

@app.get("/admin_profile", response_class=HTMLResponse)
def admin_profile_page(request: Request, db: Session = Depends(get_db)):
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
def add_lessons_page(request: Request, db: Session = Depends(get_db)):
    # Fetch all lessons for display in table
    lessons = db.query(Lesson).all()
    return templates.TemplateResponse("add_lessons.html", {"request": request, "lessons": lessons})


@app.get("/logout")
def logout(request: Request):
    """Logout route - clears session and redirects to login."""
    request.session.clear()
    return RedirectResponse(url="/login", status_code=303)

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

    return RedirectResponse(url="/login", status_code=303)

# -------------------------
# POST Login
# -------------------------
@app.post("/login")
def login_submit(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db)
):
    # Admin check from database
    admin = db.query(Admin).first()
    if admin and username == admin.username:
        if not verify_password(password, admin.password):
            return templates.TemplateResponse(
                "login.html", {"request": request, "error": "Incorrect password"}
            )
        # Store admin session
        request.session["admin_id"] = admin.id
        request.session["is_admin"] = True
        return RedirectResponse(url="/dashboard", status_code=303)

    # Normal user check
    user = db.query(User).filter(User.username == username).first()
    if not user:
        return templates.TemplateResponse(
            "login.html", {"request": request, "error": "User not found"}
        )

    if not verify_password(password, user.password):
        return templates.TemplateResponse(
            "login.html", {"request": request, "error": "Incorrect password"}
        )

    # Store user session
    request.session["user_id"] = user.id
    request.session["is_admin"] = False
    return RedirectResponse(url="/home", status_code=303)


# -------------------------
# POST Update User (Admin)
# -------------------------
@app.post("/update_user")
def update_user_submit(
    request: Request,
    user_id: int = Form(...),
    email: str = Form(...),
    username: str = Form(...),
    db: Session = Depends(get_db),
):
    """
    Allow admin to update a user's email and username.
    """
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
        users = db.query(User).all()
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
                "user_error": "Email or username is already in use by another account.",
            },
        )

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        return RedirectResponse(url="/dashboard", status_code=303)

    user.email = email
    user.username = username
    db.commit()

    return RedirectResponse(url="/dashboard", status_code=303)


# -------------------------
# POST Delete User (Admin)
# -------------------------
@app.post("/delete_user")
def delete_user_submit(
    request: Request,
    user_id: int = Form(...),
    db: Session = Depends(get_db),
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

    return RedirectResponse(url="/dashboard", status_code=303)

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
    db: Session = Depends(get_db)
):
    # Save uploaded image file
    image_path = await save_uploaded_file(image)
    
    # Create new lesson
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
    
    return RedirectResponse(url="/add_lessons", status_code=303)

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
    db: Session = Depends(get_db)
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
    
    # Update image only if a new file is uploaded
    if image and image.filename:
        image_path = await save_uploaded_file(image)
        lesson.image = image_path
    elif existing_image:
        # Keep existing image if no new file uploaded
        lesson.image = existing_image
    
    db.commit()
    
    return RedirectResponse(url="/add_lessons", status_code=303)

# -------------------------
# POST Delete Lesson
# -------------------------
@app.post("/delete_lesson")
def delete_lesson_submit(
    request: Request,
    lesson_id: int = Form(...),
    db: Session = Depends(get_db)
):
    # Find and delete lesson
    lesson = db.query(Lesson).filter(Lesson.id == lesson_id).first()
    if lesson:
        db.delete(lesson)
        db.commit()
    
    return RedirectResponse(url="/add_lessons", status_code=303)


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
):
    # Save images if provided
    question_image_path = await save_uploaded_file(question_image) if question_image and question_image.filename else None
    opt1_img_path = await save_uploaded_file(option1_image) if option1_image and option1_image.filename else None
    opt2_img_path = await save_uploaded_file(option2_image) if option2_image and option2_image.filename else None
    opt3_img_path = await save_uploaded_file(option3_image) if option3_image and option3_image.filename else None
    opt4_img_path = await save_uploaded_file(option4_image) if option4_image and option4_image.filename else None

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

    return RedirectResponse(url="/add_quizzes", status_code=303)


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
):
    quiz = db.query(Quiz).filter(Quiz.id == quiz_id).first()
    if not quiz:
        return RedirectResponse(url="/add_quizzes", status_code=303)

    quiz.level = level
    # Allow empty question text
    quiz.question_text = question_text if question_text else None

    # Question image
    if question_image and question_image.filename:
        quiz.question_image = await save_uploaded_file(question_image)
    else:
        quiz.question_image = existing_question_image

    quiz.option1_text = option1_text
    quiz.option2_text = option2_text
    quiz.option3_text = option3_text
    quiz.option4_text = option4_text

    # Option images
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

    quiz.correct_option = correct_option

    db.commit()

    return RedirectResponse(url="/add_quizzes", status_code=303)


# -------------------------
# POST Delete Quiz
# -------------------------
@app.post("/delete_quiz")
def delete_quiz_submit(
    request: Request,
    quiz_id: int = Form(...),
    db: Session = Depends(get_db),
):
    quiz = db.query(Quiz).filter(Quiz.id == quiz_id).first()
    if quiz:
        db.delete(quiz)
        db.commit()

    return RedirectResponse(url="/add_quizzes", status_code=303)


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
    
    # Check if new username or email conflicts with existing users
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
    
    # Validate password if provided
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
        if len(new_password) < 6:
            return templates.TemplateResponse(
                "admin_profile.html",
                {
                    "request": request,
                    "admin": admin,
                    "error": "Password must be at least 6 characters long.",
                    "success": None,
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
    
    # Validate password if provided
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
        if len(new_password) < 6:
            return templates.TemplateResponse(
                "profile.html",
                {
                    "request": request,
                    "user": user,
                    "error": "Password must be at least 6 characters long.",
                    "success": None,
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
