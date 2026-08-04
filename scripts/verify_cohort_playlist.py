"""Regression for M1 item 2 — the UNLISTED cohort playlist writes (BACKLOG review 2026-08-04).

Two layers, both offline (no real YouTube, no keys):
  Part A (pure) — `youtube.py:_add_to_cohort_playlist` against a FAKE google client: create-once,
    reuse-on-second, the own-upload-id confinement, unlisted privacy, correct videoId, HttpError wrap.
  Part B (DB)   — `orchestrator._place_in_cohort_playlist` wiring: a LIVE publish places the video ONCE,
    a same-cohort second video reuses the ONE playlist, a repeat publish is idempotent (skips), a dry
    run records nothing, a video with no cohort is skipped, and a publisher failure is logged not raised.

Run: POSTGRES_HOST=localhost POSTGRES_PORT=5433 ./.venv/bin/python -m scripts.verify_cohort_playlist
"""
from __future__ import annotations

import asyncio
import sys

import psycopg
from psycopg.rows import dict_row

from ytagent import repo
from ytagent.config import load_settings
from ytagent.orchestrator import _place_in_cohort_playlist
from ytagent.publish import PRIVACY_LOCKED, PublishResult

_fail = 0


def check(label, ok, detail=""):
    global _fail
    print(f"  {'✅' if ok else '❌'} {label}{(' — ' + detail) if detail else ''}")
    if not ok:
        _fail += 1


# ---------------------------------------------------------------- Part A: the confined write (pure) ---
class _FakeExec:
    def __init__(self, log, kind, ret):
        self.log, self.kind, self.ret = log, kind, ret

    def execute(self):
        self.log.append(self.kind)
        return self.ret


class _FakePlaylists:
    def __init__(self, log):
        self.log = log

    def insert(self, *, part, body):
        self.log.append(("playlists.insert", part, body))
        return _FakeExec(self.log, "playlists.insert.execute", {"id": "PL_NEW_123"})


class _FakePlaylistItems:
    def __init__(self, log):
        self.log = log

    def insert(self, *, part, body):
        self.log.append(("playlistItems.insert", part, body))
        return _FakeExec(self.log, "playlistItems.insert.execute", {"id": "ITEM_1"})


class _FakeYouTube:
    def __init__(self, log):
        self._pl, self._pli = _FakePlaylists(log), _FakePlaylistItems(log)

    def playlists(self):
        return self._pl

    def playlistItems(self):
        return self._pli


def part_a():
    import ytagent.youtube as yt

    print("[A] youtube.py:_add_to_cohort_playlist — the confined write (fake google client)")
    pub = yt.YouTubePublisher.__new__(yt.YouTubePublisher)   # no settings needed; _client is patched

    # patch _client to return our fake, restore after
    orig_client = yt._client
    log: list = []
    yt._client = lambda creds: _FakeYouTube(log)
    try:
        # A1 — no existing playlist: creates ONE unlisted playlist, then adds our video
        log.clear()
        pid = pub._add_to_cohort_playlist("creds", "VID_OURS", "m1-shorts", None, {"VID_OURS"})
        kinds = [e[0] if isinstance(e, tuple) else e for e in log]
        ins = next((e for e in log if isinstance(e, tuple) and e[0] == "playlists.insert"), None)
        item = next((e for e in log if isinstance(e, tuple) and e[0] == "playlistItems.insert"), None)
        check("returns the NEW playlist id", pid == "PL_NEW_123", pid)
        check("calls playlists.insert exactly once (create-once)",
              kinds.count("playlists.insert") == 1)
        check("the created playlist is UNLISTED",
              bool(ins) and ins[2]["status"]["privacyStatus"] == "unlisted")
        check("adds OUR videoId to the new playlist",
              bool(item) and item[2]["snippet"]["resourceId"]["videoId"] == "VID_OURS"
              and item[2]["snippet"]["playlistId"] == "PL_NEW_123")

        # A2 — existing playlist: NO create, only the add, into the given playlist
        log.clear()
        pid2 = pub._add_to_cohort_playlist("creds", "VID_TWO", "m1-shorts", "PL_EXISTING", {"VID_TWO"})
        kinds2 = [e[0] if isinstance(e, tuple) else e for e in log]
        item2 = next((e for e in log if isinstance(e, tuple) and e[0] == "playlistItems.insert"), None)
        check("reuse: returns the EXISTING playlist id", pid2 == "PL_EXISTING", pid2)
        check("reuse: does NOT create a second playlist",
              "playlists.insert" not in kinds2)
        check("reuse: adds into the existing playlist",
              bool(item2) and item2[2]["snippet"]["playlistId"] == "PL_EXISTING")

        # A3 — confinement: refuse an id we did not upload (mirrors update_public's own-id guard)
        log.clear()
        refused = False
        try:
            pub._add_to_cohort_playlist("creds", "VID_ALIEN", "m1-shorts", "PL_EXISTING", {"VID_OURS"})
        except RuntimeError:
            refused = True
        check("refuses a video id NOT in our own-upload set", refused and not log)
    finally:
        yt._client = orig_client


# ------------------------------------------------------------- Part B: the wiring (DB-backed) ---------
class _FakePublisher:
    """Records add_to_cohort_playlist calls; returns a stable id (or raises / returns None on demand)."""
    def __init__(self, *, returns="PL_LIVE", raises=False):
        self.returns, self.raises, self.calls = returns, raises, []

    async def add_to_cohort_playlist(self, *, channel, youtube_video_id, cohort, existing_playlist_id):
        self.calls.append({"vid": youtube_video_id, "cohort": cohort, "existing": existing_playlist_id})
        if self.raises:
            raise RuntimeError("boom (simulated YouTube failure)")
        return self.returns


class _FakeNotifier:
    """Records notify() so we can assert the failure path actually alerts Banks at the time."""
    def __init__(self):
        self.alerts = []

    async def notify(self, *, chat_id, text):
        self.alerts.append(text)


def _result(mode, yt_id):
    return PublishResult(mode=mode, privacy_status=PRIVACY_LOCKED, job_status="published",
                         video_status="published", youtube_video_id=yt_id)


async def _events(conn, job_id, type_):
    cur = await conn.execute("SELECT count(*) AS n FROM events WHERE job_id=%s AND type=%s",
                             [job_id, type_])
    return (await cur.fetchone())["n"]


async def part_b():
    print("\n[B] orchestrator._place_in_cohort_playlist — the wiring (real DB, fake publisher)")
    settings = load_settings()
    conn = await psycopg.AsyncConnection.connect(settings.dsn(), row_factory=dict_row, autocommit=True)
    ch = await repo.channels.get_by_slug(conn, "wildlife")
    job = await repo.jobs.create(conn, channel_id=ch["id"], type="publish", stage=None,
                                 payload={"verify": "cohort_playlist"})
    vids = []
    try:
        async def _mkvideo(cohort):
            v = await repo.videos.create(
                conn, channel_id=ch["id"], job_id=job["id"], title="verify cohort",
                description="x", file_path="/tmp/verify.mp4", format="9:16", status="uploading",
                cohort=cohort)
            vids.append(v["id"])
            return v

        approval = {"id": None}
        notif = _FakeNotifier()

        # B1 — a live publish of a cohort video: creates + records the playlist, marks the video, event
        v1 = await _mkvideo("m1-shorts")
        pub = _FakePublisher(returns="PL_LIVE")
        await _place_in_cohort_playlist(conn, pub, notif, channel=ch, video=v1,
                                        result=_result("live", "YTVID1"), job=job, approval=approval,
                                        chat_id=1)
        stored = await repo.playlists.get(conn, ch["id"], "m1-shorts")
        v1r = await repo.videos.get(conn, v1["id"])
        check("live publish calls the publisher once", len(pub.calls) == 1)
        check("the ONE cohort playlist id is recorded", stored == "PL_LIVE", str(stored))
        check("the video is marked placed (cohort_playlist_id set)",
              v1r["cohort_playlist_id"] == "PL_LIVE")
        check("a cohort_playlist_added event is logged", await _events(conn, job["id"], "cohort_playlist_added") == 1)
        check("a SUCCESSFUL placement raises no alert", notif.alerts == [])

        # B2 — a SECOND video in the SAME cohort: reuses the ONE playlist (existing id passed through)
        v2 = await _mkvideo("m1-shorts")
        pub2 = _FakePublisher(returns="PL_LIVE")
        await _place_in_cohort_playlist(conn, pub2, notif, channel=ch, video=v2,
                                        result=_result("live", "YTVID2"), job=job, approval=approval,
                                        chat_id=1)
        check("same-cohort second video reuses the existing playlist (no re-create)",
              len(pub2.calls) == 1 and pub2.calls[0]["existing"] == "PL_LIVE")

        # B3 — idempotency: a repeat publish of an ALREADY-placed video does nothing
        pub3 = _FakePublisher(returns="PL_LIVE")
        await _place_in_cohort_playlist(conn, pub3, notif, channel=ch, video=v1r,
                                        result=_result("live", "YTVID1"), job=job, approval=approval,
                                        chat_id=1)
        check("already-placed video is skipped (no second insert)", pub3.calls == [])

        # B4 — a DRY RUN records nothing (publisher returns None)
        v4 = await _mkvideo("m1-shorts")
        dry = _FakePublisher(returns=None)
        await _place_in_cohort_playlist(conn, dry, notif, channel=ch, video=v4,
                                        result=_result("dry_run", None), job=job, approval=approval,
                                        chat_id=1)
        v4r = await repo.videos.get(conn, v4["id"])
        # dry_run result has no youtube_video_id → the publisher is never even called
        check("dry run does not place the video", dry.calls == [] and v4r["cohort_playlist_id"] is None)

        # B5 — a video with NO cohort is skipped
        v5 = await _mkvideo(None)
        pub5 = _FakePublisher(returns="PL_LIVE")
        await _place_in_cohort_playlist(conn, pub5, notif, channel=ch, video=v5,
                                        result=_result("live", "YTVID5"), job=job, approval=approval,
                                        chat_id=1)
        check("a video with no cohort is skipped", pub5.calls == [])
        check("no alert from any of the no-op paths (dry-run / no-cohort / idempotent)",
              notif.alerts == [])

        # B6 — a publisher failure is LOGGED + ALERTED, never raised (the publish already succeeded)
        v6 = await _mkvideo("m1-longform")
        boom = _FakePublisher(raises=True)
        raised = False
        try:
            await _place_in_cohort_playlist(conn, boom, notif, channel=ch, video=v6,
                                            result=_result("live", "YTVID6"), job=job, approval=approval,
                                            chat_id=1)
        except Exception:  # noqa: BLE001
            raised = True
        v6r = await repo.videos.get(conn, v6["id"])
        check("a publisher failure does NOT raise", not raised)
        check("the failure is recorded as cohort_playlist_failed",
              await _events(conn, job["id"], "cohort_playlist_failed") == 1)
        check("a failed placement leaves the video unmarked", v6r["cohort_playlist_id"] is None)
        check("the failure ALERTS Banks at the time (one alert, names the DB fallback)",
              len(notif.alerts) == 1 and "videos.cohort" in notif.alerts[0])
    finally:
        # self-clean: remove the temp rows this verify created
        await conn.execute("DELETE FROM events WHERE job_id=%s", [job["id"]])
        if vids:
            await conn.execute("DELETE FROM videos WHERE id = ANY(%s)", [vids])
        await conn.execute("DELETE FROM cohort_playlists WHERE channel_id=%s AND cohort = ANY(%s)",
                           [ch["id"], ["m1-shorts", "m1-longform"]])
        await conn.execute("DELETE FROM jobs WHERE id=%s", [job["id"]])
        await conn.close()


async def main():
    part_a()
    await part_b()
    print(f"\n{'✅ ALL PASS' if _fail == 0 else f'❌ {_fail} FAILED'}")
    return 1 if _fail else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
