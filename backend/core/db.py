"""Database configuration and shared SQLAlchemy engine/sessions."""

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy.pool import NullPool

from core.config import DATABASE_URL
from utils.logger import get_logger

logger = get_logger(__name__)

Base = declarative_base()

def get_engine():
    """Create and return a SQLAlchemy engine.

    Uses NullPool by default so SQLAlchemy never holds idle pooled connections
    open between requests - simplest correct default for a locally-run,
    single-process app.
    """
    if not DATABASE_URL:
        raise RuntimeError("DATABASE_URL is not configured.")

    return create_engine(DATABASE_URL, poolclass=NullPool)

try:
    engine = get_engine()
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
except RuntimeError as exc:
    logger.warning("Database not configured at startup: %s", exc)
    engine = None
    SessionLocal = None

def get_db_session():
    """Get a database session, intended to be used in context managers."""
    if SessionLocal is None:
        raise RuntimeError("Database engine is not initialized.")
    return SessionLocal()
