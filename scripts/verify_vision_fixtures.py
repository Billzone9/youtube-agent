"""PERMANENT calibration regression for the VISION GATE (live — needs ANTHROPIC_API_KEY; ~3 cheap
Haiku-vision calls, no Music spend). Runs the real gate on the three saved fixtures extracted from the
wolf Pass-A cut and asserts the two-sided calibration (the doctrine used for the AI-tell + noise gates):

  fail_fence.jpg     (wolf in a captive enclosure, wolf expected) → wild=FALSE    → REJECTED
  fail_coyote.jpg    (a coyote, grey wolf expected)               → species=FALSE → REJECTED
  pass_wild_lion.jpg (two wild lions in open savanna, lion expected) → all TRUE   → ACCEPTED

The pass case uses the hand-curated lion footage (Banks-approved as the standard) because the wolf
Pass-A cut was BROADLY captive/off-brief — the gate rightly rejects every wolf frame in it, which is
exactly the problem this whole slice fixes. The two-sided calibration proves the gate discriminates
(accepts genuinely-wild, correct-species footage) rather than simply rejecting everything.

Run: ./.venv/bin/python -m scripts.verify_vision_fixtures
"""
from __future__ import annotations

import sys

from ytagent.config import load_settings
from ytagent.providers import ListUsageSink, get_llm_provider
from ytagent.sourcing.vision import Expect, vision_check

_FIX = "tests/fixtures/vision"
_WOLF = Expect(subject="grey wolf", wild=True, season=("winter", "snow"))
_LION = Expect(subject="lion", wild=True, season=())      # savanna — no season constraint
PASS, FAIL = "✅", "❌"


def main():
    settings = load_settings()
    llm = get_llm_provider(settings, ListUsageSink())
    if llm is None:
        print("No ANTHROPIC_API_KEY — cannot calibrate the vision gate (skipped).")
        sys.exit(2)

    fails = 0
    cases = [
        ("fail_fence.jpg", "captive fence", _WOLF,
         lambda v: (not v.overall_ok) and (not v.wild_ok), "wild=False"),
        ("fail_coyote.jpg", "coyote≠wolf", _WOLF,
         lambda v: (not v.overall_ok) and (not v.species_ok), "species=False"),
        ("pass_wild_lion.jpg", "wild lions in savanna", _LION,
         lambda v: v.overall_ok, "all True"),
    ]
    for fname, desc, expect, want, expect_str in cases:
        v = vision_check([f"{_FIX}/{fname}"], expect=expect, llm=llm)
        ok = want(v)
        fails += 0 if ok else 1
        print(f"  {PASS if ok else FAIL} {fname} ({desc}) → want {expect_str}; got "
              f"species={v.species_ok} wild={v.wild_ok} season={v.season_ok} overall={v.overall_ok}")
        print(f"      reason: {v.reason}")

    print(f"\n{'ALL PASSED — vision gate calibrated' if not fails else str(fails) + ' CALIBRATION FAILURE(S)'}")
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    main()
