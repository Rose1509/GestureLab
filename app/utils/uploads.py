"""
Upload validation and file handling moved from `app/main.py` (structural refactor only).
"""

import os
import uuid

from fastapi import UploadFile

from ..config import IMAGES_DIR

# -------------------------
# Admin upload validation (lessons / quizzes)
# -------------------------
ALLOWED_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png"}
ALLOWED_IMAGE_CONTENT_TYPES = {"image/jpeg", "image/png"}
MAX_IMAGE_SIZE_BYTES = 5 * 1024 * 1024  # 5 MB
UPLOAD_TOO_LARGE_MESSAGE = "Image too large (max 5 MB)."
UPLOAD_INVALID_TYPE_MESSAGE = "JPG, JPEG, or PNG only. Max 5MB Optional."


def validate_uploaded_image(file: UploadFile, content: bytes) -> None:
    """Raise ValueError with UPLOAD_VALIDATION_MESSAGE if file is invalid."""
    if len(content) > MAX_IMAGE_SIZE_BYTES:
        raise ValueError(UPLOAD_TOO_LARGE_MESSAGE)
    ext = os.path.splitext(file.filename or "")[1].lower()
    content_type = (file.content_type or "").strip().lower().split(";")[0]
    if ext not in ALLOWED_IMAGE_EXTENSIONS or content_type not in ALLOWED_IMAGE_CONTENT_TYPES:
        raise ValueError(UPLOAD_INVALID_TYPE_MESSAGE)


# -------------------------
# Helper function to save uploaded file
# -------------------------
async def save_uploaded_file(file: UploadFile) -> str:
    """Save uploaded file and return the relative path. Validates type and size (max 5 MB)."""
    content = await file.read()
    validate_uploaded_image(file, content)

    # Generate unique filename
    file_ext = os.path.splitext(file.filename)[1] if file.filename else ".jpg"
    if file_ext.lower() not in ALLOWED_IMAGE_EXTENSIONS:
        file_ext = ".jpg"
    unique_filename = f"{uuid.uuid4()}{file_ext}"
    file_path = os.path.join(IMAGES_DIR, unique_filename)

    with open(file_path, "wb") as buffer:
        buffer.write(content)

    await file.seek(0)
    return f"/static/images/{unique_filename}"

