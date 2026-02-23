# app/auth.py

from typing import Optional, Tuple

from passlib.context import CryptContext

# Use Argon2 for password hashing (better than bcrypt for long passwords)
pwd_context = CryptContext(schemes=["argon2"], deprecated="auto")

def hash_password(password: str) -> str:
    return pwd_context.hash(password)

def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


# -------------------------
# Validation helpers (username max 15, password must have #/@/$, email must have @)
# -------------------------

USERNAME_MAX_LENGTH = 25
PASSWORD_SPECIAL_CHARS = ("#", "@", "$")

def validate_username(username: str) -> Tuple[bool, Optional[str]]:
    """Returns (valid, error_message). Username must be at most 25 characters."""
    if not username or not username.strip():
        return False, "Username is required."
    if len(username.strip()) > USERNAME_MAX_LENGTH:
        return False, f"Username must be at most {USERNAME_MAX_LENGTH} characters."
    return True, None

def validate_password(password: str) -> Tuple[bool, Optional[str]]:
    """Returns (valid, error_message). Password must contain at least one of #, @, $."""
    if not password:
        return False, "Password is required."
    if not any(c in password for c in PASSWORD_SPECIAL_CHARS):
        return False, "Password must contain at least one of: #, @, $."
    return True, None

def validate_email(email: str) -> Tuple[bool, Optional[str]]:
    """Returns (valid, error_message). Email must contain @."""
    if not email or not email.strip():
        return False, "Email is required."
    if "@" not in email.strip():
        return False, "Email must contain @."
    return True, None
