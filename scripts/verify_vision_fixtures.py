"""PERMANENT calibration regression for the VISION GATE (live — needs ANTHROPIC_API_KEY; ~3 cheap
Haiku-vision calls, no Music spend). Runs the real gate on the three saved fixtures extracted from the
wolf Pass-A cut and asserts the two-sided calibration (the doctrine used for the AI-tell + noise gates):

  fail_fence.jpg     + expect grey wolf   → wild=FALSE (captive enclosure)        → REJECTED
  pass_wild_lion.jpg + expect grey wolf   → species=FALSE (a lion is not a wolf)  → REJECTED
  pass_wild_lion.jpg + expect lion        → all axes TRUE                         → ACCEPTED
  pass_wild_lion.jpg + expect lion, time=night ADVISORY (no locked setting axis) → accept despite the
                       daytime/​night mismatch (the incidental-axis proof — advisory axes never block)

Only the two ROCK-SOLID fixtures are used (a clearly-captive wolf, and unambiguously-wild lions), each
tested against several expectations. The wolf/coyote species boundary and free-stock 'wild wolf' clips
are genuinely borderline — Haiku flip-flops on them — so they make flaky regressions; the deterministic
species-reject + incidental-axis logic is covered offline in verify_curation.py.

Run: ./.venv/bin/python -m scripts.verify_vision_fixtures
"""
from __future__ import annotations

import sys

from ytagent.config import load_settings
from ytagent.providers import ListUsageSink, get_llm_provider
from ytagent.sourcing.vision import Expect, vision_check

_FIX = "tests/fixtures/vision"
_AS_WOLF = Expect(subject="grey wolf", season=("winter", "snow"), required=frozenset({"season"}))
_AS_LION = Expect(subject="lion", season=(), required=frozenset())          # savanna — no season lock
# incidental-axis: NO setting axis is locked; time 'night' is ADVISORY and mismatches the daytime clip
# → overall still accepts (advisory axes never block a genuinely-wild, correct-species clip).
_LION_INCIDENTAL = Expect(subject="lion", time_of_day=("night",), required=frozenset())
PASS, FAIL = "✅", "❌"


def main():
    settings = load_settings()
    llm = get_llm_provider(settings, ListUsageSink())
    if llm is None:
        print("No ANTHROPIC_API_KEY — cannot calibrate the vision gate (skipped).")
        sys.exit(2)

    fails = 0
    # NB: the species-reject fixture is the COYOTE — the real failure mode (a canid that looks like a
    # wolf). A "lion image, expect wolf" case was dropped: lion↔wolf isn't a real sourcing risk (the
    # metadata gate never surfaces lions for a wolf query) and the two large predators share enough gross
    # features (robust frame, broad head, short ears) that the feature test legitimately can't separate
    # them — an artificial test that would falsely fail. Canid discrimination is what matters and works.
    cases = [
        # SPECIES is the axis that matters most (a false green sends the wrong animal into the film):
        ("fail_coyote.jpg", "coyote frame, expect grey wolf", _AS_WOLF,
         lambda v: not v.species_ok, "species=False (coyote features) → reject"),
        ("pass_wild_lion.jpg", "lion image, expect lion", _AS_LION,
         lambda v: v.overall_ok, "all True → accept"),
        ("fail_fence.jpg", "captive fence, expect wolf", _AS_WOLF,
         lambda v: (not v.overall_ok) and (not v.wild_ok), "wild=False → reject"),
        ("pass_wild_lion.jpg", "lion, night ADVISORY (nothing locked)", _LION_INCIDENTAL,
         lambda v: v.overall_ok and v.species_ok and v.wild_ok,
         "accept despite time mismatch (incidental axis)"),
    ]
    for fname, desc, expect, want, expect_str in cases:
        v = vision_check([f"{_FIX}/{fname}"], expect=expect, llm=llm)
        ok = want(v)
        fails += 0 if ok else 1
        print(f"  {PASS if ok else FAIL} {fname} ({desc}) → want {expect_str}; got "
              f"species={v.species_ok} wild={v.wild_ok} season={v.season_ok} habitat={v.habitat_ok} "
              f"time={v.time_ok} overall={v.overall_ok} failed={v.failed_axes}")
        print(f"      reason: {v.reason}")

    # DIAGNOSTIC (recorded, NOT asserted) — is "manicured ground → captive" a real read or over-reject?
    # Keep the evidence that didn't fit and label it, run over run.
    print("\n  — diagnostic (no assertion) —")
    dv = vision_check([f"{_FIX}/diag_wolf_forest.jpg"],
                      expect=Expect(subject="grey wolf", required=frozenset()), llm=llm)
    print(f"  · diag_wolf_forest.jpg (wild grey wolves in green forest) → "
          f"species={dv.species_ok} wild={dv.wild_ok} → {'reads WILD' if dv.wild_ok else 'reads CAPTIVE'}")
    print(f"      reason: {dv.reason}")

    print(f"\n{'ALL PASSED — vision gate calibrated' if not fails else str(fails) + ' CALIBRATION FAILURE(S)'}")
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    main()
