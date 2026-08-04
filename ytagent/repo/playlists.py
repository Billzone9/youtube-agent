"""The cohort-playlist store (M1 item 2). ONE unlisted YouTube playlist per (channel, cohort), recorded
here so the create-once is idempotent across publishes and the id is reusable by the Analytics pull.
See migration 0020 and the BACKLOG review (2026-08-04)."""
from __future__ import annotations


async def get(conn, channel_id: int, cohort: str) -> str | None:
    """The recorded cohort playlist id for this (channel, cohort), or None if not created yet."""
    cur = await conn.execute(
        "SELECT youtube_playlist_id FROM cohort_playlists WHERE channel_id = %s AND cohort = %s",
        [channel_id, cohort])
    row = await cur.fetchone()
    return row["youtube_playlist_id"] if row else None


async def save(conn, channel_id: int, cohort: str, youtube_playlist_id: str) -> None:
    """Record the ONE cohort playlist. ON CONFLICT keeps the first (a concurrent create is a no-op)."""
    await conn.execute(
        "INSERT INTO cohort_playlists (channel_id, cohort, youtube_playlist_id) VALUES (%s, %s, %s) "
        "ON CONFLICT (channel_id, cohort) DO NOTHING",
        [channel_id, cohort, youtube_playlist_id])
