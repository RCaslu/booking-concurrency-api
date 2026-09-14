from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from booking_api.config import settings


class Base(DeclarativeBase):
    pass


def build_engine(database_url: str, pool_size: int = 20, max_overflow: int = 10):
    """pool_size must be >= the concurrency test's thread count, otherwise the
    test measures connection-pool contention instead of the database lock."""
    return create_engine(database_url, pool_size=pool_size, max_overflow=max_overflow)


engine = build_engine(settings.database_url)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_session() -> Session:
    return SessionLocal()
