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
from ytagent.sourcing.vision import Expect, VisionUnavailable, vision_check

PASS, FAIL = "✅", "❌"
_failures = 0
_FRAME = "tests/fixtures/vision/fail_fence.jpg"   # any real jpg — content ignored by the fake LLM


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


def _v(species=True, wild=True, season=True, habitat=True, time=True):
    j = {"species_ok": species, "wild": wild, "season_ok": season, "habitat_ok": habitat, "time_ok": time}
    return "{" + ", ".join(f'"{k}": {str(x).lower()}' for k, x in j.items()) + ', "reason": "test"}'


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

    print("[4] per-axis vision verdict — season blocks, habitat/time advisory unless required")
    wolf = Expect(subject="grey wolf", season=("snow",), habitat=("forest",), time_of_day=("dusk",),
                  required=frozenset({"season"}))
    wolf_dusk = Expect(subject="grey wolf", season=("snow",), time_of_day=("dusk",),
                       required=frozenset({"season", "time_of_day"}))
    cases = [
        ("all axes pass → accept", wolf, _v(), True),
        ("wrong species → reject", wolf, _v(species=False), False),
        ("captive → reject", wolf, _v(wild=False), False),
        ("wrong season (required) → reject", wolf, _v(season=False), False),
        ("wrong HABITAT but habitat advisory → accept (incidental)", wolf, _v(habitat=False), True),
        ("wrong TIME but time advisory → accept (incidental)", wolf, _v(time=False), True),
        ("wrong TIME when time is a PER-BEAT lock → reject", wolf_dusk, _v(time=False), False),
    ]
    for label, expect, verdict, want in cases:
        vd = vision_check([_FRAME], expect=expect, llm=_FakeVisionLLM(verdict))
        check(label, vd.overall_ok is want, f"overall={vd.overall_ok} failed={vd.failed_axes}")

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
