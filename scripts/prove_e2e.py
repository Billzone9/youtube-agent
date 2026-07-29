"""LIVE wolf re-make, TWO-STAGE (Amendment 3).

STAGE 1 (default) — CURATION + VISION GATE ONLY, zero Music spend. Measures the preserved narration
(measure-first), sources each beat through the season/negative/vision curation gates, and reports per
beat whether n_min CONTENT-VERIFIED clips were reached, with every vision verdict. Then STOPS for Banks.
Cost: free stock downloads + a few pence of Haiku (query + vision). No music, no assembly, no upload.

STAGE 2 (PROVE_E2E_STAGE=2) — generate cues + bed + full audio design. NOT built yet; runs only after
Stage 1 is green and Banks says go.

  POSTGRES_HOST=localhost POSTGRES_PORT=5433 ./.venv/bin/python -m scripts.prove_e2e
"""
from __future__ import annotations

import asyncio
import os

import psycopg
from psycopg.rows import dict_row

from ytagent import produce, repo
from ytagent.assembly.ffmpeg import probe
from ytagent.authoring.script import Beat, Fact, Script
from ytagent.budget import budget_status
from ytagent.config import load_settings
from ytagent.events import record_event
from ytagent.providers import ListUsageSink, get_llm_provider
from ytagent.sourcing import get_stock_providers

_NARR = "assets/produced/wolf/narration"

# Reconstructed from job 29's beat LABELS (the shot-briefs weren't persisted; the VO mp3s are intact).
# These steer sourcing only — they never touch the narration.
_BEATS = [
    (1, "Before the pack wakes",
     "grey wolf pack resting in snowy boreal forest before dawn, wolves lying in snow, misty winter woods"),
    (2, "A life made for the cold",
     "grey wolf with thick winter coat walking and trotting through deep snow, wolf in falling snow"),
    (3, "Reading the snow",
     "grey wolf nose to the ground tracking a scent, wolf pack moving single file through deep snow"),
    (4, "The howl at the edge of dark",
     "grey wolf howling at dusk, lone wolf silhouette against twilight, wolf in the evening forest"),
]


def _reconstructed_script(lengths):
    beats = tuple(Beat(index=i, label=lbl, shot_brief=brief, vo="", approx_seconds=int(lengths[i]))
                  for i, lbl, brief in _BEATS)
    return Script(title="Wolf", runtime_target_s=160, word_target=340, beats=beats,
                  facts_used=(Fact("x", True),), provenance={"reused_narration": True})


async def stage1(conn, settings):
    sink = ListUsageSink()
    llm = get_llm_provider(settings, sink)
    providers = [p for p in get_stock_providers(settings) if await p.healthcheck()]
    narration = {i: os.path.abspath(os.path.join(_NARR, f"narr_beat{i}.mp3")) for i, _, _ in _BEATS}
    missing = [p for p in narration.values() if not os.path.exists(p)]
    if not (llm and providers) or missing:
        print(f"Missing prerequisites — llm={bool(llm)} stock={[p.name() for p in providers]} "
              f"missing_narration={missing}")
        raise SystemExit(2)

    lengths = {i: float(probe(narration[i])["duration"]) for i, _, _ in _BEATS}   # MEASURE FIRST
    script = _reconstructed_script(lengths)
    channel = await repo.channels.get_by_slug(conn, "wildlife")
    pricing = await repo.ledger.get_llm_pricing(conn)
    async with conn.transaction():
        job = await repo.jobs.create(conn, channel_id=channel["id"], type="curate", status="running",
                                     payload={"topic": "wolf", "stage": 1})
        await record_event(conn, "curate_started", message="wolf Stage-1 curation + vision gate",
                           channel_id=channel["id"], job_id=job["id"])

    print("=== STAGE 1 — CURATION + VISION GATE (no Music spend, no upload) ===")
    print(f"measured narration: " + ", ".join(f"beat{i} {lengths[i]:.1f}s" for i, _, _ in _BEATS)
          + f"  (total {sum(lengths.values()):.1f}s)\n")
    report = await produce.curate_report(
        conn, providers, script, channel_id=channel["id"], job_id=job["id"], llm=llm,
        length_of=lambda b: lengths[b.index])
    await produce._drain_llm(conn, sink, pricing, channel_id=channel["id"], job_id=job["id"])

    all_ok = True
    for r in report:
        mark = "✅ PASS" if r["reached_min"] else "❌ NEEDS WORK"
        all_ok = all_ok and r["reached_min"]
        print(f"beat{r['beat']} '{r['label']}' — {mark}: {r['verified']} verified / {r['n_min']} min "
              f"(target {r['n_target']}, {r['narration_s']}s)")
        for a in r["accepted"]:
            print(f"    ✓ {a['asset_id']}  {a['url']}")
        for v in r["verdicts"]:
            if not v["ok"]:
                print(f"    ✗ {v['asset_id']} — species={v['species']} wild={v['wild']} "
                      f"season={v['season']}: {v['reason'][:110]}")
        if not r["reached_min"]:
            print(f"    → {r['reason']}")
    bud = await budget_status(conn)
    print(f"\nStage-1 result: {'ALL BEATS REACHED n_min — ready for Stage 2 on your go' if all_ok else 'SOME BEATS SHORT — curation needs a rethink before Stage 2'}")
    print(f"spend this run: LLM (Haiku query+vision) only; month-to-date £{bud['month_spend_gbp']:.2f} "
          f"/ £{bud['ceiling_gbp']:.0f} ({bud['tier']}). No Music spent.")


async def run():
    settings = load_settings()
    stage = os.environ.get("PROVE_E2E_STAGE", "1")
    conn = await psycopg.AsyncConnection.connect(settings.dsn(), row_factory=dict_row, autocommit=True)
    try:
        if stage == "1":
            await stage1(conn, settings)
        else:
            print("Stage 2 (audio design + full re-make) is not built yet — run Stage 1 first.")
            raise SystemExit(2)
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(run())
