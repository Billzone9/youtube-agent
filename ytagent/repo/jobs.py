"""Jobs access."""
from __future__ import annotations

from typing import Any

from psycopg.types.json import Jsonb


async def create(
    conn,
    *,
    channel_id: int,
    type: str,
    status: str = "queued",
    stage: str | None = None,
    payload: dict[str, Any] | None = None,
) -> dict:
    cur = await conn.execute(
        "INSERT INTO jobs (channel_id, type, status, stage, payload) "
        "VALUES (%s, %s, %s, %s, %s) RETURNING *",
        [channel_id, type, status, stage, Jsonb(payload or {})],
    )
    return await cur.fetchone()


async def set_status(
    conn, job_id: int, status: str, *, result: dict[str, Any] | None = None, error: str | None = None
) -> dict:
    cur = await conn.execute(
        "UPDATE jobs SET status = %s, "
        "result = COALESCE(%s, result), "
        "error = COALESCE(%s, error) "
        "WHERE id = %s RETURNING *",
        [status, Jsonb(result) if result is not None else None, error, job_id],
    )
    return await cur.fetchone()


async def get(conn, job_id: int) -> dict | None:
    cur = await conn.execute("SELECT * FROM jobs WHERE id = %s", [job_id])
    return await cur.fetchone()
