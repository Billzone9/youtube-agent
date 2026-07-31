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
# These steer sourcing only — they never touch the narration. The film's SEASON (winter/snow) is a
# film-level constraint carried on EVERY beat; TIME is locked only where the label names it.
_BEATS = [
    (1, "Before the pack wakes",
     "grey wolf pack in deep snow in winter boreal forest before dawn, wolves resting in the snow at first light"),
    (2, "A life made for the cold",
     "grey wolf with thick winter coat walking and trotting through deep snow, wolf in falling snow in winter"),
    (3, "Reading the snow",
     "grey wolf nose to the ground tracking a scent in snow, wolf pack moving single file through deep winter snow"),
    (4, "The howl at the edge of dark",
     "grey wolf howling in the snow at dusk in winter, lone wolf silhouette against snowy twilight in the evening"),
]

# Per-beat axis requiredness (the Amendment). Season BLOCKS on every beat (film-level winter). Time
# BLOCKS only where the beat's meaning locks it: beat1 "Before the pack wakes" → dawn; beat4 "edge of
# dark" → dusk. Habitat stays ADVISORY (the labels don't lock it; the brief only incidentally names
# forest). Derived here from the reconstructed brief because job 29 did not persist the VO text — the
# general rule reads the VO; this is the honest wolf-specific stand-in, reported so Banks sees it.
_TIME_LOCKED = {1, 4}


def _required_axes(beat):
    req = {"season"}
    if beat.index in _TIME_LOCKED:
        req.add("time_of_day")
    return frozenset(req)


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
        length_of=lambda b: lengths[b.index], required_of=_required_axes)
    await produce._drain_llm(conn, sink, pricing, channel_id=channel["id"], job_id=job["id"])

    all_ok = True
    for r in report:
        mark = "✅ PASS" if r["reached_min"] else "❌ NEEDS WORK"
        all_ok = all_ok and r["reached_min"]
        print(f"beat{r['beat']} '{r['label']}' — {mark}: {r['verified']} verified / {r['n_min']} min "
              f"(target {r['n_target']}, {r['narration_s']}s)  [BLOCKING: species, wild, "
              f"{', '.join(r['required_axes'])}]")
        for a in r["accepted"]:
            print(f"    ✓ {a['asset_id']}  {a['url']}")
        # per-axis rejection breakdown (the clean-evidence answer): which axis each miss died on
        axis_tally = {}
        for v in r["verdicts"]:
            if not v["ok"]:
                for ax in (v.get("failed_axes") or []):
                    axis_tally[ax] = axis_tally.get(ax, 0) + 1
                print(f"    ✗ {v['asset_id']} — failed {','.join(v.get('failed_axes') or [])}: {v['reason'][:100]}")
        if axis_tally:
            print(f"    rejection breakdown: " + ", ".join(f"{k}×{n}" for k, n in sorted(axis_tally.items())))
        if not r["reached_min"]:
            print(f"    → {r['reason']}")

    # SPECIFY-2 decision rule, applied to the numbers
    short = [r for r in report if not r["reached_min"]]
    dom = {}
    for r in report:
        for v in r["verdicts"]:
            for ax in (v.get("failed_axes") or []):
                dom[ax] = dom.get(ax, 0) + 1
    scarcity = sum(dom.get(a, 0) for a in ("species", "wild", "season"))
    incidental = sum(dom.get(a, 0) for a in ("habitat", "time_of_day"))
    if not short:
        verdict = "PASS — every beat reached n_min. Ready for Stage 2 on your go."
    elif scarcity >= incidental:
        verdict = "FAIL — shortfall is subject×season scarcity (species/wild/season dominate). The A/B/C fork."
    else:
        verdict = "MARGINAL — shortfall is incidental (habitat/time). Re-brief the short beats, don't change subject."
    bud = await budget_status(conn)
    print(f"\nStage-1 decision: {verdict}")
    print(f"per-axis totals across all beats: {dict(sorted(dom.items()))}")
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
