"""Offline (zero network/spend) verification for footage CURATION — the logic units behind Part 1:
season/setting terms reach the queries, the negative-tag filter disqualifies captive footage, and the
vision-gate verdict logic (required axes) is correct. The LIVE two-sided calibration of the real gate
against the saved fixtures lives in scripts/verify_vision_fixtures.py.

Run: ./.venv/bin/python -m scripts.verify_curation
"""
from __future__ import annotations

import sys

from ytagent.providers.base import LLMResponse, TokenUsage
from ytagent.sourcing.base import Candidate, QueryPlan
from ytagent.sourcing.query import build_query_plan
from ytagent.sourcing.rank import score_candidate
from ytagent.sourcing.vision import Expect, vision_check

PASS, FAIL = "✅", "❌"
_failures = 0
_FRAME = "tests/fixtures/vision/fail_fence.jpg"   # any real jpg — content ignored by the fake LLM


def check(label, ok, detail=""):
    global _failures
    print(f"  {PASS if ok else FAIL} {label}{(' — ' + detail) if detail else ''}")
    if not ok:
        _failures += 1


class _FakeVisionLLM:
    """Returns a canned verdict JSON — tests the wiring/required-axis logic without a network call."""
    def __init__(self, verdict_json):
        self._v = verdict_json

    def complete(self, req):
        # sanity: the request must actually carry image blocks (proves frames were attached)
        assert any(b.get("type") == "image" for m in req.messages for b in m["content"]), "no image block"
        return LLMResponse(text=self._v, model="fake-haiku", usage=TokenUsage(), request_id="r")


def _v(species, wild, season):
    return f'{{"species_ok": {str(species).lower()}, "wild": {str(wild).lower()}, ' \
           f'"season_ok": {str(season).lower()}, "reason": "test"}}'


def main():
    print("[1] season/setting terms reach the queries (deterministic, no LLM)")
    p = build_query_plan("a grey wolf pack in snowy boreal forest at dusk", approx_seconds=40,
                         target_fmt="16:9")
    check("setting terms captured from the brief", bool(p.setting), str(p.setting))
    check("a query pairs subject + a setting term",
          any(any(s in q for s in p.setting) for q in p.queries), str(p.queries))

    print("[2] negative-tag filter disqualifies captive footage")
    plan = QueryPlan(queries=("grey wolf", "wolf snow"), orientation="landscape", min_seconds=10,
                     must_terms=("wolf",), subject="grey wolf", setting=("snow",))
    wild = Candidate("pixabay", "1", "https://x/wolf-snow/", "u", "L", 1920, 1080,
                     tags=("wolf", "snow", "wild"))
    zoo = Candidate("pixabay", "2", "https://x/wolf/", "u", "L", 1920, 1080,
                    tags=("wolf", "zoo", "enclosure"))
    sw, _ = score_candidate(wild, plan, target_w=1920, target_h=1080)
    sz, bd = score_candidate(zoo, plan, target_w=1920, target_h=1080)
    check("wild clip scores above threshold", sw > 0.45, f"{sw}")
    check("captive (zoo/enclosure) clip disqualified", sz == 0.0, bd.get("disqualified", ""))

    print("[3] vision-gate required-axis logic")
    wolf = Expect(subject="grey wolf", wild=True, season=("winter", "snow"))
    lion = Expect(subject="lion", wild=True, season=())          # no season required
    cases = [
        ("all pass → accept", wolf, _v(True, True, True), True),
        ("wrong species → reject", wolf, _v(False, True, True), False),
        ("captive (wild=false) → reject", wolf, _v(True, False, True), False),
        ("wrong season → reject", wolf, _v(True, True, False), False),
        ("no-season-expected ignores season → accept", lion, _v(True, True, False), True),
    ]
    for label, expect, verdict, want in cases:
        v = vision_check([_FRAME], expect=expect, llm=_FakeVisionLLM(verdict))
        check(label, v.overall_ok is want, f"overall={v.overall_ok}")
    skipped = vision_check([_FRAME], expect=wolf, llm=None)
    check("no LLM → gate SKIPPED (degrades honestly, passes)", skipped.skipped and skipped.overall_ok)

    print(f"\n{'ALL PASSED' if _failures == 0 else str(_failures) + ' CHECK(S) FAILED'}")
    sys.exit(1 if _failures else 0)


if __name__ == "__main__":
    main()
