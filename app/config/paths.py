"""Central config: project paths and directory names."""

import os

# Project root (parent of app/)
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Static assets and templates
STATIC_DIR = os.path.join(BASE_DIR, "static")
IMAGES_DIR = os.path.join(STATIC_DIR, "images")
TEMPLATES_DIR = os.path.join(BASE_DIR, "templates")

