# app/main.py

import os
from fastapi import FastAPI, Request, Form, Depends
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from sqlalchemy import or_

from .database import SessionLocal
from .models import User
from .authentication import hash_password, verify_password

# -------------------------
# FastAPI app
# -------------------------
app = FastAPI()

# -------------------------
# Paths for static and templates
# -------------------------
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # Points to Gesture Lab/
STATIC_DIR = os.path.join(BASE_DIR, "static")                            # now static is outside app/
TEMPLATES_DIR = os.path.join(BASE_DIR, "Frontend")                       # templates outside app/

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
templates = Jinja2Templates(directory=TEMPLATES_DIR)

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
# Routes - GET
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

# -------------------------
# Routes - POST Register
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
    if password != confirm_password:
        return templates.TemplateResponse(
            "register.html", {"request": request, "error": "Passwords do not match!"}
        )

    existing_user = db.query(User).filter(or_(User.username == username, User.email == email)).first()
    if existing_user:
        return templates.TemplateResponse(
            "register.html", {"request": request, "error": "Username or email already exists!"}
        )

    user = User(email=email, username=username, password=hash_password(password))
    db.add(user)
    db.commit()

    # Redirect to login page
    return RedirectResponse(url="/login", status_code=303)

# -------------------------
# Routes - POST Login
# -------------------------
@app.post("/login")
def login_submit(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db)
):
    user = db.query(User).filter(User.username == username).first()
    if not user:
        return templates.TemplateResponse(
            "home.html", {"request": request, "error": "User not found"}
        )

    if not verify_password(password, user.password):
        return templates.TemplateResponse(
            "home.html", {"request": request, "error": "Incorrect password"}
        )
    response = RedirectResponse(url="/home", status_code=303)
    return response
    
