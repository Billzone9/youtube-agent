"""Real YouTube client. YouTubePublisher implements the Publisher protocol; the orchestrator never
imports googleapiclient. Credentials are built from a stored refresh token (one-time consent via
ytagent/youtube_auth.py).

Two write capabilities, both CHANNEL-VERIFIED and guard-scanned:
  * publish(video, channel)        — videos.INSERT, LOCKED to private (a new upload).
  * update_public(video, channel)  — videos.UPDATE to PUBLIC with a clean snippet (the gated publish
                                     of a video WE already uploaded). This is the ONLY path that may
                                     set a non-private privacyStatus.

Channel safety (item 1 + Amendment A): videos.insert has no channelId parameter — an upload lands on
whatever channel the token is bound to. So `_expected_channel_id(channel)` (the stored
youtube_channel_id) is asserted two ways: a best-effort PRE-FLIGHT (channels.list mine=true, readable
only under force-ssl) and — the backstop that matters most because insert is IRREVERSIBLE — a
POST-assert that the response's snippet.channelId equals the expected id. A mismatch raises
ChannelMismatchError carrying the stray video id so the caller records it MISPLACED and alerts.

Scope note: videos.update needs youtube.force-ssl (there is NO 'own-uploads-only' scope — see BACKLOG).
The restriction to "set metadata + publish only videos we uploaded" is enforced HERE (own-DB-ids only,
channel assertion, no delete/list/playlist/comment/branding code) + the Telegram gate, NOT by the scope.
"""
from __future__ import annotations

import asyncio
import os
import socket
from datetime import datetime, timezone

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload

from .config import Settings
from .metadata.guard import assert_no_internal_artifacts
from .publish import (PRIVACY_LOCKED, PRIVACY_PUBLIC, ChannelMismatchError, PublishResult,
                      build_public_update_body, build_youtube_body, validate_media)

SCOPES = ["https://www.googleapis.com/auth/youtube.force-ssl"]
_TOKEN_URI = "https://oauth2.googleapis.com/token"
_CHUNK = 8 * 1024 * 1024   # 8 MiB (multiple of 256 KiB) — resumable resilience + progress
_SOCKET_TIMEOUT = 120      # seconds; bounds a stalled connection in the worker thread


def _refresh_token_for(channel: dict, settings: Settings) -> str | None:
    """Per-channel token first (env var by slug), else the global one — secrets stay in .env."""
    slug = (channel.get("slug") or "").upper()
    if slug:
        per = os.environ.get(f"YOUTUBE_REFRESH_TOKEN_{slug}")
        if per:
            return per
    return settings.youtube_refresh_token


def get_credentials(channel: dict, settings: Settings) -> Credentials | None:
    token = _refresh_token_for(channel, settings)
    if not (token and settings.youtube_client_id and settings.youtube_client_secret):
        return None
    return Credentials(
        token=None,                       # access token minted from the refresh token on first use
        refresh_token=token,
        token_uri=_TOKEN_URI,
        client_id=settings.youtube_client_id,
        client_secret=settings.youtube_client_secret,
        scopes=SCOPES,
    )


def _expected_channel_id(channel: dict) -> str | None:
    return ((channel.get("config") or {}).get("youtube_channel_id")) or None


_SHORT_MAX_S = 60.0


class ShortConditionError(RuntimeError):
    """A 9:16 upload fails the conditions YouTube CLASSIFIES a Short by (vertical aspect + ≤60s + a
    #Shorts tag in the public text). Publishing it anyway files it as an ordinary vertical video, which
    silently invalidates the Shorts-cohort experiment. Asserted the way channel_id is — not assumed."""


def assert_short_conditions(video: dict, title: str, description: str) -> None:
    """For a Short-shaped (9:16) upload, REFUSE unless it will actually classify as a Short. No-op for
    16:9 long-form. The upload does not infer Short-ness for us — aspect + duration + #Shorts are the
    signals, and only aspect is inherent to the file, so we assert all three at the publish boundary."""
    if video.get("format") != "9:16":
        return
    w, h = int(video.get("width") or 0), int(video.get("height") or 0)
    dur = float(video.get("duration_s") or 0.0)
    text = f"{title or ''}\n{description or ''}".lower()
    problems = []
    if not (h > w):
        problems.append(f"not vertical ({w}x{h})")
    if not (0 < dur <= _SHORT_MAX_S):
        problems.append(f"duration {dur:.1f}s outside (0, {_SHORT_MAX_S:.0f}]s")
    if "#shorts" not in text:
        problems.append("no #Shorts in title/description")
    if problems:
        raise ShortConditionError(
            "9:16 upload fails Short classification (" + "; ".join(problems) + ") — YouTube would file "
            "it as an ordinary vertical video, not a Short. Refusing (the cohort experiment needs Shorts).")


def _client(creds: Credentials):
    socket.setdefaulttimeout(_SOCKET_TIMEOUT)
    return build("youtube", "v3", credentials=creds, cache_discovery=False)


def _actual_channel_id(youtube) -> str | None:
    """The channel the token is bound to (channels.list mine=true). Returns None if the scope can't read
    it (e.g. the legacy upload-only token 403s) — then only the POST-assert can verify."""
    try:
        resp = youtube.channels().list(part="id", mine=True).execute()
        items = resp.get("items", [])
        return items[0]["id"] if items else None
    except HttpError:
        return None


def _preflight_channel(youtube, expected: str) -> None:
    """Best-effort PRE-flight: if the channel is readable and DEFINITELY wrong, refuse before any write.
    Unreadable (upload-only scope) → no-op; the post-assert is the real guard."""
    actual = _actual_channel_id(youtube)
    if actual is not None and actual != expected:
        raise ChannelMismatchError(youtube_video_id=None, actual=actual, expected=expected)


def _resource_channel_id(resource: dict) -> str | None:
    return ((resource.get("snippet") or {}).get("channelId")) or None


class YouTubePublisher:
    mode = "live"

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    # --- INSERT (new upload, LOCKED private) -------------------------------------------------------
    async def publish(self, video: dict, channel: dict) -> PublishResult:
        validation = validate_media(video)
        if not validation["size_matches"]:
            raise RuntimeError(
                f"media validation failed (size {validation['size_bytes_actual']} != "
                f"{validation['size_bytes_expected']}) — refusing to upload")
        expected = _expected_channel_id(channel)
        if not expected:
            raise RuntimeError(
                "channel has no youtube_channel_id configured — refusing to upload (cannot verify target)")
        creds = get_credentials(channel, self.settings)
        if creds is None:
            raise RuntimeError("no YouTube credentials (run `python -m ytagent.youtube_auth`)")

        body = build_youtube_body(video, channel)
        if body["status"]["privacyStatus"] != PRIVACY_LOCKED:  # belt-and-braces private lock
            raise RuntimeError("privacyStatus not locked to private — refusing to upload")
        snip = body["snippet"]
        assert_no_internal_artifacts(snip["title"], snip["description"], *snip.get("tags", []))
        assert_short_conditions(video, snip["title"], snip["description"])   # 9:16 must classify as a Short

        youtube = _client(creds)
        _preflight_channel(youtube, expected)                  # cheap pre-check when readable
        resource = await asyncio.to_thread(self._upload, youtube, body, video["file_path"])

        # BACKSTOP (Amendment A) — insert is irreversible; verify where it actually landed.
        actual = _resource_channel_id(resource)
        if actual != expected:
            raise ChannelMismatchError(youtube_video_id=resource.get("id"), actual=actual, expected=expected)

        return PublishResult(
            mode="live", privacy_status=PRIVACY_LOCKED, job_status="published",
            video_status="published", youtube_video_id=resource.get("id"),
            published_at=datetime.now(timezone.utc), body=body, validation=validation,
            raw={"youtube_resource": resource})

    def _upload(self, youtube, body: dict, path: str) -> dict:
        """Synchronous resumable upload — runs in a worker thread via asyncio.to_thread."""
        media = MediaFileUpload(path, mimetype="video/mp4", resumable=True, chunksize=_CHUNK)
        request = youtube.videos().insert(part="snippet,status", body=body, media_body=media)
        try:
            response = None
            while response is None:
                status, response = request.next_chunk(num_retries=3)
                if status:
                    print(f"[youtube] upload {int(status.progress() * 100)}%")
            print(f"[youtube] uploaded id={response.get('id')} (private)")
            return response
        except HttpError as e:
            raise _http_error("upload", e) from e

    # --- UPDATE to PUBLIC (gated publish of a video WE uploaded) ------------------------------------
    async def update_public(self, video: dict, channel: dict) -> PublishResult:
        yt_id = video.get("youtube_video_id")
        if not yt_id:
            raise RuntimeError("update_public called on a video with no youtube_video_id (not ours/uploaded)")
        expected = _expected_channel_id(channel)
        if not expected:
            raise RuntimeError("channel has no youtube_channel_id configured — refusing to update")
        creds = get_credentials(channel, self.settings)
        if creds is None:
            raise RuntimeError("no YouTube credentials (run `python -m ytagent.youtube_auth`)")

        body = build_public_update_body(video, channel)        # clean snippet + privacyStatus=public
        snip = body["snippet"]
        assert_no_internal_artifacts(snip["title"], snip["description"], *snip.get("tags", []))
        assert_short_conditions(video, snip["title"], snip["description"])   # 9:16 must classify as a Short

        resource = await asyncio.to_thread(
            self._update, creds, yt_id, body, expected, {yt_id})   # own-id set = this video only
        return PublishResult(
            mode="live", privacy_status=PRIVACY_PUBLIC, job_status="published",
            video_status="published", youtube_video_id=yt_id,
            published_at=datetime.now(timezone.utc), body=body, validation={},
            raw={"youtube_resource": resource})

    def _update(self, creds: Credentials, yt_id: str, body: dict, expected: str, our_ids: set) -> dict:
        """The ONLY videos.update call site. Refuses any id we did not upload; verifies the channel both
        before (pre-flight) and after (backstop) the write."""
        if yt_id not in our_ids:
            raise RuntimeError(f"refusing to update {yt_id}: not in our own-upload set {our_ids}")
        youtube = _client(creds)
        _preflight_channel(youtube, expected)                  # readable under force-ssl
        update_body = {"id": yt_id, **body}
        try:
            resource = youtube.videos().update(part="snippet,status", body=update_body).execute()
        except HttpError as e:
            raise _http_error("update", e) from e
        actual = _resource_channel_id(resource)
        if actual is not None and actual != expected:          # backstop
            raise ChannelMismatchError(youtube_video_id=yt_id, actual=actual, expected=expected)
        print(f"[youtube] updated id={yt_id} -> {body['status'].get('privacyStatus')}")
        return resource


def _http_error(op: str, e: HttpError) -> RuntimeError:
    # provider-error-standard.md: carry Google's OWN message + reason through; only ADD a hint, hedged.
    reason, message = "", ""
    try:
        reason = e.error_details[0].get("reason", "") if e.error_details else ""
    except Exception:  # noqa: BLE001
        pass
    try:
        message = (e.reason or "") or str(e)
    except Exception:  # noqa: BLE001
        pass
    base = f"YouTube {op} failed (HTTP {e.resp.status} {reason}): {message}".rstrip(": ").rstrip()
    if e.resp.status == 403 and reason in ("quotaExceeded", "dailyLimitExceeded"):
        return RuntimeError(f"{base} — API quota exhausted, retry tomorrow")
    if e.resp.status in (401, 403) and reason in ("insufficientPermissions", "forbidden", ""):
        return RuntimeError(f"{base} — the token may lack the youtube.force-ssl scope; re-run "
                            "`python -m ytagent.youtube_auth`")
    return RuntimeError(base)
