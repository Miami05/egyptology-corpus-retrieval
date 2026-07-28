from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.core.config import settings


class Base(DeclarativeBase):
    pass


def normalise_database_url(url: str) -> str:
    """Make hosted-Postgres URLs usable by SQLAlchemy.

    Neon, Supabase, Render and Heroku all hand out `postgres://...`, which SQLAlchemy
    rejects outright — it only knows the `postgresql` dialect name. Rewriting it here
    means the deployment secret can be pasted in exactly as the provider gives it,
    which is the difference between a working deploy and a baffling crash on boot.

    `psycopg` (v3) is named explicitly so the driver never depends on whichever DBAPI
    happens to be importable in the container.
    """
    if url.startswith("postgres://"):
        return "postgresql+psycopg://" + url[len("postgres://") :]
    if url.startswith("postgresql://"):
        return "postgresql+psycopg://" + url[len("postgresql://") :]
    return url


DATABASE_URL = normalise_database_url(settings.database_url)
IS_SQLITE = DATABASE_URL.startswith("sqlite")

if IS_SQLITE:
    _engine_kwargs: dict = {
        # Streamlit touches the connection from its script thread, not the thread
        # that created it.
        "connect_args": {"check_same_thread": False},
    }
else:
    _engine_kwargs = {
        # Hosted Postgres closes idle connections aggressively (Neon suspends the
        # compute entirely). Without pre-ping, the first query after an idle period
        # fails on a dead connection instead of transparently reconnecting.
        "pool_pre_ping": True,
        # Free tiers cap connection counts, and a Streamlit container needs very few.
        "pool_size": 5,
        "max_overflow": 2,
        "pool_recycle": 300,
    }

engine = create_engine(DATABASE_URL, **_engine_kwargs)

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
