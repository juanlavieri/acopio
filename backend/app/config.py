"""Application configuration.

Mirrors the crypto-pay-poc philosophy: sensible local defaults (SQLite, no API
keys required), production behaviour switched on purely by environment variables
so the same image runs everywhere.
"""
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


# Project root = .../acopio
ROOT_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(ROOT_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "Acopio"
    port: int = 8000
    cors_origins: str = "*"

    secret_key: str = "dev-insecure-secret-change-me"
    admin_email: str = "admin@acopio.org"

    # Optional one-time bootstrap of the first country manager on a fresh DB.
    # Keep the password out of git — set it in .env locally / the host dashboard.
    bootstrap_admin_email: str | None = None
    bootstrap_admin_name: str | None = None
    bootstrap_admin_password: str | None = None

    # Seed region/center for the operation (the collection-center country).
    default_country: str = "Venezuela"
    default_region: str = "Nacional"
    default_center: str = "Centro Principal"

    # Empty => SQLite fallback (data/acopio.db)
    database_url: str | None = None

    openai_api_key: str | None = None
    openai_model: str = "gpt-4o-mini"
    openai_embed_model: str = "text-embedding-3-small"
    openai_transcribe_model: str = "whisper-1"

    data_dir: str = "data"

    # --- derived helpers -------------------------------------------------
    @property
    def data_path(self) -> Path:
        p = (ROOT_DIR / self.data_dir) if not os.path.isabs(self.data_dir) else Path(self.data_dir)
        p.mkdir(parents=True, exist_ok=True)
        return p

    @property
    def sqlalchemy_url(self) -> str:
        """Normalise the DB URL.

        Render hands out URLs that start with ``postgres://``; SQLAlchemy +
        psycopg3 wants ``postgresql+psycopg://``. If nothing is set we use a
        local SQLite file so the app boots with zero configuration.
        """
        url = self.database_url
        if not url:
            return f"sqlite:///{self.data_path / 'acopio.db'}"
        if url.startswith("postgres://"):
            url = url.replace("postgres://", "postgresql+psycopg://", 1)
        elif url.startswith("postgresql://"):
            url = url.replace("postgresql://", "postgresql+psycopg://", 1)
        return url

    @property
    def ai_enabled(self) -> bool:
        return bool(self.openai_api_key)

    @property
    def cors_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
