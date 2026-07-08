"""Videos access — the finished artifact + its QC metadata."""
from __future__ import annotations

from typing import Any

_INSERT_COLS = (
    "channel_id", "job_id", "title", "description", "file_path", "format",
    "duration_s", "width", "height", "fps", "loudness_lufs", "peak_dbfs",
    "noise_floor_db", "size_bytes", "checksum", "provenance_ref", "status",
)


async def create(conn, **fields: Any) -> dict:
    cols = [c for c in _INSERT_COLS if c in fields]
    placeholders = ", ".join(["%s"] * len(cols))
    cur = await conn.execute(
        f"INSERT INTO videos ({', '.join(cols)}) VALUES ({placeholders}) RETURNING *",
        [fields[c] for c in cols],
    )
    return await cur.fetchone()


async def set_status(conn, video_id: int, status: str) -> dict:
    cur = await conn.execute(
        "UPDATE videos SET status = %s WHERE id = %s RETURNING *", [status, video_id]
    )
    return await cur.fetchone()


async def set_published(
    conn, video_id: int, *, youtube_video_id: str | None, privacy_status: str,
    published_at, status: str
) -> dict:
    cur = await conn.execute(
        "UPDATE videos SET status = %s, youtube_video_id = %s, privacy_status = %s, "
        "published_at = %s WHERE id = %s RETURNING *",
        [status, youtube_video_id, privacy_status, published_at, video_id],
    )
    return await cur.fetchone()


async def get(conn, video_id: int) -> dict | None:
    cur = await conn.execute("SELECT * FROM videos WHERE id = %s", [video_id])
    return await cur.fetchone()


async def get_by_job(conn, job_id: int) -> dict | None:
    cur = await conn.execute(
        "SELECT * FROM videos WHERE job_id = %s ORDER BY id LIMIT 1", [job_id]
    )
    return await cur.fetchone()
