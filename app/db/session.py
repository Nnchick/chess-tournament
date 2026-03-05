from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.core.config import settings


class Base(DeclarativeBase):
    """Base class for all SQLAlchemy models."""


engine = create_engine(
    settings.database_url,
    connect_args={"check_same_thread": False},  # only for SQLite
)

SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
)


def get_db():
    """
    Dependency for FastAPI routes.

    Yields:
        Session: SQLAlchemy session connected to current DB.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

