"""Hermetic-by-default helper for verify_*.py — see `verify-hermeticity-standard.md`.

WHY THIS EXISTS (not hygiene — a safety gate). A verify that leaves production-state rows behind is an
accidental-upload path: a leftover `pending` publish approval becomes a tap-to-upload card the moment the
YouTube token is armed. On 2026-08-04 exactly this had accumulated **32 armed publish cards + 9 stuck
jobs** from verifies that created jobs/videos/approvals and never fully cleaned them (partial per-script
DELETEs kept missing the rows the pipeline created internally). So: no verify may leave production state.

HOW. `hermetic(conn)` is an async context manager built on a HIGH-WATER MARK: it records `max(id)` of
every id-keyed production table on entry and, on exit (even on exception), deletes every row created
during the block (`id > mark`), child tables first for FK safety. Serial ids are monotonic, so
`id > mark` == "created in this run" — no per-row bookkeeping, and it works no matter how many
transactions the code-under-test opens (which is why the connection is autocommit). `cohort_playlists`
has no `id`, so it's cleaned by `created_at`. Playbook rows are SNAPSHOT+RESTORED (enabled/state/
next_run_at) so a scheduler verify that enables the playbook can't leave it armed for an unattended run.

It does NOT restore arbitrary UPDATEs to other pre-existing rows (channel config etc.); a verify that
mutates one must snapshot+restore it itself. `assert_clean(conn, marks)` fails loud if anything slipped.
"""
from __future__ import annotations

from contextlib import asynccontextmanager

# id-keyed production tables in FK-safe DELETE order (children before parents). Never includes
# `channels` (seed/config). `playbooks` inserts are cleaned here; the seed row is restored separately.
_ID_TABLES_CHILD_FIRST = (
    "events",           # -> channels, jobs, approvals
    "video_metrics",    # -> channels, videos, video_metadata
    "video_metadata",   # -> videos, channels
    "approvals",        # -> channels, jobs
    "cost_ledger",      # -> channels, jobs
    "revenue_ledger",   # -> channels
    "sourced_assets",   # -> channels, jobs
    "channel_subjects", # -> channels, jobs
    "vision_verdicts",  # standalone
    "videos",           # -> jobs, channels
    "jobs",             # -> channels
    "playbooks",        # -> channels (test-INSERTED playbooks only; seed row restored, not deleted)
)

# the "did a verify leave an accidental-upload card?" invariant tables
_DANGER_TABLES = ("approvals", "videos", "jobs")


async def _max_id(conn, table: str) -> int:
    cur = await conn.execute(f"SELECT COALESCE(MAX(id), 0) AS m FROM {table}")
    return (await cur.fetchone())["m"]


async def _snapshot_playbooks(conn) -> list[dict]:
    cur = await conn.execute("SELECT id, enabled, state, next_run_at FROM playbooks")
    return await cur.fetchall()


async def high_water(conn) -> dict:
    """Capture the pre-run state a `sweep` will roll back to. Call right after `connect`."""
    marks = {t: await _max_id(conn, t) for t in _ID_TABLES_CHILD_FIRST}
    cur = await conn.execute("SELECT now() AS t")
    marks["_start_ts"] = (await cur.fetchone())["t"]
    marks["_playbooks"] = await _snapshot_playbooks(conn)
    return marks


async def sweep(conn, marks: dict) -> None:
    """Undo everything created since `high_water(conn)`: delete inserted rows (child tables first),
    clean id-less `cohort_playlists` by time, and restore the pre-run playbook arming. Idempotent."""
    for t in _ID_TABLES_CHILD_FIRST:
        await conn.execute(f"DELETE FROM {t} WHERE id > %s", [marks[t]])
    await conn.execute("DELETE FROM cohort_playlists WHERE created_at >= %s", [marks["_start_ts"]])
    for pb in marks["_playbooks"]:
        await conn.execute(
            "UPDATE playbooks SET enabled=%s, state=%s, next_run_at=%s WHERE id=%s",
            [pb["enabled"], pb["state"], pb["next_run_at"], pb["id"]])


@asynccontextmanager
async def hermetic(conn):
    """Wrap a verify's DB work. On exit, every row it inserted is deleted and the playbook seed rows are
    restored to their pre-run enabled/state/next_run_at — even if the body raised."""
    marks = await high_water(conn)
    try:
        yield marks
    finally:
        await sweep(conn, marks)


async def assert_clean(conn, marks: dict) -> list[str]:
    """Return a list like ['approvals:2','videos:1'] of production rows left behind (empty == clean).
    A verify calls this before its hermetic block exits to prove it did not pollute; `health.py` calls
    the DB-wide form after the whole suite."""
    dirty = []
    for t in _DANGER_TABLES:
        cur = await conn.execute(f"SELECT count(*) AS n FROM {t} WHERE id > %s", [marks[t]])
        n = (await cur.fetchone())["n"]
        if n:
            dirty.append(f"{t}:{n}")
    return dirty
