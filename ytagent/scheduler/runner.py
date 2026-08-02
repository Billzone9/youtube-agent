"""The scheduler runner (Slice 6c) — turns due per-channel PLAYBOOKS into produced videos, unattended,
on a cadence, surviving restarts. Postgres-backed queue (the `jobs` table) + a single polling loop;
no broker (the engineering call: at ~2 videos/week a broker is a second source of truth and a failure
mode we don't need — the jobs rows ARE the durable queue).

Commissioning order (6b-bis, enforced): probe → observed distribution → script-to-distribution → source.
The probe verdict GATES commissioning — an infeasible subject is skipped + recorded, and the next is
picked (bounded by the domain-loop cap), never asking Banks. HARD human gates stay: publishing, and
spend above the per-job threshold OR the rolling global ceiling.

A playbook's `state` is its claim/lock (`FOR UPDATE SKIP LOCKED`): idle → producing → idle (on submit,
with the next cadence time) | paused_spend/paused_ceiling (spend gate) | paused_pool (no subject) |
blocked (a hard config failure). One in-flight production per playbook; a restart resumes it.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from psycopg.types.json import Jsonb

from .. import produce, repo
from ..assembly.assembler import AssemblyNoiseError
from ..assembly.density import VisualDensityError
from ..assembly.ffmpeg import FFmpegError
from ..authoring.script import ScriptWriter
from ..events import record_event
from ..sourcing.feasibility import probe_feasibility
from ..tts import TTSScopeError
from .selection import next_subject

_MAX_ATTEMPTS = 3            # transient retries before a job is failed
_BACKOFF_BASE_S = 60         # transient backoff = base × 2^(attempt-1)
_MAX_COMMISSION_TRIES = 6    # bound on the probe-reject loop per commission (the domain cap also bounds it)
_VERDICT_RANK = {"INFEASIBLE": 0, "INCONCLUSIVE-SHALLOW": 0, "MARGINAL": 1, "FEASIBLE": 2}
# failures that are DETERMINISTIC — same spec + clips → same result; retrying only burns compute to fail
# identically. They fail ONCE, alert, and PRESERVE the spent assets for a Banks-fixed resume.
_DETERMINISTIC = (AssemblyNoiseError, VisualDensityError, FFmpegError)


@dataclass
class Deps:
    channel: dict
    providers: list
    tts: object
    music: object
    llm: object
    usage_sink: object
    notifier: object
    publisher: object
    chat_id: str
    description_exemplar: object = None
    now: datetime = None
    summary: dict = field(default_factory=lambda: {
        "resumed": [], "commissioned": [], "skipped_infeasible": [], "submitted": [],
        "paused": [], "failed": [], "retrying": [], "blocked": []})


def next_run_from_cadence(cadence: dict, now: datetime) -> datetime | None:
    """per_week → the next run time (Note 1, now due). per_week=2 → every 3.5 days. 0/absent → None."""
    per_week = float((cadence or {}).get("per_week") or 0)
    return now + timedelta(days=7.0 / per_week) if per_week > 0 else None


async def _db_now(conn) -> datetime:
    return (await (await conn.execute("SELECT now() AS t")).fetchone())["t"]


async def _alert(deps: Deps, text: str) -> None:
    try:
        await deps.notifier.notify(chat_id=deps.chat_id, text=text)
    except Exception:  # noqa: BLE001 — an alert failure must never crash the loop
        pass


# --- claim (FOR UPDATE SKIP LOCKED) ------------------------------------------------------------------
async def _claim(conn, *, now, states, due_only: bool) -> list[dict]:
    """Atomically claim enabled playbooks in `states` (optionally only those DUE), marking them
    'producing' so a concurrent tick skips them. SKIP LOCKED keeps it correct under >1 runner."""
    q = ("SELECT * FROM playbooks WHERE enabled=true AND state = ANY(%s) "
         + ("AND (next_run_at IS NULL OR next_run_at <= %s) " if due_only else "")
         + "ORDER BY next_run_at NULLS FIRST FOR UPDATE SKIP LOCKED")
    async with conn.transaction():
        params = [list(states)] + ([now] if due_only else [])
        rows = await (await conn.execute(q, params)).fetchall()
        for r in rows:
            await conn.execute("UPDATE playbooks SET state='producing' WHERE id=%s", [r["id"]])
    return rows


async def _inflight_job(conn, pb, now) -> dict | None:
    """A produce job for this channel that is mid-flight (not submitted, not failed) and due to run
    (past its retry backoff). Restart survival + retry pickup."""
    cur = await conn.execute(
        "SELECT * FROM jobs WHERE channel_id=%s AND type='produce' AND status='assembling' "
        "AND (stage IS NULL OR stage <> 'submitted') "
        "AND (next_attempt_at IS NULL OR next_attempt_at <= %s) ORDER BY id DESC LIMIT 1",
        [pb["channel_id"], now])
    return await cur.fetchone()


# --- the tick ----------------------------------------------------------------------------------------
async def tick(conn, deps: Deps) -> dict:
    """One scheduler pass: resume any in-flight production, then commission due playbooks. Returns a
    summary of what happened (for logging/tests)."""
    deps.now = await _db_now(conn)
    # 1) resume in-flight/retryable work first (restart survival) — playbooks already 'producing'
    for pb in await _claim(conn, now=deps.now, states=("producing",), due_only=False):
        job = await _inflight_job(conn, pb, deps.now)
        if job:
            deps.summary["resumed"].append(job["id"])
            await _run_job(conn, pb, job, deps)
        else:                                    # 'producing' with no resumable job → return to idle
            await repo.playbooks.set_state(conn, pb["id"], "idle")
    # 2) commission due, idle playbooks
    for pb in await _claim(conn, now=deps.now, states=("idle",), due_only=True):
        await _commission(conn, pb, deps)
    return deps.summary


async def run_forever(conn, deps: Deps, *, interval_s: int = 30, max_ticks: int | None = None) -> None:
    """The poll loop. `max_ticks` bounds it for tests; None runs until cancelled."""
    n = 0
    while max_ticks is None or n < max_ticks:
        try:
            await tick(conn, deps)
        except Exception as e:  # noqa: BLE001 — a tick error must not kill the loop
            await _alert(deps, f"⚠️ scheduler tick error: {e}")
        n += 1
        if max_ticks is not None and n >= max_ticks:
            break
        await asyncio.sleep(interval_s)


# --- commissioning -----------------------------------------------------------------------------------
async def _commission(conn, pb, deps: Deps) -> None:
    """Pick a subject → probe (verdict gate) → seed the distribution → run the production to the gate.
    Rejects infeasible subjects and picks the next, bounded, without asking Banks."""
    for _ in range(_MAX_COMMISSION_TRIES):
        pick = await next_subject(conn, pb, llm=deps.llm)
        if pick.subject is None:                 # pool exhausted / cap reached / needs LLM
            await repo.playbooks.set_state(conn, pb["id"], "paused_pool")
            await _alert(deps, f"⏸️ <b>{deps.channel['name']}</b> paused — no subject to commission "
                               f"({pick.reason}). Add to the subject pool or set a domain.")
            deps.summary["paused"].append(("pool", pick.reason))
            return
        subj = await repo.subjects.record(conn, channel_id=pb["channel_id"], subject=pick.subject,
                                          source=pick.source, status="proposed")
        rep = await probe_feasibility(conn, deps.providers, pick.subject, llm=deps.llm,
                                      channel_id=pb["channel_id"], runtime_s=pb["runtime_target_s"],
                                      n_beats=pb["n_beats"])
        if _VERDICT_RANK.get(rep.verdict, 0) < _VERDICT_RANK.get(pb["min_verdict"], 2):
            await repo.subjects.set_status(conn, subj["id"], "infeasible", verdict=rep.verdict,
                                           pool_depth=rep.pool_depth)
            await record_event(conn, "subject_rejected",
                               message=f"'{pick.subject}' {rep.verdict} (E={rep.pool_depth}) < "
                                       f"{pb['min_verdict']} — skipped, next subject",
                               channel_id=pb["channel_id"])
            deps.summary["skipped_infeasible"].append((pick.subject, rep.verdict))
            continue                             # try the next subject, no ask
        # FEASIBLE enough → commission it (seed the OBSERVED distribution — footage-led, no double-probe)
        dist = {"season": rep.season_dist, "habitat": rep.habitat_dist,
                "time_of_day": rep.time_dist, "shot_type": rep.shot_dist}
        job = await _create_job(conn, pb, pick.subject, dist, deps)
        await repo.subjects.set_status(conn, subj["id"], "selected", verdict=rep.verdict,
                                       pool_depth=rep.pool_depth, job_id=job["id"])
        deps.summary["commissioned"].append((pick.subject, job["id"]))
        await _run_job(conn, pb, job, deps)
        return
    await repo.playbooks.set_state(conn, pb["id"], "paused_pool")
    await _alert(deps, f"⏸️ <b>{deps.channel['name']}</b> paused — too many infeasible candidates.")
    deps.summary["paused"].append(("pool", "too_many_infeasible"))


async def _create_job(conn, pb, subject, dist, deps: Deps) -> dict:
    vp = (deps.channel.get("config") or {}).get("voice_profile") or {}
    cfg = {"runtime_target_s": pb["runtime_target_s"], "n_beats": pb["n_beats"],
           "target_fmt": pb.get("format", "16:9"), "target_w": 1920, "target_h": 1080,
           "budget_credits": 4000, "voice_id": vp.get("voice_id"),
           "model": vp.get("model", "eleven_multilingual_v2")}
    async with conn.transaction():
        job = await repo.jobs.create(conn, channel_id=pb["channel_id"], type="produce",
                                     status="assembling", payload={"topic": subject, "cfg": cfg})
        await record_event(conn, "produce_started", message=f"scheduler commissioned '{subject}'",
                           channel_id=pb["channel_id"], job_id=job["id"])
    # seed the observed distribution into production_state so _st_script does NOT re-probe
    state = produce._initial_state(job)
    state["footage_distribution"] = dist
    await repo.jobs.set_status(conn, job["id"], "assembling", result={"production_state": state})
    return await repo.jobs.get(conn, job["id"])


# --- running one production job to its natural boundary, routing every outcome --------------------------
async def _run_job(conn, pb, job, deps: Deps) -> None:
    try:
        await produce.produce_video(
            conn, deps.notifier, channel=deps.channel, topic=(job.get("payload") or {}).get("topic"),
            providers=deps.providers, tts=deps.tts, music=deps.music, script_writer=ScriptWriter(deps.llm),
            llm_provider=deps.llm, usage_sink=deps.usage_sink,
            description_exemplar=deps.description_exemplar, publisher=deps.publisher,
            chat_id=deps.chat_id, job=job,
            per_job_threshold_gbp=(None if (job.get("payload") or {}).get("spend_approved")
                                   else pb.get("per_job_threshold_gbp")),
            enforce_ceiling=not (job.get("payload") or {}).get("spend_approved"))
        await _on_submitted(conn, pb, job, deps)

    except produce.SpendGatePause as e:
        await _on_spend_pause(conn, pb, job, e, deps)
    except produce.ProductionError as e:                    # sourcing shortfall — expected; next subject
        await record_event(conn, "produce_failed", message=f"sourcing shortfall: {e}",
                           channel_id=pb["channel_id"], job_id=job["id"])
        deps.summary["failed"].append((job["id"], "sourcing"))
        await _commission(conn, pb, deps)                  # try a different subject, no spend lost
    except _DETERMINISTIC as e:                             # render/gate — fail ONCE, do not re-render
        await repo.playbooks.set_state(conn, pb["id"], "blocked")
        await _alert(deps, f"🛑 <b>{deps.channel['name']}</b> job {job['id']} — deterministic failure "
                           f"(spent assets preserved for a fix + resume):\n<code>{e}</code>")
        deps.summary["failed"].append((job["id"], "deterministic"))
    except TTSScopeError as e:                              # config blocker — nothing can be produced
        await repo.playbooks.set_state(conn, pb["id"], "blocked")
        await _alert(deps, f"🛑 <b>{deps.channel['name']}</b> BLOCKED — TTS scope: <code>{e}</code>")
        deps.summary["blocked"].append(job["id"])
    except Exception as e:  # noqa: BLE001 — TRANSIENT (network/5xx/timeout): retry with backoff
        await _on_transient(conn, pb, job, e, deps)


async def _on_submitted(conn, pb, job, deps: Deps) -> None:
    """Production reached the Telegram approval gate. Mark the subject produced, return the playbook to
    idle, and schedule the next run from cadence. Publishing stays Banks's gate downstream."""
    await conn.execute("UPDATE channel_subjects SET status='produced' WHERE job_id=%s", [job["id"]])
    nxt = next_run_from_cadence(pb.get("cadence"), deps.now)
    async with conn.transaction():
        await repo.playbooks.set_state(conn, pb["id"], "idle")
        await repo.playbooks.set_next_run(conn, pb["id"], nxt)
    deps.summary["submitted"].append(job["id"])


async def _on_spend_pause(conn, pb, job, e, deps: Deps) -> None:
    state = "paused_ceiling" if e.gate == "ceiling" else "paused_spend"
    await repo.playbooks.set_state(conn, pb["id"], state)
    where = ("month-to-date + estimate would breach the £{:.0f} ceiling".format(e.limit)
             if e.gate == "ceiling" else "estimate £{:.2f} exceeds the per-job £{:.2f} threshold".format(
                 e.estimate, e.limit))
    await _alert(deps, f"⏸️ <b>{deps.channel['name']}</b> job {job['id']} PAUSED for spend approval — "
                       f"{where}. Approve to proceed (the job resumes without re-charging TTS/music).")
    deps.summary["paused"].append(("spend", e.gate))


async def _on_transient(conn, pb, job, e, deps: Deps) -> None:
    attempts = (job.get("attempts") or 0) + 1
    if attempts >= _MAX_ATTEMPTS:
        await repo.playbooks.set_state(conn, pb["id"], "blocked")
        await conn.execute("UPDATE jobs SET status='failed', attempts=%s, error=%s WHERE id=%s",
                           [attempts, str(e), job["id"]])
        await _alert(deps, f"🛑 <b>{deps.channel['name']}</b> job {job['id']} failed after "
                           f"{attempts} attempts: <code>{e}</code>")
        deps.summary["failed"].append((job["id"], "transient_exhausted"))
        return
    backoff = _BACKOFF_BASE_S * (2 ** (attempts - 1))
    async with conn.transaction():
        await conn.execute(
            "UPDATE jobs SET status='assembling', attempts=%s, next_attempt_at=now() + %s * interval "
            "'1 second', error=%s WHERE id=%s", [attempts, backoff, str(e), job["id"]])
        await repo.playbooks.set_state(conn, pb["id"], "producing")   # stays claimed; retried next tick
        await record_event(conn, "produce_retry",
                           message=f"transient failure (attempt {attempts}/{_MAX_ATTEMPTS}, "
                                   f"backoff {backoff}s): {e}", channel_id=pb["channel_id"], job_id=job["id"])
    deps.summary["retrying"].append((job["id"], attempts))


async def approve_spend(conn, job_id: int) -> None:
    """Banks approved the paused spend: flag the job so its resume bypasses the gate, and return its
    playbook to idle so the next tick resumes it (no TTS/music re-charge — the state machine reloads)."""
    job = await repo.jobs.get(conn, job_id)
    payload = {**(job.get("payload") or {}), "spend_approved": True}
    await conn.execute("UPDATE jobs SET payload=%s WHERE id=%s", [Jsonb(payload), job_id])
    await conn.execute("UPDATE playbooks SET state='producing' WHERE channel_id=%s", [job["channel_id"]])
