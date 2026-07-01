"""Cost/revenue ledger reads. Slice 1 reads only (seeding is done by seed.py); writes from
running jobs arrive in later slices.
"""
from __future__ import annotations

from decimal import Decimal


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


async def totals_gbp(conn) -> dict:
    """Lifetime totals for an honest net-position summary."""
    cur = await conn.execute("SELECT COALESCE(SUM(amount_gbp), 0) AS c FROM cost_ledger")
    cost = (await cur.fetchone())["c"]
    cur = await conn.execute("SELECT COALESCE(SUM(amount_gbp), 0) AS r FROM revenue_ledger")
    revenue = (await cur.fetchone())["r"]
    return {"cost_gbp": cost, "revenue_gbp": revenue, "net_gbp": revenue - cost}
