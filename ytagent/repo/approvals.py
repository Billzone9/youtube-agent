"""Approvals access — the human gate record."""
from __future__ import annotations


async def create(
    conn, *, channel_id: int, job_id: int, kind: str = "publish", telegram_chat_id: str | None = None
) -> dict:
    cur = await conn.execute(
        "INSERT INTO approvals (channel_id, job_id, kind, telegram_chat_id) "
        "VALUES (%s, %s, %s, %s) RETURNING *",
        [channel_id, job_id, kind, telegram_chat_id],
    )
    return await cur.fetchone()


async def set_message_id(conn, approval_id: int, message_id: int) -> dict:
    cur = await conn.execute(
        "UPDATE approvals SET telegram_message_id = %s WHERE id = %s RETURNING *",
        [message_id, approval_id],
    )
    return await cur.fetchone()


async def decide(conn, approval_id: int, state: str, *, decided_by: str, reason: str | None = None) -> dict:
    cur = await conn.execute(
        "UPDATE approvals SET state = %s, decided_by = %s, reason = %s, decided_at = now() "
        "WHERE id = %s AND state = 'pending' RETURNING *",
        [state, decided_by, reason, approval_id],
    )
    return await cur.fetchone()


async def get(conn, approval_id: int) -> dict | None:
    cur = await conn.execute("SELECT * FROM approvals WHERE id = %s", [approval_id])
    return await cur.fetchone()
