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

        tot = conn.execute(
            "SELECT (SELECT COALESCE(SUM(amount_gbp),0) FROM cost_ledger) c, "
            "(SELECT COALESCE(SUM(amount_gbp),0) FROM revenue_ledger) r, "
            "(SELECT COALESCE(SUM(amount_gbp),0) FROM cost_ledger "
            " WHERE period_month=date_trunc('month',now())::date) m").fetchone()
        print(f"\nnet position: cost £{tot['c']}  revenue £{tot['r']}  net £{tot['r']-tot['c']}")
        print(f"month-to-date spend: £{tot['m']}")

        print("\njobs:")
        for r in conn.execute("SELECT id, type, status FROM jobs ORDER BY id").fetchall():
            print(f"  job #{r['id']} {r['type']} -> {r['status']}")

        print("\nevents (audit timeline):")
        for r in conn.execute(
            "SELECT id, type, job_id, message FROM events ORDER BY id").fetchall():
            print(f"  [{r['id']:>2}] job={r['job_id']}  {r['type']:<20} {r['message'] or ''}")


if __name__ == "__main__":
    main()
