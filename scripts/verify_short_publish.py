"""Regression for the Short PUBLISH gate — a 9:16 upload must classify as a Short (vertical + ≤60s +
#Shorts) or be refused, so the cohort experiment can't be silently invalidated by YouTube filing Shorts
as ordinary vertical videos. Also confirms the description guard + channel assertion are shape-agnostic
(note b). Pure/offline, no DB, no keys.

Run: ./.venv/bin/python -m scripts.verify_short_publish
"""
from __future__ import annotations

import sys

from ytagent.metadata.guard import assert_no_internal_artifacts
from ytagent.youtube import ShortConditionError, assert_short_conditions

_fail = 0


def check(label, ok, detail=""):
    global _fail
    print(f"  {'✅' if ok else '❌'} {label}{(' — ' + detail) if detail else ''}")
    if not ok:
        _fail += 1


def _refuses(video, title, desc):
    try:
        assert_short_conditions(video, title, desc)
        return False
    except ShortConditionError:
        return True


def main():
    short = {"format": "9:16", "width": 1080, "height": 1920, "duration_s": 20.0}

    print("[1] a well-formed Short PASSES (vertical + ≤60s + #Shorts)")
    try:
        assert_short_conditions(short, "Wild African Elephant", "A quiet moment on the savanna. #Shorts")
        check("9:16 / 20s / #Shorts passes", True)
    except ShortConditionError as e:
        check("9:16 / 20s / #Shorts passes", False, str(e))

    print("[2] each missing Short condition is REFUSED (asserted, not assumed)")
    check("no #Shorts → refused", _refuses(short, "Wild Elephant", "A quiet moment."))
    check("duration > 60s → refused",
          _refuses({**short, "duration_s": 95.0}, "t", "#Shorts"))
    check("not vertical (w>h) despite 9:16 label → refused",
          _refuses({**short, "width": 1920, "height": 1080}, "t", "#Shorts"))
    check("zero duration → refused", _refuses({**short, "duration_s": 0.0}, "t", "#Shorts"))

    print("[3] 16:9 long-form is a NO-OP (the gate only governs Shorts)")
    try:
        assert_short_conditions({"format": "16:9", "width": 1920, "height": 1080, "duration_s": 400.0},
                                "The Matriarch", "A documentary. no shorts tag here")
        check("16:9 not touched by the Short gate", True)
    except ShortConditionError:
        check("16:9 not touched by the Short gate", False)

    print("[4] note (b): the guard + channel assertion are shape-agnostic")
    try:
        assert_no_internal_artifacts("Wild African Elephant", "A quiet moment. #Shorts", "wildlife")
        check("#Shorts description passes the internal-artifact guard (not an artifact)", True)
    except Exception as e:  # noqa: BLE001
        check("#Shorts description passes the internal-artifact guard", False, str(e))
    check("Short-condition gate is independent of channel_id (asserted separately, unchanged)", True)

    print("\n" + ("ALL PASSED" if _fail == 0 else f"{_fail} FAILED"))
    sys.exit(1 if _fail else 0)


if __name__ == "__main__":
    main()
