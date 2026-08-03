"""sourced_assets access — the provenance/cache record (mirrors repo/ledger.py conventions)."""
from __future__ import annotations

from typing import Any

from psycopg.types.json import Jsonb

_JSONB = {"tags", "gate_report", "api_response"}


async def get_by_asset(conn, source: str, asset_id: str) -> dict | None:
    cur = await conn.execute(
        "SELECT * FROM sourced_assets WHERE source = %s AND asset_id = %s", [source, asset_id]
    )
    return await cur.fetchone()


async def used_asset_ids(conn, channel_id: int) -> set:
    """The (source, asset_id) clips this channel has already USED across its prior videos — the
    authoritative allocation of every non-failed produce job (jobs.result.production_state.allocation).
    Seed a new production's `exclude_ids` with this so NO CLIP REPEATS ACROSS VIDEOS (the visual-density
    no-reuse rule is otherwise within-spec only — a real hole at Short volume, 1-3 clips × 4/week)."""
    rows = await (await conn.execute(
        "SELECT DISTINCT elem->>'source' AS source, elem->>'asset_id' AS asset_id "
        "FROM jobs j, "
        "     jsonb_each(j.result->'production_state'->'allocation') AS beats(k, arr), "
        "     jsonb_array_elements(arr) AS elem "
        "WHERE j.channel_id = %s AND j.status <> 'failed' "
        "  AND jsonb_typeof(j.result->'production_state'->'allocation') = 'object'",
        [channel_id])).fetchall()
    return {(r["source"], r["asset_id"]) for r in rows if r["source"] and r["asset_id"]}


async def upsert(conn, *, channel_id: int, source: str, asset_id: str, **fields: Any) -> dict:
    """Insert (or return the existing) row keyed by idempotency 'source:asset_id'."""
    cols = ["channel_id", "source", "asset_id", "idempotency_key"]
    vals: list[Any] = [channel_id, source, asset_id, f"{source}:{asset_id}"]
    for k, v in fields.items():
        cols.append(k)
        vals.append(Jsonb(v) if k in _JSONB else v)
    placeholders = ", ".join(["%s"] * len(cols))
    cur = await conn.execute(
        f"INSERT INTO sourced_assets ({', '.join(cols)}) VALUES ({placeholders}) "
        "ON CONFLICT (idempotency_key) DO UPDATE SET local_path = EXCLUDED.local_path "
        "RETURNING *",
        vals,
    )
    return await cur.fetchone()
