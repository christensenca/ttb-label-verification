"""SQLAlchemy 2.x engine, session factory, and FastAPI request dependency."""

from __future__ import annotations

from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import get_settings


def _make_engine() -> Engine:
    url = get_settings().database_url
    # Railway/Heroku-style postgres URLs use the bare `postgresql://` scheme;
    # this project only ships psycopg3, so SQLAlchemy needs the `+psycopg` driver.
    if url.startswith("postgres://"):
        url = "postgresql+psycopg://" + url[len("postgres://") :]
    elif url.startswith("postgresql://"):
        url = "postgresql+psycopg://" + url[len("postgresql://") :]
    return create_engine(
        url,
        pool_pre_ping=True,
        future=True,
    )


engine: Engine = _make_engine()
SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    autocommit=False,
    expire_on_commit=False,
    future=True,
)


def get_db() -> Iterator[Session]:
    """FastAPI dependency that yields a transactional Session per request.

    The session is committed if the handler returns successfully and rolled back
    on any exception. Closed in either case.
    """
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
