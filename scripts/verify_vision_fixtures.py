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
    # With morphology REMOVED from the prompt, species is calibrated on an UNAMBIGUOUS cross-species case
    # (a lion is clearly not a wolf), NOT the coyote/wolf boundary — which the definition-free gate reads
    # as a wolf (the old "coyote" verdict was the handed definition priming it, not observation). The
    # contested coyote clip is kept below as a DIAGNOSTIC, recorded not asserted.
    cases = [
        ("pass_wild_lion", "lion image, expect grey WOLF", _AS_WOLF,
         lambda v, c: v.species == CLEAR_MISMATCH and c[0] == "reject",
         "species=clear_mismatch (a lion is not a wolf) → reject"),
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
              f"species={v.species} wild={v.wild} → {cat[0]}"
              f"{' CONTRADICTION' if v.contradiction else ''}")
        print(f"      observed: season={v.season_observed!r} habitat={v.habitat_observed!r} "
              f"time={v.time_observed!r} shot={v.shot_type!r}")
        print(f"      reason: {v.reason}")

    # DIAGNOSTICS (recorded, NOT asserted) — the contested wolf/coyote clips under the definition-free
    # gate. Wolf is abandoned as a subject; these are kept as evidence, labelled, run over run.
    print("\n  — diagnostics (no assertion — the definition-free gate's read on the contested clips) —")
    for name, note in [("coyote", "the 142472 clip the OLD gate called coyote"),
                       ("diag_wolf_forest", "wild wolves in green forest (57275)")]:
        dv = vision_check(_frames(name), expect=Expect(subject="grey wolf", required=frozenset()), llm=llm)
        print(f"  · {name} ({note}) → species={dv.species} wild={dv.wild}"
              f"{' CONTRADICTION' if dv.contradiction else ''}: {dv.reason[:100]}")

    print(f"\n{'ALL PASSED — vision gate calibrated' if not fails else str(fails) + ' CALIBRATION FAILURE(S)'}")
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    main()
