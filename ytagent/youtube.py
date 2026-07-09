"""Real YouTube upload. YouTubePublisher implements the Publisher protocol; the orchestrator
never imports googleapiclient. Credentials are built from a stored refresh token (no interactive
consent at runtime — that happens once via ytagent/youtube_auth.py). Uploads are LOCKED to private.
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
from .publish import PRIVACY_LOCKED, PublishResult, build_youtube_body, validate_media

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]
_TOKEN_URI = "https://oauth2.googleapis.com/token"
_CHUNK = 8 * 1024 * 1024   # 8 MiB (multiple of 256 KiB) — resumable resilience + progress
_SOCKET_TIMEOUT = 120      # seconds; bounds a stalled connection in the worker thread


def _refresh_token_for(channel: dict, settings: Settings) -> str | None:
    """Per-channel token first (env var by slug), else the global one — secrets stay in .env,
    never in the DB."""
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


class YouTubePublisher:
    mode = "live"

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    async def publish(self, video: dict, channel: dict) -> PublishResult:
        validation = validate_media(video)
        if not validation["size_matches"]:
            raise RuntimeError(
                f"media validation failed (size {validation['size_bytes_actual']} != "
                f"{validation['size_bytes_expected']}) — refusing to upload"
            )
        creds = get_credentials(channel, self.settings)
        if creds is None:
            raise RuntimeError("no YouTube credentials (run `python -m ytagent.youtube_auth`)")

        body = build_youtube_body(video, channel)
        if body["status"]["privacyStatus"] != PRIVACY_LOCKED:  # belt-and-braces private lock
            raise RuntimeError("privacyStatus not locked to private — refusing to upload")
        # belt-and-braces artifact lock at the live boundary — re-scan the exact snippet we're about
        # to send, so no other path can slip an internal artifact past the build-time guard.
        snip = body["snippet"]
        assert_no_internal_artifacts(snip["title"], snip["description"], *snip.get("tags", []))

        resource = await asyncio.to_thread(self._upload, creds, body, video["file_path"])

        return PublishResult(
            mode="live",
            privacy_status=PRIVACY_LOCKED,
            job_status="published",
            video_status="published",
            youtube_video_id=resource.get("id"),
            published_at=datetime.now(timezone.utc),
            body=body,
            validation=validation,
            raw={"youtube_resource": resource},
        )

    def _upload(self, creds: Credentials, body: dict, path: str) -> dict:
        """Synchronous resumable upload — runs in a worker thread via asyncio.to_thread."""
        socket.setdefaulttimeout(_SOCKET_TIMEOUT)
        youtube = build("youtube", "v3", credentials=creds, cache_discovery=False)
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
            reason = ""
            try:
                reason = e.error_details[0].get("reason", "") if e.error_details else ""
            except Exception:  # noqa: BLE001
                pass
            if e.resp.status == 403 and reason in ("quotaExceeded", "dailyLimitExceeded"):
                raise RuntimeError(
                    "YouTube API quota exhausted (one upload ~1600 of 10,000 units/day) — "
                    "retry tomorrow"
                ) from e
            raise RuntimeError(f"YouTube upload failed (HTTP {e.resp.status} {reason})") from e
