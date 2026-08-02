"""6c performance confirmation — early-stop + vision-verdict cache on the elephant.

Runs source_film TWICE on the same subject/beats:
  RUN 1 (cold cache): early-stop caps the verify work once the clear pool ≥ 1.5×Σn_target.
  RUN 2 (warm cache): every clip already judged → cache hits, no Haiku frames → near-instant.
The pair is the scheduler's win: a first job is bounded, and a resumed/repeated job re-pays nothing.
Reports wall-clock + clear + cache-hits + early-stop for each, against the diagnostic run (~40min/54).

Run: POSTGRES_HOST=localhost POSTGRES_PORT=5433 ./.venv/bin/python -m scripts.prove_source_perf
"""
from __future__ import annotations

import asyncio
import json
import time

import psycopg
from psycopg.rows import dict_row

from ytagent import repo
from ytagent.assembly.density import min_clips, target_clips
from ytagent.config import load_settings
from ytagent.providers import ListUsageSink, get_llm_provider
from ytagent.sourcing import get_stock_providers, source_film

_SUBJECT = "african elephant"
_SCRIPT = "assets/produced/elephant/script.json"   # The Old Paths briefs (proven, deterministic)


def _beats():
    d = json.load(open(_SCRIPT))
    out = []
    for b in d["beats"]:
        s = b["approx_seconds"]
        out.append({"index": b["index"], "label": b["label"], "brief": b["shot_brief"],
                    "approx_seconds": s, "n_min": min_clips(s),
                    "n_target": max(target_clips(s), min_clips(s) + 1)})
    return out


async def _run(conn, providers, llm, beats, ch, label):
    t0 = time.monotonic()
    alloc, rep = await source_film(conn, providers, subject=_SUBJECT, beats=beats, target_fmt="16:9",
                                   target_w=1920, target_h=1080, cache_dir="assets/sourced",
                                   channel_id=ch["id"], job_id=None, llm=llm)
    dt = time.monotonic() - t0
    print(f"\n[{label}] {dt/60:.1f} min  |  pool {rep['pool_candidates']} → {rep['eligible']} eligible "
          f"→ verified {rep['verified']} ({rep['cache_hits']} cached) → clear {rep['clear']} "
          f"→ allocated {rep['allocated_total']}  |  early-stop@{rep['stop_at']}: {rep['stopped_early']} "
          f"|  all beats: {'PASS' if rep['all_reached_min'] else 'SHORT'}")
    return dt, rep


async def run():
    settings = load_settings()
    sink = ListUsageSink()
    llm = get_llm_provider(settings, sink)
    providers = [p for p in get_stock_providers(settings) if await p.healthcheck()]
    if not (llm and providers):
        raise SystemExit("prereqs")
    conn = await psycopg.AsyncConnection.connect(settings.dsn(), row_factory=dict_row, autocommit=True)
    ch = await repo.channels.get_by_slug(conn, "wildlife")
    beats = _beats()
    sigma = sum(b["n_target"] for b in beats)
    print(f"=== 6c PERF — early-stop + verdict cache — '{_SUBJECT}' (Σn_target={sigma}) ===")
    print("baseline (diagnostic footage-led run): ~40 min, 54 clear, no early-stop, no cache")

    dt1, r1 = await _run(conn, providers, llm, beats, ch, "RUN 1 cold")
    dt2, r2 = await _run(conn, providers, llm, beats, ch, "RUN 2 warm")

    print("\n=== SUMMARY ===")
    print(f"  RUN 1 (cold): {dt1/60:.1f} min, {r1['clear']} clear, {r1['cache_hits']} cache-hits, "
          f"early-stop={r1['stopped_early']}")
    print(f"  RUN 2 (warm): {dt2/60:.1f} min, {r2['clear']} clear, {r2['cache_hits']} cache-hits "
          f"(the resume/repeat case) — {dt1/max(dt2,0.01):.0f}× faster than cold")
    await conn.close()


if __name__ == "__main__":
    asyncio.run(run())
