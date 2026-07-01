"""The audit chokepoint. EVERY state change in the system records an event here, so the
`events` table alone can reconstruct the whole story (the dashboard-ready acid test).
"""
from __future__ import annotations

from typing import Any

from psycopg.types.json import Jsonb


async def record_event(
    conn,
    type: str,
    *,
    message: str | None = None,
    channel_id: int | None = None,
    job_id: int | None = None,
    approval_id: int | None = None,
    data: dict[str, Any] | None = None,
) -> dict:
    cur = await conn.execute(
        "INSERT INTO events (type, message, channel_id, job_id, approval_id, data) "
        "VALUES (%s, %s, %s, %s, %s, %s) RETURNING *",
        [type, message, channel_id, job_id, approval_id, Jsonb(data or {})],
    )
    return await cur.fetchone()
