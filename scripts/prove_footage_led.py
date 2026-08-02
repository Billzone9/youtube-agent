"""6b-bis PROOF — re-run the SUBJECT THAT FAILED (african elephant) through the fixed FOOTAGE-LED path,
sourcing-only. Probe → observed distribution → ScriptWriter (now REQUIRES the distribution) → source_film.
Reports the new briefs, the new queries, and the new pool numbers against the diagnostic's table. STOPS
before TTS — no TTS, no music, no £ spend (only the pennies of Haiku the probe + sourcing gate need).

Diagnostic baseline (script-first): pool 871 → 18 eligible → 8 clear → FAILED the density floor.

Run: POSTGRES_HOST=localhost POSTGRES_PORT=5433 SUBJECT="african elephant" BEATS=7 RUNTIME=394 \
     ./.venv/bin/python -m scripts.prove_footage_led
"""
from __future__ import annotations

import asyncio
import os

import psycopg
from psycopg.rows import dict_row

from ytagent import repo
from ytagent.assembly.density import min_clips, target_clips
from ytagent.authoring.script import ScriptWriter
from ytagent.config import load_settings
from ytagent.events import record_event
from ytagent.providers import ListUsageSink, get_llm_provider
from ytagent.sourcing import get_stock_providers, source_film
from ytagent.sourcing.feasibility import probe_feasibility


async def run():
    subject = os.environ.get("SUBJECT", "african elephant")
    n_beats = int(os.environ.get("BEATS", "7"))
    runtime = int(os.environ.get("RUNTIME", "394"))
    settings = load_settings()
    sink = ListUsageSink()
    llm = get_llm_provider(settings, sink)
    providers = [p for p in get_stock_providers(settings) if await p.healthcheck()]
    if not (llm and providers):
        raise SystemExit(f"prereqs — llm={bool(llm)} stock={[p.name() for p in providers]}")
    conn = await psycopg.AsyncConnection.connect(settings.dsn(), row_factory=dict_row, autocommit=True)
    ch = await repo.channels.get_by_slug(conn, "wildlife")
    t0 = (await (await conn.execute("SELECT now() AS t")).fetchone())["t"]
    job = await repo.jobs.create(conn, channel_id=ch["id"], type="produce", status="assembling",
                                 payload={"topic": subject, "proof": "footage_led"})
    jid = job["id"]

    print(f"=== 6b-bis PROOF — FOOTAGE-LED '{subject}' ({n_beats} beats, ~{runtime}s), sourcing only ===\n")

    # 1) PROBE → observed distribution (the reliable output; NOT the verdict)
    print("[1] probing observed footage distribution…")
    rep = await probe_feasibility(conn, providers, subject, llm=llm, channel_id=ch["id"],
                                  runtime_s=runtime, n_beats=n_beats)
    dist = {"season": rep.season_dist, "habitat": rep.habitat_dist,
            "time_of_day": rep.time_dist, "shot_type": rep.shot_dist}
    print(f"    verdict {rep.verdict} (E={rep.pool_depth}); distribution:")
    for k, v in dist.items():
        print(f"      {k}: {v}")

    # 2) SCRIPT written TO that distribution (the ScriptWriter now REQUIRES it)
    print("\n[2] scripting to the distribution (footage-led, unsourceable content forbidden)…")
    script = ScriptWriter(llm).write(topic=subject, channel=ch, research=_NoResearch(),
                                     footage_distribution=dist, runtime_target_s=runtime, n_beats=n_beats)
    print(f"    '{script.title}' — new shot-briefs:")
    for b in script.beats:
        print(f"      beat{b.index}: {b.shot_brief[:96]}")

    # 3) SOURCE film-wide → the yield number (STOP here — no TTS)
    print("\n[3] film-wide sourcing (the yield number)…")
    beats = [{"index": b.index, "label": b.label, "brief": b.shot_brief,
              "approx_seconds": b.approx_seconds, "n_min": min_clips(b.approx_seconds),
              "n_target": max(target_clips(b.approx_seconds), min_clips(b.approx_seconds) + 1)}
             for b in script.beats]
    alloc, srep = await source_film(conn, providers, subject=subject, beats=beats, target_fmt="16:9",
                                    target_w=1920, target_h=1080, cache_dir="assets/sourced",
                                    channel_id=ch["id"], job_id=jid, llm=llm)

    # queries generated this run (from events since t0)
    qs = await (await conn.execute(
        "SELECT DISTINCT regexp_replace(message, '^[a-z]+ ''(.*)'' p[0-9].*', '\\1') AS q "
        "FROM events WHERE type='sourcing.search' AND created_at >= %s ORDER BY 1", [t0])).fetchall()

    print("\n=== NEW QUERIES (footage-led) ===")
    for r in qs:
        print(f"    {r['q']}")

    all_ok = all(br["reached_min"] for br in srep["beats"])
    print("\n=== YIELD vs the diagnostic ===")
    print(f"  {'run':<26} {'pool':>6} {'eligible':>9} {'clear':>6} {'allocated':>10}  outcome")
    print(f"  {'The Old Paths (probe-led)':<26} {1731:>6} {157:>9} {52:>6} {26:>10}  full film")
    print(f"  {'African Elephant (fresh)':<26} {871:>6} {18:>9} {8:>6} {9:>10}  FAILED")
    print(f"  {'FOOTAGE-LED (this run)':<26} {srep['pool_candidates']:>6} {srep['eligible']:>9} "
          f"{srep['clear']:>6} {srep['allocated_total']:>10}  {'PASS' if all_ok else 'SHORT'}")
    print("\n  per-beat:")
    for br in srep["beats"]:
        print(f"    beat{br['beat']}: {br['verified']}/{br['n_min']} "
              f"{'✅' if br['reached_min'] else '❌ SHORT'}")

    bud_row = await (await conn.execute(
        "SELECT COALESCE(SUM(amount_gbp),0) c FROM cost_ledger WHERE period_month=date_trunc('month',now())::date")).fetchone()
    print(f"\nRESULT: {'ALL BEATS CLEAR THE DENSITY FLOOR — footage-led fix sufficient' if all_ok else 'STILL SHORT — fix NOT sufficient'}")
    print("No TTS, no music, no £ spend (Haiku probe + vision gate only).")
    await record_event(conn, "proof_footage_led",
                       message=f"footage-led '{subject}': pool {srep['pool_candidates']} → "
                               f"{srep['eligible']} eligible → {srep['clear']} clear → "
                               f"{'PASS' if all_ok else 'SHORT'}",
                       channel_id=ch["id"], job_id=jid, data={"report": {k: srep[k] for k in
                       ("pool_candidates", "eligible", "clear", "allocated_total", "all_reached_min")}})
    await conn.close()


class _NoResearch:
    available = False
    notes = ""


if __name__ == "__main__":
    asyncio.run(run())
