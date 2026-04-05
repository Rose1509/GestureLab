"""GestureLab FastAPI application entrypoint (initializer only)."""

import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from starlette.middleware.sessions import SessionMiddleware

from .config import IMAGES_DIR
from .staticfiles_buffered import BufferedStaticFiles
from .config.runtime import _session_secret
from .routes import admin, api, auth, pages, prediction
from .services.startup import on_startup
from .utils.deps import AdminRequiredRedirect, admin_required_redirect_handler

app = FastAPI()


@app.get("/favicon.ico", include_in_schema=False)
def _favicon() -> RedirectResponse:
    """Browsers request this by default; point at site logo under /static."""
    return RedirectResponse(url="/static/images/logo.png")


# Middleware (unchanged behavior)
app.add_middleware(SessionMiddleware, secret_key=_session_secret)

# Static files — resolve from app/main.py (repo_root/static), must match real `static/` next to `app/`
os.makedirs(IMAGES_DIR, exist_ok=True)
_static_root = str((Path(__file__).resolve().parent.parent / "static").resolve())
app.mount(
    "/static",
    BufferedStaticFiles(directory=_static_root, follow_symlink=True),
    name="static",
)

# Exception handling (unchanged behavior)
app.add_exception_handler(AdminRequiredRedirect, admin_required_redirect_handler)


@app.on_event("startup")
def _startup() -> None:
    on_startup()


# Routers
app.include_router(auth.router)
app.include_router(pages.router)
app.include_router(admin.router)
app.include_router(api.router)
app.include_router(prediction.router)
