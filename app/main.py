"""GestureLab FastAPI application entrypoint (initializer only)."""

import os

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from .config import IMAGES_DIR, STATIC_DIR
from .config.runtime import _session_secret
from .routes import admin, api, auth, pages, prediction
from .services.startup import on_startup
from .utils.deps import AdminRequiredRedirect, admin_required_redirect_handler

app = FastAPI()

# Middleware (unchanged behavior)
app.add_middleware(SessionMiddleware, secret_key=_session_secret)

# Static files (unchanged behavior)
os.makedirs(IMAGES_DIR, exist_ok=True)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

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
