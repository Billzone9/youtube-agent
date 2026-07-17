"""Regenerate the emperor-penguin script under the pacing standard (penguin v2 — paced).

Same subject/target as the prove_slice5 script demo, but the writer now enforces ~120–140 wpm per
beat (regenerating an over-long beat, like the tell-scan retry). Prints per-beat wpm so the calm pace
is visible. Makes a real (paid) Sonnet call; writes spend to cost_ledger. Run:
  POSTGRES_HOST=localhost POSTGRES_PORT=5433 ./.venv/bin/python -m scripts.regen_penguin_paced
"""
from __future__ import annotations

import pathlib
import sys

import psycopg
from psycopg.rows import dict_row

from ytagent import repo
from ytagent.authoring.script import _WPM_MAX, _WPM_TARGET, ScriptWriter
from ytagent.authoring.tells import scan_tells
from ytagent.budget import budget_status
from ytagent.config import load_settings
from ytagent.metadata.research import UnavailableResearch
from ytagent.providers import ListUsageSink, get_llm_provider

_TOPIC = ("the emperor penguin's Antarctic winter — the huddle, and the father balancing the single "
          "egg on his feet through the long polar night")


def _rule(w=88): print("─" * w)


async def _run() -> None:
    settings = load_settings()
    sink = ListUsageSink()
    provider = get_llm_provider(settings, sink)
    if provider is None:
        print("No ANTHROPIC_API_KEY configured — cannot run. (Honest degradation.)")
        sys.exit(2)

    conn = await psycopg.AsyncConnection.connect(settings.dsn(), row_factory=dict_row, autocommit=True)
    try:
        channel = await repo.channels.get_by_slug(conn, "wildlife")
        pricing = await repo.ledger.get_llm_pricing(conn)
        cfg = channel.get("config") or {}
        exemplar_file = (cfg.get("style_exemplars") or {}).get("script", "lion-doc-01-script.md")
        script_exemplar = pathlib.Path(exemplar_file).read_text()

        sw = ScriptWriter(provider, exemplar_text=script_exemplar)
        script = sw.write(topic=_TOPIC, channel=channel, research=UnavailableResearch(),
                          runtime_target_s=150, n_beats=4)

        cost = 0.0
        for rec in sink.drain():
            cost += float((await repo.ledger.write_llm_cost(conn, rec, pricing))["amount_gbp"])

        print(f"TITLE: {script.title}")
        print(f"pace standard: ~{_WPM_TARGET} wpm target, ≤{_WPM_MAX} wpm enforced per beat")
        print(f"target ~{script.runtime_target_s}s / ~{script.word_target} spoken words   "
              f"actual: {script.word_count} spoken words, {len(script.beats)} beats, "
              f"overall {script.word_count / (sum(b.approx_seconds for b in script.beats) / 60):.0f} wpm\n")
        for b in script.beats:
            _rule()
            print(f"BEAT {b.index} — {b.label}   (~{b.approx_seconds}s)   "
                  f"[{b.spoken_words} spoken words → {b.wpm:.0f} wpm]")
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
        print(f"provenance: {script.provenance}")
        _rule()
        bud = await budget_status(conn)
        print(f"THIS RUN cost: £{cost:.4f}")
        print(f"Month-to-date spend: £{bud['month_spend_gbp']:.2f} / £{bud['ceiling_gbp']:.0f} "
              f"({bud['tier']})  •  remaining £{bud['remaining_gbp']:.2f}")
    finally:
        await conn.close()


if __name__ == "__main__":
    import asyncio
    asyncio.run(_run())
