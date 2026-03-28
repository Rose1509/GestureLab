"""
Startup initialization moved from `app/main.py` (structural refactor only).
"""

from ..authentication import hash_password
from ..database import SessionLocal, ensure_schema
from ..models import Admin


def init_admin():
    """Create default admin account if it doesn't exist."""
    db = SessionLocal()
    try:
        admin = db.query(Admin).first()
        if not admin:
            default_admin = Admin(
                full_name="Rose Khatiwada",
                username="Rose",
                email="rkc123@gmail.com",
                password=hash_password("Rose@123"),
            )
            db.add(default_admin)
            db.commit()
            print("Default admin account created: username='Rose', password='Rose@123'")
    except Exception as e:
        print(f"Error initializing admin: {e}")
        db.rollback()
    finally:
        db.close()


def on_startup() -> None:
    try:
        from ..database import Base, engine

        Base.metadata.create_all(bind=engine)
        print("[OK] Database tables created")

        ensure_schema()
        init_admin()
        print("[OK] Database schema and admin initialization completed successfully")
    except Exception as e:
        print(f"[WARN] Warning during startup: {e}")
        print("App will continue, but database operations may fail until the database is available")
