"""Mac-side simulated end-to-end test for Slice 1 (Telegram stubbed).

Runs migrations + seed, then drives submit -> approve and submit -> reject through the
orchestrator with a StubNotifier, asserting DB state, idempotency, stale-callback handling,
and audit completeness. No Telegram, no network.

Run (from repo root):
  POSTGRES_HOST=localhost POSTGRES_PORT=5433 \
  ASSETS_DIR=$PWD/assets ./.venv/bin/python -m scripts.simulate_slice1
"""
from __future__ import annotations

import asyncio
import sys

import psycopg
from psycopg.rows import dict_row

from ytagent import orchestrator, repo
from ytagent.artifacts import lion_video_meta
from ytagent.config import load_settings
from ytagent.migrations.runner import run_migrations
from ytagent.notifier import StubNotifier
from ytagent.publish import DryRunPublisher
from ytagent.seed import run_seed

PASS, FAIL = "✅", "❌"
_failures = 0


def check(label: str, ok: bool, detail: str = "") -> None:
    global _failures
    print(f"  {PASS if ok else FAIL} {label}{(' — ' + detail) if detail else ''}")
    if not ok:
        _failures += 1


async def run() -> None:
    settings = load_settings()

    print("[1] migrations")
    applied = run_migrations(settings)
    print("[2] seed")
    run_seed()

    conn = await psycopg.AsyncConnection.connect(
        settings.dsn(), row_factory=dict_row, autocommit=True
    )
    try:
        # baseline state
        ch = await repo.channels.get_by_slug(conn, "wildlife")
        check("wildlife channel seeded", ch is not None)
        cost_n = (await (await conn.execute("SELECT count(*) n FROM cost_ledger")).fetchone())["n"]
        rev_n = (await (await conn.execute("SELECT count(*) n FROM revenue_ledger")).fetchone())["n"]
        check("cost_ledger has baseline rows", cost_n >= 4, f"{cost_n} rows")
        check("revenue_ledger empty", rev_n == 0, f"{rev_n} rows")

        # --- submit -> APPROVE ---
        print("[3] submit -> approve")
        notifier = StubNotifier()
        publisher = DryRunPublisher()
        res = await orchestrator.submit_video_for_approval(
            conn, notifier, channel=ch, video_meta=lion_video_meta(), chat_id=settings.chat_id,
            publish_mode=publisher.mode,
        )
        job_id, video_id, appr_id = res["job"]["id"], res["video"]["id"], res["approval"]["id"]
        check("notifier received 1 approval request", len(notifier.requests) == 1)
        appr = await repo.approvals.get(conn, appr_id)
        job = await repo.jobs.get(conn, job_id)
        check("job awaiting_approval", job["status"] == "awaiting_approval", job["status"])
        check("approval pending", appr["state"] == "pending")
        check("approval message_id stored", appr["telegram_message_id"] is not None)

        dec = await orchestrator.handle_decision(
            conn, notifier, publisher, approval_id=appr_id, decision="approve", decided_by="banks"
        )
        check("decision handled", dec.get("handled") is True)
        job = await repo.jobs.get(conn, job_id)
        vid = await repo.videos.get(conn, video_id)
        check("job published_dryrun", job["status"] == "published_dryrun", job["status"])
        check("video published_dryrun", vid["status"] == "published_dryrun")
        body = dec["result"]["body"]
        check("dry-run privacy private", body["status"]["privacyStatus"] == "private")
        check("dry-run synthetic-media disclosed", body["status"]["containsSyntheticMedia"] is True)
        check("dry-run NOT made-for-kids", body["status"]["selfDeclaredMadeForKids"] is False)
        val = dec["result"]["validation"]
        check("media size matches 368,842,754", val["size_matches"] is True,
              f"actual={val['size_bytes_actual']}")
        check("notifier got 1 resolution", len(notifier.resolutions) == 1)

        # stale callback: approving again is a no-op
        stale = await orchestrator.handle_decision(
            conn, notifier, publisher, approval_id=appr_id, decision="approve", decided_by="banks"
        )
        check("stale callback ignored", stale.get("handled") is False, stale.get("reason", ""))

        # audit completeness for this job
        evs = (await (await conn.execute(
            "SELECT type FROM events WHERE job_id=%s ORDER BY id", [job_id])).fetchall())
        types = [e["type"] for e in evs]
        needed = {"video_submitted", "approval_requested", "approval_approved", "dry_run_published"}
        check("audit reconstructs the story", needed.issubset(set(types)), str(types))

        # --- submit -> REJECT ---
        print("[4] submit -> reject")
        res2 = await orchestrator.submit_video_for_approval(
            conn, notifier, channel=ch, video_meta=lion_video_meta(), chat_id=settings.chat_id,
            publish_mode=publisher.mode,
        )
        dec2 = await orchestrator.handle_decision(
            conn, notifier, publisher, approval_id=res2["approval"]["id"], decision="reject",
            decided_by="banks"
        )
        check("reject handled", dec2.get("handled") is True)
        job2 = await repo.jobs.get(conn, res2["job"]["id"])
        check("rejected job status", job2["status"] == "rejected", job2["status"])
        pub_evs = (await (await conn.execute(
            "SELECT count(*) n FROM events WHERE job_id=%s AND type='dry_run_published'",
            [res2["job"]["id"]])).fetchone())["n"]
        check("no publish on reject", pub_evs == 0)

        # --- idempotency: re-seed must not duplicate baseline ---
        print("[5] idempotency (re-seed)")
        run_seed()
        cost_n2 = (await (await conn.execute("SELECT count(*) n FROM cost_ledger")).fetchone())["n"]
        check("baseline rows not duplicated", cost_n2 == cost_n, f"{cost_n}->{cost_n2}")
    finally:
        await conn.close()

    print(f"\n{'ALL PASSED' if _failures == 0 else str(_failures) + ' CHECK(S) FAILED'}")
    sys.exit(1 if _failures else 0)


if __name__ == "__main__":
    asyncio.run(run())
