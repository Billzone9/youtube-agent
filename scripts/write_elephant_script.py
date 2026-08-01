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

# The footage IN HAND (from the probe) + the DENSITY brief are handed to the writer as research, so the
# script is written to what exists AND earns its length like the lion (not six ideas stretched thin).
_FOOTAGE_BRIEF = (
    "FOOTAGE IN HAND — write ONLY to what this pool contains; do not invent shots it lacks. Available: "
    "African elephant, WILD (no captivity), DRY SAVANNA (some green flush), GOLDEN-HOUR light dominant, "
    "mostly WIDE shots. Every SHOT-BRIEF must be satisfiable by wild dry-savanna golden-hour elephant "
    "footage, and must FAVOUR shots with INTERNAL MOVEMENT (a herd crossing, a calf running to keep up, "
    "dust in low sun, trunks and ears in motion, a matriarch walking a line) over static portraits — at "
    "this cutting rhythm each shot HOLDS ~20s and a static clip held that long reads dead.\n"
    "DENSITY — match the LION exemplar (in the examples): the lion earned 801 words because it had SEVEN "
    "distinct things to say and DEVELOPED EACH FULLY — a complete movement per beat. Every beat here must "
    "likewise sustain ~120 words per minute across its SPOKEN seconds and DEVELOP ONE IDEA FULLY (a ~55s "
    "beat carries ~100–120 spoken words). Do NOT pad or add pauses to fill time; DEVELOP. Give each beat "
    "its full weight. The seven ideas, one per beat: (1) a SHORT 10–15s WORDLESS cold open — the herd "
    "emerging, picture+score only; (2) the matriarch's leadership — the herd moves because she has "
    "already chosen; (3) the OLD ROUTES — paths walked across generations, unmarked yet carried; (4) "
    "WATER MEMORY — she holds in memory the water sources of decades, dry and found again; (5) the CALVES "
    "learning the route by walking it, knowledge absorbed not taught; (6) how the herd COMMUNICATES and "
    "moves — infrasonic rumbles felt more than heard, the unhurried precision of the crossing; (7) the "
    "CLOSE — evening light, the herd receding, what is carried forward. Put the reverent breathing at "
    "BEAT BOUNDARIES (the score carries the transition), not all in the cold open."
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
                              runtime_target_s=394, n_beats=7)   # match the lion benchmark (6:34)
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

    from ytagent.authoring.script import _WPM_MIN, _spoken, _spoken_seconds
    print(f"TITLE: {script.title}   ({len(script.beats)} beats, {script.word_count} spoken words, "
          f"target {script.runtime_target_s}s)\n")
    for b in script.beats:
        print(f"── beat{b.index}  “{b.label}”   (~{b.approx_seconds}s)")
        print(f"   SHOT: {b.shot_brief}")
        print(f"   VO:   {b.vo}\n")

    # VERIFY on the FIXED denominator (spoken words / SPOKEN seconds), vs the lion benchmark
    print("PER-BEAT DENSITY CHECK (spoken words / spoken seconds → wpm; floor ≥110):")
    tot_words = tot_spoken_s = 0
    weak = []
    for b in script.beats:
        w = len(_spoken(b.vo).split())
        ssec = _spoken_seconds(b.vo, b.approx_seconds)
        wpm = w / (ssec / 60) if ssec > 0 else 0.0
        tot_words += w
        tot_spoken_s += ssec
        wordless = (w == 0)
        flag = "  [WORDLESS cold open]" if wordless else ("  ⚠ UNDER-WRITTEN" if wpm < _WPM_MIN else "")
        if not wordless and wpm < _WPM_MIN:
            weak.append(b.index)
        print(f"   beat{b.index}: {w:3} words | {ssec:5.1f}s spoken | {wpm:5.0f} wpm{flag}")
    rt = sum(b.approx_seconds for b in script.beats)
    film_wpm = tot_words / (tot_spoken_s / 60) if tot_spoken_s else 0
    print(f"\nFILM: {tot_words} spoken words | {rt}s runtime ({rt/60:.1f} min) | "
          f"{film_wpm:.0f} wpm on spoken time")
    print(f"LION: 801 spoken words | 394s (6:34) | 122 wpm  ← the benchmark")
    print(f"→ elephant is {tot_words/801*100:.0f}% of the lion's words; "
          + ("ALL BEATS ≥110 wpm — dense enough" if not weak
             else f"UNDER-WRITTEN beats: {weak} — regenerate before shipping"))
    print("\nFACTS USED (accuracy block):")
    for f in script.facts_used:
        print(f"   [{'established' if f.established else 'FLAG'}] {f.claim}")
    print(f"\nsaved → {out}/script.json   |   script LLM spend ledgered: £{spent:.4f}")


if __name__ == "__main__":
    asyncio.run(main())
