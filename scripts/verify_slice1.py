"""Print the Slice 1 DB state: tables, channel, honest cost baseline, net position, audit trail.
Run: POSTGRES_HOST=localhost POSTGRES_PORT=5433 ./.venv/bin/python -m scripts.verify_slice1
"""
from __future__ import annotations

from ytagent.config import load_settings
from ytagent.db import sync_connect


def main() -> None:
    with sync_connect(load_settings()) as conn:
        tables = [r["tablename"] for r in conn.execute(
            "SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY 1").fetchall()]
        print(f"tables ({len(tables)}): {', '.join(tables)}\n")

        print("channels:")
        for r in conn.execute("SELECT id, slug, name, status FROM channels ORDER BY id").fetchall():
            print(f"  #{r['id']} {r['slug']}  {r['name']}  [{r['status']}]")

        print("\ncost_ledger (honest baseline):")
        for r in conn.execute(
            "SELECT category, description, amount_gbp, currency, is_amortised, reconciled, "
            "period_month FROM cost_ledger ORDER BY id").fetchall():
            flag = "reconciled" if r["reconciled"] else "ESTIMATE"
            am = " (amortised)" if r["is_amortised"] else ""
            print(f"  £{r['amount_gbp']:>7} {r['currency']}  {r['category']:<14}{am}  "
                  f"{r['period_month']}  [{flag}]  {r['description']}")

        # accrual view (excludes the capital lump; uses amortised) vs the cash outlay recorded
        lump = "(category='infrastructure' AND is_amortised=false)"
        tot = conn.execute(
            f"SELECT (SELECT COALESCE(SUM(amount_gbp),0) FROM cost_ledger WHERE NOT {lump}) op, "
            f"(SELECT COALESCE(SUM(amount_gbp),0) FROM cost_ledger WHERE {lump}) cap, "
            "(SELECT COALESCE(SUM(amount_gbp),0) FROM revenue_ledger) r, "
            f"(SELECT COALESCE(SUM(amount_gbp),0) FROM cost_ledger "
            f" WHERE period_month=date_trunc('month',now())::date AND NOT {lump}) m").fetchone()
        print(f"\noperating cost to date (accrual, excl. capital): £{tot['op']}")
        print(f"capital outlay recorded (cash, e.g. annual VPS): £{tot['cap']}")
        print(f"revenue: £{tot['r']}   net (revenue - operating): £{tot['r']-tot['op']}")
        print(f"month-to-date operating spend: £{tot['m']}")

        print("\njobs:")
        for r in conn.execute("SELECT id, type, status FROM jobs ORDER BY id").fetchall():
            print(f"  job #{r['id']} {r['type']} -> {r['status']}")

        print("\nevents (audit timeline):")
        for r in conn.execute(
            "SELECT id, type, job_id, message FROM events ORDER BY id").fetchall():
            print(f"  [{r['id']:>2}] job={r['job_id']}  {r['type']:<20} {r['message'] or ''}")


if __name__ == "__main__":
    main()
