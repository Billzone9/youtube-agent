"""BROADENED re-probe (Banks's fixes 1–3): wider search reach + INCONCLUSIVE-SHALLOW + length-
parameterised thresholds. Re-probes the elephant (truer depth for film length) and the zebra (confirm
the shallow-pool artifact + prove the rule). Reports broadened pool depth, setting distribution,
yield vs the intended-length thresholds, and the max beat count the footage sustains.

Run: POSTGRES_HOST=localhost POSTGRES_PORT=5433 ./.venv/bin/python -m scripts.reprobe
"""
from __future__ import annotations

import asyncio

import psycopg
from psycopg.rows import dict_row

from ytagent import repo
from ytagent.assembly.density import film_thresholds
from ytagent.config import load_settings
from ytagent.providers import ListUsageSink, get_llm_provider
from ytagent.sourcing import get_stock_providers
from ytagent.sourcing.feasibility import probe_feasibility

_SUBJECTS = ["African elephant", "zebra"]
_LION_ACTUAL_PER_BEAT = 17 / 7        # the benchmark's ACTUAL density (17 clips / 7 beats ≈ 2.4)


def _dist(d):
    return ", ".join(f"{k}:{n}" for k, n in d.items()) or "—"


async def run():
    settings = load_settings()
    sink = ListUsageSink()
    llm = get_llm_provider(settings, sink)
    providers = [p for p in get_stock_providers(settings) if await p.healthcheck()]
    conn = await psycopg.AsyncConnection.connect(settings.dsn(), row_factory=dict_row, autocommit=True)
    ch = await repo.channels.get_by_slug(conn, "wildlife")
    try:
        for subject in _SUBJECTS:
            r = await probe_feasibility(conn, providers, subject, llm=llm, channel_id=ch["id"],
                                        broad=True, sample_n=12, runtime_s=394.0, n_beats=7)
            t = r.thresholds
            print(f"\n=== {subject} (BROADENED) → {r.verdict} ===")
            print(f"  pool depth E={r.pool_depth} (min for a trusted verdict: 15)  sampled={r.sampled}  "
                  f"species={r.species_match}/{r.sampled} wild={r.wild_match}/{r.sampled} "
                  f"wild+species={r.both_match}/{r.sampled}  →  yield Y≈{r.yield_est}")
            print(f"  thresholds for a LION-shape film ({t['runtime_s']}s / {t['n_beats']} beats, "
                  f"{t['beat_len_s']}s/beat): floor={t['floor']} (≥{t['n_min_per_beat']}/beat), "
                  f"target={t['target']} (≥{t['n_target_per_beat']}/beat @ ~10s shots + 25% margin)")
            print(f"  max beats Y sustains: {r.max_beats} @ standard density (~10s shots); "
                  f"~{int(r.yield_est // _LION_ACTUAL_PER_BEAT)} @ the LION's actual density (2.4/beat, ~23s shots)")
            print(f"  setting distribution (over {r.both_match} wild+species clips):")
            print(f"    season : {_dist(r.season_dist)}")
            print(f"    habitat: {_dist(r.habitat_dist)}")
            print(f"    time   : {_dist(r.time_dist)}")
            print(f"    shot   : {_dist(r.shot_dist)}")
            print(f"  self-checks: {r.contradictions} contradiction, {r.echo_pairs} clip-echo")
    finally:
        pricing = await repo.ledger.get_llm_pricing(conn)
        spent = await repo.ledger.drain_dev_usage(conn, sink, pricing, context="calibration")
        await conn.close()
    # what beat counts elephant's yield supports, so Banks can set the target length
    print("\nWolf thresholds for reference: " + str(film_thresholds(157, 4)))
    print(f"broadened re-probe LLM spend (context=calibration): £{spent:.4f}. No Music, no TTS.")


if __name__ == "__main__":
    asyncio.run(run())
