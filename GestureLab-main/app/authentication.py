# app/auth.py

from passlib.context import CryptContext

# Use Argon2 for password hashing (better than bcrypt for long passwords)
pwd_context = CryptContext(schemes=["argon2"], deprecated="auto")

def hash_password(password: str) -> str:
    return pwd_context.hash(password)

def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)
