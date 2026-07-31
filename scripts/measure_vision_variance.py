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
# species/wild are THREE-WAY labels; season/habitat/time are booleans
_LABEL_AXES = ("species", "wild")
_BOOL_AXES = ("season_ok", "habitat_ok", "time_ok")

_CASES = [
    ("coyote", Expect(subject="grey wolf", season=("winter", "snow"), required=frozenset({"season"}))),
    ("fence", Expect(subject="grey wolf", season=("winter", "snow"), required=frozenset({"season"}))),
    ("pass_wild_lion", Expect(subject="lion", required=frozenset())),
    ("diag_wolf_forest", Expect(subject="grey wolf", required=frozenset())),
]


def _frames(name):
    d = os.path.join(_FIX, name)
    if os.path.isdir(d):
        return [os.path.join(d, f) for f in sorted(os.listdir(d)) if f.endswith(".jpg")]
    return [os.path.join(_FIX, name + ".jpg")]


def _measure(llm, samples):
    print(f"\n=== samples={samples} ({'RAW single call' if samples == 1 else 'majority-of-%d' % samples}), "
          f"N={N} runs, temperature=0, 3-frame ===")
    total_flips = 0
    for name, expect in _CASES:
        frames = _frames(name)
        if not frames or not os.path.exists(frames[0]):
            print(f"  {name}: MISSING")
            continue
        runs = [vision_check(frames, expect=expect, llm=llm, samples=samples) for _ in range(N)]
        print(f"  {name} (expect {expect.subject}):")
        for ax in _LABEL_AXES:                       # three-way: show the labels seen
            vals = [getattr(r, ax) for r in runs]
            flipped = len(set(vals)) > 1
            total_flips += 1 if flipped else 0
            flag = " ⚠️ FLIPPED" if flipped else ""
            print(f"    {ax:9} = {[v[:6] for v in vals]}{flag}")
        for ax in _BOOL_AXES:                        # booleans: only show if they flip
            vals = [getattr(r, ax) for r in runs]
            if len(set(vals)) > 1:
                total_flips += 1
                print(f"    {ax:9} = {['T' if v else 'F' for v in vals]} ⚠️ FLIPPED")
    return total_flips


def main():
    sink = ListUsageSink()
    llm = get_llm_provider(load_settings(), sink)
    if llm is None:
        print("No ANTHROPIC_API_KEY.")
        sys.exit(2)
    try:
        raw = _measure(llm, 1)
        maj = _measure(llm, 3)
        print(f"\nRAW flips: {raw} · MAJORITY-of-3 flips: {maj}")
        print("(species/wild labels printed every row; booleans only when they flip)")
    finally:
        from scripts._devcost import ledger_calibration_spend
        print(f"\ncalibration LLM spend ledgered (context=calibration): £{ledger_calibration_spend(sink):.4f}")


if __name__ == "__main__":
    main()
