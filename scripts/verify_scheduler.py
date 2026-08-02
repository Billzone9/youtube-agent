"""Offline verification for Slice 6a — playbook storage + subject SELECTION (no-repeat + the bounded
domain proposal loop). Zero network/spend: a fake LLM stands in for domain proposals. Uses a throwaway
test channel so the real wildlife history is never touched; cleans up after.

Run: POSTGRES_HOST=localhost POSTGRES_PORT=5433 ./.venv/bin/python -m scripts.verify_scheduler
"""
from __future__ import annotations

import asyncio
import sys

import psycopg
from psycopg.rows import dict_row

from ytagent import repo
from ytagent.config import load_settings
from ytagent.providers.base import LLMResponse, TokenUsage
from ytagent.scheduler import CONSECUTIVE_INFEASIBLE_CAP, next_subject

PASS, FAIL = "✅", "❌"
_failures = 0


def check(label, ok, detail=""):
    global _failures
    print(f"  {PASS if ok else FAIL} {label}{(' — ' + detail) if detail else ''}")
    if not ok:
        _failures += 1


class _FakeLLM:
    def __init__(self, subjects): self._s = subjects
    def complete(self, req):
        import json
        return LLMResponse(text=json.dumps({"subjects": self._s}), model="fake",
                           usage=TokenUsage(), request_id="r")


async def run():
    settings = load_settings()
    conn = await psycopg.AsyncConnection.connect(settings.dsn(), row_factory=dict_row, autocommit=True)
    # throwaway test channel (isolated history)
    ch = await (await conn.execute(
        "INSERT INTO channels (slug, name, config) VALUES ('__sched_test__','Sched Test','{}'::jsonb) "
        "ON CONFLICT (slug) DO UPDATE SET name=EXCLUDED.name RETURNING *")).fetchone()
    cid = ch["id"]
    await conn.execute("DELETE FROM channel_subjects WHERE channel_id=%s", [cid])
    await conn.execute("DELETE FROM playbooks WHERE channel_id=%s", [cid])

    try:
        print("[1] playbook repo: due() returns enabled+idle+due; excludes disabled/future/paused")
        pb = await (await conn.execute(
            "INSERT INTO playbooks (channel_id, enabled, subject_pool, domain) "
            "VALUES (%s, true, '[\"lion\",\"cheetah\"]'::jsonb, 'African wildlife') RETURNING *",
            [cid])).fetchone()
        due = await repo.playbooks.due(conn)
        check("enabled+idle+next_run NULL playbook is DUE", any(p["id"] == pb["id"] for p in due))
        await repo.playbooks.update_config(conn, pb["id"], enabled=False)
        due2 = await repo.playbooks.due(conn)
        check("disabled playbook is NOT due", not any(p["id"] == pb["id"] for p in due2))
        await repo.playbooks.update_config(conn, pb["id"], enabled=True)
        await repo.playbooks.set_state(conn, pb["id"], "producing")
        check("non-idle (producing) playbook is NOT due", not any(p["id"] == pb["id"] for p in await repo.playbooks.due(conn)))
        await repo.playbooks.set_state(conn, pb["id"], "idle")
        pb = await repo.playbooks.get_by_channel(conn, cid)

        print("[2] selection: pool order, first NOVEL entry wins")
        pick = await next_subject(conn, pb)
        check("empty history → first pool subject 'lion'", pick.subject == "lion" and pick.source == "pool", pick.reason)
        await repo.subjects.record(conn, channel_id=cid, subject="lion", status="produced", verdict="FEASIBLE")
        pick = await next_subject(conn, pb)
        check("'lion' produced → skip to 'cheetah'", pick.subject == "cheetah")

        print("[3] no-repeat covers in-flight + rejected; 'failed' is retryable")
        await repo.subjects.record(conn, channel_id=cid, subject="cheetah", status="selected")
        pick = await next_subject(conn, pb)   # both pool subjects now used → pool exhausted → domain
        check("both pool used → falls through to domain path", pick.source != "pool" or pick.subject is None, pick.reason)
        await repo.subjects.record(conn, channel_id=cid, subject="wombat", status="failed")
        used = await repo.subjects.used_subjects(conn, cid)
        check("'failed' subject is NOT in used (retryable)", "wombat" not in used)
        check("'produced'/'selected' ARE in used", {"lion", "cheetah"} <= used)

        print("[4] domain proposals via LLM, deduped against ALL history")
        pick = await next_subject(conn, pb, llm=_FakeLLM(["lion", "leopard", "zebra"]))
        check("LLM proposes; 'lion' (already made) skipped → 'leopard'", pick.subject == "leopard" and pick.source == "domain")
        pick = await next_subject(conn, pb, llm=_FakeLLM(["lion", "cheetah"]))   # all already used
        check("all proposals already used → no_novel_proposal", pick.subject is None and pick.reason == "no_novel_proposal")
        pick = await next_subject(conn, pb, llm=None)
        check("domain set but no LLM → needs_llm (honest, no fabrication)", pick.reason == "needs_llm")

        print("[5] pool exhausted + NO domain → pool_exhausted")
        pb_nodomain = {**pb, "domain": None}
        pick = await next_subject(conn, pb_nodomain)
        check("no domain, pool used → pool_exhausted", pick.subject is None and pick.reason == "pool_exhausted")

        print(f"[6] Amendment 3 — the domain loop is BOUNDED at {CONSECUTIVE_INFEASIBLE_CAP} consecutive infeasible")
        for s in ("d1", "d2", "d3"):
            await repo.subjects.record(conn, channel_id=cid, subject=s, source="domain",
                                       status="infeasible", verdict="INFEASIBLE", pool_depth=3)
        cnt = await repo.subjects.trailing_infeasible(conn, cid, source="domain")
        check(f"trailing infeasible counted = {CONSECUTIVE_INFEASIBLE_CAP}", cnt == 3, str(cnt))
        pick = await next_subject(conn, pb, llm=_FakeLLM(["newone"]))
        check("cap reached → pause (cap_reached), even with novel proposals available",
              pick.subject is None and pick.reason == "cap_reached")

        print("[7] a later NON-infeasible domain outcome RESETS the run (cap is CONSECUTIVE, not total)")
        await repo.subjects.record(conn, channel_id=cid, subject="d4", source="domain", status="produced")
        check("trailing infeasible resets to 0 after a produced", await repo.subjects.trailing_infeasible(conn, cid, source="domain") == 0)
        pick = await next_subject(conn, pb, llm=_FakeLLM(["freshsubject"]))
        check("proposals flow again after reset → 'freshsubject'", pick.subject == "freshsubject")

        print("[8] Note 2 (deliberate): an UNRESOLVED 'proposed' row does NOT break an infeasible streak")
        await conn.execute("DELETE FROM channel_subjects WHERE channel_id=%s", [cid])
        # newest→oldest: infeasible, proposed(in-flight), infeasible, infeasible  → streak must count 3
        await repo.subjects.record(conn, channel_id=cid, subject="s1", source="domain", status="infeasible")
        await repo.subjects.record(conn, channel_id=cid, subject="s2", source="domain", status="infeasible")
        await repo.subjects.record(conn, channel_id=cid, subject="s3", source="domain", status="proposed")
        await repo.subjects.record(conn, channel_id=cid, subject="s4", source="domain", status="infeasible")
        check("a 'proposed' between infeasibles is transparent → streak still 3",
              await repo.subjects.trailing_infeasible(conn, cid, source="domain") == 3)
        await repo.subjects.record(conn, channel_id=cid, subject="s5", source="domain", status="produced")
        check("but a 'produced' DOES break the streak → 0",
              await repo.subjects.trailing_infeasible(conn, cid, source="domain") == 0)

    finally:
        await conn.execute("DELETE FROM channel_subjects WHERE channel_id=%s", [cid])
        await conn.execute("DELETE FROM playbooks WHERE channel_id=%s", [cid])
        await conn.execute("DELETE FROM channels WHERE id=%s", [cid])
        await conn.close()

    print(f"\n{'ALL PASSED' if _failures == 0 else str(_failures) + ' CHECK(S) FAILED'}")
    sys.exit(1 if _failures else 0)


if __name__ == "__main__":
    asyncio.run(run())
