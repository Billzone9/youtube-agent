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
    def __init__(self): self.msgs = []; self.cards = []
    async def notify(self, *, chat_id, text): self.msgs.append(text)
    async def send_approval_request(self, *, chat_id, text, approval_id):
        self.cards.append(text); return 1
    async def update_resolved(self, *, chat_id, message_id, text): pass


def _fake_report(verdict, E=30):
    return SimpleNamespace(verdict=verdict, pool_depth=E,
                           season_dist={"dry": 10}, habitat_dist={"savanna/grassland": 12},
                           time_dist={"golden/dawn/dusk": 11}, shot_dist={"wide": 12})


async def _fake_probe(conn, providers, subject, *, llm, channel_id, runtime_s, n_beats):
    # NEW GATE: only the pool-depth FLOOR skips. 'shallow*' → E<5 (skip); 'lowyield*' → deep pool but
    # INFEASIBLE verdict (PROCEEDS — the verdict no longer gates); everything else → deep + FEASIBLE.
    if subject.startswith("shallow"):
        return _fake_report("INCONCLUSIVE-SHALLOW", E=2)
    if subject.startswith("lowyield"):
        return _fake_report("INFEASIBLE", E=30)
    return _fake_report("FEASIBLE", E=30)


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
            err = produce.ProductionError("insufficient distinct footage — held 8 clear")
            err.clear_count = 8
            raise err
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


class _FakeTTS:
    """A tts stub whose credit_status returns a FIXED dict (or None). Lets the recurring-gate test drive
    the exact failing state: KEY remaining large (rollover) but RECURRING remaining exhausted."""
    def __init__(self, cs): self._cs = cs
    def credit_status(self, *, key_cap=None, recurring_allowance=None): return self._cs


def _mk_short(mode="submit"):
    """A fake produce.produce_short driving one outcome."""
    async def _fake(conn, notifier, *, channel, subject, brief, **kw):
        if mode == "submit":
            j = await (await conn.execute(
                "INSERT INTO jobs (channel_id, type, status, payload) VALUES (%s,'produce','assembling',%s) "
                "RETURNING id", [channel["id"], Jsonb({"topic": subject, "format": "short"})])).fetchone()
            return {"ok": True, "job_id": j["id"], "submit": {"ok": True}}
        if mode == "nomatch":
            raise produce.ProductionError("short sourcing: no candidates")
        if mode == "bed":
            raise produce.BedUnavailableError("no attested bed")
        if mode == "qc":
            raise produce.ShortQCError("LUFS drift")
        raise AssertionError(mode)
    return _fake


def _deps(ch, notif, *, tts=None, recurring_allowance=None):
    return Deps(channel=ch, providers=[], tts=tts or object(), music=object(), llm=object(),
                usage_sink=object(), notifier=notif, publisher=SimpleNamespace(mode="dry_run"), chat_id="0",
                recurring_allowance=recurring_allowance)


async def run():
    settings = load_settings()
    conn = await psycopg.AsyncConnection.connect(settings.dsn(), row_factory=dict_row, autocommit=True)
    R.probe_feasibility = _fake_probe
    _orig_produce = produce.produce_video
    _orig_short = produce.produce_short
    ch = await _mk_channel(conn)
    cid = ch["id"]

    try:
        print("[1] cadence computation (Note 1 now due)")
        now = datetime(2026, 8, 2, tzinfo=timezone.utc)
        check("per_week=2 → +3.5 days", next_run_from_cadence({"per_week": 2}, now) == now + timedelta(days=3.5))
        check("per_week=0 → None (no auto-cadence)", next_run_from_cadence({"per_week": 0}, now) is None)

        print("[2] gate redesign: pool-depth FLOOR skips E<5; the VERDICT no longer gates")
        pb = await _mk_playbook(conn, ch, pool=["shallow1", "lowyield1"])
        produce.produce_video = _mk_produce("submit")
        notif = _Notifier()
        await tick(conn, _deps(ch, notif))
        subs = {r["subject"]: r["status"] for r in await repo.subjects.list_for_channel(conn, cid)}
        check("E<5 subject skipped on the pool-depth floor", subs.get("shallow1") == "infeasible")
        check("INFEASIBLE-verdict but deep-pool subject PROCEEDS + produces (verdict no longer gates)",
              subs.get("lowyield1") == "produced")
        pbx = await repo.playbooks.get_by_channel(conn, cid)
        check("playbook back to idle with next_run scheduled (cadence)",
              pbx["state"] == "idle" and pbx["next_run_at"] is not None, pbx["state"])

        print("[2c] subject-terms FLAG is non-blocking: a bare polysemous term still commissions")
        await conn.execute("DELETE FROM channel_subjects WHERE channel_id=%s", [cid])
        await _reset_pb(conn, cid, pool=["lion"])
        produce.produce_video = _mk_produce("submit")
        await tick(conn, _deps(ch, _Notifier()))
        flagged = await (await conn.execute(
            "SELECT count(*) n FROM events WHERE channel_id=%s AND type='subject_term_flagged'", [cid])).fetchone()
        check("bare 'lion' emitted a subject_term_flagged event", flagged["n"] >= 1, str(flagged["n"]))
        lion_status = {r["subject"]: r["status"] for r in await repo.subjects.list_for_channel(conn, cid)}
        check("...and STILL commissioned (flag did not block)", lion_status.get("lion") == "produced",
              lion_status.get("lion"))

        print("[2b] sourcing is the REAL gate: consecutive sourcing failures capped at 3 → pause")
        await conn.execute("DELETE FROM channel_subjects WHERE channel_id=%s", [cid])
        await _reset_pb(conn, cid, pool=["s1", "s2", "s3", "s4"])
        produce.produce_video = _mk_produce("sourcing")
        notif = _Notifier()
        await tick(conn, _deps(ch, notif))
        shorts = await (await conn.execute(
            "SELECT subject, clear_count FROM channel_subjects WHERE channel_id=%s AND verdict='SOURCING_SHORT'",
            [cid])).fetchall()
        check("exactly 3 subjects failed at sourcing then it paused (4th not attempted)", len(shorts) == 3, str(len(shorts)))
        check("each records the ACTUAL clear count (8), not the probe guess", all(r["clear_count"] == 8 for r in shorts))
        check("paused_pool after 3 consecutive sourcing failures + alert",
              (await repo.playbooks.get_by_channel(conn, cid))["state"] == "paused_pool"
              and any("sourcing" in m.lower() for m in notif.msgs))

        print("[3] spend gate → playbook PAUSED + alert (per-job and ceiling)")
        await conn.execute("DELETE FROM channel_subjects WHERE channel_id=%s", [cid])
        pb = await _reset_pb(conn, cid, pool=["good2"])
        produce.produce_video = _mk_produce("spend")
        notif = _Notifier()
        await tick(conn, _deps(ch, notif))
        check("per-job over threshold → paused_spend",
              (await repo.playbooks.get_by_channel(conn, cid))["state"] == "paused_spend")
        check("spend APPROVAL CARD sent (inline gate, not a plain alert)",
              any("spend approval" in c.lower() for c in notif.cards))
        spend_appr = await (await conn.execute(
            "SELECT id, job_id FROM approvals WHERE channel_id=%s AND kind='spend' "
            "ORDER BY id DESC LIMIT 1", [cid])).fetchone()
        check("a 'spend' approval row exists for the paused job", spend_appr is not None)

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

        print("[7] RECURRING cadence gate — paces on remaining_recurring, NOT the rollover-inflated key")
        await conn.execute("DELETE FROM channel_subjects WHERE channel_id=%s", [cid])
        await _reset_pb(conn, cid, pool=["good7"])          # default format_mix ["16:9"] → a film
        produce.produce_video = _mk_produce("submit")       # would succeed IF the gate let it through
        # THE FAILING CASE: key remaining HUGE (rollover), recurring EXHAUSTED → must PAUSE, not commission.
        tts_exhausted = _FakeTTS({"remaining": 50000, "remaining_recurring": 100})
        notif = _Notifier()
        await tick(conn, _deps(ch, notif, tts=tts_exhausted, recurring_allowance=30000))
        pbx = await repo.playbooks.get_by_channel(conn, cid)
        # a film needs ~6850 EL; remaining_recurring=100 < 6850 → pause. If the gate read the KEY remaining
        # (50000) instead, 6850 < 50000 → it would PROCEED. So paused_ceiling IS the proof it read the right field.
        check("recurring exhausted (100) DESPITE key remaining 50000 → PAUSED (proves it read remaining_recurring)",
              pbx["state"] == "paused_ceiling", pbx["state"])
        check("no subject was commissioned (the gate is BEFORE the commit)",
              len(await repo.subjects.list_for_channel(conn, cid)) == 0)

        print("[7b] cadence gate FAILS CLOSED when the credit read is unavailable (None)")
        await conn.execute("DELETE FROM channel_subjects WHERE channel_id=%s", [cid])
        await _reset_pb(conn, cid, pool=["good7b"])
        notif = _Notifier()
        await tick(conn, _deps(ch, notif, tts=_FakeTTS(None), recurring_allowance=30000))
        check("credit_status None → PAUSED (fail closed, not commissioning blind)",
              (await repo.playbooks.get_by_channel(conn, cid))["state"] == "paused_ceiling"
              and any("recurring" in m.lower() for m in notif.msgs))

        print("[8] format-mix routes 9:16 to produce_short; NoMatch skips ONE (no 3× retry), bed→blocked")
        produce.produce_short = _mk_short("submit")
        await conn.execute("DELETE FROM channel_subjects WHERE channel_id=%s", [cid])
        pb = await _reset_pb(conn, cid, pool=["s_ok"])
        await conn.execute("UPDATE playbooks SET format_mix='[\"9:16\"]'::jsonb WHERE channel_id=%s", [cid])
        notif = _Notifier()
        await tick(conn, _deps(ch, notif))                  # no recurring_allowance → gate off; Short est=0 anyway
        subs = {r["subject"]: r["status"] for r in await repo.subjects.list_for_channel(conn, cid)}
        check("Short subject marked produced", subs.get("s_ok") == "produced", str(subs))
        check("playbook rescheduled to idle (not stuck producing)",
              (await repo.playbooks.get_by_channel(conn, cid))["state"] == "idle")

        await conn.execute("DELETE FROM channel_subjects WHERE channel_id=%s", [cid])
        await _reset_pb(conn, cid, pool=["s_bad"])
        await conn.execute("UPDATE playbooks SET format_mix='[\"9:16\"]'::jsonb WHERE channel_id=%s", [cid])
        produce.produce_short = _mk_short("nomatch")
        await tick(conn, _deps(ch, _Notifier()))
        check("Short NoMatch → subject infeasible, playbook idle (skip to next tick, no 3× retry)",
              (await repo.playbooks.get_by_channel(conn, cid))["state"] == "idle"
              and {r["status"] for r in await repo.subjects.list_for_channel(conn, cid)} == {"infeasible"})

        await conn.execute("DELETE FROM channel_subjects WHERE channel_id=%s", [cid])
        await _reset_pb(conn, cid, pool=["s_nobed"])
        await conn.execute("UPDATE playbooks SET format_mix='[\"9:16\"]'::jsonb WHERE channel_id=%s", [cid])
        produce.produce_short = _mk_short("bed")
        await tick(conn, _deps(ch, _Notifier()))
        check("Short empty-bed → playbook BLOCKED (config; not retried)",
              (await repo.playbooks.get_by_channel(conn, cid))["state"] == "blocked")

    finally:
        produce.produce_video = _orig_produce
        produce.produce_short = _orig_short
        await conn.execute("DELETE FROM channel_subjects WHERE channel_id=%s", [cid])
        await conn.execute("DELETE FROM approvals WHERE channel_id=%s", [cid])   # spend cards FK jobs
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
