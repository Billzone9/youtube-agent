"""Cost/revenue ledger reads. Slice 1 reads only (seeding is done by seed.py); writes from
running jobs arrive in later slices.
"""
from __future__ import annotations

from decimal import Decimal


async def month_to_date_cost_gbp(conn) -> Decimal:
    """Total cost (all channels) recorded in the current calendar month."""
    cur = await conn.execute(
        "SELECT COALESCE(SUM(amount_gbp), 0) AS total FROM cost_ledger "
        "WHERE period_month = date_trunc('month', now())::date"
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
