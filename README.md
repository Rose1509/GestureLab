# 🙌 GestureLab

GestureLab is a modular, cleanly structured **FastAPI-powered web application** for **gesture recognition** and related user interaction features. It uses a Convolutional Neural Network (CNN) model to classify hand gestures and exposes routes for predictions, user authentication, dashboard interaction, and analytics.


---

## 🧠 About

GestureLab lets users:
- Upload and recognize hand gestures through a trained CNN model
- Manage and track practice sessions
- View statistics and receive notifications
- Download certificates and track progress
- Admins can manage users and system data through a dashboard

The repository is organized to follow clean architecture principles, with routes, services, models, and utilities properly separated for maintainability and extensibility.

---

## 🚀 Features

- **Gesture prediction API** (`/api/predict-sign`)
- **User authentication** (email/password + Google OAuth)
- **Admin dashboard and routes**
- **Practice tracking, streaks, notifications**
- **Certificate download and user stats**
- Modular backend architecture  
- Ready for deployment and extension

---

## 🛠 Tech Stack

- **Backend:** FastAPI  
- **Database:** SQLAlchemy with ORM  
- **Machine Learning:** CNN-based model (via PyTorch/TensorFlow usage patterns)  
- **Frontend Templates:** Jinja2  
- **Deployment:** Uvicorn, optional Docker  
- **Language:** Python 3.11+

---

## 📦 Installation

```bash
# Clone this repository
git clone https://github.com/Rose1509/GestureLab.git
cd GestureLab
```

## ⚡ Running the Application

Start the FastAPI server locally:

uvicorn app.main:app --reload
Visit http://127.0.0.1:8000/ for the homepage and UI templates.
Visit http://127.0.0.1:8000/docs for auto-generated API documentation.
Use /api/predict-sign to make gesture prediction calls.
# Create and activate virtual environment
python -m venv venv
source venv/bin/activate     # macOS/Linux
venv\Scripts\activate        # Windows

### Login
- **Users** log in with **email + password**
- **Admin** logs in with **email + password**

## 📂 Folder Structure
```bash
GestureLab/
├── app/
│   ├── main.py                  # FastAPI app initialization + router includes
│   ├── routes/                 # API routes separated by feature
│   │   ├── auth.py
│   │   ├── pages.py
│   │   ├── admin.py
│   │   ├── api.py
│   │   └── prediction.py
│   ├── services/              # Business logic separated into modules
│   ├── utils/                 # Utility helpers, dependencies, uploads
│   └── config/                # Config constants and runtime settings
│
├── models/                     # ORM models
├── static/                     # Static assets (CSS, JS, images)
├── templates/                  # Jinja2 templates for UI
├── requirements.txt            # Python dependencies
├── README.md                  # Project documentation
└── using cnn.ipynb            # Notebook reference for model work
```

---

## 📡 API Endpoints (at a glance)

| Route Module    | Path                             | Purpose            |
| --------------- | -------------------------------- | ------------------ |
| `auth.py`       | `/login`, `/register`, `/logout` | User auth          |
| `pages.py`      | Template routes                  | UI pages           |
| `admin.py`      | `/admin/*`                       | Admin features     |
| `api.py`        | `/notifications`, `/stats`       | Data APIs          |
| `prediction.py` | `/api/predict-sign`              | Gesture prediction |

---

## Install dependencies
pip install -r requirements.txt

![Gesture Prediction Demo](assets/demo.gif)
