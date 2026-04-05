# app/database.py

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker, declarative_base

DATABASE_URL = "postgresql://postgres:Arpan%401509@localhost:5432/GestureLab"

engine = create_engine(
    DATABASE_URL,
    connect_args={"connect_timeout": 5},
    pool_pre_ping=True,
    pool_recycle=3600,
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def ensure_schema() -> None:
    """
    Lightweight safety net for local/dev environments.

    This project uses `Base.metadata.create_all()` (no migrations), which does NOT
    add new columns to existing tables.
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
                conn.execute(
                    text(
                        'CREATE UNIQUE INDEX IF NOT EXISTS ix_register_google_id '
                        'ON "register" (google_id)'
                    )
                )

            if "last_login_at" not in columns:
                conn.execute(
                    text('ALTER TABLE "register" ADD COLUMN last_login_at TIMESTAMP WITH TIME ZONE')
                )

            if "admin" in inspector.get_table_names():
                admin_cols = {c["name"] for c in inspector.get_columns("admin")}
                if "last_login_at" not in admin_cols:
                    conn.execute(
                        text("ALTER TABLE admin ADD COLUMN last_login_at TIMESTAMP WITH TIME ZONE")
                    )

            if "password_reset_codes" not in inspector.get_table_names():
                conn.execute(
                    text(
                        """
                        CREATE TABLE IF NOT EXISTS password_reset_codes (
                            id SERIAL PRIMARY KEY,
                            email VARCHAR(255) NOT NULL,
                            code_hash VARCHAR(64) NOT NULL,
                            expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
                            created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
                            used_at TIMESTAMP WITH TIME ZONE NULL
                        )
                        """
                    )
                )
                conn.execute(
                    text(
                        "CREATE INDEX IF NOT EXISTS ix_password_reset_codes_email ON password_reset_codes (email)"
                    )
                )

            if "quiz_results" in inspector.get_table_names():
                qr_cols = {c["name"] for c in inspector.get_columns("quiz_results")}

                if "quiz_level" not in qr_cols:
                    conn.execute(
                        text('ALTER TABLE quiz_results ADD COLUMN quiz_level VARCHAR(50)')
                    )

                if "quiz_id" in qr_cols:
                    try:
                        conn.execute(text("ALTER TABLE quiz_results ALTER COLUMN quiz_id DROP NOT NULL"))
                    except Exception:
                        pass
                if "taken_at" not in qr_cols:
                    conn.execute(
                        text("ALTER TABLE quiz_results ADD COLUMN taken_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()")
                    )
                else:
                    conn.execute(
                        text("UPDATE quiz_results SET taken_at = COALESCE(taken_at, NOW()) WHERE taken_at IS NULL")
                    )

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

            if "contact_submissions" in inspector.get_table_names():
                cs_cols = {c["name"] for c in inspector.get_columns("contact_submissions")}
                if "admin_reply" not in cs_cols:
                    conn.execute(text("ALTER TABLE contact_submissions ADD COLUMN admin_reply TEXT"))
                if "replied_at" not in cs_cols:
                    conn.execute(
                        text(
                            "ALTER TABLE contact_submissions ADD COLUMN replied_at TIMESTAMP WITH TIME ZONE"
                        )
                    )
    except Exception:
        return
