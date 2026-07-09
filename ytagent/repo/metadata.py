"""video_metadata + video_metrics access.

video_metadata is the authored public text, versioned per (video, language). Two distinct notions:
  * latest authored  = MAX(version)              -> get_latest_authored
  * currently live    = newest non-null applied_at -> get_current
They differ on purpose (the lion: clean regen authored, old leaked text still live under upload-only
scope). video_metrics is reserved for Layer 2 — upsert_metrics exists so the shape is exercised, but
nothing writes to it until analytics read-scope lands.
"""
from __future__ import annotations

from typing import Any

from psycopg.types.json import Jsonb


async def create_version(
    conn, *, video_id: int, channel_id: int, title: str, description: str,
    tags: list[str] | tuple[str, ...] = (), source: str = "manual", language: str = "en",
    research_notes: dict | None = None, applied_at=None, applied_via: str | None = None,
) -> dict:
    """Append the next version for (video_id, language). Version numbers are contiguous per language."""
    row = await (await conn.execute(
        "SELECT COALESCE(MAX(version), 0) + 1 AS next FROM video_metadata "
        "WHERE video_id = %s AND language = %s",
        [video_id, language],
    )).fetchone()
    cur = await conn.execute(
        "INSERT INTO video_metadata (video_id, channel_id, language, version, title, description, "
        " tags, source, research_notes, applied_at, applied_via) "
        "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING *",
        [video_id, channel_id, language, row["next"], title, description,
         Jsonb(list(tags)), source, Jsonb(research_notes or {}), applied_at, applied_via],
    )
    return await cur.fetchone()


async def get_current(conn, video_id: int, language: str = "en") -> dict | None:
    """The version currently LIVE (newest applied_at). None if nothing has been applied yet."""
    cur = await conn.execute(
        "SELECT * FROM video_metadata WHERE video_id = %s AND language = %s AND applied_at IS NOT NULL "
        "ORDER BY applied_at DESC, version DESC LIMIT 1",
        [video_id, language],
    )
    return await cur.fetchone()


async def get_latest_authored(conn, video_id: int, language: str = "en") -> dict | None:
    """The newest authored version, applied or not (MAX(version))."""
    cur = await conn.execute(
        "SELECT * FROM video_metadata WHERE video_id = %s AND language = %s "
        "ORDER BY version DESC LIMIT 1",
        [video_id, language],
    )
    return await cur.fetchone()


async def list_versions(conn, video_id: int, language: str = "en") -> list[dict]:
    cur = await conn.execute(
        "SELECT * FROM video_metadata WHERE video_id = %s AND language = %s ORDER BY version",
        [video_id, language],
    )
    return await cur.fetchall()


async def mark_applied(conn, metadata_id: int, *, applied_at, applied_via: str) -> dict:
    """Record that a version became live (e.g. upload_insert at publish, or studio_manual paste)."""
    cur = await conn.execute(
        "UPDATE video_metadata SET applied_at = %s, applied_via = %s WHERE id = %s RETURNING *",
        [applied_at, applied_via, metadata_id],
    )
    return await cur.fetchone()


async def upsert_metrics(
    conn, *, video_id: int, channel_id: int, period_start, grain: str, idempotency_key: str,
    metadata_version_id: int | None = None, source: str = "youtube_analytics", **fields: Any
) -> dict:
    """RESERVED (Layer 2). Upsert a metrics row keyed by idempotency_key so re-pulls don't duplicate.

    Only whitelisted metric columns are accepted; nothing calls this until analytics read-scope
    lands (a private/zero-view upload has nothing to record — doctrine §4).
    """
    allowed = (
        "impressions", "ctr", "views", "avg_view_duration_s", "watch_time_minutes",
        "subscribers_gained", "search_terms", "traffic_sources",
    )
    cols = ["video_id", "channel_id", "metadata_version_id", "period_start", "grain",
            "source", "idempotency_key"]
    vals: list[Any] = [video_id, channel_id, metadata_version_id, period_start, grain,
                       source, idempotency_key]
    for k in allowed:
        if k in fields:
            cols.append(k)
            v = fields[k]
            vals.append(Jsonb(v) if k in ("search_terms", "traffic_sources") else v)
    updates = ", ".join(f"{c} = EXCLUDED.{c}" for c in cols if c != "idempotency_key")
    placeholders = ", ".join(["%s"] * len(cols))
    cur = await conn.execute(
        f"INSERT INTO video_metrics ({', '.join(cols)}) VALUES ({placeholders}) "
        f"ON CONFLICT (idempotency_key) DO UPDATE SET {updates} RETURNING *",
        vals,
    )
    return await cur.fetchone()
