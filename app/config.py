"""Compatibility shim for prior imports.

Structural refactor only: the canonical location is now `app/config/paths.py`.
"""

from .config.paths import BASE_DIR, STATIC_DIR, IMAGES_DIR, TEMPLATES_DIR  # noqa: F401
