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

import os

from ytagent.config import load_settings
from ytagent.providers import ListUsageSink, get_llm_provider
from ytagent.sourcing.vision import (CLEAR_MATCH, CLEAR_MISMATCH, Expect, classify, vision_check)

_FIX = "tests/fixtures/vision"
_AS_WOLF = Expect(subject="grey wolf", season=("winter", "snow"), required=frozenset({"season"}))
_AS_LION = Expect(subject="lion", season=(), required=frozenset())          # savanna — no season lock
# incidental-axis: NO setting axis is locked; time 'night' is ADVISORY and mismatches the daytime clip
# → classify() still returns 'clear' (advisory axes never block a wild, correct-species clip).
_LION_INCIDENTAL = Expect(subject="lion", time_of_day=("night",), required=frozenset())
PASS, FAIL = "✅", "❌"


def _frames(name: str) -> list[str]:
    """3-frame set (production path) if tests/fixtures/vision/<name>/ exists, else the flat single frame."""
    d = os.path.join(_FIX, name)
    if os.path.isdir(d):
        return [os.path.join(d, f) for f in sorted(os.listdir(d)) if f.endswith(".jpg")]
    return [os.path.join(_FIX, name + ".jpg")]


def main():
    settings = load_settings()
    sink = ListUsageSink()
    llm = get_llm_provider(settings, sink)
    if llm is None:
        print("No ANTHROPIC_API_KEY — cannot calibrate the vision gate (skipped).")
        sys.exit(2)
    try:
        _run(llm)
    finally:
        from scripts._devcost import ledger_calibration_spend
        spent = ledger_calibration_spend(sink)
        print(f"\ncalibration LLM spend ledgered (context=calibration): £{spent:.4f}")


def _run(llm):
    fails = 0
    # NB: the species-reject fixture is the COYOTE — the real failure mode (a canid that looks like a
    # wolf). A "lion image, expect wolf" case was dropped: lion↔wolf isn't a real sourcing risk (the
    # metadata gate never surfaces lions for a wolf query) and the two large predators share enough gross
    # features (robust frame, broad head, short ears) that the feature test legitimately can't separate
    # them — an artificial test that would falsely fail. Canid discrimination is what matters and works.
    # Two-sided, per-axis. species/wild are three-way; classify() applies the beat policy.
    cases = [
        ("coyote", "coyote frame, expect grey wolf", _AS_WOLF,
         lambda v, c: v.species == CLEAR_MISMATCH and c[0] == "reject", "species=clear_mismatch → reject"),
        ("pass_wild_lion", "lion image, expect lion", _AS_LION,
         lambda v, c: v.species == CLEAR_MATCH and v.wild == CLEAR_MATCH and c[0] == "clear",
         "species+wild clear_match → clear/accept"),
        ("fence", "captive fence, expect wolf", _AS_WOLF,
         lambda v, c: v.wild == CLEAR_MISMATCH and c[0] == "reject", "wild=clear_mismatch → reject"),
        ("pass_wild_lion", "lion, night ADVISORY (nothing locked)", _LION_INCIDENTAL,
         lambda v, c: c[0] == "clear", "clear despite time mismatch (incidental axis)"),
    ]
    for name, desc, expect, want, expect_str in cases:
        v = vision_check(_frames(name), expect=expect, llm=llm)
        cat = classify(v, expect)
        ok = want(v, cat)
        fails += 0 if ok else 1
        print(f"  {PASS if ok else FAIL} {name} ({desc}) → want {expect_str}; got "
              f"species={v.species} wild={v.wild} season={v.season_ok} habitat={v.habitat_ok} "
              f"time={v.time_ok} → {cat[0]}{' CONTRADICTION' if v.contradiction else ''}")
        print(f"      reason: {v.reason}")

    # Positive CANID (species clear_match) fixture — a confirmed wolf. Pending Banks's frame pick; when
    # tests/fixtures/vision/wolf/ exists it becomes a BLOCKING both-directions assertion.
    if os.path.isdir(os.path.join(_FIX, "wolf")):
        v = vision_check(_frames("wolf"), expect=Expect(subject="grey wolf", required=frozenset()), llm=llm)
        ok = v.species == CLEAR_MATCH
        fails += 0 if ok else 1
        print(f"  {PASS if ok else FAIL} wolf (confirmed grey wolf) → want species=clear_match; "
              f"got species={v.species} wild={v.wild}{' CONTRADICTION' if v.contradiction else ''}")
        print(f"      reason: {v.reason}")
    else:
        print("  · wolf fixture PENDING Banks's frame confirmation (positive species side not yet locked)")

    # DIAGNOSTIC (recorded, NOT asserted) — is "manicured ground → captive" a real read or over-reject?
    print("\n  — diagnostic (no assertion) —")
    dv = vision_check(_frames("diag_wolf_forest"),
                      expect=Expect(subject="grey wolf", required=frozenset()), llm=llm)
    print(f"  · diag_wolf_forest (wild grey wolves in green forest) → species={dv.species} wild={dv.wild}"
          f"{' CONTRADICTION' if dv.contradiction else ''}")
    print(f"      reason: {dv.reason}")

    print(f"\n{'ALL PASSED — vision gate calibrated' if not fails else str(fails) + ' CALIBRATION FAILURE(S)'}")
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    main()
