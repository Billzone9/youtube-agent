"""Regression for the §1 allowance fix — the affordability model must keep RECURRING and AVAILABLE-now
strictly distinct, and compute cadence off RECURRING (not off rollover-inflated availability). Pure,
offline, no DB, no keys.

Run: ./.venv/bin/python -m scripts.verify_allowance
"""
from __future__ import annotations

import sys

from scripts.roi_report import affordability

_fail = 0


def check(label, ok, detail=""):
    global _fail
    print(f"  {'✅' if ok else '❌'} {label}{(' — ' + detail) if detail else ''}")
    if not ok:
        _fail += 1


def main():
    recurring, credits_per_film = 30_000, 6_850     # ~4.4 films/mo sustainable

    print("[1] cadence is computed off RECURRING, never off available_now (incl rollover)")
    a = affordability(recurring, available_now_cr=53_599, credits_per_film=credits_per_film)
    check("sustainable_films_pm uses recurring (30,000/6,850 ≈ 4.4)",
          abs(a["sustainable_films_pm"] - 30_000 / 6_850) < 1e-9, f"{a['sustainable_films_pm']:.2f}")
    check("sustainable is NOT computed off available_now (would be ~7.8)",
          abs(a["sustainable_films_pm"] - 53_599 / 6_850) > 1.0)

    print("[2] recurring and available_now stay DISTINCT; rollover is the surplus")
    check("recurring preserved", a["recurring_cr"] == 30_000)
    check("available_now preserved", a["available_now_cr"] == 53_599)
    check("rollover = available_now − recurring", a["rollover_cr"] == 53_599 - 30_000, f"{a['rollover_cr']}")
    check("available_films_this_month uses available_now (~7.8)",
          abs(a["available_films_this_month"] - 53_599 / 6_850) < 1e-9)

    print("[3] no rollover when available == recurring; negative surplus floored at 0")
    b = affordability(recurring, available_now_cr=30_000, credits_per_film=credits_per_film)
    check("rollover is 0 when available == recurring", b["rollover_cr"] == 0)
    c = affordability(recurring, available_now_cr=25_000, credits_per_film=credits_per_film)
    check("rollover floored at 0 when available < recurring", c["rollover_cr"] == 0)

    print("[4] degrades when the live read is unavailable (available_now = None)")
    d = affordability(recurring, available_now_cr=None, credits_per_film=credits_per_film)
    check("sustainable still computed off recurring", abs(d["sustainable_films_pm"] - 30_000 / 6_850) < 1e-9)
    check("available/rollover are None (not fabricated)",
          d["available_now_cr"] is None and d["rollover_cr"] is None)

    print("\n" + ("ALL PASSED" if _fail == 0 else f"{_fail} FAILED"))
    sys.exit(1 if _fail else 0)


if __name__ == "__main__":
    main()
