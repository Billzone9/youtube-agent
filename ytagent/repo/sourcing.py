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
