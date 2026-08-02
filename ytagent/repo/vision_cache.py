"""vision_verdicts access — the vision gate's per-(clip, subject) verdict cache (Slice 6c). A verdict
is a property of the clip and the expected subject, not the run, so caching it makes a resumed or
repeated production skip the 3 Haiku frames for any clip already judged."""
from __future__ import annotations

from psycopg.types.json import Jsonb


async def get(conn, source: str, asset_id: str, subject: str) -> dict | None:
    """The cached VisionVerdict dict for this clip+subject, or None on a miss."""
    cur = await conn.execute(
        "SELECT verdict FROM vision_verdicts WHERE source=%s AND asset_id=%s AND subject=%s",
        [source, asset_id, subject])
    row = await cur.fetchone()
    return row["verdict"] if row else None


async def put(conn, source: str, asset_id: str, subject: str, verdict: dict) -> None:
    """Upsert a verdict (idempotent on the clip+subject key)."""
    await conn.execute(
        "INSERT INTO vision_verdicts (source, asset_id, subject, verdict) VALUES (%s,%s,%s,%s) "
        "ON CONFLICT (source, asset_id, subject) DO UPDATE SET verdict=EXCLUDED.verdict",
        [source, asset_id, subject, Jsonb(verdict)])
