"""Regression for D2 — job-lifecycle terminal status + the two implicit-state decisions:
  [1] Explicit live-publish (pure): `_build_publisher` returns DRY-RUN unless YTAGENT_LIVE_PUBLISH is
      set AND a token exists — a credential's presence is NOT consent to publish.
  [2] Produce-job terminal status (DB): `_checkpoint(...,'submitted')` -> terminal 'produced'; every
      pre-submit stage -> 'assembling' (resumable). No more jobs stranded at a non-terminal status.
  [3] Publish-approval staleness (DB): a card tapped after the 7-day TTL is REFUSED (state 'expired',
      NO upload), not published against a stale review.

Run: POSTGRES_HOST=localhost POSTGRES_PORT=5433 ./.venv/bin/python -m scripts.verify_d2
"""
from __future__ import annotations

import asyncio
import sys
from dataclasses import replace

import psycopg
from psycopg.rows import dict_row

from ytagent import produce, repo
from ytagent.config import load_settings
from ytagent.notifier import StubNotifier
from ytagent.orchestrator import _PUBLISH_APPROVAL_TTL, handle_decision

from scripts._hermetic import high_water, sweep

_fail = 0


def check(label, ok, detail=""):
    global _fail
    print(f"  {'✅' if ok else '❌'} {label}{(' — ' + detail) if detail else ''}")
    if not ok:
        _fail += 1


class _RecordingPublisher:
    """mode='live' so it WOULD upload if reached; records whether it actually was."""
    mode = "live"

    def __init__(self):
        self.published = False

    async def publish(self, video, channel):
        self.published = True
        raise AssertionError("publisher.publish MUST NOT be called on an expired approval")

    async def update_public(self, video, channel):
        self.published = True
        raise AssertionError("publisher.update_public MUST NOT be called on an expired approval")


def part1_publisher_config():
    from ytagent.bot import _build_publisher
    from ytagent.publish import DryRunPublisher

    print("[1] explicit live-publish — a token alone does not go live")
    base = load_settings()

    def pub(*, token, live):
        s = replace(base, youtube_refresh_token=("tok" if token else None), live_publish=live,
                    youtube_client_id="cid", youtube_client_secret="sec")
        return _build_publisher(s)

    check("no token, flag off → dry-run", isinstance(pub(token=False, live=False), DryRunPublisher))
    check("TOKEN present, flag OFF → still DRY-RUN (the key fix)",
          isinstance(pub(token=True, live=False), DryRunPublisher))
    check("no token, flag on → dry-run (can't publish without creds)",
          isinstance(pub(token=False, live=True), DryRunPublisher))
    # token + flag → live; construct lazily (needs google libs) — assert it's NOT the dry-run one
    live = pub(token=True, live=True)
    check("TOKEN present AND flag ON → live publisher", not isinstance(live, DryRunPublisher),
          type(live).__name__)


async def part2_terminal_status(conn, ch):
    print("[2] produce-job terminal status — 'produced' at submit, 'assembling' before")
    job = await repo.jobs.create(conn, channel_id=ch["id"], type="produce", status="assembling",
                                 stage="scripted", payload={"topic": "d2-test"})
    state = {"job_id": job["id"], "channel_id": ch["id"], "stage": "scripted"}
    await produce._checkpoint(conn, state, "assembled")
    row = await repo.jobs.get(conn, job["id"])
    check("a pre-submit stage ('assembled') keeps status 'assembling' (resumable)",
          row["status"] == "assembling", row["status"])
    await produce._checkpoint(conn, state, "submitted")
    row = await repo.jobs.get(conn, job["id"])
    check("stage 'submitted' → TERMINAL status 'produced'", row["status"] == "produced", row["status"])


async def part3_staleness(conn, ch):
    print(f"[3] publish-approval staleness — refuse a tap after the {_PUBLISH_APPROVAL_TTL.days}-day TTL")
    job = await repo.jobs.create(conn, channel_id=ch["id"], type="publish", status="awaiting_approval",
                                 stage="publish", payload={})
    v = await repo.videos.create(conn, channel_id=ch["id"], job_id=job["id"], title="Stale Test",
                                 description="x", file_path="/tmp/stale.mp4", format="16:9",
                                 status="awaiting_approval")
    appr = await repo.approvals.create(conn, channel_id=ch["id"], job_id=job["id"], kind="publish")
    # backdate the approval to just past the TTL
    await conn.execute("UPDATE approvals SET created_at = now() - (%s || ' days')::interval WHERE id=%s",
                       [_PUBLISH_APPROVAL_TTL.days + 1, appr["id"]])
    pub = _RecordingPublisher()
    res = await handle_decision(conn, StubNotifier(), pub, approval_id=appr["id"],
                                decision="approve", decided_by="banks")
    check("a stale approve returns decision 'expired'", res.get("decision") == "expired", str(res))
    check("the publisher was NOT called (no upload)", pub.published is False)
    appr2 = await repo.approvals.get(conn, appr["id"])
    jrow = await repo.jobs.get(conn, job["id"])
    check("approval state set to 'expired'", appr2["state"] == "expired", appr2["state"])
    check("job set to 'rejected' (not published)", jrow["status"] == "rejected", jrow["status"])

    # control: a FRESH approval of the same shape is NOT expired (proves the gate is time-bound, not a
    # blanket refusal). Use a DRY-RUN publisher so it proceeds cleanly past the staleness gate.
    from ytagent.publish import DryRunPublisher
    job2 = await repo.jobs.create(conn, channel_id=ch["id"], type="publish", status="awaiting_approval",
                                  stage="publish", payload={})
    await repo.videos.create(conn, channel_id=ch["id"], job_id=job2["id"], title="Fresh Test",
                             description="x", file_path="/tmp/fresh.mp4", format="16:9",
                             status="awaiting_approval")
    appr_f = await repo.approvals.create(conn, channel_id=ch["id"], job_id=job2["id"], kind="publish")
    res_f = await handle_decision(conn, StubNotifier(), DryRunPublisher(), approval_id=appr_f["id"],
                                  decision="approve", decided_by="banks")
    check("a FRESH approval is NOT expired (proceeds past the gate)",
          res_f.get("decision") != "expired", str(res_f))


async def main():
    part1_publisher_config()
    settings = load_settings()
    conn = await psycopg.AsyncConnection.connect(settings.dsn(), row_factory=dict_row, autocommit=True)
    hw = await high_water(conn)
    try:
        ch = await repo.channels.get_by_slug(conn, "wildlife")
        await part2_terminal_status(conn, ch)
        await part3_staleness(conn, ch)
    finally:
        await sweep(conn, hw)
        await conn.close()
    print(f"\n{'✅ ALL PASS' if _fail == 0 else f'❌ {_fail} FAILED'}")
    return 1 if _fail else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
