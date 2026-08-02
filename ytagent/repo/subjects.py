"""channel_subjects access — the record of every subject offered to a channel + its probe outcome.
Powers no-repeat selection and (Amendment 3) the learning-loop raw material. One row per ATTEMPT,
updated through its lifecycle (proposed → selected → produced, or proposed → infeasible/failed)."""
from __future__ import annotations

# statuses that mean "do not offer this subject again" (in-flight or resolved); 'failed' is retryable.
_USED = ("proposed", "selected", "produced", "infeasible")


async def record(conn, *, channel_id: int, subject: str, source: str = "pool",
                 status: str = "proposed", verdict: str | None = None, pool_depth: int | None = None,
                 job_id: int | None = None) -> dict:
    """Append a subject attempt (records EVERY proposal — Amendment 3)."""
    cur = await conn.execute(
        "INSERT INTO channel_subjects (channel_id, subject, source, status, verdict, pool_depth, job_id) "
        "VALUES (%s,%s,%s,%s,%s,%s,%s) RETURNING *",
        [channel_id, subject, source, status, verdict, pool_depth, job_id])
    return await cur.fetchone()


async def set_status(conn, subject_id: int, status: str, *, verdict: str | None = None,
                     pool_depth: int | None = None, job_id: int | None = None) -> dict:
    cur = await conn.execute(
        "UPDATE channel_subjects SET status = %s, verdict = COALESCE(%s, verdict), "
        "pool_depth = COALESCE(%s, pool_depth), job_id = COALESCE(%s, job_id) "
        "WHERE id = %s RETURNING *",
        [status, verdict, pool_depth, job_id, subject_id])
    return await cur.fetchone()


async def used_subjects(conn, channel_id: int) -> set[str]:
    """Subjects that must NOT be re-offered (in-flight or resolved as produced/infeasible). Case-folded."""
    cur = await conn.execute(
        "SELECT DISTINCT lower(subject) AS s FROM channel_subjects "
        "WHERE channel_id = %s AND status = ANY(%s)",
        [channel_id, list(_USED)])
    return {r["s"] for r in await cur.fetchall()}


async def trailing_infeasible(conn, channel_id: int, *, source: str = "domain", limit: int = 20) -> int:
    """Consecutive most-recent proposals (of `source`) resolved INFEASIBLE, i.e. the run-length of the
    domain loop's failures since its last non-infeasible outcome. Drives Amendment 3's cap."""
    cur = await conn.execute(
        "SELECT status FROM channel_subjects WHERE channel_id = %s AND source = %s "
        "ORDER BY created_at DESC, id DESC LIMIT %s",
        [channel_id, source, limit])
    n = 0
    for r in await cur.fetchall():
        if r["status"] == "infeasible":
            n += 1
        elif r["status"] == "proposed":
            continue                      # not yet resolved — skip, keep scanning back
        else:
            break                         # a produced/selected/failed breaks the infeasible run
    return n


async def list_for_channel(conn, channel_id: int, *, limit: int = 100) -> list[dict]:
    cur = await conn.execute(
        "SELECT * FROM channel_subjects WHERE channel_id = %s ORDER BY created_at DESC, id DESC LIMIT %s",
        [channel_id, limit])
    return await cur.fetchall()
