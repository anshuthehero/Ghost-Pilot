"""
Database Connection & Session Management.
Supports SQLite (Local Dev) and PostgreSQL (Production).
"""

from typing import Generator
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from server.config.settings import settings
from server.database.models import Base

# Configure connect_args for SQLite if needed (check_same_thread=False)
connect_args = {"check_same_thread": False} if settings.resolved_database_url.startswith("sqlite") else {}

engine = create_engine(
    settings.resolved_database_url,
    connect_args=connect_args,
    pool_pre_ping=True
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def init_db():
    """Initializes tables in development if not already created."""
    Base.metadata.create_all(bind=engine)


def get_db() -> Generator[Session, None, None]:
    """Dependency for obtaining an isolated database session per request."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
