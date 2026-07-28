from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


@dataclass(slots=True)
class Settings:
    app_name: str = os.getenv("APP_NAME", "Egyptology MVP")
    database_url: str = os.getenv("DATABASE_URL", "sqlite:///egyptology.db")
    top_k: int = int(os.getenv("TOP_K", 3))


settings = Settings()
