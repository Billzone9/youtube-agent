"""Offline verification for the Slice 6c RUNNER — commissioning (probe-gate), the failure routing
matrix, spend pause, retries (transient/deterministic split), restart survival, and cadence. Zero
network/spend: `probe_feasibility` and `produce.produce_video` are monkeypatched to drive each branch.
Uses a throwaway test channel/playbook and cleans up.

Run: POSTGRES_HOST=localhost POSTGRES_PORT=5433 ./.venv/bin/python -m scripts.verify_scheduler_run
"""
from __future__ import annotations

import asyncio
import sys
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from ytagent import produce, repo
from ytagent.assembly.assembler import AssemblyNoiseError
from ytagent.config import load_settings
import ytagent.scheduler.runner as R
from ytagent.scheduler import Deps, next_run_from_cadence, tick

PASS, FAIL = "✅", "❌"
_failures = 0


def check(label, ok, detail=""):
    global _failures
    print(f"  {PASS if ok else FAIL} {label}{(' — ' + detail) if detail else ''}")
    if not ok:
        _failures += 1


class _Notifier:
    def __init__(self): self.msgs = []
    async def notify(self, *, chat_id, text): self.msgs.append(text)
    async def send_approval_request(self, *, chat_id, text, approval_id): return 1
    async def update_resolved(self, *, chat_id, message_id, text): pass


def _fake_report(verdict):
    return SimpleNamespace(verdict=verdict, pool_depth=30,
                           season_dist={"dry": 10}, habitat_dist={"savanna/grassland": 12},
                           time_dist={"golden/dawn/dusk": 11}, shot_dist={"wide": 12})


async def _fake_probe(conn, providers, subject, *, llm, channel_id, runtime_s, n_beats):
    # 'bad*' subjects are INFEASIBLE; everything else FEASIBLE
    return _fake_report("INFEASIBLE" if subject.startswith("bad") else "FEASIBLE")


def _mk_produce(mode="submit"):
    """A fake produce_video that drives one outcome. 'submit' → reaches the gate (stage=submitted);
    else raises the mapped exception."""
    async def _fake(conn, notifier, *, channel, topic, job, **kw):
        if mode == "submit":
            await conn.execute("UPDATE jobs SET stage='submitted', status='assembled' WHERE id=%s", [job["id"]])
            return {"ok": True, "job_id": job["id"], "submit": {"ok": True}}
        if mode == "spend":
            raise produce.SpendGatePause("per_job", 9.12, limit=5.0)
        if mode == "ceiling":
            raise produce.SpendGatePause("ceiling", 9.12, limit=200.0, mtd=195.0)
        if mode == "deterministic":
            raise AssemblyNoiseError("output failed the noise gate — deleted")
        if mode == "transient":
            raise ConnectionError("temporary network blip")
        if mode == "sourcing":
            raise produce.ProductionError("insufficient distinct footage")
        raise AssertionError(mode)
    return _fake


async def _mk_channel(conn):
    ch = await (await conn.execute(
        "INSERT INTO channels (slug, name, config) VALUES ('__sched_run__','Sched Run',"
        "'{\"voice_profile\":{\"voice_id\":\"v\"}}'::jsonb) "
        "ON CONFLICT (slug) DO UPDATE SET name=EXCLUDED.name RETURNING *")).fetchone()
    await conn.execute("DELETE FROM channel_subjects WHERE channel_id=%s", [ch["id"]])
    await conn.execute("DELETE FROM playbooks WHERE channel_id=%s", [ch["id"]])
    return ch


async def _mk_playbook(conn, ch, *, pool, domain=None, state="idle", next_run=None, per_job=5.0):
    row = await (await conn.execute(
        "INSERT INTO playbooks (channel_id, enabled, cadence, subject_pool, domain, state, "
        " next_run_at, per_job_threshold_gbp, runtime_target_s, n_beats) "
        "VALUES (%s,true,'{\"per_week\":2}'::jsonb,%s,%s,%s,%s,%s,120,4) RETURNING *",
        [ch["id"], Jsonb(pool), domain, state, next_run, per_job])).fetchone()
    return row


def _deps(ch, notif):
    return Deps(channel=ch, providers=[], tts=object(), music=object(), llm=object(),
                usage_sink=object(), notifier=notif, publisher=SimpleNamespace(mode="dry_run"), chat_id="0")


async def run():
    settings = load_settings()
    conn = await psycopg.AsyncConnection.connect(settings.dsn(), row_factory=dict_row, autocommit=True)
    R.probe_feasibility = _fake_probe
    _orig_produce = produce.produce_video
    ch = await _mk_channel(conn)
    cid = ch["id"]

    try:
        print("[1] cadence computation (Note 1 now due)")
        now = datetime(2026, 8, 2, tzinfo=timezone.utc)
        check("per_week=2 → +3.5 days", next_run_from_cadence({"per_week": 2}, now) == now + timedelta(days=3.5))
        check("per_week=0 → None (no auto-cadence)", next_run_from_cadence({"per_week": 0}, now) is None)

        print("[2] commission: infeasible subject SKIPPED (no ask), feasible one commissioned → submitted")
        pb = await _mk_playbook(conn, ch, pool=["bad1", "good1"])
        produce.produce_video = _mk_produce("submit")
        notif = _Notifier()
        await tick(conn, _deps(ch, notif))
        subs = {r["subject"]: r["status"] for r in await repo.subjects.list_for_channel(conn, cid)}
        check("infeasible 'bad1' recorded, not asked", subs.get("bad1") == "infeasible")
        check("feasible 'good1' produced (reached the gate)", subs.get("good1") == "produced")
        pbx = await repo.playbooks.get_by_channel(conn, cid)
        check("playbook back to idle with next_run scheduled (cadence)",
              pbx["state"] == "idle" and pbx["next_run_at"] is not None, pbx["state"])

        print("[3] spend gate → playbook PAUSED + alert (per-job and ceiling)")
        await conn.execute("DELETE FROM channel_subjects WHERE channel_id=%s", [cid])
        pb = await _reset_pb(conn, cid, pool=["good2"])
        produce.produce_video = _mk_produce("spend")
        notif = _Notifier()
        await tick(conn, _deps(ch, notif))
        check("per-job over threshold → paused_spend",
              (await repo.playbooks.get_by_channel(conn, cid))["state"] == "paused_spend")
        check("spend alert sent", any("spend approval" in m.lower() or "PAUSED" in m for m in notif.msgs))

        await conn.execute("DELETE FROM channel_subjects WHERE channel_id=%s", [cid])
        await _reset_pb(conn, cid, pool=["good3"])
        produce.produce_video = _mk_produce("ceiling")
        await tick(conn, _deps(ch, _Notifier()))
        check("ceiling breach → paused_ceiling",
              (await repo.playbooks.get_by_channel(conn, cid))["state"] == "paused_ceiling")

        print("[4] transient failure → RETRY with backoff (not failed); deterministic → FAIL ONCE")
        await conn.execute("DELETE FROM channel_subjects WHERE channel_id=%s", [cid])
        await _reset_pb(conn, cid, pool=["good4"])
        produce.produce_video = _mk_produce("transient")
        await tick(conn, _deps(ch, _Notifier()))
        j = await (await conn.execute("SELECT * FROM jobs WHERE channel_id=%s AND type='produce' ORDER BY id DESC LIMIT 1", [cid])).fetchone()
        check("transient → job kept assembling, attempts=1, backoff set",
              j["status"] == "assembling" and j["attempts"] == 1 and j["next_attempt_at"] is not None)

        await conn.execute("DELETE FROM channel_subjects WHERE channel_id=%s", [cid])
        await _reset_pb(conn, cid, pool=["good5"])
        notif = _Notifier()
        produce.produce_video = _mk_produce("deterministic")
        await tick(conn, _deps(ch, notif))
        j = await (await conn.execute("SELECT * FROM jobs WHERE channel_id=%s AND type='produce' ORDER BY id DESC LIMIT 1", [cid])).fetchone()
        check("deterministic → NOT retried (attempts stays 0), playbook blocked",
              j["attempts"] == 0 and (await repo.playbooks.get_by_channel(conn, cid))["state"] == "blocked")
        check("deterministic alert names 'deterministic'", any("deterministic" in m for m in notif.msgs))

        print("[5] restart survival: an in-flight job is RESUMED by the next tick")
        await conn.execute("DELETE FROM channel_subjects WHERE channel_id=%s", [cid])
        await _reset_pb(conn, cid, pool=["good6"], state="producing")
        job = await repo.jobs.create(conn, channel_id=cid, type="produce", status="assembling",
                                     stage="sourced", payload={"topic": "good6"})
        resumed = {"called_with": None}
        async def _resume_fake(conn, notifier, *, channel, topic, job, **kw):
            resumed["called_with"] = job["id"]
            await conn.execute("UPDATE jobs SET stage='submitted', status='assembled' WHERE id=%s", [job["id"]])
            return {"ok": True, "job_id": job["id"], "submit": {}}
        produce.produce_video = _resume_fake
        await tick(conn, _deps(ch, _Notifier()))
        check("in-flight job resumed (not a fresh commission)", resumed["called_with"] == job["id"])

        print("[6] no subject → PAUSED (pool exhausted, no ask beyond the alert)")
        await conn.execute("DELETE FROM channel_subjects WHERE channel_id=%s", [cid])
        await _reset_pb(conn, cid, pool=[], domain=None)
        notif = _Notifier()
        produce.produce_video = _mk_produce("submit")
        await tick(conn, _deps(ch, notif))
        check("empty pool, no domain → paused_pool + alert",
              (await repo.playbooks.get_by_channel(conn, cid))["state"] == "paused_pool"
              and any("paused" in m.lower() for m in notif.msgs))

    finally:
        produce.produce_video = _orig_produce
        await conn.execute("DELETE FROM channel_subjects WHERE channel_id=%s", [cid])
        await conn.execute("DELETE FROM jobs WHERE channel_id=%s", [cid])
        await conn.execute("DELETE FROM playbooks WHERE channel_id=%s", [cid])
        await conn.execute("DELETE FROM channels WHERE id=%s", [cid])
        await conn.close()

    print(f"\n{'ALL PASSED' if _failures == 0 else str(_failures) + ' CHECK(S) FAILED'}")
    sys.exit(1 if _failures else 0)


async def _reset_pb(conn, cid, *, pool, domain=None, state="idle"):
    await conn.execute("DELETE FROM playbooks WHERE channel_id=%s", [cid])
    row = await (await conn.execute(
        "INSERT INTO playbooks (channel_id, enabled, cadence, subject_pool, domain, state, "
        " per_job_threshold_gbp, runtime_target_s, n_beats) "
        "VALUES (%s,true,'{\"per_week\":2}'::jsonb,%s,%s,%s,5.0,120,4) RETURNING *",
        [cid, Jsonb(pool), domain, state])).fetchone()
    return row


if __name__ == "__main__":
    asyncio.run(run())
