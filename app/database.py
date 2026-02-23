# app/database.py

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker, declarative_base

DATABASE_URL = "postgresql://postgres:Arpan%401509@localhost:5432/GestureLab"

engine = create_engine(
    DATABASE_URL,
    connect_args={"connect_timeout": 5},  # 5-second timeout for connections
    pool_pre_ping=True,  # Test connections before using them
    pool_recycle=3600  # Recycle connections after 1 hour
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def ensure_schema() -> None:
    """
    Lightweight safety net for local/dev environments.

    This project uses `Base.metadata.create_all()` (no migrations), which does NOT
    add new columns to existing tables. If your DB was created before a column
    existed in the SQLAlchemy model, queries can crash (e.g. missing `google_id`).
    """
    try:
        with engine.begin() as conn:
            inspector = inspect(conn)
            if "register" not in inspector.get_table_names():
                return

            columns = {c["name"] for c in inspector.get_columns("register")}
            if "google_id" not in columns:
                conn.execute(
                    text('ALTER TABLE "register" ADD COLUMN google_id VARCHAR(255)')
                )
                # Keep behavior close to the SQLAlchemy model (nullable + unique index).
                # Postgres allows multiple NULLs in a UNIQUE index, so this is safe.
                conn.execute(
                    text(
                        'CREATE UNIQUE INDEX IF NOT EXISTS ix_register_google_id '
                        'ON "register" (google_id)'
                    )
                )

            # Keep quiz_results compatible with evolving SQLAlchemy model.
            if "quiz_results" in inspector.get_table_names():
                qr_cols = {c["name"] for c in inspector.get_columns("quiz_results")}

                if "quiz_level" not in qr_cols:
                    conn.execute(
                        text('ALTER TABLE quiz_results ADD COLUMN quiz_level VARCHAR(50)')
                    )

                # Older schemas may have quiz_id NOT NULL; drop NOT NULL so we can store
                # a level-based attempt (one row per submission) without a single quiz_id.
                if "quiz_id" in qr_cols:
                    try:
                        conn.execute(text("ALTER TABLE quiz_results ALTER COLUMN quiz_id DROP NOT NULL"))
                    except Exception:
                        pass
                if "taken_at" not in qr_cols:
                    conn.execute(
                        text("ALTER TABLE quiz_results ADD COLUMN taken_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()")
                    )

            # Notifications: admin-created flag and batch id for admin panel
            if "notifications" in inspector.get_table_names():
                notif_cols = {c["name"] for c in inspector.get_columns("notifications")}
                if "is_admin_created" not in notif_cols:
                    conn.execute(
                        text("ALTER TABLE notifications ADD COLUMN is_admin_created BOOLEAN NOT NULL DEFAULT FALSE")
                    )
                if "admin_batch_id" not in notif_cols:
                    conn.execute(
                        text("ALTER TABLE notifications ADD COLUMN admin_batch_id VARCHAR(100)")
                    )
    except Exception:
        # Don't block app startup if schema auto-fix fails; endpoints will surface errors.
        return
