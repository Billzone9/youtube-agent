"""Read-only budget view. Slice 1 DISPLAYS month-to-date spend vs the global ceiling in the
approval message (exercising the ledger end to end); it does NOT enforce. Enforcement is a
later slice. The ceiling is read from platform_settings so it is dashboard-controllable.
"""
from __future__ import annotations

from decimal import Decimal

from . import repo


async def budget_status(conn) -> dict:
    cur = await conn.execute(
        "SELECT value FROM platform_settings WHERE key = 'budget'"
    )
    row = await cur.fetchone()
    ceiling = Decimal(str(row["value"].get("ceiling_gbp", 200))) if row else Decimal("200")
    tier = row["value"].get("tier", "m1") if row else "m1"
    spent = await repo.ledger.month_to_date_cost_gbp(conn)
    return {
        "tier": tier,
        "ceiling_gbp": ceiling,
        "month_spend_gbp": spent,
        "remaining_gbp": ceiling - spent,
    }
