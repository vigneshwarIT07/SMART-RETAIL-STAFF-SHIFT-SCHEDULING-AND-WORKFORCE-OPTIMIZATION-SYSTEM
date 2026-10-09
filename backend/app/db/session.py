"""SQLAlchemy engine, session factory and declarative base.

A single module owns database connectivity so that the engine is created
exactly once per process and every request shares the same configuration.
"""

from __future__ import annotations

from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import settings


class Base(DeclarativeBase):
    """Declarative base shared by every ORM model."""


def _build_engine() -> Engine:
    """Create the SQLAlchemy engine from settings.

    Pool sizing arguments are ignored by SQLite, which is acceptable because
    SQLite is only used as an explicitly documented fallback when PostgreSQL
    is unavailable locally.
    """
    kwargs: dict = {
        "echo": settings.db_echo,
        "future": True,
        "pool_pre_ping": True,
    }
    if not settings.database_url.startswith("sqlite"):
        kwargs.update(
            pool_size=settings.db_pool_size,
            max_overflow=settings.db_max_overflow,
            pool_recycle=1800,
        )
    else:  # pragma: no cover - fallback path only
        from sqlalchemy.pool import StaticPool

        kwargs["connect_args"] = {"check_same_thread": False}
        kwargs["poolclass"] = StaticPool

    return create_engine(settings.database_url, **kwargs)


engine = _build_engine()

SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    autocommit=False,
    expire_on_commit=False,
    class_=Session,
)


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency yielding a request-scoped database session.

    The session is always closed, including when the request raises, and it
    is rolled back so that a failed handler cannot leave partial work
    committed by the next handler on the same connection.
    """
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
