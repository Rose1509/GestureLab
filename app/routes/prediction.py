from fastapi import APIRouter, File, Form, UploadFile
from typing import Optional

from .. import sign_model
from ..utils.uploads import MAX_IMAGE_SIZE_BYTES

router = APIRouter()


@router.get("/api/practice-status")
def practice_status():
    """Tell the practice page if the CNN model is loaded (TensorFlow + files on disk)."""
    return sign_model.practice_status()


@router.post("/api/predict-sign")
async def predict_sign(frame: UploadFile = File(..., alias="frame"), target: Optional[str] = Form(None)):
    """
    Accept a single image (webcam frame), run the sign language CNN, return predicted letter and confidence.
    Expects multipart form with field 'frame' containing an image file (e.g. image/jpeg, image/png).
    """
    if not frame.content_type or not frame.content_type.startswith("image/"):
        return {"letter": None, "confidence": 0.0, "error": "Invalid image type"}
    try:
        data = await frame.read()
    except Exception as e:
        return {"letter": None, "confidence": 0.0, "error": str(e)}
    if len(data) > MAX_IMAGE_SIZE_BYTES:
        return {"letter": None, "confidence": 0.0, "error": "Image too large (max 5 MB)"}
    if not data:
        return {"letter": None, "confidence": 0.0, "error": "Empty image"}
    try:
        from io import BytesIO
        from PIL import Image

        img = Image.open(BytesIO(data)).copy()
    except Exception as e:
        return {"letter": None, "confidence": 0.0, "error": f"Image open failed: {e}"}
    labels, probs = sign_model.predict_proba(img)
    if labels is None or probs is None:
        err = sign_model.get_load_error()
        return {"letter": None, "confidence": 0.0, "error": err or "Prediction failed"}

    idx = int(probs.argmax()) if probs.size else 0
    letter = labels[idx] if idx < len(labels) else None
    confidence = float(probs[idx]) if probs.size and idx < probs.size else 0.0

    target_conf = None
    target_label = None
    if target:
        raw_target = target.strip()
        # Extract the LAST A-Z letter from whatever lesson.name contains
        # e.g. "B", "Letter B", "B - Basics" -> "B"
        import re

        letters = re.findall(r"[A-Za-z]", raw_target)
        target_label = letters[-1].upper() if letters else raw_target.upper()

        lookup = {str(l).strip().upper(): i for i, l in enumerate(labels)}
        ti = lookup.get(target_label)
        if ti is not None and ti < probs.size:
            target_conf = float(probs[ti])

    return {
        "letter": letter,
        "confidence": round(confidence, 4),
        "target": target_label,
        "target_confidence": round(target_conf, 4) if target_conf is not None else None,
    }

