"""Cost/revenue ledger reads + LLM-spend writes.

Slice 1 read-only; Slice 5 adds `write_llm_cost` — the first per-job cost WRITE (real Anthropic token
spend, idempotent by vendor request id). The governor stays display-only (§4.10 owns enforcement).
"""
from __future__ import annotations

from decimal import Decimal

from psycopg.types.json import Jsonb


async def month_to_date_cost_gbp(conn) -> Decimal:
    """Honest monthly cost (all channels) for the current calendar month.

    Excludes the capital lump (a non-amortised infrastructure outlay like the annual VPS): that
    cost is represented month-by-month by its amortised rows, so counting the lump too would
    double-count and make the term-start month look falsely expensive.
    """
    cur = await conn.execute(
        "SELECT COALESCE(SUM(amount_gbp), 0) AS total FROM cost_ledger "
        "WHERE period_month = date_trunc('month', now())::date "
        "AND NOT (category = 'infrastructure' AND is_amortised = false)"
    )
    row = await cur.fetchone()
    return row["total"]


async def get_llm_pricing(conn) -> dict:
    """The dashboard-controllable LLM price/FX table from platform_settings."""
    cur = await conn.execute("SELECT value FROM platform_settings WHERE key = 'llm_pricing'")
    row = await cur.fetchone()
    return row["value"] if row else {}


async def write_llm_cost(conn, rec, pricing: dict, *, reconciled: bool = True) -> dict:
    """Write one Anthropic call's real token spend to cost_ledger (category 'ai_generation').

    Idempotent on `llm:{request_id}` (plain-unique index; a replay upserts, never duplicates). USD is
    stored in amount_original/currency; amount_gbp is the FX-converted figure the budget view sums.
    `rec` is a providers.base.UsageRecord; `pricing` is the platform_settings llm_pricing dict.
    """
    from ..providers.pricing import usage_to_gbp

    calc = usage_to_gbp(rec.usage, rec.model, pricing)
    fx_date = ((pricing.get("fx") or {}).get("as_of"))
    tier = rec.tier.value if hasattr(rec.tier, "value") else str(rec.tier)
    meta = {
        "model": rec.model, "tier": tier, "purpose": rec.purpose,
        "input_tokens": rec.usage.input_tokens, "output_tokens": rec.usage.output_tokens,
        "cache_read_input_tokens": rec.usage.cache_read_input_tokens,
        "cache_creation_input_tokens": rec.usage.cache_creation_input_tokens,
        "batch_id": rec.batch_id,
    }
    cur = await conn.execute(
        "INSERT INTO cost_ledger (idempotency_key, channel_id, job_id, category, is_amortised, "
        " provider, description, amount_original, currency, amount_gbp, fx_rate, fx_rate_date, "
        " period_month, reconciled, metadata) "
        "VALUES (%(key)s,%(channel_id)s,%(job_id)s,'ai_generation',false,'Anthropic',%(desc)s,"
        " %(usd)s,'USD',%(gbp)s,%(fx)s,%(fxdate)s,date_trunc('month',now())::date,%(recon)s,%(meta)s) "
        "ON CONFLICT (idempotency_key) DO UPDATE SET amount_original=EXCLUDED.amount_original, "
        " amount_gbp=EXCLUDED.amount_gbp, fx_rate=EXCLUDED.fx_rate, fx_rate_date=EXCLUDED.fx_rate_date, "
        " reconciled=EXCLUDED.reconciled, metadata=EXCLUDED.metadata RETURNING *",
        {
            "key": f"llm:{rec.request_id}", "channel_id": rec.channel_id, "job_id": rec.job_id,
            "desc": f"LLM {rec.purpose} ({rec.model})", "usd": calc["amount_usd"],
            "gbp": calc["amount_gbp"], "fx": calc["fx_rate"], "fxdate": fx_date,
            "recon": reconciled, "meta": Jsonb(meta),
        },
    )
    row = await cur.fetchone()
    return {"row": row, "amount_gbp": calc["amount_gbp"], "amount_usd": calc["amount_usd"]}


async def totals_gbp(conn) -> dict:
    """Lifetime totals for an honest net-position summary."""
    cur = await conn.execute("SELECT COALESCE(SUM(amount_gbp), 0) AS c FROM cost_ledger")
    cost = (await cur.fetchone())["c"]
    cur = await conn.execute("SELECT COALESCE(SUM(amount_gbp), 0) AS r FROM revenue_ledger")
    revenue = (await cur.fetchone())["r"]
    return {"cost_gbp": cost, "revenue_gbp": revenue, "net_gbp": revenue - cost}
