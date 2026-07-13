"""LIVE proof of Slice 5 — the agent writes for itself. Makes REAL (paid) Anthropic calls.

Two demonstrations for Banks to judge:
  (a) an AUTONOMOUS lion description, shown side-by-side against the locked hand-authored reference
      (ytagent/metadata/lion_reference.py), with the guard verdict + AI-tell numbers;
  (b) an AUTONOMOUS short footage-led script on a DIFFERENT subject (emperor penguin — Antarctic
      winter), printed in full with its facts-used block + AI-tell numbers, to judge against the lion
      script's voice.

Real token spend is written to cost_ledger (category 'ai_generation') and month-to-date is printed.
No YouTube calls, no publishing, no VPS. Gated behind ANTHROPIC_API_KEY. Run only after Banks's go:
  POSTGRES_HOST=localhost POSTGRES_PORT=5433 ./.venv/bin/python -m scripts.prove_slice5
"""
from __future__ import annotations

import asyncio
import pathlib
import sys

import psycopg
from psycopg.rows import dict_row

from ytagent import repo
from ytagent.authoring.script import ScriptWriter
from ytagent.authoring.tells import scan_tells
from ytagent.budget import budget_status
from ytagent.config import load_settings
from ytagent.metadata.description import generate_description
from ytagent.metadata.guard import scan
from ytagent.metadata.lion_reference import build_lion_reference
from ytagent.metadata.llm_writer import LLMWriter
from ytagent.metadata.research import UnavailableResearch
from ytagent.providers import ListUsageSink, get_llm_provider

_LION_BEATS = [
    {"start_seconds": 0, "hint": "cold open: the savanna as an empty kingdom; the lion walks in"},
    {"start_seconds": 51, "hint": "the lion at rest — up to ~20 hours still; the mane"},
    {"start_seconds": 114, "hint": "the pride and its lionesses; the social bond"},
    {"start_seconds": 178, "hint": "the hunt; lionesses cooperate; most hunts fail"},
    {"start_seconds": 239, "hint": "the cubs; play as rehearsal; high mortality"},
    {"start_seconds": 303, "hint": "the roar at dusk; carries ~8 km; warning and summons"},
    {"start_seconds": 347, "hint": "golden-hour close; the day folds shut"},
]
_PENGUIN_TOPIC = ("the emperor penguin's Antarctic winter — the huddle, and the father balancing the "
                  "single egg on his feet through the long polar night")


async def _drain_costs(conn, sink, pricing) -> float:
    total = 0.0
    for rec in sink.drain():
        res = await repo.ledger.write_llm_cost(conn, rec, pricing)
        total += float(res["amount_gbp"])
    return total


def _rule(w=88): print("─" * w)


async def run() -> None:
    settings = load_settings()
    sink = ListUsageSink()
    provider = get_llm_provider(settings, sink)
    if provider is None:
        print("No ANTHROPIC_API_KEY configured — cannot run the live proof. (Honest degradation.)")
        sys.exit(2)

    conn = await psycopg.AsyncConnection.connect(settings.dsn(), row_factory=dict_row, autocommit=True)
    try:
        channel = await repo.channels.get_by_slug(conn, "wildlife")
        pricing = await repo.ledger.get_llm_pricing(conn)
        cfg = channel.get("config") or {}
        exemplar_file = (cfg.get("style_exemplars") or {}).get("script", "lion-doc-01-script.md")
        script_exemplar = pathlib.Path(exemplar_file).read_text()

        # ============ (a) autonomous lion description vs the locked reference ============
        print("\n" + "=" * 88)
        print("(a) AUTONOMOUS LION DESCRIPTION  vs  the locked hand-authored reference")
        print("=" * 88)
        ref = build_lion_reference()
        video = {
            "topic": "Lion — a cinematic portrait of the lion across one day on the African savanna "
                     "(the pride, the hunt, the cubs, the roar)",
            "beats": _LION_BEATS,
        }
        writer = LLMWriter(provider, exemplar=ref)
        gen = generate_description(video, channel, UnavailableResearch(), writer)
        run_a = await _drain_costs(conn, sink, pricing)

        print("\n— AGENT'S OWN TITLE —      ", gen.title)
        print("— REFERENCE TITLE —        ", ref.title)
        _rule()
        print("AGENT'S OWN DESCRIPTION:\n")
        print(gen.description)
        _rule()
        print("REFERENCE DESCRIPTION (locked, for comparison):\n")
        print(ref.description)
        _rule()
        print("AGENT'S TAGS:   ", ", ".join(gen.tags))
        print("REFERENCE TAGS: ", ", ".join(ref.tags))
        _rule()
        gt = scan_tells(gen.description)
        print(f"guard on agent output: {'CLEAN ✅' if not scan(gen.title, gen.description, *gen.tags) else 'ARTIFACT'}")
        print(f"AI-tell scan: flagged={gt.flagged}  em-dash={gt.em_dash_per_100w}/100w  "
              f"exclamations={gt.exclamations}  tricolon(advisory)={gt.tricolon_count}  "
              f"crutches(advisory)={gt.lexical_crutches or '{}'}")
        print(f"provenance: {writer.last_run}")

        # store as an authored version (research_writer), NOT applied — truthful, once per source
        lion = await (await conn.execute(
            "SELECT id FROM videos WHERE file_path LIKE %s AND status='published' "
            "AND youtube_video_id IS NOT NULL ORDER BY id DESC LIMIT 1",
            ["%lion-doc-01_scored.mp4"])).fetchone()
        if lion:
            have = {r["source"] for r in await repo.metadata.list_versions(conn, lion["id"])}
            if "research_writer" not in have:
                meta = await repo.metadata.create_version(
                    conn, video_id=lion["id"], channel_id=channel["id"], title=gen.title,
                    description=gen.description, tags=list(gen.tags), source="research_writer",
                    research_notes={**writer.last_run, "note": "slice5 autonomous proof; not applied"})
                print(f"stored as authored video_metadata v{meta['version']} (research_writer, not live)")
            else:
                print("research_writer version already present — not storing a duplicate")

        # ============ (b) autonomous footage-led script on a different subject ============
        print("\n" + "=" * 88)
        print("(b) AUTONOMOUS FOOTAGE-LED SCRIPT — emperor penguin (a subject the agent has not seen)")
        print("Judge against the lion script's voice: poetic surface, accurate underneath, no AI tells.")
        print("=" * 88)
        sw = ScriptWriter(provider, exemplar_text=script_exemplar)
        script = sw.write(topic=_PENGUIN_TOPIC, channel=channel, research=UnavailableResearch(),
                          runtime_target_s=150, n_beats=4)
        run_b = await _drain_costs(conn, sink, pricing)

        print(f"\nTITLE: {script.title}")
        print(f"target ~{script.runtime_target_s}s / ~{script.word_target} words   "
              f"actual VO: {script.word_count} words, {len(script.beats)} beats\n")
        for b in script.beats:
            _rule()
            print(f"BEAT {b.index} — {b.label}   (~{b.approx_seconds}s)")
            print(f"  VISUALS (shot-brief): {b.shot_brief}")
            print(f"  VO: {b.vo}")
        _rule()
        print("FACTS USED (accuracy block):")
        for f in script.facts_used:
            print(f"  [{'established' if f.established else 'VERIFY  '}] {f.claim}")
        _rule()
        st = scan_tells(" ".join(b.vo for b in script.beats))
        print(f"AI-tell scan: flagged={st.flagged}  em-dash={st.em_dash_per_100w}/100w  "
              f"exclamations={st.exclamations}  not_only_but_also={st.not_only_but_also}  "
              f"tricolon(advisory)={st.tricolon_count}  crutches(advisory)={st.lexical_crutches or '{}'}")
        if st.reasons:
            print(f"  reasons: {st.reasons}")
        print(f"provenance: {script.provenance}")

        # ============ cost summary ============
        print("\n" + "=" * 88)
        bud = await budget_status(conn)
        print(f"THIS RUN cost: £{run_a + run_b:.4f}  (description £{run_a:.4f} + script £{run_b:.4f})")
        print(f"Month-to-date spend: £{bud['month_spend_gbp']:.2f} / £{bud['ceiling_gbp']:.0f} "
              f"({bud['tier']})  •  remaining £{bud['remaining_gbp']:.2f}")
        print("=" * 88)
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(run())
