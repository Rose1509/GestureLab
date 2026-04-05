# app/sign_model.py
"""
Load sign_language_model_improved.keras and class_labels.pkl,
preprocess webcam frames, and return predictions (letter + confidence).
Search order: env vars → project root → models/ → ~/Documents/Sign Language.

NumPy is imported lazily so a broken venv (missing RECORD / DLL errors) does not
prevent the rest of the app (e.g. uvicorn) from starting.
"""

from __future__ import annotations

import importlib
import os
import pickle
import sys
from typing import Any, List, Optional, Tuple

from PIL import Image

_np = None  # type: ignore[assignment]
_numpy_load_error: Optional[str] = None


def _prepare_windows_tensorflow_dlls() -> None:
    """
    On Windows, TensorFlow sometimes fails with DLL load failed for _pywrap_*
    unless DLL search paths include the package tree. Must run before importing tensorflow.
    """
    if sys.platform != "win32":
        return
    try:
        import site

        roots: List[str] = []
        if hasattr(site, "getsitepackages"):
            roots.extend(site.getsitepackages())
        if hasattr(site, "getusersitepackages"):
            try:
                roots.append(site.getusersitepackages())
            except Exception:
                pass
        venv_site = os.path.join(sys.prefix, "Lib", "site-packages")
        if os.path.isdir(venv_site):
            roots.append(venv_site)
        for dll_root in (sys.prefix, sys.base_prefix):
            dlls = os.path.join(dll_root, "DLLs")
            if os.path.isdir(dlls):
                try:
                    os.add_dll_directory(dlls)
                except (OSError, AttributeError, FileNotFoundError):
                    pass
            lib_bin = os.path.join(dll_root, "Library", "bin")
            if os.path.isdir(lib_bin):
                try:
                    os.add_dll_directory(lib_bin)
                except (OSError, AttributeError, FileNotFoundError):
                    pass

        for root in roots:
            if not root or not os.path.isdir(root):
                continue
            # Windows wheels split native code across tensorflow and tensorflow_intel
            for pkg_name in ("tensorflow_intel", "tensorflow"):
                tf_pkg = os.path.join(root, pkg_name)
                if not os.path.isdir(tf_pkg):
                    continue
                for sub in (
                    tf_pkg,
                    os.path.join(tf_pkg, "python"),
                    os.path.join(tf_pkg, "core"),
                    os.path.join(tf_pkg, "compiler"),
                ):
                    if os.path.isdir(sub):
                        try:
                            os.add_dll_directory(sub)
                        except (OSError, AttributeError, FileNotFoundError):
                            pass
    except Exception:
        pass


def _import_tensorflow():
    """
    Import TensorFlow in an order that works on Windows + tensorflow-intel wheels:
    preload tensorflow_intel so native libs and tensorflow.python.* resolve, then import tensorflow.
    """
    _prepare_windows_tensorflow_dlls()
    os.environ.setdefault("KERAS_BACKEND", "tensorflow")
    if sys.platform == "win32":
        try:
            import tensorflow_intel  # noqa: F401
        except Exception:
            pass
        # Prime tensorflow.python subpackages before keras imports trackable helpers (Windows wheels).
        try:
            import tensorflow.python as _tfpy  # noqa: F401
        except Exception:
            pass
    import tensorflow as tf

    return tf

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MODELS_DIR = os.path.join(BASE_DIR, "models")
# Fallback: where using cnn.ipynb saves the model (Documents/Sign Language)
SIGN_LANG_FALLBACK = os.path.join(os.path.expanduser("~"), "Documents", "Sign Language")
MODEL_FILENAME = "sign_language_model_improved.keras"
LABELS_FILENAME = "class_labels.pkl"

_model = None
_labels: Optional[List[str]] = None
_input_shape: Optional[Tuple[int, int, int]] = None  # (height, width, channels)
_last_load_error: Optional[str] = None


def _ensure_numpy() -> bool:
    """Import NumPy once; failures are recorded for get_load_error()."""
    global _np, _numpy_load_error
    if _np is not None:
        return True
    if _numpy_load_error is not None:
        return False
    try:
        import numpy as np

        _np = np
        return True
    except Exception as e:
        _numpy_load_error = f"{type(e).__name__}: {e}"
        return False


def _get_keras_module(tf: Any):
    """
    Resolve Keras API for load_model/predict.

    Some Windows TensorFlow wheels do not set ``tf.keras`` on the top-level module even
    though ``tensorflow.keras`` works; standalone ``keras`` (Keras 3) is the fallback.
    """
    keras_mod = getattr(tf, "keras", None)
    if keras_mod is not None:
        return keras_mod
    try:
        return importlib.import_module("tensorflow.keras")
    except Exception:
        pass
    try:
        import keras as keras_mod  # type: ignore

        return keras_mod
    except Exception as e:
        raise ImportError(
            "Could not load Keras after importing TensorFlow. "
            "Your venv TensorFlow install is incomplete or mixed versions. "
            "Fix: deactivate other Python installs, then run: "
            "pip uninstall -y tensorflow tensorflow-intel keras && "
            'pip install "tensorflow>=2.15,<2.18" '
            f"(original error: {e!s})"
        ) from e


def _load_keras_model_file(model_path: str, load_model_fn: Any) -> Any:
    """
    Load a .keras file the same way as using cnn.ipynb (tf.keras.models.load_model).
    Retries with TopKCategoricalAccuracy if the notebook-trained model references it.
    """
    _model = None
    _last_kw_err: Optional[Exception] = None
    for kwargs in (
        {"compile": False, "safe_mode": False},
        {"compile": False},
        {},
    ):
        try:
            _model = load_model_fn(model_path, **kwargs)
            break
        except TypeError as te:
            _last_kw_err = te
            if kwargs.get("safe_mode") is False:
                try:
                    _model = load_model_fn(model_path, compile=False)
                    break
                except Exception as e2:
                    _last_kw_err = e2
        except Exception as e:
            _last_kw_err = e
    if _model is not None:
        return _model
    # Notebook uses TopKCategoricalAccuracy(k=3) in compile; rare load edge cases need it
    try:
        try:
            from tensorflow.keras.metrics import TopKCategoricalAccuracy
        except Exception:
            from keras.metrics import TopKCategoricalAccuracy

        co = {"TopKCategoricalAccuracy": TopKCategoricalAccuracy}
        _model = load_model_fn(model_path, compile=False, custom_objects=co)
        return _model
    except Exception:
        pass
    raise _last_kw_err if _last_kw_err else RuntimeError("keras load_model failed")


def _load_model_via_saving_api(model_path: str) -> Any:
    """Keras 3 ``keras.saving.load_model`` when ``keras.models.load_model`` path fails."""
    try:
        from keras.saving import load_model as saving_load

        for kwargs in (
            {"compile": False, "safe_mode": False},
            {"compile": False},
            {},
        ):
            try:
                return saving_load(model_path, **kwargs)
            except TypeError:
                if kwargs.get("safe_mode") is False:
                    return saving_load(model_path, compile=False)
            except Exception:
                continue
        return saving_load(model_path, compile=False)
    except Exception:
        raise


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
    global _model, _labels, _input_shape, _last_load_error
    if _model is not None and _labels is not None:
        return True

    _last_load_error = None
    if not _ensure_numpy():
        _last_load_error = _numpy_load_error or "NumPy import failed"
        return False

    model_path, labels_path = _get_paths()
    if not os.path.isfile(model_path) or not os.path.isfile(labels_path):
        return False

    try:
        # Reduce log noise; harmless on all platforms
        os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "2")
        os.environ.setdefault("TF_ENABLE_ONEDNN_OPTS", "0")
        tf = _import_tensorflow()
        try:
            import tensorflow.keras as _tfk  # noqa: F401
        except Exception:
            pass

        keras = _get_keras_module(tf)
        load_model_fn = keras.models.load_model
        try:
            _model = _load_keras_model_file(model_path, load_model_fn)
        except Exception:
            _model = _load_model_via_saving_api(model_path)
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
            except Exception as e2:
                raise RuntimeError(f"Could not read labels as pickle or joblib: {e2}") from e2
        if not isinstance(_labels, (list, tuple)):
            _labels = list(_labels) if hasattr(_labels, "__iter__") else [_labels]
        return True
    except Exception as e:
        _model = None
        _labels = None
        _input_shape = None
        _last_load_error = f"{type(e).__name__}: {e}"
        return False


def get_load_error() -> Optional[str]:
    """Return None if model and labels are loadable, else a short error message."""
    if _model is not None and _labels is not None:
        return None
    if not _ensure_numpy() and _numpy_load_error:
        return (
            "NumPy failed to load ("
            + _numpy_load_error
            + "). Fix the venv: delete venv\\Lib\\site-packages\\numpy and any numpy-*.dist-info folder, then "
            "pip install --ignore-installed 'numpy>=1.26.0,<2.2.0' and pip install -r requirements.txt."
        )
    model_path, labels_path = _get_paths()
    if not os.path.isfile(model_path):
        return (
            "Model file not found. The GitHub repo does not include the CNN files (they are large). "
            "Train or copy sign_language_model_improved.keras into models/ (see using cnn.ipynb), "
            "or set SIGN_MODEL_PATH in .env."
        )
    if not os.path.isfile(labels_path):
        return (
            "Class labels not found. Place class_labels.pkl next to the model in models/ "
            "(joblib output from the notebook), or set SIGN_LABELS_PATH in .env."
        )
    if _last_load_error:
        msg = (
            "Failed to load model or labels. "
            + _last_load_error
            + " Ensure the .keras file matches your installed TensorFlow version and class_labels.pkl is a list of labels saved with compatible pickle/joblib."
        )
        if sys.platform == "win32" and "dll" in _last_load_error.lower():
            msg += (
                " On Windows, install the latest Microsoft Visual C++ Redistributable (x64) from Microsoft, "
                "then restart the terminal and app."
            )
        return msg
    return "Failed to load model or labels. Check file format."


def practice_status() -> dict:
    """
    Whether the practice page AI can run. Triggers a load attempt once.
    Used by GET /api/practice-status and optional startup warmup.
    """
    ok = load_model_and_labels()
    if ok:
        return {"ready": True, "message": None}
    err = get_load_error() or "Prediction is not available."
    return {"ready": False, "message": err}


def preprocess_image(image: Image.Image) -> Any:
    """
    Resize and normalize to the loaded model's input (same as using cnn.ipynb:
    RGB/grayscale, target_size match, values in [0, 1] like ImageDataGenerator rescale=1./255).
    Uses LANCZOS when downsampling for sharper hand edges than bilinear alone.
    """
    global _input_shape
    if not _ensure_numpy():
        raise RuntimeError(_numpy_load_error or "NumPy unavailable")
    np = _np
    if _input_shape is None:
        load_model_and_labels()
    h, w = _input_shape[0], _input_shape[1]
    channels = _input_shape[2] if len(_input_shape) > 2 else 1

    img = image.convert("L" if channels == 1 else "RGB")
    # Sharper resize for small inputs (e.g. 64x64) than BILINEAR alone
    try:
        resample = Image.Resampling.LANCZOS
    except AttributeError:
        resample = getattr(Image, "LANCZOS", Image.BICUBIC)
    img = img.resize((w, h), resample)
    arr = np.asarray(img, dtype=np.float32) / 255.0
    np.clip(arr, 0.0, 1.0, out=arr)
    if channels == 1 and len(arr.shape) == 2:
        arr = np.expand_dims(arr, axis=-1)
    arr = np.expand_dims(arr, axis=0)
    return arr


def predict_proba(image: Image.Image) -> Tuple[Optional[List[str]], Optional[Any]]:
    """
    Return (labels, probabilities) for a single image.
    - labels: list of class labels in model order
    - probabilities: numpy array shape (num_classes,)
    Returns (None, None) on error / missing model.
    """
    if not load_model_and_labels() or _model is None or _labels is None:
        return None, None

    try:
        np = _np
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
    np = _np
    idx = int(np.argmax(probs))
    if idx < len(labels):
        return labels[idx], float(probs[idx])
    return None, 0.0
