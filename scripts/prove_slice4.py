"""LIVE proof of Slice 4 — source real claim-safe footage for the emperor-penguin script's 5
shot-briefs (from PROOF_SLICE5.md's paced v2), gated + provenance-logged + cached.

Needs PEXELS_API_KEY / PIXABAY_API_KEY. Downloads are FREE; the only spend is the pennies of Haiku
query extraction (deterministic fallback if no LLM key → £0). Run only on Banks's go:
  POSTGRES_HOST=localhost POSTGRES_PORT=5433 ./.venv/bin/python -m scripts.prove_slice4
"""
from __future__ import annotations

import asyncio
import os
import sys

import psycopg
from psycopg.rows import dict_row

from ytagent import repo
from ytagent.budget import budget_status
from ytagent.config import load_settings
from ytagent.providers import ListUsageSink, get_llm_provider
from ytagent.sourcing import NoMatch, SourcedAsset, get_stock_providers, orchestrator, to_clip

_CACHE = "assets/sourced"
_TARGET = ("16:9", 1920, 1080)

# The emperor-penguin script's 5 shot-briefs (PROOF_SLICE5.md, penguin v2 — paced): (ref, brief, secs)
_BRIEFS = [
    ("penguin:beat1", "Aerial or wide shot of Antarctic ice shelf fading into polar twilight; no sun "
     "on the horizon; vast, featureless white plain; perhaps a faint aurora beginning to colour the "
     "sky above.", 40),
    ("penguin:beat2", "Ground-level shot of a mass emperor penguin huddle; thousands of birds pressed "
     "together; slow pan across the outer edge and then into the dense, dark interior of the group; "
     "individual birds shuffling inward; breath misting in the cold air.", 45),
    ("penguin:beat3", "Close-up of a single emperor penguin male standing apart or at the huddle's "
     "edge; slow tilt down to reveal the brood pouch — a feathered fold of skin above the feet; one "
     "egg just visible, balanced there; the bird utterly still; wind moving the feathers slightly.", 45),
    ("penguin:beat4", "Medium shot of a lone male or small cluster of male emperor penguins; one bird "
     "lowering his head against a wind blast; feathers pressed flat; snow driving sideways across "
     "frame; a slow zoom in on a bird braced against the storm.", 45),
    ("penguin:beat5", "Dawn light — first faint Antarctic sunrise after weeks of darkness — spilling "
     "low and pale across the ice; a huddle beginning to loosen as light returns; close-up of a newly "
     "hatched penguin chick, grey and downy, at a father's brood pouch.", 38),
]


def _report(ref: str, res) -> None:
    if isinstance(res, NoMatch):
        print(f"  ❌ {res.shot_brief_ref}: NO GOOD MATCH — failed loudly ({res.reason})")
        if res.considered:
            print(f"       considered: {list(res.considered)}")
        return
    a: SourcedAsset = res
    p = a.provenance
    tag = "cached" if a.cached else "downloaded + gated"
    print(f"  ✅ {ref}  {a.source}:{a.asset_id}  score {a.score}  [{tag}]")
    print(f"       file: {a.local_path}  ({a.gate.probe.get('width')}x{a.gate.probe.get('height')} "
          f"{a.gate.probe.get('duration', 0):.1f}s, audio={a.gate.probe.get('has_audio')})")
    print(f"       provenance: {p['url']}  · {p['contributor']} · {p['licence']} · {p['downloaded_at'][:19]}")


async def run() -> None:
    settings = load_settings()
    sink = ListUsageSink()
    providers = get_stock_providers(settings)
    if not providers:
        print("No PEXELS_API_KEY / PIXABAY_API_KEY configured — cannot run the live proof.")
        sys.exit(2)

    print("=== provider healthchecks (Pexels may 403 this IP — honest degradation) ===")
    live = []
    for prov in providers:
        ok = await prov.healthcheck()
        print(f"  {prov.name()}: {'available ✅' if ok else 'UNAVAILABLE (dropped) ⚠️'}")
        if ok:
            live.append(prov)
    if not live:
        print("No provider answered from this IP (Pexels 403 + no Pixabay?). Pixabay carries the proof; "
              "Pexels is designed-but-deferred to a network where the API answers.")
        sys.exit(3)

    llm = get_llm_provider(settings, sink)   # Haiku query extraction (pennies); None → deterministic
    print(f"query extraction: {'Haiku (LLM)' if llm else 'deterministic (no LLM key)'}")

    conn = await psycopg.AsyncConnection.connect(settings.dsn(), row_factory=dict_row, autocommit=True)
    try:
        channel = await repo.channels.get_by_slug(conn, "wildlife")
        fmt, tw, th = _TARGET

        print("\n=== (1) source the 5 penguin shot-briefs (target 16:9 landscape) ===")
        results = await orchestrator.source_shot_briefs(
            conn, live, _BRIEFS, target_fmt=fmt, target_w=tw, target_h=th, cache_dir=_CACHE,
            channel_id=channel["id"], llm=llm)
        for (ref, _, _), r in zip(_BRIEFS, results):
            _report(ref, r)

        # log the pennies of Haiku spend
        pricing = await repo.ledger.get_llm_pricing(conn)
        spend = 0.0
        for rec in sink.drain():
            spend += float((await repo.ledger.write_llm_cost(conn, rec, pricing))["amount_gbp"])

        sourced = [r for r in results if isinstance(r, SourcedAsset)]
        nomatch = [r for r in results if isinstance(r, NoMatch)]
        print(f"\nsourced {len(sourced)}/{len(_BRIEFS)} briefs · {len(nomatch)} no-match (flagged, not padded)")
        if sourced:
            print(f"  → each maps to an EditSpec Clip, e.g. {to_clip(sourced[0], approx_seconds=40).src}")

        print("\n=== (2) cache demo — re-run, expect 0 downloads ===")
        results2 = await orchestrator.source_shot_briefs(
            conn, live, _BRIEFS, target_fmt=fmt, target_w=tw, target_h=th, cache_dir=_CACHE,
            channel_id=channel["id"], llm=llm)
        cached = sum(1 for r in results2 if isinstance(r, SourcedAsset) and r.cached)
        print(f"  {cached}/{len(sourced)} previously-sourced assets served from cache (no re-fetch)")

        bud = await budget_status(conn)
        print(f"\nquery-extraction spend this run: £{spend:.4f}  ·  downloads: free")
        print(f"month-to-date: £{bud['month_spend_gbp']:.2f} / £{bud['ceiling_gbp']:.0f} ({bud['tier']})")
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(run())
