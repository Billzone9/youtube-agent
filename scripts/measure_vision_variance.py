"""Measure the VISION GATE's run-to-run variance (the fence flip-flop was non-determinism from default
sampling, not flakiness). Runs each fixture N times and reports, per fixture PER AXIS, the values seen
and whether the axis FLIPPED across runs. With temperature=0 the flip rate should be ~0; any residual
flipping on the species axis justifies majority-of-N sampling.

Run: N=5 ./.venv/bin/python -m scripts.measure_vision_variance
"""
from __future__ import annotations

import os
import sys

from ytagent.config import load_settings
from ytagent.providers import ListUsageSink, get_llm_provider
from ytagent.sourcing.vision import Expect, vision_check

_FIX = "tests/fixtures/vision"
N = int(os.environ.get("N", "5"))
_AXES = ("species_ok", "wild_ok", "season_ok", "habitat_ok", "time_ok")

_CASES = [
    ("fail_coyote.jpg", Expect(subject="grey wolf", season=("winter", "snow"), required=frozenset({"season"}))),
    ("fail_fence.jpg", Expect(subject="grey wolf", season=("winter", "snow"), required=frozenset({"season"}))),
    ("pass_wild_lion.jpg", Expect(subject="lion", required=frozenset())),
    ("diag_wolf_forest.jpg", Expect(subject="grey wolf", required=frozenset())),
]


def _measure(llm, samples):
    print(f"\n=== samples={samples} ({'RAW single call' if samples == 1 else 'majority-of-%d' % samples}), "
          f"N={N} runs, temperature=0 ===")
    total_flips = 0
    for fname, expect in _CASES:
        path = f"{_FIX}/{fname}"
        if not os.path.exists(path):
            print(f"  {fname}: MISSING")
            continue
        runs = [vision_check([path], expect=expect, llm=llm, samples=samples) for _ in range(N)]
        print(f"  {fname} (expect {expect.subject}):")
        for ax in _AXES:
            vals = [getattr(r, ax) for r in runs]
            flipped = len(set(vals)) > 1
            total_flips += 1 if flipped else 0
            if flipped or ax == "species_ok":
                flag = " ⚠️ FLIPPED" if flipped else ""
                print(f"    {ax:11} = {['T' if v else 'F' for v in vals]}{flag}")
    return total_flips


def main():
    llm = get_llm_provider(load_settings(), ListUsageSink())
    if llm is None:
        print("No ANTHROPIC_API_KEY.")
        sys.exit(2)
    raw = _measure(llm, 1)
    maj = _measure(llm, 3)
    print(f"\nRAW flips: {raw} · MAJORITY-of-3 flips: {maj}")
    print("(species is printed every row; other axes only when they flipped)")


if __name__ == "__main__":
    main()
