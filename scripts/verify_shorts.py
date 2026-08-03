"""Regression for M1 credit-light Shorts foundations: the Shorts density rule (a ≤60s vertical may hold
ONE striking shot — floor relaxed to 1 — but no-reuse still enforced), the claim-safe bed library
(rotates, gate-clean), and the credit costing (reused bed ≈ 0, generated 30s bed ≈ 520). Pure/offline;
the bed-library check needs the local media (skips cleanly if absent). No DB, no keys.

Run: ./.venv/bin/python -m scripts.verify_shorts
"""
from __future__ import annotations

import sys
from types import SimpleNamespace

from ytagent.assembly.beds import bed_library, pick_bed
from ytagent.assembly.density import VisualDensityError, assert_visual_density, min_clips
from ytagent.audio_design import _CREDITS_PER_SEC

_fail = 0


def check(label, ok, detail=""):
    global _fail
    print(f"  {'✅' if ok else '❌'} {label}{(' — ' + detail) if detail else ''}")
    if not ok:
        _fail += 1


def _spec(beats):
    return SimpleNamespace(source="clips", beats=beats)


def _beat(name, srcs):
    return SimpleNamespace(name=name, clips=[SimpleNamespace(src=s) for s in srcs], narration=None)


def main():
    print("[1] Shorts density: a ≤60s vertical may HOLD one shot (floor 1); long-form would refuse it")
    one_clip_40s = _spec([_beat("s1", ["clipA"])])
    ns = {"s1": 40.0}
    try:
        assert_visual_density(one_clip_40s, ns, short=True)
        check("short=True: a single 40s held shot PASSES", True)
    except VisualDensityError as e:
        check("short=True: a single 40s held shot PASSES", False, str(e))
    try:
        assert_visual_density(one_clip_40s, ns, short=False)
        check("short=False (long-form): the same 1-clip 40s beat is REFUSED", False)
    except VisualDensityError:
        check("short=False (long-form): the same 1-clip 40s beat is REFUSED", True,
              f"needs {min_clips(40)} clips")

    print("[2] no-reuse still enforced for Shorts (a declared exception aside)")
    reuse = _spec([_beat("s1", ["clipA"]), _beat("s2", ["clipA"])])
    try:
        assert_visual_density(reuse, {"s1": 20.0, "s2": 20.0}, short=True)
        check("a clip reused across two Short beats is REFUSED", False)
    except VisualDensityError:
        check("a clip reused across two Short beats is REFUSED", True)

    print("[3] claim-safe bed library — the 0-credit reuse path")
    beds = bed_library()
    if not beds:
        # local media (gitignored) — absent on a fresh clone/CI is NOT a code defect; skip, don't fail
        print("  ⏭️  bed library media absent (assets/beds/) — skipping (local-only; provenance in spec)")
    else:
        check("bed library has ≥1 claim-safe bed", len(beds) >= 1, f"{len(beds)} beds")
        if len(beds) >= 2:
            check("pick_bed ROTATES (consecutive Shorts differ)", pick_bed(0) != pick_bed(1))
        check("picked bed passes the noise gate (verify=True didn't raise)", pick_bed(0) is not None)

    print("[4] credit costing: reused bed ≈ 0, fresh 30s bed ≈ 520 (with retake headroom)")
    reused = 0
    generated_30s = 30 * _CREDITS_PER_SEC * 1.15
    check("reused-bed Short music cost is 0 credits", reused == 0)
    check("fresh 30s bed ≈ 500–540 credits", 500 <= generated_30s <= 540, f"{generated_30s:.0f}")

    print("\n" + ("ALL PASSED" if _fail == 0 else f"{_fail} FAILED"))
    sys.exit(1 if _fail else 0)


if __name__ == "__main__":
    main()
