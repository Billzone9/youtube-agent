"""STAGE 1 curation for the elephant film — FILM-WIDE sourcing + allocation through the reconciled
density gate + the definition-free vision gate. The subject (african elephant) is FORCED into every
beat's query set and into the vision Expect, so scene-only briefs ('the herd', 'the column') can no
longer surface muskox/woolly sheep. One verified pool is gathered for the whole film, then allocated
to beats by fit — no beat is starved by a greedy earlier beat. Species=elephant + wild are the blocking
identity axes; setting is OBSERVED and reported (the script was written TO the distribution). STOPS
before any Music/TTS/assembly spend.

Run: POSTGRES_HOST=localhost POSTGRES_PORT=5433 ./.venv/bin/python -m scripts.curate_elephant
"""
from __future__ import annotations

import asyncio
import json
import os

import psycopg
from psycopg.rows import dict_row

from ytagent import produce, repo
from ytagent.assembly.density import min_clips, target_clips
from ytagent.authoring.script import Beat, Fact, Script
from ytagent.budget import budget_status
from ytagent.config import load_settings
from ytagent.events import record_event
from ytagent.providers import ListUsageSink, get_llm_provider
from ytagent.sourcing import get_stock_providers, source_film

_SCRIPT = "assets/produced/elephant/script.json"
_SUBJECT = "african elephant"
# setting buckets (reuse the probe's) to summarise what the accepted clips actually show
from ytagent.sourcing.feasibility import (_HABITAT_BUCKETS, _SEASON_BUCKETS, _SHOT_BUCKETS,  # noqa: E402
                                          _TIME_BUCKETS, _bucket)


def _load_script():
    d = json.load(open(_SCRIPT))
    beats = tuple(Beat(index=b["index"], label=b["label"], shot_brief=b["shot_brief"],
                       vo=b["vo"], approx_seconds=b["approx_seconds"]) for b in d["beats"])
    return Script(title=d["title"], runtime_target_s=d["runtime_target_s"], word_target=d["word_target"],
                  beats=beats, facts_used=tuple(Fact(**f) for f in d["facts_used"]))


def _dist(verdicts, key, buckets):
    out = {}
    for v in verdicts:
        if v.get("category") == "clear":
            out[_bucket(v.get(key, ""), buckets)] = out.get(_bucket(v.get(key, ""), buckets), 0) + 1
    return ", ".join(f"{k}:{n}" for k, n in sorted(out.items(), key=lambda kv: -kv[1])) or "—"


async def run():
    settings = load_settings()
    sink = ListUsageSink()
    llm = get_llm_provider(settings, sink)
    providers = [p for p in get_stock_providers(settings) if await p.healthcheck()]
    if not (llm and providers) or not os.path.exists(_SCRIPT):
        print(f"prereqs — llm={bool(llm)} stock={[p.name() for p in providers]} script={os.path.exists(_SCRIPT)}")
        raise SystemExit(2)
    script = _load_script()
    conn = await psycopg.AsyncConnection.connect(settings.dsn(), row_factory=dict_row, autocommit=True)
    ch = await repo.channels.get_by_slug(conn, "wildlife")
    pricing = await repo.ledger.get_llm_pricing(conn)
    async with conn.transaction():
        job = await repo.jobs.create(conn, channel_id=ch["id"], type="curate", status="running",
                                     payload={"topic": "elephant", "stage": 1})
        await record_event(conn, "curate_started", message="elephant Stage-1 curation (film-wide)",
                           channel_id=ch["id"], job_id=job["id"])

    print(f"=== ELEPHANT STAGE 1 — '{script.title}' — FILM-WIDE CURATION + VISION GATE (no Music/TTS/assembly) ===")
    print(f"subject FORCED into every query + Expect: '{_SUBJECT}'. Blocking axes: species + wild. "
          "Setting OBSERVED + reported.\n")

    beats = []
    for b in script.beats:
        hint = b.approx_seconds
        n_min = min_clips(hint)
        beats.append({"index": b.index, "label": b.label, "brief": b.shot_brief,
                      "approx_seconds": hint, "n_min": n_min,
                      "n_target": max(target_clips(hint), n_min + 1)})

    alloc, rep = await source_film(
        conn, providers, subject=_SUBJECT, beats=beats, target_fmt="16:9", target_w=1920, target_h=1080,
        cache_dir="assets/sourced", channel_id=ch["id"], job_id=job["id"], llm=llm,
        required_axes=frozenset())                          # species + wild only; setting observed
    await produce._drain_llm(conn, sink, pricing, channel_id=ch["id"], job_id=job["id"])

    for r in rep["beats"]:
        wordless = " [WORDLESS cold open]" if not script.beats[r["beat"] - 1].vo.strip() else ""
        mark = "✅ PASS" if r["reached_min"] else "❌ SHORT"
        print(f"beat{r['beat']} “{r['label']}”{wordless} — {mark}: {r['verified']} allocated "
              f"({r['clear']} clear) / {r['n_min']} min (target {r['n_target']}, {r['narration_s']}s)")
        for a in r["accepted"]:
            print(f"    ✓ {a['asset_id']}  {a['url']}")
        vs = r["verdicts"]
        print(f"    setting → season[{_dist(vs,'season_obs',_SEASON_BUCKETS)}]  "
              f"habitat[{_dist(vs,'habitat_obs',_HABITAT_BUCKETS)}]  time[{_dist(vs,'time_obs',_TIME_BUCKETS)}]  "
              f"shot[{_dist(vs,'shot_type',_SHOT_BUCKETS)}]")

    print(f"\nFILM POOL: {rep['pool_candidates']} candidates → {rep['eligible']} eligible → "
          f"{rep['verified']} verified → {rep['clear']} clear + {rep['reserve']} reserve "
          f"({rep['rejected']} rejected by the gate, {rep['contradictions']} contradiction, "
          f"{len(rep['echo_pairs'])} clip-echo) → {rep['allocated_total']} allocated across {len(beats)} beats")
    rejects = [v for v in rep["verdicts"] if v["category"] == "reject"][:6]
    for v in rejects:
        print(f"    ✗ {v['asset_id']} [{','.join(v.get('drivers') or [])}] species={v['species']} "
              f"wild={v['wild']}: {v.get('reason','')[:80]}")

    bud = await budget_status(conn)
    all_ok = rep["all_reached_min"]
    print(f"\nStage-1 result: {'ALL BEATS REACHED n_min — ready for Stage 2 on your go' if all_ok else 'SOME BEATS SHORT — see above'}")
    print(f"spend this run: Haiku (query+vision) only; month-to-date £{bud['month_spend_gbp']:.2f} "
          f"/ £{bud['ceiling_gbp']:.0f} ({bud['tier']}). NO Music, NO TTS.")
    await conn.close()


if __name__ == "__main__":
    asyncio.run(run())
