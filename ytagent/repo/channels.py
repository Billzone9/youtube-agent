"""Channels registry access."""
from __future__ import annotations


async def get_by_slug(conn, slug: str) -> dict | None:
    cur = await conn.execute("SELECT * FROM channels WHERE slug = %s", [slug])
    return await cur.fetchone()


async def get_by_id(conn, channel_id: int) -> dict | None:
    cur = await conn.execute("SELECT * FROM channels WHERE id = %s", [channel_id])
    return await cur.fetchone()
