"""STAGE 1 curation for the elephant film — source footage for each beat of 'The Old Paths' through the
reconciled density gate + the definition-free vision gate (species=elephant + wild are the blocking
identity axes; setting is OBSERVED and reported, not gated — the script was written TO the distribution).
Reports per beat: verified count vs the reconciled n_min/n_target, the vision verdicts, the setting
distribution of the accepted clips, and the self-checks. STOPS before any Music/TTS/assembly spend.

Run: POSTGRES_HOST=localhost POSTGRES_PORT=5433 ./.venv/bin/python -m scripts.curate_elephant
"""
from __future__ import annotations

import asyncio
import json
import os

import psycopg
from psycopg.rows import dict_row

from ytagent import produce, repo
from ytagent.authoring.script import Beat, Fact, Script
from ytagent.budget import budget_status
from ytagent.config import load_settings
from ytagent.events import record_event
from ytagent.providers import ListUsageSink, get_llm_provider
from ytagent.sourcing import get_stock_providers

_SCRIPT = "assets/produced/elephant/script.json"
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
        await record_event(conn, "curate_started", message="elephant Stage-1 curation",
                           channel_id=ch["id"], job_id=job["id"])

    print(f"=== ELEPHANT STAGE 1 — '{script.title}' — CURATION + VISION GATE (no Music/TTS/assembly) ===")
    print("blocking axes: species (elephant) + wild. Setting is OBSERVED + reported (film written to it).\n")
    report = await produce.curate_report(
        conn, providers, script, channel_id=ch["id"], job_id=job["id"], llm=llm,
        length_of=lambda b: b.approx_seconds, required_of=lambda b: frozenset())   # species+wild only
    await produce._drain_llm(conn, sink, pricing, channel_id=ch["id"], job_id=job["id"])

    all_ok = True
    for r in report:
        wordless = " [WORDLESS cold open]" if not any(v for v in [script.beats[r["beat"]-1].vo.strip()]) else ""
        mark = "✅ PASS" if r["reached_min"] else "❌ SHORT"
        all_ok = all_ok and r["reached_min"]
        print(f"beat{r['beat']} “{r['label']}”{wordless} — {mark}: {r['verified']} verified "
              f"({r.get('clear',0)} clear) / {r['n_min']} min (target {r['n_target']}, {r['narration_s']}s)")
        for a in r["accepted"]:
            print(f"    ✓ {a['asset_id']}  {a['url']}")
        for v in r["verdicts"]:
            if v.get("category") == "reject":
                print(f"    ✗ {v['asset_id']} [{','.join(v.get('drivers') or [])}] "
                      f"species={v.get('species')} wild={v.get('wild')}: {v.get('reason','')[:80]}")
        vs = r["verdicts"]
        print(f"    accepted setting → season[{_dist(vs,'season_obs',_SEASON_BUCKETS)}]  "
              f"habitat[{_dist(vs,'habitat_obs',_HABITAT_BUCKETS)}]  time[{_dist(vs,'time_obs',_TIME_BUCKETS)}]  "
              f"shot[{_dist(vs,'shot_type',_SHOT_BUCKETS)}]")
        if r.get("contradictions") or r.get("echo_pairs"):
            print(f"    ⚠ {r.get('contradictions',0)} contradiction, {len(r.get('echo_pairs',[]))} clip-echo")

    bud = await budget_status(conn)
    print(f"\nStage-1 result: {'ALL BEATS REACHED n_min — ready for Stage 2 on your go' if all_ok else 'SOME BEATS SHORT — see above'}")
    print(f"spend this run: Haiku (query+vision) only; month-to-date £{bud['month_spend_gbp']:.2f} "
          f"/ £{bud['ceiling_gbp']:.0f} ({bud['tier']}). NO Music, NO TTS.")
    await conn.close()


if __name__ == "__main__":
    asyncio.run(run())
