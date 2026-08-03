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
from ytagent.tts import get_tts_provider

_FILMS_PER_MONTH = 8.67          # 2/week × 52/12 — the TARGET cadence (not necessarily sustainable)
# Music rate: the GATE uses 15.0 cr/s (erring high is correct for a gate). The ONLY reference for actual
# cost is the lion — but that 1,500-credit figure is a HAND-SEEDED estimate (seed.py: "~1,500 credits"),
# NOT a precise per-call settlement, so 1,500/120.06s ≈ 12.5 carries more precision than it earned. Treat
# it as ~12–13 cr/s from a SINGLE hand-seeded film: the direction is sound (15 over-estimates real cost)
# but the exact figure is provisional until a real settlement replaces it. We use 12.5 as the point
# estimate and label it approximate everywhere.
_GATE_MUSIC_CR_PER_S = 15.0
_REF_MUSIC_CR_PER_S = 12.5       # ≈, from one hand-seeded reference (the lion) — NOT a settled measurement
_SETTLE = _REF_MUSIC_CR_PER_S / _GATE_MUSIC_CR_PER_S         # scale ledgered (15/s) music to the reference
# ElevenLabs plan. tier + overage read from the API; RECURRING allowance is an inference (config); the
# AVAILABLE-now credit_limit (base + rollover) is read LIVE — the two are kept strictly distinct.
_EL_TIER = "starter"
_EL_FIXED_GBP_MO = 5.0           # the monthly subscription (already ledgered as a fixed cost)
_EL_OVERAGE = False              # starter can_extend=False → going over BLOCKS, it does NOT bill extra
_NOTIONAL_GBP_PER_CR = 0.00133   # the codebase's PAYG credit valuation — NOT the starter effective rate


def _g(x):
    return float(x or 0)


def affordability(recurring_cr: int, available_now_cr, credits_per_film: float) -> dict:
    """Cadence is computed off RECURRING (the sustainable number), never off available_now (which
    includes one-off rollover). Kept a pure function so it is testable without a live API call."""
    cpf = credits_per_film or 1.0
    avail = available_now_cr if available_now_cr is not None else None
    return {
        "recurring_cr": recurring_cr,
        "available_now_cr": avail,
        "rollover_cr": max(0, (avail - recurring_cr)) if avail is not None else None,
        "sustainable_films_pm": recurring_cr / cpf,               # ← RECURRING, the honest cadence
        "available_films_this_month": (avail / cpf) if avail is not None else None,
    }


async def run():
    settings = load_settings()
    conn = await psycopg.AsyncConnection.connect(settings.dsn(), row_factory=dict_row, autocommit=True)
    b = await repo.ledger.roi_breakdown(conn)
    bud = await budget_status(conn)

    print("=" * 74)
    print("PER-FILM PRODUCTION COST — by provider, music at ~12-13 cr/s (1 hand-seeded reference)")
    print("=" * 74)
    print(f"  {'job':>4} {'film':<24} {'status':<10} {'TTS':>7} {'Music':>7} {'LLM':>7} {'TOTAL':>8}")
    complete = []
    for r in b["per_film"]:
        film = (r["film"] or "?")[:24]
        music_settled = _g(r["music"]) * _SETTLE          # ledger is 15/s; report at settled 12.49/s
        tot = _g(r["tts"]) + music_settled + _g(r["llm"])
        gate_tot = _g(r["tts"]) + _g(r["music"]) + _g(r["llm"])    # music at the 15/s gate rate
        if r["status"] == "assembled" and _g(r["music"]) > 0:      # a full production (audio designed)
            complete.append((tot, gate_tot))
        print(f"  {r['id']:>4} {film:<24} {r['status']:<10} £{_g(r['tts']):>5.2f} "
              f"£{music_settled:>5.2f} £{_g(r['llm']):>5.3f} £{tot:>6.2f}")

    ref, ref_gate = max(complete) if complete else (0.0, 0.0)      # notional per-film (settled + gate music)
    # credits/film from the reference film's ledgered £ (at the codebase PAYG rate) — the allowance currency
    ref_credits = (ref_gate / _NOTIONAL_GBP_PER_CR) if ref_gate else 0.0

    # AVAILABLE-now (base + rollover) read LIVE; RECURRING allowance is the config inference. Kept distinct.
    recurring = settings.elevenlabs_recurring_allowance_cr
    tts = get_tts_provider(settings)
    cs = await asyncio.to_thread(tts.credit_status, key_cap=settings.elevenlabs_key_credit_cap) if tts else None
    available_now = cs.get("account_limit") if cs else None
    aff = affordability(recurring, available_now, ref_credits)

    print("\n" + "=" * 74)
    print("CADENCE AFFORDABILITY — INCREMENTAL CASH (what you actually pay)")
    print("=" * 74)
    print(f"  ElevenLabs plan: {_EL_TIER} — RECURRING allowance {recurring:,} credits/mo for "
          f"£{_EL_FIXED_GBP_MO:.0f}/mo fixed (already ledgered).")
    print(f"    (recurring is an INFERENCE from published Starter pricing — unverified until the 27 Aug reset.)")
    print(f"  Overage: {'billed per credit' if _EL_OVERAGE else 'NONE — going over BLOCKS, it does not bill extra'}.")
    print(f"  A film ≈ {ref_credits:,.0f} credits.")
    print(f"  ► SUSTAINABLE cadence (off RECURRING): ~{aff['sustainable_films_pm']:.1f} films/mo "
          f"(~{aff['sustainable_films_pm'] / 4.33:.1f}/wk).")
    if available_now is not None:
        print(f"  ► AVAILABLE THIS MONTH (live character_limit): {available_now:,} cr "
              f"→ ~{aff['available_films_this_month']:.1f} films this month.")
        if aff["rollover_cr"] and aff["rollover_cr"] > 0:
            print(f"    ⚠ {aff['rollover_cr']:,} of that is NON-RECURRING ROLLOVER (one-off surplus, not "
                  f"next month's budget). Plan cadence on RECURRING, not this.")
    else:
        print(f"  ► AVAILABLE THIS MONTH: live read unavailable — reporting recurring only.")
    print(f"  ► INCREMENTAL CASH PER FILM (inside allowance): £0.00  — the £{_EL_FIXED_GBP_MO:.0f}/mo is "
          f"already spent; effective amortised if fully used: "
          f"~£{_EL_FIXED_GBP_MO / (aff['sustainable_films_pm'] or 1):.2f}/film.")
    if _FILMS_PER_MONTH > aff["sustainable_films_pm"]:
        print(f"  ► The 2-films/wk TARGET ({_FILMS_PER_MONTH:.1f}/mo) EXCEEDS the sustainable "
              f"~{aff['sustainable_films_pm']:.1f}/mo. Starter can't overage → sustained 2/wk needs a PLAN "
              f"CHANGE (fixed step), not per-film spend. Rollover can carry a short burst, not the cadence.")

    print("\n" + "-" * 74)
    print("NOTIONAL CREDIT VALUATION — for scaling BEYOND the plan, NOT current cash")
    print("-" * 74)
    eff = _EL_FIXED_GBP_MO / recurring
    print(f"  per film at the codebase PAYG rate (£{_NOTIONAL_GBP_PER_CR}/cr): ~£{ref:.2f} "
          f"(gate rate £{ref_gate:.2f}); TTS settled, music provisional.")
    print(f"  NB the starter EFFECTIVE rate (on RECURRING) is £{_EL_FIXED_GBP_MO:.0f}/{recurring:,} = "
          f"£{eff:.6f}/cr — ~{_NOTIONAL_GBP_PER_CR / eff:.0f}× below the notional. "
          f"The £{ref:.2f} is what credits WOULD cost at PAYG, not what you pay now.")

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
    print("  • TTS is SETTLED and validated (job 155: 4,379 est vs 4,378 settled, 1.00x; all 18 rows")
    print("    settled by request_id). TTS is the largest per-film component, so per-film cost is now")
    print("    PROVISIONAL ONLY ON MUSIC. See estimate_vs_actual.")
    print("  • MUSIC RATE is PROVISIONAL: the gate uses 15.0 cr/s (err-high, correct for a gate). The only")
    print("    reference for real cost is the lion — but its 1,500 credits is a HAND-SEEDED estimate")
    print("    (seed.py: '~1,500 credits'), not a per-call settlement, so ~12-13 cr/s is a direction, not")
    print("    a measured figure. Per-film cost above uses ~12.5; a real music settlement (balance-delta,")
    print("    once the cap allows a clean run) will replace it. Ledgered buckets are at 15/s.")
    await conn.close()


if __name__ == "__main__":
    asyncio.run(run())
