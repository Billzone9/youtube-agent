"""Database access: an async pool for the bot, a sync connection for CLIs, and a
wait-for-db retry loop so the app is self-healing regardless of container start order.

Repo functions take a connection/cursor and contain the SQL; this module only manages
connections. psycopg3 gives us both async (pool) and sync (CLI) from one dependency.
"""
from __future__ import annotations

import time
from contextlib import contextmanager
from typing import Iterator

import psycopg
from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool

from .config import Settings


def make_pool(settings: Settings) -> AsyncConnectionPool:
    """Build (but do not open) the async pool. Open it in the bot's post_init hook."""
    return AsyncConnectionPool(
        conninfo=settings.dsn(),
        open=False,
        min_size=1,
        max_size=5,
        kwargs={"row_factory": dict_row, "autocommit": True},
    )


@contextmanager
def sync_connect(settings: Settings, autocommit: bool = False) -> Iterator[psycopg.Connection]:
    """A plain sync connection for the migrate/seed CLIs."""
    conn = psycopg.connect(settings.dsn(), row_factory=dict_row, autocommit=autocommit)
    try:
        yield conn
    finally:
        conn.close()


def wait_for_db(settings: Settings, attempts: int = 30, delay: float = 1.0) -> None:
    """Block until Postgres accepts a connection, or raise after `attempts`.

    depends_on:[postgres] (and even condition: service_healthy) does not guarantee the DB
    is reachable after a crash/restart, so the app waits explicitly.
    """
    last_err: Exception | None = None
    for i in range(1, attempts + 1):
        try:
            with psycopg.connect(settings.dsn(), connect_timeout=5) as conn:
                conn.execute("SELECT 1")
            print(f"[db] reachable at {settings.pg_host}:{settings.pg_port} (attempt {i})")
            return
        except Exception as e:  # noqa: BLE001 — we genuinely retry any connection failure
            last_err = e
            print(f"[db] not ready (attempt {i}/{attempts}); retrying in {delay}s")
            time.sleep(delay)
    raise SystemExit(f"[db] unreachable after {attempts} attempts: {last_err}")
