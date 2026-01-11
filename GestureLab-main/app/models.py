# app/models.py

from sqlalchemy import Column, Integer, String
from .database import Base, engine  # import engine from database.py

class User(Base):
    __tablename__ = "register"  # match your PostgreSQL table

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(255), unique=True, index=True, nullable=False)
    username = Column(String(50), unique=True, index=True, nullable=False)
    password = Column(String(255), nullable=False)

# Correct way to create tables
Base.metadata.create_all(bind=engine)
