"""Idempotent migration runner.

Applies every `NNNN_*.sql` in this directory that is not yet recorded in `schema_migrations`,
each in its own transaction, under a session-level advisory lock so two instances can never
race. Re-running is a no-op. Sync (psycopg) — called once at startup before the bot loop.
"""
from __future__ import annotations

from pathlib import Path

from ..config import Settings
from ..db import sync_connect

_MIGRATIONS_DIR = Path(__file__).resolve().parent
_ADVISORY_LOCK_KEY = 837465  # arbitrary, stable across the app


def _migration_files() -> list[Path]:
    return sorted(p for p in _MIGRATIONS_DIR.glob("*.sql"))


def run_migrations(settings: Settings) -> list[str]:
    """Apply pending migrations. Returns the list of versions applied this run (may be empty)."""
    applied_now: list[str] = []
    with sync_connect(settings, autocommit=True) as conn:
        conn.execute("SELECT pg_advisory_lock(%s)", [_ADVISORY_LOCK_KEY])
        try:
            conn.execute(
                "CREATE TABLE IF NOT EXISTS schema_migrations ("
                "  version text PRIMARY KEY,"
                "  applied_at timestamptz NOT NULL DEFAULT now())"
            )
            done = {
                r["version"]
                for r in conn.execute("SELECT version FROM schema_migrations").fetchall()
            }
            for path in _migration_files():
                version = path.name
                if version in done:
                    continue
                sql = path.read_text()
                with conn.transaction():
                    conn.execute(sql)
                    conn.execute(
                        "INSERT INTO schema_migrations (version) VALUES (%s)", [version]
                    )
                applied_now.append(version)
                print(f"[migrate] applied {version}")
            if not applied_now:
                print("[migrate] up to date")
        finally:
            conn.execute("SELECT pg_advisory_unlock(%s)", [_ADVISORY_LOCK_KEY])
    return applied_now
