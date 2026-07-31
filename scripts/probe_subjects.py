"""Run the footage-feasibility probe on the four approved subjects BEFORE any script is written.
Exploratory: species + wild only, setting DISTRIBUTION reported. Pennies of Haiku, no Music, no TTS.
Film #2 is chosen from the TERRESTRIAL three (elephant/giraffe/zebra); the whale is probed for data but
is the Phase-2 cross-biome test, not film #2 (Refinement 2).

Run: POSTGRES_HOST=localhost POSTGRES_PORT=5433 ./.venv/bin/python -m scripts.probe_subjects
"""
from __future__ import annotations

import asyncio

import psycopg
from psycopg.rows import dict_row

from ytagent import repo
from ytagent.config import load_settings
from ytagent.providers import ListUsageSink, get_llm_provider
from ytagent.sourcing import get_stock_providers
from ytagent.sourcing.feasibility import probe_feasibility

_TERRESTRIAL = ["African elephant", "giraffe", "zebra"]
_PHASE2 = ["humpback whale"]                       # probed for data; not a film-#2 candidate (Refinement 2)


def _dist(d):
    return ", ".join(f"{k}:{n}" for k, n in d.items()) or "—"


async def run():
    settings = load_settings()
    sink = ListUsageSink()
    llm = get_llm_provider(settings, sink)
    providers = [p for p in get_stock_providers(settings) if await p.healthcheck()]
    if not (llm and providers):
        print(f"missing prerequisites — llm={bool(llm)} stock={[p.name() for p in providers]}")
        raise SystemExit(2)
    conn = await psycopg.AsyncConnection.connect(settings.dsn(), row_factory=dict_row, autocommit=True)
    ch = await repo.channels.get_by_slug(conn, "wildlife")
    reports = []
    try:
        for subject in _TERRESTRIAL + _PHASE2:
            r = await probe_feasibility(conn, providers, subject, llm=llm, channel_id=ch["id"])
            reports.append(r)
            tag = "" if subject in _TERRESTRIAL else "  [PHASE-2 cross-biome — not a film-#2 candidate]"
            print(f"\n=== {subject}{tag} → {r.verdict} ===")
            print(f"  pool depth E={r.pool_depth}  sampled={r.sampled}  "
                  f"species-match={r.species_match}/{r.sampled}  wild-match={r.wild_match}/{r.sampled}  "
                  f"wild+species={r.both_match}/{r.sampled}  →  yield Y≈{r.yield_est} "
                  f"(floor {12}, target {20})")
            print(f"  setting distribution (over the {r.both_match} wild+species clips):")
            print(f"    season : {_dist(r.season_dist)}")
            print(f"    habitat: {_dist(r.habitat_dist)}")
            print(f"    time   : {_dist(r.time_dist)}")
            print(f"    shot   : {_dist(r.shot_dist)}")
            print(f"  self-checks: {r.contradictions} contradiction(s), {r.echo_pairs} clip-echo pair(s)")
    finally:
        from ytagent.repo.ledger import get_llm_pricing
        pricing = await get_llm_pricing(conn)
        spent = await repo.ledger.drain_dev_usage(conn, sink, pricing, context="calibration")
        await conn.close()

    print("\n" + "=" * 70)
    terr = [r for r in reports if r.subject in _TERRESTRIAL]
    rank = sorted(terr, key=lambda r: (-r.yield_est, -r.pool_depth))
    print("FILM #2 CANDIDATES (terrestrial), ranked by wild+species yield:")
    for r in rank:
        print(f"  {r.verdict:10} Y≈{r.yield_est:5}  pool {r.pool_depth:4}  {r.subject}")
    print(f"probe LLM spend ledgered (context=calibration): £{spent:.4f}. No Music, no TTS.")
    print("Banks picks the subject from the data.")


if __name__ == "__main__":
    asyncio.run(run())
