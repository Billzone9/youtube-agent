"""Offline (zero network/spend) verification for footage CURATION — the logic units behind the
footage-led slice: setting words split into SEPARATE axes; a strict majority of season-locked queries
carry the season; the minimal negative-tag filter; the per-axis vision verdict (season required,
habitat/time advisory or per-beat-required); the incidental-axis rule (a good clip is NOT rejected for
an unlocked axis); and the Item-6 FAIL-LOUD when the gate is required but no LLM is configured. The LIVE
two-sided calibration of the real gate lives in scripts/verify_vision_fixtures.py.

Run: ./.venv/bin/python -m scripts.verify_curation
"""
from __future__ import annotations

import asyncio
import sys

from ytagent.providers.base import LLMResponse, TokenUsage
from ytagent.sourcing import source_clips_for_brief
from ytagent.sourcing.base import Candidate, QueryPlan
from ytagent.sourcing.query import build_query_plan, derive_axis_locks
from ytagent.sourcing.rank import score_candidate
from ytagent.sourcing.vision import (CLEAR_MATCH, CLEAR_MISMATCH, UNCERTAIN, Expect, VisionUnavailable,
                                     classify, vision_check)

PASS, FAIL = "✅", "❌"
_failures = 0
_FRAME = "tests/fixtures/vision/fence/vf_0.jpg"   # any real jpg — content ignored by the fake LLM


def check(label, ok, detail=""):
    global _failures
    print(f"  {PASS if ok else FAIL} {label}{(' — ' + detail) if detail else ''}")
    if not ok:
        _failures += 1


class _FakeVisionLLM:
    def __init__(self, verdict_json):
        self._v = verdict_json

    def complete(self, req):
        assert any(b.get("type") == "image" for m in req.messages for b in m["content"]), "no image block"
        return LLMResponse(text=self._v, model="fake-haiku", usage=TokenUsage(), request_id="r")


def _v(species=CLEAR_MATCH, wild=CLEAR_MATCH, season="snow", habitat="forest", time="dusk",
       indicate="grey wolf"):
    import json
    # NEW gate shape: setting axes are OBSERVED free labels (matched to expectations in code).
    return json.dumps({"features": "broad muzzle, blocky head, heavy frame", "features_indicate": indicate,
                       "species": species, "wild": wild, "season": season, "habitat": habitat,
                       "time_of_day": time, "shot_type": "wide", "reason": "test"})


def main():
    print("[1] setting words split into SEPARATE axes (season / habitat / time)")
    p = build_query_plan("a grey wolf pack in snowy boreal forest at dusk", approx_seconds=40,
                         target_fmt="16:9")
    check("season axis = snow", p.season == ("snowy",), str(p.season))
    check("habitat axis = boreal/forest", set(p.habitat) == {"boreal", "forest"}, str(p.habitat))
    check("time axis = dusk (NOT mixed into season)", p.time_of_day == ("dusk",), str(p.time_of_day))
    locks = derive_axis_locks("wolf in deep snow on the tundra at dawn")
    check("derive_axis_locks names each axis", locks.get("season") and locks.get("habitat") and locks.get("time_of_day"),
          str(locks))

    print("[2] a strict MAJORITY of season-locked queries carry the season term")
    maj = sum(1 for q in p.queries if "snow" in q)
    check("majority carry season", maj > len(p.queries) // 2, f"{maj}/{len(p.queries)}: {p.queries}")

    print("[3] minimal negative-tag filter (unambiguous captivity only)")
    plan = QueryPlan(queries=("grey wolf", "wolf snow"), orientation="landscape", min_seconds=10,
                     must_terms=("wolf",), subject="grey wolf", season=("snow",))
    def score(tags):
        c = Candidate("pixabay", "1", "https://x/w/", "u", "L", 1920, 1080, tags=tags)
        return score_candidate(c, plan, target_w=1920, target_h=1080)
    check("zoo/enclosure disqualified", score(("wolf", "zoo", "enclosure"))[0] == 0.0)
    check("SANCTUARY no longer disqualified (land designation, not captivity)",
          score(("wolf", "sanctuary", "snow"))[0] > 0.45)
    check("FARM no longer disqualified", score(("wolf", "farm", "snow"))[0] > 0.45)

    print("[4] three-way verdict → POLICY category (clear/uncertain/reject)")
    wolf = Expect(subject="grey wolf", season=("snow",), habitat=("forest",), time_of_day=("dusk",),
                  required=frozenset({"season"}))
    wolf_dusk = Expect(subject="grey wolf", season=("snow",), time_of_day=("dusk",),
                       required=frozenset({"season", "time_of_day"}))
    cases = [
        ("all clear_match, season observed matches → clear", wolf, _v(), "clear"),
        ("species clear_mismatch → reject", wolf, _v(species=CLEAR_MISMATCH, indicate="coyote"), "reject"),
        ("species UNCERTAIN → uncertain (reserve)", wolf, _v(species=UNCERTAIN, indicate="wolf or coyote"), "uncertain"),
        ("wild clear_mismatch (captive) → reject", wolf, _v(wild=CLEAR_MISMATCH), "reject"),
        ("observed season 'dry' vs required snow → reject", wolf, _v(season="dry"), "reject"),
        ("observed habitat mismatch but habitat advisory → clear", wolf, _v(habitat="savanna"), "clear"),
        ("observed time mismatch but time advisory → clear", wolf, _v(time="midday"), "clear"),
        ("observed time 'midday' when time is a PER-BEAT lock → reject", wolf_dusk, _v(time="midday"), "reject"),
    ]
    for label, expect, verdict, want in cases:
        vd = vision_check([_FRAME], expect=expect, llm=_FakeVisionLLM(verdict))
        cat = classify(vd, expect)
        check(label, cat[0] == want, f"category={cat}")

    print("[4b] evidence↔verdict CONTRADICTION detected")
    vd = vision_check([_FRAME], expect=wolf, llm=_FakeVisionLLM(_v(species=CLEAR_MISMATCH, indicate="grey wolf")))
    check("features say wolf but verdict rejects → contradiction=True", vd.contradiction is True)
    vd2 = vision_check([_FRAME], expect=wolf, llm=_FakeVisionLLM(_v(species=CLEAR_MATCH, indicate="grey wolf")))
    check("features say wolf and verdict accepts → contradiction=False", vd2.contradiction is False)

    print("[4c] CLIP-ECHO fires only on DIFFERENT verdicts (density-compatible)")
    from ytagent.sourcing.vision import detect_echo
    CM, MM = CLEAR_MATCH, CLEAR_MISMATCH
    # THE density case: four genuinely different clips of the SAME subject, all clear_match → NO flag.
    four = [("a", "broad muzzle, blocky head", CM), ("b", "heavy frame, deep chest, long legs", CM),
            ("c", "thick neck, robust build", CM), ("d", "large paws, bushy tail, alert ears", CM)]
    check("4 different same-VERDICT clips → NO clip-echo (density-safe)", len(detect_echo(four)) == 0)
    ident = "narrow pointed muzzle, large ears, slender frame, long legs"
    check("near-identical features but DIFFERENT verdicts → flagged",
          len(detect_echo([("a", ident, CM), ("b", ident, MM)])) == 1)
    check("identical features, SAME verdict → NOT flagged (expected recurrence)",
          len(detect_echo([("a", ident, MM), ("b", ident, MM)])) == 0)

    print("[5] Item 6 — vision gate FAILS LOUD when required but no LLM")
    async def _no_llm():
        return await source_clips_for_brief(
            None, [], brief="grey wolf", brief_ref="b", approx_seconds=10, target_fmt="16:9",
            target_w=1920, target_h=1080, cache_dir="/tmp", channel_id=1, llm=None,
            n_target=3, n_min=3, vision=True)
    try:
        asyncio.run(_no_llm())
        check("vision=True + no LLM raises VisionUnavailable", False, "did NOT raise")
    except VisionUnavailable:
        check("vision=True + no LLM raises VisionUnavailable", True)
    skipped = vision_check([_FRAME], expect=wolf, llm=None)
    check("explicit no-LLM vision_check still SKIPS (the vision=False path)", skipped.skipped)

    print(f"\n{'ALL PASSED' if _failures == 0 else str(_failures) + ' CHECK(S) FAILED'}")
    sys.exit(1 if _failures else 0)


if __name__ == "__main__":
    main()
