"""
Runtime singletons previously defined in `app/main.py`.

Structural refactor only: this module centralizes env loading, templates, and OAuth objects
so route modules can import them without changing behavior.
"""

import json
import os
from typing import Optional

from authlib.integrations.starlette_client import OAuth
from dotenv import load_dotenv
from fastapi.templating import Jinja2Templates

from .paths import BASE_DIR, TEMPLATES_DIR

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
GOOGLE_OAUTH_ENABLED = bool(
    _google_settings.get("client_id") and _google_settings.get("client_secret")
)
if GOOGLE_OAUTH_ENABLED:
    oauth.register(
        name="google",
        client_id=_google_settings["client_id"],
        client_secret=_google_settings["client_secret"],
        server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
        client_kwargs={"scope": "openid email profile"},
    )


def get_session_secret() -> str:
    return (os.getenv("SESSION_SECRET_KEY") or "").strip() or "your-secret-key-change-in-production"


# Keep the same module-level variable name used in the original `main.py`.
_session_secret = get_session_secret()


def _render_login(request, error: Optional[str] = None):
    return templates.TemplateResponse(
        "login.html",
        {"request": request, "error": error},
    )

