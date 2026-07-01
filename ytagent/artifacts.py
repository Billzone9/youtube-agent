"""Known test artifacts (telegram-free so tests can import without python-telegram-bot).

The lion film is the platform's first known-good payload threaded through the pipeline.
"""
from __future__ import annotations

import os

_LION_DESCRIPTION = (
    "Lion — Lord of the Savanna. A short wildlife documentary.\n\n"
    "AI disclosure: narration (ElevenLabs voice 'David') and the original instrumental score "
    "(ElevenLabs Music) are AI-generated; footage is licensed claim-safe stock (Pexels & Pixabay).\n\n"
    "Chapters:\n"
    "0:00 The kingdom and its sovereign\n0:51 The lion at rest\n1:54 The pride\n"
    "2:58 The hunt\n3:59 The cubs\n5:03 The roar\n5:47 Golden-hour close\n\n"
    "Footage provenance logged in lion-doc-01-footage-manifest.md."
)


def lion_video_meta() -> dict:
    base = os.environ.get("ASSETS_DIR", "/app/assets")
    return {
        "title": "Lion — Lord of the Savanna",
        "description": _LION_DESCRIPTION,
        "file_path": os.path.join(base, "lion-doc-01/output/lion-doc-01_scored.mp4"),
        "format": "16:9",
        "duration_s": 394.783,
        "width": 1920,
        "height": 1080,
        "fps": 24,
        "loudness_lufs": -13.8,
        "peak_dbfs": -0.5,
        "noise_floor_db": None,  # scored mix: true silence at fades; no broadband hiss (>8kHz -33.8 dB)
        "size_bytes": 368842754,
        "checksum": None,        # sha256 recompute deferred to the assembly slice
        "provenance_ref": "lion-doc-01-footage-manifest.md",
    }
