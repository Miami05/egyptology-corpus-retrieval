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
        "connect_args": {
            # Fail fast instead of hanging forever. Neon suspends an idle compute
            # and the wake-up takes a second or two, but a black-holed endpoint
            # would otherwise block the Streamlit script thread indefinitely — the
            # app would look frozen rather than degraded.
            "connect_timeout": 10,
            # Works with a connection-pooler endpoint as well as a direct one.
            # Neon's `-pooler` host runs PgBouncer in transaction mode, where a
            # server connection is handed to a different client between statements.
            # psycopg starts issuing named prepared statements after a few repeats
            # of the same query, and those names then collide or vanish, producing
            # intermittent "prepared statement already exists" errors that only
            # show up under load. Disabling the automatic prepare removes the whole
            # failure mode; the cost is negligible at this query volume.
            "prepare_threshold": None,
        },
    }

engine = create_engine(DATABASE_URL, **_engine_kwargs)

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


class DatabaseUnavailable(RuntimeError):
    """The database could not be reached.

    Raised by the read/write helpers so the UI can fall back to a read-only mode
    with a plain-language banner. Before this existed, an unreachable database
    raised OperationalError inside the cached corpus loader at import time, which
    took down every page — including Corpus and Sign readings, which need no
    database at all.
    """


def database_available() -> bool:
    """One cheap round trip to see whether the database answers."""
    from sqlalchemy import text

    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        return True
    except Exception:
        return False
