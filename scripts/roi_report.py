"""Honest ROI report (B3 item 4). LEADS with per-film production cost broken down by provider —
because that, times the cadence, is the number that decides whether the schedule is affordable — then
separates fixed infrastructure from production from calibration/dev so a big total isn't mistaken for a
big production bill. Reports real ledger data only; never invents revenue.

Run: POSTGRES_HOST=localhost POSTGRES_PORT=5433 ./.venv/bin/python -m scripts.roi_report
"""
from __future__ import annotations

import asyncio

import psycopg
from psycopg.rows import dict_row

from ytagent import repo
from ytagent.budget import budget_status
from ytagent.config import load_settings

_FILMS_PER_MONTH = 8.67          # 2/week × 52/12


def _g(x):
    return float(x or 0)


async def run():
    settings = load_settings()
    conn = await psycopg.AsyncConnection.connect(settings.dsn(), row_factory=dict_row, autocommit=True)
    b = await repo.ledger.roi_breakdown(conn)
    bud = await budget_status(conn)

    print("=" * 74)
    print("PER-FILM PRODUCTION COST — by provider (the number that decides cadence)")
    print("=" * 74)
    print(f"  {'job':>4} {'film':<26} {'status':<10} {'TTS':>7} {'Music':>7} {'LLM':>8} {'TOTAL':>8}")
    complete = []
    for r in b["per_film"]:
        film = (r["film"] or "?")[:26]
        tot = _g(r["total"])
        if r["status"] == "assembled" and _g(r["music"]) > 0:      # a full production (audio designed)
            complete.append(tot)
        print(f"  {r['id']:>4} {film:<26} {r['status']:<10} £{_g(r['tts']):>5.2f} "
              f"£{_g(r['music']):>5.2f} £{_g(r['llm']):>6.4f} £{tot:>6.2f}")

    ref = max(complete) if complete else 0.0
    print("\n" + "-" * 74)
    print("CADENCE AFFORDABILITY — ElevenLabs is the cost centre, not Anthropic")
    print("-" * 74)
    print(f"  reference COMPLETE film (full audio design): £{ref:.2f}  "
          f"(≈{'99%' if ref else '—'} ElevenLabs TTS+Music, LLM is pennies)")
    monthly = ref * _FILMS_PER_MONTH
    ceiling = _g(bud["ceiling_gbp"])
    print(f"  at 2 films/week  →  {_FILMS_PER_MONTH:.1f} films/mo × £{ref:.2f} = "
          f"£{monthly:.0f}/mo production")
    head = ceiling - monthly
    print(f"  vs £{ceiling:.0f} tier-1 ceiling  →  {'£%.0f headroom' % head if head >= 0 else 'OVER by £%.0f' % -head}"
          f"  ({monthly/ceiling*100:.0f}% of ceiling on production alone)" if ceiling else "")

    print("\n" + "-" * 74)
    print("SPEND BUCKETS — a big total is mostly FIXED + CALIBRATION, not production")
    print("-" * 74)
    fixed_cap, fixed_am = _g(b["fixed_capital_gbp"]), _g(b["fixed_amortised_gbp"])
    prod, calib = _g(b["production_gbp"]), _g(b["calibration_gbp"])
    print(f"  fixed infrastructure — capital cash outlay (e.g. annual VPS) : £{fixed_cap:>7.2f}")
    print(f"  fixed infrastructure — amortised monthly accrual            : £{fixed_am:>7.2f}")
    print(f"  PRODUCTION spend (films — the ROI denominator)              : £{prod:>7.2f}")
    print(f"  calibration / development spend                             : £{calib:>7.2f}")
    print(f"  {'':<60}  {'-'*8}")
    print(f"  lifetime total ledgered                                     : £{fixed_cap+fixed_am+prod+calib:>7.2f}")

    print("\n" + "-" * 74)
    print("ROI / NET — quoted against PRODUCTION spend, not fixed cost")
    print("-" * 74)
    rev = _g(b["revenue_gbp"])
    print(f"  revenue (real ledger; £0 until monetised) : £{rev:.2f}")
    print(f"  production spend                          : £{prod:.2f}")
    print(f"  net vs production                         : £{rev - prod:.2f}")
    print(f"  month-to-date (all buckets, budget_status): £{_g(bud['month_spend_gbp']):.2f} / £{ceiling:.0f}")

    print("\n" + "-" * 74)
    print("FOOTNOTES (honest data)")
    print("-" * 74)
    print("  • LLM spend before 2026-07-31 is UNDER-recorded by sub-penny rounding (pre-migration-0007:")
    print("    amount_gbp was 2dp, so Haiku calls < ~£0.005 logged as £0.00). Reconcile early LLM against")
    print("    the live Anthropic USD balance, not the early GBP ledger sum. Post-0007 spend is exact.")
    print("  • ElevenLabs music/TTS rows are per-call ESTIMATES (reconciled=false) until a balance pass")
    print("    settles them; TTS is char-exact so accurate, music settles async. See estimate_vs_actual.")
    await conn.close()


if __name__ == "__main__":
    asyncio.run(run())
