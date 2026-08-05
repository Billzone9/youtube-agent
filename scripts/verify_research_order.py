"""Regression for the research CONDUCTOR ordering (Phase 1, note 1): the gate must fire BEFORE research
spends — and we assert the SEQUENCE, not merely that both happened (a test where both run would pass
even if research ran first). A fake gate and a fake provider append to a SHARED list; assert
gate-before-research. Also proves resume: a COMPLETE persisted result skips the gate + the provider
entirely (no re-spend). Hermetic (verify-hermeticity-standard.md).

Run: POSTGRES_HOST=localhost POSTGRES_PORT=5433 ./.venv/bin/python -m scripts.verify_research_order
"""
from __future__ import annotations

import asyncio
import os
import sys
import tempfile

import psycopg
from psycopg.rows import dict_row

from ytagent import produce, repo
from ytagent.authoring.grounding import SearchOutcome
from ytagent.authoring.script import Fact
from ytagent.config import load_settings

from scripts._hermetic import high_water, sweep

_fail = 0


def check(label, ok, detail=""):
    global _fail
    print(f"  {'✅' if ok else '❌'} {label}{(' — ' + detail) if detail else ''}")
    if not ok:
        _fail += 1


class _OrderProvider:
    """A research provider that records WHEN it ran, into a shared order list, then finishes."""
    def __init__(self, order):
        self.order = order
        self.calls = 0

    def search(self, subject, *, gathered):
        self.order.append("research")
        self.calls += 1
        return SearchOutcome(facts=(Fact(claim="a verified fact.", established=True),),
                             input_tokens=1000, searches=1, done=True)


async def main():
    settings = load_settings()
    conn = await psycopg.AsyncConnection.connect(settings.dsn(), row_factory=dict_row, autocommit=True)
    hw = await high_water(conn)
    try:
        ch = await repo.channels.get_by_slug(conn, "wildlife")
        job = await repo.jobs.create(conn, channel_id=ch["id"], type="produce", status="assembling",
                                     stage="scripted", payload={"topic": "wolf"})
        work = tempfile.mkdtemp(prefix="res-order-")
        state = {"job_id": job["id"], "channel_id": ch["id"], "topic": "wolf", "workdir": work}

        order: list = []
        orig_gate = produce._research_gate

        async def _fake_gate(conn, state, *, channel, per_job_threshold_gbp, enforce_ceiling):
            order.append("gate")

        produce._research_gate = _fake_gate
        try:
            prov = _OrderProvider(order)
            print("[1] a fresh research: the gate fires BEFORE the provider spends")
            rf = await produce._st_research(conn, state, research_provider=prov, channel=ch)
            check("both the gate and research ran", order.count("gate") == 1 and order.count("research") == 1,
                  str(order))
            check("SEQUENCE is gate → research (gate index < research index)",
                  order.index("gate") < order.index("research"), str(order))
            check("research produced facts + persisted a COMPLETE result",
                  rf is not None and rf.complete and len(rf.facts) == 1 and state.get("research"))

            print("[2] resume: a COMPLETE result skips the gate AND the provider (no re-spend)")
            order.clear()
            prov2 = _OrderProvider(order)
            rf2 = await produce._st_research(conn, state, research_provider=prov2, channel=ch)
            check("a complete persisted result → no gate, no provider call", order == [] and prov2.calls == 0,
                  str(order))
            check("the reloaded result equals the persisted one", rf2 is not None and rf2.complete
                  and len(rf2.facts) == 1)

            print("[3] no provider → research is skipped entirely (facts=None path)")
            s3 = {"job_id": job["id"], "channel_id": ch["id"], "topic": "wolf", "workdir": work}
            rf3 = await produce._st_research(conn, s3, research_provider=None, channel=ch)
            check("no research provider → returns None (no gate, no spend)", rf3 is None)
        finally:
            produce._research_gate = orig_gate
    finally:
        await sweep(conn, hw)
        await conn.close()

    print(f"\n{'✅ ALL PASS' if _fail == 0 else f'❌ {_fail} FAILED'}")
    return 1 if _fail else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
