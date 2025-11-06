"""
Database configuration and session management.

This module defines the SQLAlchemy engine and session factory for the
application.  A SQLite database is used for simplicity, but you can
replace the connection string with any other supported backend.
"""

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

# Use a relative path for the SQLite database.  When running inside
# Docker the working directory is `/app`, so the database will be
# created at `/app/app.db`.  For local development it will be
# `project/backend/app.db`.
SQLALCHEMY_DATABASE_URL = "sqlite:///./app.db"

# Disable thread check because FastAPI uses an async worker model
# which can spawn multiple threads.
engine = create_engine(
    SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False}
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db():
    """
    Provide a transactional scope around a series of operations.

    This dependency yields a SQLAlchemy session to the caller and
    ensures that the session is closed once the request has finished.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()