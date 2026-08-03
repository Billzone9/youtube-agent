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


# INFERENCE from published ElevenLabs Starter pricing (~30,000 credits/mo). NOT API-sourced and NOT a
# verified fact: the /v1/user/subscription endpoint returns character_limit = recurring base + rollover,
# never the recurring base alone. UNVERIFIED until the 27 Aug 2026 reset (see BACKLOG). Do not present
# this as sourced. It is the ONLY thing carrying this uncertainty — keep the caveat if you touch it.
_STARTER_RECURRING_ALLOWANCE_CR = 30_000


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
    # LLM provider (optional — no key ⇒ the writer degrades to NullWriter, never fabricates)
    anthropic_api_key: str | None = None
    # Stock footage providers (optional — no key ⇒ that provider is dropped from the pool)
    pexels_api_key: str | None = None
    pixabay_api_key: str | None = None
    # TTS narration (optional — no key/scope ⇒ TTS unavailable; the key is Music+TTS scoped)
    elevenlabs_api_key: str | None = None
    # The ElevenLabs key's HARD credit cap (structural spend control). ElevenLabs does NOT expose a
    # key's cap via any GET, so we mirror it here to PRE-CHECK the spend gate against remaining credits;
    # keep it in sync with the dashboard cap. When Banks raises the dashboard cap he raises this too.
    elevenlabs_key_credit_cap: int | None = 20000   # matches the live dashboard cap (also set via .env)
    # The RECURRING monthly credit allowance (an inference — see _STARTER_RECURRING_ALLOWANCE_CR). Used
    # to compute SUSTAINABLE cadence; distinct from the live character_limit (which includes rollover).
    elevenlabs_recurring_allowance_cr: int = _STARTER_RECURRING_ALLOWANCE_CR
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
            "anthropic_configured": bool(self.anthropic_api_key),
            "pexels_configured": bool(self.pexels_api_key),
            "pixabay_configured": bool(self.pixabay_api_key),
            "elevenlabs_configured": bool(self.elevenlabs_api_key),
            "elevenlabs_key_credit_cap": self.elevenlabs_key_credit_cap,
            "elevenlabs_recurring_allowance_cr": self.elevenlabs_recurring_allowance_cr,
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
        anthropic_api_key=os.environ.get("ANTHROPIC_API_KEY"),
        pexels_api_key=os.environ.get("PEXELS_API_KEY"),
        pixabay_api_key=os.environ.get("PIXABAY_API_KEY"),
        elevenlabs_api_key=os.environ.get("ELEVENLABS_API_KEY"),
        elevenlabs_key_credit_cap=(int(os.environ["ELEVENLABS_KEY_CREDIT_CAP"])
                                   if os.environ.get("ELEVENLABS_KEY_CREDIT_CAP") else 20000),
        elevenlabs_recurring_allowance_cr=int(os.environ.get(
            "ELEVENLABS_RECURRING_ALLOWANCE_CR", _STARTER_RECURRING_ALLOWANCE_CR)),
    )
