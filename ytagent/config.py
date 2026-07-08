"""Typed settings loaded from the environment (.env via python-dotenv).

Secrets are read here and never printed, echoed, or logged. The DB connection info is
built from POSTGRES_* plus a host/port that defaults to the in-container Postgres
(`postgres:5432`); Mac-side CLI runs override with POSTGRES_HOST=localhost
POSTGRES_PORT=5433 (the compose port mapping).
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field

from dotenv import load_dotenv

# Load .env from the project root if present (no-op in-container where env_file injects vars).
load_dotenv()


def _require(name: str) -> str:
    val = os.environ.get(name)
    if not val:
        raise SystemExit(f"{name} is not set. Check your .env file.")
    return val


@dataclass(frozen=True)
class Settings:
    # Postgres
    pg_user: str
    pg_password: str
    pg_db: str
    pg_host: str
    pg_port: str
    # Telegram
    bot_token: str
    chat_id: str  # the single allow-listed operator (Banks)
    # YouTube OAuth (optional — the dry-run path runs without them; present after youtube_auth)
    youtube_client_id: str | None = None
    youtube_client_secret: str | None = None
    youtube_refresh_token: str | None = None
    # Honest-baseline constants (the lion film's known costs; subscription/VPS supplied at seed time)
    lion_music_credits: int = 1500
    # Budget (global, month-1 tier) — seeded into platform_settings
    budget_tier: str = "m1"
    budget_ceiling_gbp: int = 200

    def dsn(self) -> str:
        return (
            f"host={self.pg_host} port={self.pg_port} dbname={self.pg_db} "
            f"user={self.pg_user} password={self.pg_password}"
        )

    def safe_summary(self) -> dict:
        """Non-secret view for logging/diagnostics."""
        return {
            "pg_host": self.pg_host,
            "pg_port": self.pg_port,
            "pg_db": self.pg_db,
            "bot_token_set": bool(self.bot_token),
            "chat_id_set": bool(self.chat_id),
            "youtube_configured": bool(self.youtube_refresh_token),
        }


def load_settings() -> Settings:
    return Settings(
        pg_user=_require("POSTGRES_USER"),
        pg_password=_require("POSTGRES_PASSWORD"),
        pg_db=_require("POSTGRES_DB"),
        pg_host=os.environ.get("POSTGRES_HOST", "postgres"),
        pg_port=os.environ.get("POSTGRES_PORT", "5432"),
        bot_token=_require("TELEGRAM_BOT_TOKEN"),
        chat_id=_require("TELEGRAM_CHAT_ID"),
        youtube_client_id=os.environ.get("YOUTUBE_CLIENT_ID"),
        youtube_client_secret=os.environ.get("YOUTUBE_CLIENT_SECRET"),
        youtube_refresh_token=os.environ.get("YOUTUBE_REFRESH_TOKEN"),
    )
