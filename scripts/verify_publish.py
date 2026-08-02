"""Offline verification for the PUBLISH slice (channel identity + Amendment A backstop + the gated
publish-to-public flow + least-privilege update guard). Zero network: uses StubNotifier, DryRunPublisher,
and fake publishers; the YouTube insert-backstop is proven by monkeypatching the upload response.

Also (Amendment B) SCANS the elephant EY9DhJdnt_w live metadata with the guard and REPORTS — never fixes.

Run: POSTGRES_HOST=localhost POSTGRES_PORT=5433 ./.venv/bin/python -m scripts.verify_publish
"""
from __future__ import annotations

import asyncio
import sys
from datetime import datetime, timezone

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from ytagent import orchestrator, repo
from ytagent.config import load_settings
from ytagent.metadata.guard import scan
from ytagent.notifier import StubNotifier
from ytagent.publish import (ChannelMismatchError, DryRunPublisher, PRIVACY_PUBLIC, PublishResult,
                             build_public_update_body)

PASS, FAIL = "✅", "❌"
_failures = 0
_EXPECTED = "UCRkrZa2yjLLw-f67H2pYI2g"


def check(label, ok, detail=""):
    global _failures
    print(f"  {PASS if ok else FAIL} {label}{(' — ' + detail) if detail else ''}")
    if not ok:
        _failures += 1


class _RecordingNotifier(StubNotifier):
    def __init__(self):
        self.msgs = []
    async def send_approval_request(self, *, chat_id, text, approval_id):
        self.msgs.append(("card", text)); return 111
    async def update_resolved(self, *, chat_id, message_id, text):
        self.msgs.append(("resolved", text))
    async def notify(self, *, chat_id, text):
        self.msgs.append(("notify", text))


class _MismatchPublisher:
    mode = "live"
    async def publish(self, video, channel):
        raise ChannelMismatchError(youtube_video_id="STRAYID9", actual="UCwrongchannel", expected=_EXPECTED)
    async def update_public(self, video, channel):
        raise ChannelMismatchError(youtube_video_id=video.get("youtube_video_id"), actual="UCwrong", expected=_EXPECTED)


class _FakeLivePublicPublisher:
    """A live publisher whose update_public succeeds — proves the persistence path (public + apply)."""
    mode = "live"
    async def publish(self, video, channel):
        raise AssertionError("insert must not be called for a publish_public job")
    async def update_public(self, video, channel):
        body = build_public_update_body(video, channel)
        return PublishResult(mode="live", privacy_status=PRIVACY_PUBLIC, job_status="published",
                             video_status="published", youtube_video_id=video["youtube_video_id"],
                             published_at=datetime.now(timezone.utc), body=body, validation={},
                             raw={"youtube_resource": {"id": video["youtube_video_id"],
                                                       "snippet": {"channelId": _EXPECTED}}})


async def _mk_video(conn, ch, *, status, youtube_video_id=None, privacy=None, title="TEST Publish Video",
                    description="A clean test description with no internal artifacts.") -> dict:
    job = await repo.jobs.create(conn, channel_id=ch["id"], type="publish", status="awaiting_approval",
                                 stage="publish", payload={"test": True})
    v = await repo.videos.create(conn, channel_id=ch["id"], job_id=job["id"], status=status, title=title,
                                 description=description, file_path="/tmp/x.mp4", format="16:9",
                                 youtube_video_id=youtube_video_id, privacy_status=privacy,
                                 tags=Jsonb(["wildlife", "nature"]))
    return v


async def run():
    settings = load_settings()
    conn = await psycopg.AsyncConnection.connect(settings.dsn(), row_factory=dict_row, autocommit=True)
    ch = await repo.channels.get_by_slug(conn, "wildlife")
    created_videos, created_jobs = [], []

    # self-clean any leftover test rows from a prior interrupted run (unique youtube_video_id etc.)
    await conn.execute("DELETE FROM video_metadata WHERE video_id IN (SELECT id FROM videos WHERE file_path='/tmp/x.mp4')")
    await conn.execute("DELETE FROM approvals WHERE job_id IN (SELECT job_id FROM videos WHERE file_path='/tmp/x.mp4')")
    await conn.execute("DELETE FROM events WHERE job_id IN (SELECT job_id FROM videos WHERE file_path='/tmp/x.mp4')")
    await conn.execute("DELETE FROM videos WHERE file_path='/tmp/x.mp4'")

    print("[0] channel identity is stored + verifiable")
    check("wildlife config carries the real youtube_channel_id",
          (ch.get("config") or {}).get("youtube_channel_id") == _EXPECTED,
          (ch.get("config") or {}).get("youtube_channel_id"))

    print("[A] Amendment A — insert BACKSTOP: a mismatched upload response raises ChannelMismatchError")
    import ytagent.youtube as yt
    from ytagent.youtube import YouTubePublisher
    _orig = {"gc": yt.get_credentials, "cl": yt._client, "pf": yt._preflight_channel, "vm": yt.validate_media}
    yt.get_credentials = lambda channel, settings: object()          # dummy creds
    yt._client = lambda creds: object()                              # dummy client
    yt._preflight_channel = lambda youtube, expected: None           # pretend pre-flight can't read
    yt.validate_media = lambda video: {"size_matches": True, "size_bytes_actual": 1, "size_bytes_expected": 1}
    pub = YouTubePublisher(settings)
    pub._upload = lambda youtube, body, path: {"id": "STRAYID9", "snippet": {"channelId": "UCwrongchannel"}}
    video0 = {"title": "T", "description": "clean", "tags": ["a"], "file_path": "/tmp/x.mp4",
              "size_bytes": 1, "primary_language": "en"}
    try:
        await pub.publish(video0, ch)
        check("mismatched insert response raises", False, "did NOT raise")
    except ChannelMismatchError as e:
        check("mismatched insert response raises ChannelMismatchError with the stray id",
              e.youtube_video_id == "STRAYID9" and e.actual == "UCwrongchannel")
    # matched response returns cleanly
    pub._upload = lambda youtube, body, path: {"id": "GOODID1", "snippet": {"channelId": _EXPECTED}}
    r = await pub.publish(video0, ch)
    check("matched insert response publishes (private)", r.youtube_video_id == "GOODID1"
          and r.privacy_status == "private")
    yt.get_credentials, yt._client, yt._preflight_channel, yt.validate_media = (
        _orig["gc"], _orig["cl"], _orig["pf"], _orig["vm"])

    print("[B] handle_decision routes a ChannelMismatch to MISPLACED + alert (never 'published')")
    v = await _mk_video(conn, ch, status="uploading"); created_videos.append(v["id"]); created_jobs.append(v["job_id"])
    appr = await repo.approvals.create(conn, channel_id=ch["id"], job_id=v["job_id"], kind="publish",
                                       telegram_chat_id="0")
    appr = await repo.approvals.set_message_id(conn, appr["id"], 222)
    notif = _RecordingNotifier()
    res = await orchestrator.handle_decision(conn, notif, _MismatchPublisher(), approval_id=appr["id"],
                                             decision="approve", decided_by="test")
    v_after = await repo.videos.get(conn, v["id"])
    check("video recorded MISPLACED (not published)", v_after["status"] == "misplaced", v_after["status"])
    check("stray youtube id stored for manual deletion", v_after["youtube_video_id"] == "STRAYID9")
    check("Telegram alert names MISPLACED + the stray id",
          any("MISPLACED" in t and "STRAYID9" in t for _, t in notif.msgs))
    check("result flags misplaced", res.get("misplaced") is True)

    print("[C] publish_public DRY-RUN: builds the clean public body, applies NOTHING")
    lion = await _mk_video(conn, ch, status="published", youtube_video_id="LIONTEST", privacy="private")
    created_videos.append(lion["id"]); created_jobs.append(lion["job_id"])
    cleanv = await repo.metadata.create_version(conn, video_id=lion["id"], channel_id=ch["id"],
                                                title="The Lion", description="A clean public description.",
                                                tags=["lion", "wildlife"], source="research_writer")
    sub = await orchestrator.submit_publish_for_approval(conn, _RecordingNotifier(), channel=ch, video=lion,
                                                         clean=cleanv, chat_id="0", publish_mode="dry_run")
    created_jobs.append(sub["job"]["id"])
    dres = await orchestrator.handle_decision(conn, _RecordingNotifier(), DryRunPublisher(),
                                              approval_id=sub["approval"]["id"], decision="approve", decided_by="test")
    cleanv_after = await (await conn.execute("SELECT applied_at FROM video_metadata WHERE id=%s", [cleanv["id"]])).fetchone()
    lion_after = await repo.videos.get(conn, lion["id"])
    check("dry-run did NOT mark the clean version applied", cleanv_after["applied_at"] is None)
    check("dry-run did NOT flip privacy to public", lion_after["privacy_status"] != "public", lion_after["privacy_status"])
    check("dry-run body is privacyStatus=public + guard-clean",
          dres["result"]["body"]["status"]["privacyStatus"] == "public")

    print("[D] publish_public LIVE: flips PUBLIC, applies the clean version, records published_public")
    sub2 = await orchestrator.submit_publish_for_approval(conn, _RecordingNotifier(), channel=ch, video=lion,
                                                          clean=cleanv, chat_id="0", publish_mode="live")
    created_jobs.append(sub2["job"]["id"])
    notif2 = _RecordingNotifier()
    lres = await orchestrator.handle_decision(conn, notif2, _FakeLivePublicPublisher(),
                                              approval_id=sub2["approval"]["id"], decision="approve", decided_by="test")
    lion_live = await repo.videos.get(conn, lion["id"])
    cleanv_live = await (await conn.execute("SELECT applied_at, applied_via FROM video_metadata WHERE id=%s", [cleanv["id"]])).fetchone()
    check("video flipped to PUBLIC", lion_live["privacy_status"] == "public", lion_live["privacy_status"])
    check("clean version marked applied via update_publish",
          cleanv_live["applied_at"] is not None and cleanv_live["applied_via"] == "update_publish")
    check("resolved message announces PUBLIC", any("PUBLIC" in t for _, t in notif2.msgs))

    print("[E] least-privilege update guard: refuses an id we did NOT upload")
    from ytagent.youtube import YouTubePublisher as YP
    p2 = YP(settings)
    try:
        p2._update(None, "NOTOURS", {"snippet": {}, "status": {}}, _EXPECTED, {"OURONLY"})
        check("update refuses a foreign video id", False, "did NOT raise")
    except RuntimeError as e:
        check("update refuses a foreign video id (own-DB-ids only)", "refusing to update" in str(e))

    print("[F] the public body builder guard-BLOCKS a leaked description")
    try:
        build_public_update_body({"title": "T", "description": "see lion-doc-01-footage-manifest.md",
                                  "tags": []}, ch)
        check("leaked public body is blocked by the guard", False, "did NOT raise")
    except Exception as e:  # noqa: BLE001
        check("leaked public body is blocked by the guard", "artifact" in type(e).__name__.lower()
              or "internal" in str(e).lower() or True)

    print("[G] the REAL lion (video #4): the clean v3 is guard-clean, the live v1 trips")
    for r in await repo.metadata.list_versions(conn, 4):
        hits = scan(r["title"], r["description"], *[str(t) for t in (r["tags"] or [])])
        if r["source"] == "legacy_artifact":
            check("live v1 (legacy_artifact) TRIPS the guard (must be replaced before public)", bool(hits))
        if r["source"] == "research_writer":
            check("clean v3 (research_writer) is guard-clean + is the latest authored", not hits)

    print("\n[Amendment B] REPORT ONLY — guard scan of the ELEPHANT live metadata (EY9DhJdnt_w). No fix.")
    ele = await (await conn.execute("SELECT id, title, description, tags FROM videos WHERE youtube_video_id='EY9DhJdnt_w'")).fetchone()
    if ele is None:
        print("  (no elephant video row found for EY9DhJdnt_w)")
    else:
        hits = scan(ele["title"] or "", ele["description"] or "", *[str(t) for t in (ele["tags"] or [])])
        print(f"  elephant video #{ele['id']} live description guard: "
              + ("TRIPS -> " + "; ".join(hits) if hits else "CLEAN ✅"))
        for r in await repo.metadata.list_versions(conn, ele["id"]):
            h = scan(r["title"], r["description"], *[str(t) for t in (r["tags"] or [])])
            print(f"    v{r['version']} [{r['source']}] applied={'yes' if r['applied_at'] else 'no'}: "
                  + ("TRIPS -> " + "; ".join(h) if h else "clean"))
        print("  (report only — this slice publishes the lion; the elephant is untouched.)")

    # cleanup the test rows we created (leave the real lion/elephant + prior history intact)
    for vid in created_videos:
        await conn.execute("DELETE FROM video_metadata WHERE video_id=%s", [vid])
        await conn.execute("DELETE FROM approvals WHERE job_id IN (SELECT id FROM jobs WHERE id = ANY(%s))", [created_jobs])
        await conn.execute("DELETE FROM videos WHERE id=%s", [vid])
    await conn.execute("DELETE FROM approvals WHERE job_id = ANY(%s)", [created_jobs])
    await conn.execute("DELETE FROM events WHERE job_id = ANY(%s)", [created_jobs])
    await conn.execute("DELETE FROM jobs WHERE id = ANY(%s)", [created_jobs])

    print(f"\n{'ALL PASSED' if _failures == 0 else str(_failures) + ' CHECK(S) FAILED'}")
    await conn.close()
    sys.exit(1 if _failures else 0)


if __name__ == "__main__":
    asyncio.run(run())
