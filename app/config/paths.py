"""Central config: project paths and directory names."""

from pathlib import Path

# app/config/paths.py → parents[0]=config dir, [1]=app, [2]=repo root (must not use [1] as root)
_REPO = Path(__file__).resolve()
BASE_DIR = str(_REPO.parents[2])

STATIC_DIR = str(_REPO.parents[2] / "static")
IMAGES_DIR = str(_REPO.parents[2] / "static" / "images")
TEMPLATES_DIR = str(_REPO.parents[2] / "templates")
