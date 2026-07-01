"""Idempotent seed: one channel, the global budget setting, and an HONEST cost baseline.

Re-running is safe (channel ON CONFLICT DO NOTHING; ledger rows keyed by idempotency_key with
ON CONFLICT DO UPDATE so Banks's exact figures reconcile a prior estimate without duplicating).

Baseline figures come from env so we never bake guessed money into code:
  BASELINE_VPS_ANNUAL_GBP, BASELINE_VPS_TERM_START (YYYY-MM-DD), BASELINE_ELEVENLABS_MONTHLY_GBP
When a figure is absent we seed a clearly-FLAGGED estimate (reconciled=false, metadata.estimate=true)
so the build runs; supplying the env value and re-seeding reconciles it.  CLI: python -m ytagent.seed
"""
from __future__ import annotations

import os
from datetime import date
from decimal import Decimal

from psycopg.types.json import Jsonb

from .config import load_settings
from .db import sync_connect

WILDLIFE_CONFIG = {
    "niche": "wildlife & nature documentaries",
    "purpose": "lush, accurate long-form wildlife films that grow watch-hours toward monetisation",
    "tone": "poetic narration on the surface, accurate fact underneath",
    "cadence": {"per_week": 1},
    "languages": ["en"],
    "primary_language": "en",
    "voice_profile": {"provider": "elevenlabs", "name": "David", "style": "deep poetic British male"},
    "monetisation": {"streams": ["adsense", "affiliate", "sponsorship", "product"]},
    "approval_policy": {"publish": "manual", "default_privacy": "private"},
    "enabled_social": [],            # YouTube-only until Banks enables platforms
    "format_mix": {"long_form": True, "shorts": False},
    "youtube_category_id": "15",     # Pets & Animals
    "default_tags": ["wildlife", "nature documentary", "lion", "africa", "savanna"],
}


def _period_month(d: date) -> date:
    return date(d.year, d.month, 1)


def _money_env(name: str) -> Decimal | None:
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return None
    return Decimal(raw)


def _upsert_cost(conn, *, key, channel_id, job_id, category, is_amortised, provider, description,
                 amount_gbp, currency, amount_original, fx_rate, credits, period_month, reconciled, metadata):
    conn.execute(
        "INSERT INTO cost_ledger (idempotency_key, channel_id, job_id, category, is_amortised, "
        " provider, description, amount_gbp, currency, amount_original, fx_rate, credits, "
        " period_month, reconciled, metadata) "
        "VALUES (%(key)s,%(channel_id)s,%(job_id)s,%(category)s,%(is_amortised)s,%(provider)s,"
        " %(description)s,%(amount_gbp)s,%(currency)s,%(amount_original)s,%(fx_rate)s,%(credits)s,"
        " %(period_month)s,%(reconciled)s,%(metadata)s) "
        "ON CONFLICT (idempotency_key) DO UPDATE SET "
        " amount_gbp=EXCLUDED.amount_gbp, amount_original=EXCLUDED.amount_original, "
        " fx_rate=EXCLUDED.fx_rate, reconciled=EXCLUDED.reconciled, metadata=EXCLUDED.metadata",
        {
            "key": key, "channel_id": channel_id, "job_id": job_id, "category": category,
            "is_amortised": is_amortised, "provider": provider, "description": description,
            "amount_gbp": amount_gbp, "currency": currency, "amount_original": amount_original,
            "fx_rate": fx_rate, "credits": credits, "period_month": period_month,
            "reconciled": reconciled, "metadata": Jsonb(metadata),
        },
    )


def run_seed() -> None:
    settings = load_settings()
    today = date.today()
    cur_period = _period_month(today)

    with sync_connect(settings, autocommit=False) as conn:
        with conn.transaction():
            # channel
            conn.execute(
                "INSERT INTO channels (slug, name, config) VALUES (%s, %s, %s) "
                "ON CONFLICT (slug) DO NOTHING",
                ["wildlife", "Wildlife & Nature", Jsonb(WILDLIFE_CONFIG)],
            )
            ch = conn.execute("SELECT id FROM channels WHERE slug='wildlife'").fetchone()
            channel_id = ch["id"]

            # global budget (dashboard-controllable)
            conn.execute(
                "INSERT INTO platform_settings (key, value) VALUES ('budget', %s) "
                "ON CONFLICT (key) DO UPDATE SET value=EXCLUDED.value, updated_at=now()",
                [Jsonb({"tier": settings.budget_tier, "ceiling_gbp": settings.budget_ceiling_gbp,
                        "scope": "global"})],
            )

            # --- honest cost baseline ---
            # VPS: cash outlay (full term) + amortised current month
            vps_annual = _money_env("BASELINE_VPS_ANNUAL_GBP")
            term_start_raw = os.environ.get("BASELINE_VPS_TERM_START")
            term_start = date.fromisoformat(term_start_raw) if term_start_raw else cur_period
            vps_reconciled = vps_annual is not None
            vps_annual = vps_annual if vps_annual is not None else Decimal("120.00")  # FLAGGED estimate
            _upsert_cost(
                conn, key=f"vps-outlay:{term_start.isoformat()}", channel_id=None, job_id=None,
                category="infrastructure", is_amortised=False, provider="Hostinger",
                description="VPS annual outlay (KVM 2)", amount_gbp=vps_annual, currency="GBP",
                amount_original=vps_annual, fx_rate=None, credits=None,
                period_month=_period_month(term_start), reconciled=vps_reconciled,
                metadata={"estimate": not vps_reconciled, "term": "annual"},
            )
            _upsert_cost(
                conn, key=f"vps-amortised:{cur_period.isoformat()}", channel_id=None, job_id=None,
                category="infrastructure", is_amortised=True, provider="Hostinger",
                description="VPS amortised (1/12 of annual)",
                amount_gbp=(vps_annual / 12).quantize(Decimal("0.01")), currency="GBP",
                amount_original=None, fx_rate=None, credits=None, period_month=cur_period,
                reconciled=vps_reconciled, metadata={"estimate": not vps_reconciled},
            )

            # ElevenLabs monthly subscription (current month)
            el_monthly = _money_env("BASELINE_ELEVENLABS_MONTHLY_GBP")
            el_reconciled = el_monthly is not None
            el_monthly = el_monthly if el_monthly is not None else Decimal("18.00")  # FLAGGED estimate
            _upsert_cost(
                conn, key=f"elevenlabs-sub:{cur_period.isoformat()}", channel_id=None, job_id=None,
                category="subscription", is_amortised=False, provider="ElevenLabs",
                description="ElevenLabs subscription (monthly)", amount_gbp=el_monthly, currency="GBP",
                amount_original=el_monthly, fx_rate=None, credits=None, period_month=cur_period,
                reconciled=el_reconciled, metadata={"estimate": not el_reconciled},
            )

            # Lion film score — ~1,500 ElevenLabs music credits, marginal ~£2 (known/reconciled)
            _upsert_cost(
                conn, key="lion-music:slice1", channel_id=channel_id, job_id=None,
                category="ai_generation", is_amortised=False, provider="ElevenLabs Music",
                description="Lion film score (3 cues, ~1,500 credits)", amount_gbp=Decimal("2.00"),
                currency="GBP", amount_original=Decimal("2.00"), fx_rate=None,
                credits=Decimal("1500"), period_month=date(2026, 6, 1), reconciled=True,
                metadata={"note": "marginal credit cost; covered by subscription", "credits": 1500},
            )

    print("[seed] done (idempotent). channel 'wildlife' + global budget + baseline cost rows.")


if __name__ == "__main__":
    run_seed()
