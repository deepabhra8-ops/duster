from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy.pool import NullPool

from core.config import DATABASE_URL
from utils.logger import get_logger

logger = get_logger(__name__)

Base = declarative_base()

def get_engine():
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
    if SessionLocal is None:
        raise RuntimeError("Database engine is not initialized.")
    return SessionLocal()
