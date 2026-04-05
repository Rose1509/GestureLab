# Sign language model files

Place your trained model and class labels here so the Practice page can run real-time sign recognition:

- **sign_language_model_improved.keras** – your saved Keras CNN model
- **class_labels.pkl** – pickle file containing the list of class labels (e.g. `['A', 'B', 'C', ...]`)

The app also looks in the project root (the folder that contains `app` and `models`), in `~/Documents/Sign Language`, or at paths set by `SIGN_MODEL_PATH` and `SIGN_LABELS_PATH` in `.env`. Restart the server after adding the files.

## “Failed to load model or labels”

- Both filenames must match exactly: `sign_language_model_improved.keras` and `class_labels.pkl` (unless you override paths via env vars).
- The `.keras` model must load with the **same TensorFlow version** you used when training/saving (see `requirements.txt`). Upgrade/downgrade TensorFlow if Keras reports a compatibility error.
- `class_labels.pkl` must be a **pickle or joblib** file containing a **list/tuple** of class names (e.g. letters), in the same order as the model outputs.
- If the API still returns an error, the message now includes the **underlying exception** (e.g. corrupt file, wrong format) to help debug.

### Pip / NumPy on Windows (`uninstall-no-record-file` or `Access is denied`)

If `pip` cannot upgrade NumPy (broken `RECORD`, or `.pyd` locked), close every Python/IDE using this project, pause OneDrive sync on the project folder if needed, then either:

1. Delete the folder `venv\Lib\site-packages\numpy` and any `numpy-*.dist-info` there, then run  
   `pip install --ignore-installed "numpy>=1.26.0,<2.2.0"` and `pip install -r requirements.txt`, or  
2. Recreate the virtualenv: remove `venv`, run `python -m venv venv`, then `pip install -r requirements.txt`.

The app starts even if NumPy is broken (so login and other pages work); sign prediction returns an error until NumPy is fixed.
