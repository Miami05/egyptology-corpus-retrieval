from __future__ import annotations

import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

PROJECT_ROOT = Path(__file__).resolve().parents[2]

# `sqlite:///` + a path that does not start with "/" (absolute), "?" or ":" (:memory:).
_SQLITE_RELATIVE = re.compile(r"^(sqlite(?:\+\w+)?):///(?P<path>[^/?:][^?]*)(?P<query>\?.*)?$")


def resolve_database_url(url: str, root: Path = PROJECT_ROOT) -> str:
    """Anchor a *relative* SQLite path at the project root instead of the current folder.

    `sqlite:///egyptology.db` means "this file, next to wherever the process was started",
    so the same command run from another folder quietly opened (and created) a second,
    empty database. Everything else passes through untouched: Postgres URLs, in-memory
    SQLite (`sqlite://`, `sqlite:///:memory:`), `file:` URIs and absolute paths
    (`sqlite:////abs/path.db`).
    """
    match = _SQLITE_RELATIVE.match(url)
    if match is None or match.group("path").startswith("file:"):
        return url
    absolute = root / match.group("path")
    return f"{match.group(1)}:///{absolute}{match.group('query') or ''}"


def _announce_database(url: str, from_env: bool) -> None:
    """One stderr line saying which SQLite file this process will open.

    SQLite only: a Postgres URL carries a password, and nothing is printed for it.
    """
    if not url.startswith("sqlite") or ":memory:" in url or url.rstrip("/") in ("sqlite:", "sqlite"):
        return
    path = url.split(":///", 1)[-1].split("?", 1)[0]
    origin = "DATABASE_URL" if from_env else "default next to the code"
    print(f"database: {path} (from {origin})", file=sys.stderr)


_RAW_DATABASE_URL = os.getenv("DATABASE_URL")
_DATABASE_URL = resolve_database_url(_RAW_DATABASE_URL or "sqlite:///egyptology.db")
_announce_database(_DATABASE_URL, from_env=bool(_RAW_DATABASE_URL))


@dataclass(slots=True)
class Settings:
    app_name: str = os.getenv("APP_NAME", "Egyptology MVP")
    database_url: str = _DATABASE_URL
    top_k: int = int(os.getenv("TOP_K", 3))


settings = Settings()
