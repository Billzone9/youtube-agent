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

# The briefs used by the CONTAMINATED Stage-1 run (before the gate fix), kept so the run output can
# state exactly what changed. The clean run differs from the contaminated one in TWO ways: the gate fix
# (separated axes + stronger species) AND this brief rewrite (explicit film-wide winter/snow wording).
_OLD_BRIEFS = {
    1: "grey wolf pack resting in snowy boreal forest before dawn, wolves lying in snow, misty winter woods",
    2: "grey wolf with thick winter coat walking and trotting through deep snow, wolf in falling snow",
    3: "grey wolf nose to the ground tracking a scent, wolf pack moving single file through deep snow",
    4: "grey wolf howling at dusk, lone wolf silhouette against twilight, wolf in the evening forest",
}

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
    print("TWO variables changed vs the contaminated run — read the result honestly:")
    print("  (1) the GATE FIX: setting axes separated (season/habitat/time judged independently), "
          "species judged feature-first + sceptically; per-beat requiredness.")
    print("  (2) the BRIEF REWRITE: explicit film-wide winter/snow wording. Old → new per beat:")
    for i, _, new in _BEATS:
        print(f"      beat{i} OLD: {_OLD_BRIEFS[i]}")
        print(f"      beat{i} NEW: {new}")
    print(f"measured narration: " + ", ".join(f"beat{i} {lengths[i]:.1f}s" for i, _, _ in _BEATS)
          + f"  (total {sum(lengths.values()):.1f}s)\n")
    report = await produce.curate_report(
        conn, providers, script, channel_id=channel["id"], job_id=job["id"], llm=llm,
        length_of=lambda b: lengths[b.index], required_of=_required_axes)
    await produce._drain_llm(conn, sink, pricing, channel_id=channel["id"], job_id=job["id"])

    _INCIDENTAL = ("habitat", "time_of_day")
    short = {"wild": 0, "species": 0, "season": 0, "incidental": 0}
    total_contradictions = total_echo = 0
    for r in report:
        mark = "✅ PASS" if r["reached_min"] else "❌ NEEDS WORK"
        total_contradictions += r.get("contradictions", 0)
        total_echo += len(r.get("echo_pairs", []))
        print(f"beat{r['beat']} '{r['label']}' — {mark}: {r['verified']} verified "
              f"({r.get('clear', 0)} clear + {len(r.get('uncertain_used', []))} uncertain-used) / "
              f"{r['n_min']} min (target {r['n_target']}, {r['narration_s']}s)  "
              f"[BLOCKING: species, wild, {', '.join(r['required_axes'])}]")
        for a in r["accepted"]:
            u = " (UNCERTAIN)" if a["asset_id"] in r.get("uncertain_used", []) else ""
            print(f"    ✓ {a['asset_id']}{u}  {a['url']}")
        if r.get("contradictions"):
            print(f"    ⚠ {r['contradictions']} evidence↔verdict CONTRADICTION(S) — gate may be miscalibrated")
        if r.get("echo_pairs"):
            print(f"    ⚠ {len(r['echo_pairs'])} CLIP-ECHO pair(s) (near-identical features, DIFFERENT "
                  f"verdicts) — gate gave different answers to the same evidence")

        # rejection breakdown for THIS beat → its dominant reject driver
        beat_tally = {}
        for v in r["verdicts"]:
            if v.get("category") == "reject":
                for ax in (v.get("drivers") or []):
                    beat_tally[ax] = beat_tally.get(ax, 0) + 1
                print(f"    ✗ {v['asset_id']} [{','.join(v.get('drivers') or [])}] "
                      f"species={v.get('species')} wild={v.get('wild')}: {v['reason'][:90]}")
        if beat_tally:
            print(f"    reject breakdown: " + ", ".join(f"{k}×{n}" for k, n in sorted(beat_tally.items())))
        if not r["reached_min"]:
            dominant = max(beat_tally, key=beat_tally.get) if beat_tally else "none"
            bucket = "incidental" if dominant in _INCIDENTAL else dominant
            if bucket in short:
                short[bucket] += 1
            print(f"    → SHORT — dominant reject axis: {dominant}; {r['reason']}")

    # Decision rule (per short beat) with the world-(B) INFEASIBLE-WILD branch made explicit:
    n_short = sum(short.values())
    if total_contradictions > 0 or total_echo > 0:
        verdict = (f"INCONCLUSIVE — {total_contradictions} contradiction(s) + {total_echo} clip-echo "
                   "pair(s): the gate gave inconsistent answers to the same evidence. Recalibrate before "
                   "trusting ANY scarcity conclusion.")
    elif n_short == 0:
        verdict = "PASS — every beat reached n_min. Ready for Stage 2 on your go."
    elif short["wild"] >= 1 and short["wild"] >= short["species"] + short["season"]:
        verdict = (f"INFEASIBLE (WILD) — {short['wild']} short beat(s) dominated by the WILD axis: free "
                   "stock supplies this subject but only CAPTIVE/park footage. No gate tuning fixes a real "
                   "absence → the A/B/C fork (paid wildlife stock / change subject or season). A legitimate result.")
    elif short["species"] + short["season"] >= 1 and short["incidental"] == 0:
        verdict = (f"FAIL (scarcity) — short beat(s) dominated by species/season scarcity. The subject×"
                   "season isn't in free stock → the A/B/C fork.")
    else:
        verdict = (f"MARGINAL — {short['incidental']} short beat(s) dominated by an INCIDENTAL axis "
                   "(habitat/time lock). Re-brief/relax those beats; don't change the subject.")
    bud = await budget_status(conn)
    print(f"\nStage-1 decision: {verdict}")
    print(f"short beats by dominant axis: {dict((k, v) for k, v in short.items() if v)}  "
          f"| contradictions: {total_contradictions} | clip-echo: {total_echo}")
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
