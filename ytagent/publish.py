"""Publishing. A Publisher protocol (mirroring the Notifier seam) lets the orchestrator stay
transport/impl-agnostic: it calls publisher.publish(video, channel) and persists whatever the
returned PublishResult says. Two implementations: DryRunPublisher (here) and YouTubePublisher
(ytagent/youtube.py). build_youtube_body()/validate_media() are shared free functions.

Privacy is LOCKED to 'private' in the body builder (config cannot make it public); the live
publisher re-asserts it before calling the API. That is the literal "enforced in code" guarantee.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Protocol

PRIVACY_LOCKED = "private"  # never unlisted/public — Banks flips to public himself, by hand


@dataclass(frozen=True)
class PublishResult:
    mode: str                       # "dry_run" | "live"
    privacy_status: str             # always PRIVACY_LOCKED
    job_status: str                 # terminal status the orchestrator persists
    video_status: str
    youtube_video_id: str | None = None
    published_at: datetime | None = None
    body: dict = field(default_factory=dict)
    validation: dict = field(default_factory=dict)
    raw: dict = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "privacy_status": self.privacy_status,
            "job_status": self.job_status,
            "video_status": self.video_status,
            "youtube_video_id": self.youtube_video_id,
            "published_at": self.published_at.isoformat() if self.published_at else None,
            "body": self.body,
            "validation": self.validation,
            "raw": self.raw,
        }


class Publisher(Protocol):
    mode: str  # "dry_run" | "live"

    async def publish(self, video: dict, channel: dict) -> PublishResult:
        ...


def build_youtube_body(video: dict, channel: dict) -> dict:
    cfg = channel.get("config") or {}
    lang = video.get("primary_language") or cfg.get("primary_language") or "en"
    return {
        "snippet": {
            "title": (video["title"] or "")[:100],
            "description": video.get("description") or "",
            "tags": cfg.get("default_tags") or [],
            "categoryId": str(cfg.get("youtube_category_id", "15")),  # 15 = Pets & Animals
            "defaultLanguage": lang,
            "defaultAudioLanguage": lang,
        },
        "status": {
            "privacyStatus": PRIVACY_LOCKED,      # LOCKED — not read from config
            "selfDeclaredMadeForKids": False,
            "containsSyntheticMedia": True,       # AI narration + AI score -> disclosure required
            "license": "youtube",
            "embeddable": True,
        },
    }


def validate_media(video: dict) -> dict:
    path = video["file_path"]
    exists = os.path.exists(path)
    actual = os.path.getsize(path) if exists else None
    expected = video.get("size_bytes")
    return {
        "file_path": path,
        "exists": exists,
        "size_bytes_actual": actual,
        "size_bytes_expected": expected,
        "size_matches": bool(exists and expected is not None and actual == expected),
    }


class DryRunPublisher:
    """Builds and validates exactly as the real path, but makes no API call."""

    mode = "dry_run"

    async def publish(self, video: dict, channel: dict) -> PublishResult:
        body = build_youtube_body(video, channel)
        validation = validate_media(video)
        return PublishResult(
            mode="dry_run",
            privacy_status=PRIVACY_LOCKED,
            job_status="published_dryrun",
            video_status="published_dryrun",
            youtube_video_id=None,
            published_at=None,
            body=body,
            validation=validation,
            raw={
                "dry_run": True,
                "would_call": "youtube.videos.insert",
                "part": ["snippet", "status"],
                "media": {
                    "file_path": video["file_path"],
                    "size_bytes": video.get("size_bytes"),
                    "checksum": video.get("checksum"),
                },
            },
        )
