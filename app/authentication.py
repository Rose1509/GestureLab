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


# Contact form: email @gmail.com, subject max 200 words, name max 100, message max 5000
CONTACT_SUBJECT_MAX_WORDS = 200
CONTACT_NAME_MAX_LENGTH = 100
CONTACT_MESSAGE_MAX_LENGTH = 5000

def validate_contact_name(name: str) -> Tuple[bool, Optional[str]]:
    """Returns (valid, error_message). Name is required, max 100 characters."""
    if not name or not name.strip():
        return False, "Name is required."
    if len(name.strip()) > CONTACT_NAME_MAX_LENGTH:
        return False, f"Name must be at most {CONTACT_NAME_MAX_LENGTH} characters."
    return True, None

def validate_contact_message(message: str) -> Tuple[bool, Optional[str]]:
    """Returns (valid, error_message). Message is required, max 5000 characters."""
    if not message or not message.strip():
        return False, "Message is required."
    if len(message.strip()) > CONTACT_MESSAGE_MAX_LENGTH:
        return False, f"Message must be at most {CONTACT_MESSAGE_MAX_LENGTH} characters."
    return True, None

def validate_contact_email(email: str) -> Tuple[bool, Optional[str]]:
    """Returns (valid, error_message). Contact email must contain @gmail.com."""
    if not email or not email.strip():
        return False, "Email is required."
    if "@gmail.com" not in email.strip().lower():
        return False, "Email must contain @gmail.com."
    return True, None

def validate_subject_word_count(subject: str, max_words: int = CONTACT_SUBJECT_MAX_WORDS) -> Tuple[bool, Optional[str]]:
    """Returns (valid, error_message). Subject must have at most max_words words."""
    if not subject or not subject.strip():
        return False, "Subject is required."
    words = subject.strip().split()
    if len(words) > max_words:
        return False, f"Subject must not contain more than {max_words} words."
    return True, None
