"""Publish. Slice 1 ships dry_run_publish() ONLY: it builds the EXACT body the real YouTube
`videos.insert` call will take (so slice 2 is a client swap behind the same shape) and validates
the media, but makes NO network call and needs no credentials. Getting AI/synthetic-media
disclosure, privacyStatus and madeForKids right HERE is what makes slice 2 a config swap.
"""
from __future__ import annotations

import os
from typing import Any


def build_youtube_body(video: dict, channel: dict) -> dict:
    cfg = channel.get("config") or {}
    policy = cfg.get("approval_policy") or {}
    privacy = policy.get("default_privacy", "private")  # safe default for a first real publish
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
            "privacyStatus": privacy,
            "selfDeclaredMadeForKids": False,
            "containsSyntheticMedia": True,  # AI narration + AI score -> disclosure required
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


def dry_run_publish(video: dict, channel: dict) -> dict[str, Any]:
    body = build_youtube_body(video, channel)
    validation = validate_media(video)
    return {
        "dry_run": True,
        "would_call": "youtube.videos.insert",
        "part": ["snippet", "status"],
        "body": body,
        "media": {
            "file_path": video["file_path"],
            "size_bytes": video.get("size_bytes"),
            "checksum": video.get("checksum"),
        },
        "validation": validation,
    }
