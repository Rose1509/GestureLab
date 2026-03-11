# app/sign_model.py
"""
Load sign_language_model_improved.keras and class_labels.pkl,
preprocess webcam frames, and return predictions (letter + confidence).
Search order: env vars → project root → models/ → ~/Documents/Sign Language.
"""

import os
import pickle
from typing import List, Optional, Tuple

import numpy as np
from PIL import Image

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MODELS_DIR = os.path.join(BASE_DIR, "models")
# Fallback: where using cnn.ipynb saves the model (Documents/Sign Language)
SIGN_LANG_FALLBACK = os.path.join(os.path.expanduser("~"), "Documents", "Sign Language")
MODEL_FILENAME = "sign_language_model_improved.keras"
LABELS_FILENAME = "class_labels.pkl"

_model = None
_labels: Optional[List[str]] = None
_input_shape: Optional[Tuple[int, int, int]] = None  # (height, width, channels)


def _find_file(filename: str) -> str:
    """Return first path where filename exists."""
    env_key = "SIGN_MODEL_PATH" if filename == MODEL_FILENAME else "SIGN_LABELS_PATH"
    env_path = os.getenv(env_key)
    if env_path and os.path.isfile(env_path):
        return env_path
    for directory in (BASE_DIR, MODELS_DIR, SIGN_LANG_FALLBACK):
        path = os.path.join(directory, filename)
        if os.path.isfile(path):
            return path
    return os.path.join(BASE_DIR, filename)


def _get_paths() -> Tuple[str, str]:
    model_path = _find_file(MODEL_FILENAME)
    labels_path = _find_file(LABELS_FILENAME)
    return model_path, labels_path


def load_model_and_labels() -> bool:
    """Load the Keras model and class labels. Returns True if both loaded successfully."""
    global _model, _labels, _input_shape
    if _model is not None and _labels is not None:
        return True

    model_path, labels_path = _get_paths()
    if not os.path.isfile(model_path) or not os.path.isfile(labels_path):
        return False

    try:
        from tensorflow import keras
        _model = keras.models.load_model(model_path)
        # Infer input shape from model (e.g. (None, 64, 64, 1) or (None, 224, 224, 3))
        if _model.input_shape and len(_model.input_shape) >= 2:
            _input_shape = tuple(int(x) for x in _model.input_shape[1:])
        else:
            _input_shape = (64, 64, 1)  # fallback common for ASL

        # Class labels: notebook uses joblib.dump; support both pickle and joblib
        try:
            with open(labels_path, "rb") as f:
                _labels = pickle.load(f)
        except Exception:
            try:
                import joblib
                _labels = joblib.load(labels_path)
            except Exception:
                raise
        if not isinstance(_labels, (list, tuple)):
            _labels = list(_labels) if hasattr(_labels, "__iter__") else [_labels]
        return True
    except Exception:
        _model = None
        _labels = None
        _input_shape = None
        return False


def get_load_error() -> Optional[str]:
    """Return None if model and labels are loadable, else a short error message."""
    if _model is not None and _labels is not None:
        return None
    model_path, labels_path = _get_paths()
    if not os.path.isfile(model_path):
        return (
            "Model file not found. Place sign_language_model_improved.keras in the project root, "
            "in the models/ folder, or in your Documents/Sign Language folder."
        )
    if not os.path.isfile(labels_path):
        return (
            "Class labels file not found. Place class_labels.pkl in the project root, "
            "in the models/ folder, or in your Documents/Sign Language folder."
        )
    return "Failed to load model or labels. Check file format."


def preprocess_image(image: Image.Image) -> np.ndarray:
    """Resize and normalize image to model input shape. Returns batch of shape (1, H, W, C)."""
    global _input_shape
    if _input_shape is None:
        load_model_and_labels()
    h, w = _input_shape[0], _input_shape[1]
    channels = _input_shape[2] if len(_input_shape) > 2 else 1

    img = image.convert("L" if channels == 1 else "RGB")
    img = img.resize((w, h), Image.Resampling.BILINEAR)
    arr = np.array(img, dtype=np.float32) / 255.0
    if channels == 1 and len(arr.shape) == 2:
        arr = np.expand_dims(arr, axis=-1)
    arr = np.expand_dims(arr, axis=0)
    return arr


def predict_proba(image: Image.Image) -> Tuple[Optional[List[str]], Optional[np.ndarray]]:
    """
    Return (labels, probabilities) for a single image.
    - labels: list of class labels in model order
    - probabilities: numpy array shape (num_classes,)
    Returns (None, None) on error / missing model.
    """
    if not load_model_and_labels() or _model is None or _labels is None:
        return None, None

    try:
        arr = preprocess_image(image)
        preds = _model.predict(arr, verbose=0)
        probs = np.asarray(preds[0], dtype=np.float64)
        # If model outputs logits (e.g. no softmax), convert to probabilities
        if probs.size > 1 and (probs.max() > 1.01 or abs(probs.sum() - 1.0) > 0.01):
            exp = np.exp(probs - probs.max())
            probs = exp / exp.sum()
        return [str(x).strip() for x in _labels], probs
    except Exception:
        return None, None


def predict(image: Image.Image) -> Tuple[Optional[str], float]:
    """
    Run prediction on a single image. Returns (letter, confidence) or (None, 0.0) on error.
    """
    labels, probs = predict_proba(image)
    if labels is None or probs is None or probs.size == 0:
        return None, 0.0
    idx = int(np.argmax(probs))
    if idx < len(labels):
        return labels[idx], float(probs[idx])
    return None, 0.0
