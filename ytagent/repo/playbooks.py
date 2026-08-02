"""Playbooks access — the per-channel scheduling policy (Slice 6). One row per channel."""
from __future__ import annotations

from typing import Any

from psycopg.types.json import Jsonb


async def get_by_channel(conn, channel_id: int) -> dict | None:
    cur = await conn.execute("SELECT * FROM playbooks WHERE channel_id = %s", [channel_id])
    return await cur.fetchone()


async def due(conn, *, now=None) -> list[dict]:
    """Enabled playbooks whose next_run_at has arrived (or was never set) and which are idle — the
    scheduler's work-list. `now` defaults to the DB clock (kept out of app code so resume is stable)."""
    cur = await conn.execute(
        "SELECT * FROM playbooks WHERE enabled = true AND state = 'idle' "
        "AND (next_run_at IS NULL OR next_run_at <= COALESCE(%s, now())) "
        "ORDER BY next_run_at NULLS FIRST",
        [now],
    )
    return await cur.fetchall()


async def set_state(conn, playbook_id: int, state: str) -> dict:
    cur = await conn.execute(
        "UPDATE playbooks SET state = %s WHERE id = %s RETURNING *", [state, playbook_id])
    return await cur.fetchone()


async def set_next_run(conn, playbook_id: int, next_run_at) -> dict:
    cur = await conn.execute(
        "UPDATE playbooks SET next_run_at = %s WHERE id = %s RETURNING *", [next_run_at, playbook_id])
    return await cur.fetchone()


async def update_config(conn, playbook_id: int, **fields: Any) -> dict:
    """Patch editable playbook fields (cadence/subject_pool/domain/enabled/thresholds/…). Only known
    columns; jsonb fields are wrapped. Powers the Telegram/dashboard 'no-code' control seam."""
    allowed = {"enabled", "cadence", "subject_pool", "domain", "format", "min_verdict",
               "per_job_threshold_gbp", "runtime_target_s", "n_beats", "next_run_at", "state"}
    sets, vals = [], []
    for k, v in fields.items():
        if k not in allowed:
            continue
        sets.append(f"{k} = %s")
        vals.append(Jsonb(v) if k in ("cadence", "subject_pool") else v)
    if not sets:
        return await (await conn.execute("SELECT * FROM playbooks WHERE id = %s", [playbook_id])).fetchone()
    vals.append(playbook_id)
    cur = await conn.execute(
        f"UPDATE playbooks SET {', '.join(sets)} WHERE id = %s RETURNING *", vals)
    return await cur.fetchone()
