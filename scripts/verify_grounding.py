"""Regression for grounded research (Phase 1, A1) — the two build notes:
  NOTE 1 (bounded spend): the loop stops AT each cap, enforced BEFORE the spend — assert the STOP (the
    failing case, like the recurring-allowance verify), not the happy path. A never-done provider halts
    exactly at the search / iteration / input cap, records `declared`, and stays under the ceiling.
  NOTE 2 (degraded constrains the script): `research_directive` carries the facts AND the partiality to
    the writer — a partial set forbids ungrounded claims; a complete set does not.
Pure/offline (no DB, no keys, no real provider).

Run: ./.venv/bin/python -m scripts.verify_grounding
"""
from __future__ import annotations

import sys

from ytagent.authoring.grounding import (ResearchFacts, SearchOutcome, gather_grounded_facts,
                                         research_directive)
from ytagent.authoring.script import Fact
from ytagent.scheduler import cost

_fail = 0


def check(label, ok, detail=""):
    global _fail
    print(f"  {'✅' if ok else '❌'} {label}{(' — ' + detail) if detail else ''}")
    if not ok:
        _fail += 1


class _NeverDone:
    """A stubborn subject: every search finds one fact, costs `per_search` tokens, NEVER signals done.
    Unbounded without the caps — exactly the runaway case."""
    def __init__(self, per_search=4000):
        self.per_search = per_search
        self.calls = 0

    def search(self, subject, *, gathered):
        self.calls += 1
        return SearchOutcome(facts=(Fact(claim=f"fact {self.calls}", established=True),),
                             input_tokens=self.per_search, searches=1, done=False)


class _DoneAfter:
    def __init__(self, n):
        self.n, self.calls = n, 0

    def search(self, subject, *, gathered):
        self.calls += 1
        return SearchOutcome(facts=(Fact(claim=f"fact {self.calls}", established=True),),
                             input_tokens=3000, searches=1, done=(self.calls >= self.n))


def main():
    print("[1] NOTE 1 — the loop STOPS at each cap (enforced before the spend)")
    # search cap: give it plenty of iterations, a low search cap → stops AT the search cap
    p = _NeverDone()
    rf = gather_grounded_facts("wolf", p, max_searches=3, max_iterations=50, max_input_tokens=10**9)
    check("stops AT the search cap (3 calls, not 4)", p.calls == 3 and rf.searches_used == 3,
          f"calls={p.calls}")
    check("a stopped run is PARTIAL (complete=False)", rf.complete is False)
    check("the cap is recorded in declared", "research" in rf.declared and "searches" in rf.declared["research"],
          rf.declared.get("research"))

    # iteration cap: high search cap, low iteration cap → stops AT the iteration cap
    p2 = _NeverDone()
    rf2 = gather_grounded_facts("wolf", p2, max_searches=50, max_iterations=4, max_input_tokens=10**9)
    check("stops AT the iteration cap (4 calls, not 5)", p2.calls == 4 and rf2.searches_used == 4,
          f"calls={p2.calls}")
    check("iteration cap recorded + partial",
          rf2.complete is False and "iterations" in rf2.declared.get("research", ""))

    # input cap: never starts a search once cumulative input has hit the ceiling
    p3 = _NeverDone(per_search=4000)
    rf3 = gather_grounded_facts("wolf", p3, max_searches=50, max_iterations=50, max_input_tokens=10000)
    check("stops on the INPUT cap (never starts a search past the ceiling)",
          p3.calls == 3 and "input cap" in rf3.declared.get("research", ""), f"calls={p3.calls}")

    # the actual run is bounded by the DEFAULT caps (what the estimate quotes)
    p4 = _NeverDone()
    rf4 = gather_grounded_facts("wolf", p4)
    check("under DEFAULT caps a runaway is bounded to ≤ max_searches AND ≤ max_iterations",
          rf4.searches_used <= cost._RESEARCH_MAX_SEARCHES
          and rf4.searches_used <= cost._RESEARCH_MAX_ITERATIONS, f"searches={rf4.searches_used}")

    print("[2] NOTE 1 — a natural finish is COMPLETE, no degradation declared")
    rf_ok = gather_grounded_facts("lion", _DoneAfter(2), max_searches=8, max_iterations=4)
    check("provider signals done → complete=True, no declared",
          rf_ok.complete is True and not rf_ok.declared and rf_ok.searches_used == 2)

    print("[3] NOTE 2 — the directive carries facts + partiality to the writer")
    facts = (Fact(claim="Wolves live in packs.", established=True),
             Fact(claim="A pack hunts cooperatively.", established=True))
    d_complete = research_directive(ResearchFacts(facts=facts, complete=True))
    check("complete set: lists the facts, NO partial constraint",
          "Wolves live in packs." in d_complete and "PARTIAL" not in d_complete)
    d_partial = research_directive(ResearchFacts(facts=facts, complete=False,
                                                 declared={"research": "capped at 8 searches — partial (2 facts)"}))
    check("PARTIAL set: lists facts AND forbids ungrounded claims",
          "PARTIAL" in d_partial and "never assert an unverified claim" in d_partial
          and "Wolves live in packs." in d_partial)
    d_none = research_directive(ResearchFacts(facts=(), complete=True))
    check("no facts: explicit do-not-fabricate instruction",
          "none were gathered" in d_none and "Do NOT invent" in d_none)

    print("[4] NOTE 2 — the directive actually reaches ScriptWriter's prompt (facts=… wired)")
    from ytagent.authoring.script import ScriptWriter
    from ytagent.metadata.research import UnavailableResearch

    class _Stop(Exception):
        pass

    class _Capture:
        def __init__(self):
            self.user = None

        def complete(self, req):
            self.user = req.messages[0]["content"]
            raise _Stop()

    ch = {"id": 1, "config": {"niche": "nature documentary", "tone": "reverent",
                              "voice_profile": {"persona": "a deep, poetic British narrator"}}}
    dist = {"habitat": {"savanna": 5}, "shot_type": {"wide": 3}}
    partial_rf = ResearchFacts(facts=facts, complete=False,
                               declared={"research": "capped at 8 searches — partial (2 facts)"})
    cap = _Capture()
    try:
        ScriptWriter(cap).write(topic="wolf", channel=ch, research=UnavailableResearch(),
                                footage_distribution=dist, facts=partial_rf)
    except _Stop:
        pass
    except Exception as e:  # noqa: BLE001 — anything before the LLM call is a real wiring problem
        check("write() reached the LLM call with facts wired", False, f"{type(e).__name__}: {e}")
    check("the grounded facts appear in the writer's prompt",
          cap.user is not None and "Wolves live in packs." in cap.user)
    check("the PARTIAL constraint appears in the writer's prompt",
          cap.user is not None and "PARTIAL" in cap.user
          and "never assert an unverified claim" in cap.user)
    # control: no facts passed → no directive injected (back-compat)
    cap2 = _Capture()
    try:
        ScriptWriter(cap2).write(topic="wolf", channel=ch, research=UnavailableResearch(),
                                 footage_distribution=dist)
    except _Stop:
        pass
    check("without facts= the prompt has NO grounded-facts block (back-compat)",
          cap2.user is not None and "GROUNDED FACTS" not in cap2.user)

    print(f"\n{'✅ ALL PASS' if _fail == 0 else f'❌ {_fail} FAILED'}")
    return 1 if _fail else 0


if __name__ == "__main__":
    sys.exit(main())
