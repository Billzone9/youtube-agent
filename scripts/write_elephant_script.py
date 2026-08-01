"""Write the FOOTAGE-LED elephant script — 7 beats, ~6 min, written to what the probe actually found
(dry savanna, golden hour, mostly wide), not a script that hopes for footage. Shot briefs favour clips
with INTERNAL MOVEMENT (holds run ~23s at the reconciled lion density; static footage held that long
reads dead). House voice, ~120-140 wpm, structural breathers built into the structure from the start.

Run: POSTGRES_HOST=localhost POSTGRES_PORT=5433 ./.venv/bin/python -m scripts.write_elephant_script
"""
from __future__ import annotations

import asyncio
import dataclasses
import json
import os
import pathlib

import psycopg
from psycopg.rows import dict_row

from ytagent import repo
from ytagent.authoring.script import ScriptWriter
from ytagent.config import load_settings
from ytagent.providers import ListUsageSink, get_llm_provider

_TOPIC = ("the African elephant — the matriarch and her herd on the old paths across the dry savanna: "
          "the long walk to water, memory carried across generations, the calves learning the route, "
          "and the herd moving through the low golden light of morning and evening")

# The footage IN HAND (from the probe) is handed to the writer as research, so the script is written to
# what exists rather than hoping for shots the library lacks.
_FOOTAGE_BRIEF = (
    "FOOTAGE IN HAND — write ONLY to what this pool contains; do not invent shots it lacks. "
    "Available: African elephant, WILD (no captivity), DRY SAVANNA (some green flush), GOLDEN-HOUR "
    "light dominant (dawn/dusk), mostly WIDE shots. Every SHOT-BRIEF must be satisfiable by wild "
    "dry-savanna golden-hour elephant footage. FAVOUR shots with INTERNAL MOVEMENT — a herd crossing, "
    "a calf running to keep up, dust kicked up in low sun, trunks and ears in motion, a matriarch "
    "walking a line — over static portraits: at the house cutting rhythm each shot HOLDS ~20 seconds, "
    "and a static clip held that long reads dead. STRUCTURE with breathers: a cold open on picture and "
    "score before the first word, and a held beat-boundary pause where the music carries the image."
)


@dataclasses.dataclass
class _FootageResearch:
    available: bool = True
    notes: str = _FOOTAGE_BRIEF


async def main():
    settings = load_settings()
    sink = ListUsageSink()
    llm = get_llm_provider(settings, sink)
    if llm is None:
        print("No ANTHROPIC_API_KEY — cannot write the script.")
        raise SystemExit(2)
    exemplar = pathlib.Path("lion-doc-01-script.md").read_text()
    writer = ScriptWriter(llm, exemplar_text=exemplar)

    conn = await psycopg.AsyncConnection.connect(settings.dsn(), row_factory=dict_row, autocommit=True)
    try:
        channel = await repo.channels.get_by_slug(conn, "wildlife")
        script = writer.write(topic=_TOPIC, channel=channel, research=_FootageResearch(),
                              runtime_target_s=380, n_beats=7)
        pricing = await repo.ledger.get_llm_pricing(conn)
        spent = await repo.ledger.drain_dev_usage(conn, sink, pricing, context="production")
    finally:
        await conn.close()

    out = os.path.join("assets", "produced", "elephant")
    os.makedirs(out, exist_ok=True)
    with open(os.path.join(out, "script.json"), "w") as fh:
        json.dump({"title": script.title, "runtime_target_s": script.runtime_target_s,
                   "word_target": script.word_target, "word_count": script.word_count,
                   "beats": [dataclasses.asdict(b) for b in script.beats],
                   "facts_used": [dataclasses.asdict(f) for f in script.facts_used],
                   "provenance": script.provenance}, fh, indent=2)

    print(f"TITLE: {script.title}   ({len(script.beats)} beats, {script.word_count} spoken words, "
          f"target {script.runtime_target_s}s)\n")
    for b in script.beats:
        print(f"── beat{b.index}  “{b.label}”   (~{b.approx_seconds}s, {b.spoken_words} words, {b.wpm:.0f} wpm)")
        print(f"   SHOT: {b.shot_brief}")
        print(f"   VO:   {b.vo}\n")
    print("FACTS USED (accuracy block):")
    for f in script.facts_used:
        print(f"   [{'established' if f.established else 'FLAG'}] {f.claim}")
    print(f"\nsaved → {out}/script.json   |   script LLM spend ledgered: £{spent:.4f}")


if __name__ == "__main__":
    asyncio.run(main())
