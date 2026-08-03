"""B3 item 3 — the spend gate has TEETH: it BLOCKS with a Telegram approval card, and the decision
actually gates. Approve → the job is flagged spend_approved and its playbook returns to 'producing' so
the next tick resumes it (no re-charge). Reject → the job stays paused, nothing spent.

Run: POSTGRES_HOST=localhost POSTGRES_PORT=5433 ./.venv/bin/python -m scripts.verify_spend_gate
"""
from __future__ import annotations

import asyncio
import sys

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from ytagent import orchestrator, repo
from ytagent.config import load_settings

_fail = 0


def check(label, ok, detail=""):
    global _fail
    print(f"  {'✅' if ok else '❌'} {label}{(' — ' + detail) if detail else ''}")
    if not ok:
        _fail += 1


class _Notifier:
    def __init__(self): self.cards = []; self.resolved = []
    async def send_approval_request(self, *, chat_id, text, approval_id):
        self.cards.append(text); return 100 + approval_id
    async def update_resolved(self, *, chat_id, message_id, text): self.resolved.append(text)


class _Pub:
    mode = "dry_run"


async def _mk_job(conn, cid):
    j = await (await conn.execute(
        "INSERT INTO jobs (channel_id, type, status, stage, payload) "
        "VALUES (%s,'produce','assembling','sourced',%s) RETURNING *",
        [cid, Jsonb({"topic": "african elephant"})])).fetchone()
    return j


async def run():
    settings = load_settings()
    conn = await psycopg.AsyncConnection.connect(settings.dsn(), row_factory=dict_row, autocommit=True)
    ch = await (await conn.execute(
        "INSERT INTO channels (slug, name, status) VALUES ('spendtest','Spend Test','active') RETURNING *"
    )).fetchone()
    cid = ch["id"]
    await conn.execute(
        "INSERT INTO playbooks (channel_id, enabled, cadence, subject_pool, state, per_job_threshold_gbp,"
        " runtime_target_s, n_beats) VALUES (%s,true,'{\"per_week\":2}'::jsonb,'[]'::jsonb,'paused_spend',"
        "5.0,120,4)", [cid])
    notif = _Notifier()
    breakdown = {"total_gbp": 9.10, "tts_chars": 4379, "tts_gbp": 5.82, "music_credits": 2846,
                 "music_gbp": 3.79, "sfx_credits": 0, "sfx_gbp": 0.0, "llm_gbp": 0.02}
    try:
        print("[1] the gate BLOCKS with an approval CARD carrying the breakdown")
        job = await _mk_job(conn, cid)
        res = await orchestrator.submit_spend_for_approval(
            conn, notif, channel=ch, job=job, gate="per_job", estimate=9.10, limit=5.0,
            breakdown=breakdown, chat_id="0")
        check("a 'spend' approval was created", res["approval"]["kind"] == "spend")
        check("card sent with the per-provider breakdown",
              notif.cards and "TTS" in notif.cards[0] and "£9.10" in notif.cards[0])

        print("[2] APPROVE → job flagged spend_approved + playbook 'producing' (resumes next tick)")
        d = await orchestrator.handle_decision(conn, notif, _Pub(), approval_id=res["approval"]["id"],
                                               decision="approve", decided_by="banks")
        check("handled as a spend decision", d.get("kind") == "spend" and d["decision"] == "approve")
        j2 = await repo.jobs.get(conn, job["id"])
        check("job.payload.spend_approved == True", (j2.get("payload") or {}).get("spend_approved") is True)
        pb = await repo.playbooks.get_by_channel(conn, cid)
        check("playbook returned to 'producing'", pb["state"] == "producing", pb["state"])
        check("card resolved to approved", any("approved" in r.lower() for r in notif.resolved))

        print("[3] REJECT → job stays paused, nothing spent")
        job2 = await _mk_job(conn, cid)
        await conn.execute("UPDATE playbooks SET state='paused_spend' WHERE channel_id=%s", [cid])
        res2 = await orchestrator.submit_spend_for_approval(
            conn, notif, channel=ch, job=job2, gate="ceiling", estimate=9.10, limit=200.0, mtd=195.0,
            breakdown=breakdown, chat_id="0")
        d2 = await orchestrator.handle_decision(conn, notif, _Pub(), approval_id=res2["approval"]["id"],
                                                decision="reject", decided_by="banks")
        check("reject handled", d2.get("kind") == "spend" and d2["decision"] == "reject")
        j3 = await repo.jobs.get(conn, job2["id"])
        check("rejected job NOT flagged spend_approved",
              not (j3.get("payload") or {}).get("spend_approved"))
        pb2 = await repo.playbooks.get_by_channel(conn, cid)
        check("playbook stays paused after reject", pb2["state"] == "paused_spend", pb2["state"])
        check("card resolved to rejected", any("rejected" in r.lower() for r in notif.resolved))
    finally:
        await conn.execute("DELETE FROM approvals WHERE channel_id=%s", [cid])
        await conn.execute("DELETE FROM jobs WHERE channel_id=%s", [cid])
        await conn.execute("DELETE FROM playbooks WHERE channel_id=%s", [cid])
        await conn.execute("DELETE FROM channels WHERE id=%s", [cid])
        await conn.close()
    print(f"\n{'ALL PASSED' if _fail == 0 else str(_fail) + ' FAILED'}")
    sys.exit(1 if _fail else 0)


if __name__ == "__main__":
    asyncio.run(run())
