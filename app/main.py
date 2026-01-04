# app/main.py

import os
from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

# FastAPI app
app = FastAPI()

# Paths
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Serve static files (CSS, JS, images)
app.mount("/static", StaticFiles(directory=os.path.join(BASE_DIR, "static")), name="static")

# Templates folder
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "Frontend"))

# Routes

@app.get("/", response_class=HTMLResponse)
def landing_page(request: Request):
    """Landing page"""
    return templates.TemplateResponse("landing_page.html", {"request": request})

@app.get("/home", response_class=HTMLResponse)
def home_page(request: Request):
    """Home page"""
    return templates.TemplateResponse("home.html", {"request": request})

@app.get("/header", response_class=HTMLResponse)
def header_page(request: Request):
    """Header partial"""
    return templates.TemplateResponse("header.html", {"request": request})

@app.get("/footer", response_class=HTMLResponse)
def footer_page(request: Request):
    """Footer partial"""
    return templates.TemplateResponse("footer.html", {"request": request})

@app.get("/login", response_class=HTMLResponse)
def login_form(request: Request):
    """Login page"""
    return templates.TemplateResponse("login.html", {"request": request})

@app.get("/register", response_class=HTMLResponse)
def register_form(request: Request):
    """Show registration form"""
    return templates.TemplateResponse("register.html", {"request": request})

@app.post("/register", response_class=HTMLResponse)
def register_submit(
    full_name: str = Form(...),
    username: str = Form(...),
    password: str = Form(...),
    confirm_password: str = Form(...),
):
    """Handle registration form submission (no DB logic yet)"""
    if password != confirm_password:
        return HTMLResponse(content="Passwords do not match!", status_code=400)

    # Placeholder for success message
    return HTMLResponse(content=f"User {username} registered successfully!", status_code=200)
