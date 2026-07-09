"""Known test artifacts (telegram-free so tests can import without python-telegram-bot).

The lion film is the platform's first known-good payload threaded through the pipeline.

INTERNAL ONLY. This module carries the technical/provenance record — file path, dimensions, loudness,
size, provenance ref. It deliberately holds NO public-facing text: title, description and tags are
authored separately as a `Description` (ytagent/metadata/lion_reference.py) and stored versioned in
`video_metadata`. Keeping public text out of here is the structural fix for the leak that put
`lion-doc-01-footage-manifest.md` into the lion's live description (public-facing-output-standard §3).
"""
from __future__ import annotations

import os


def lion_video_meta() -> dict:
    """The lion film's INTERNAL technical payload. Public text lives in video_metadata, not here."""
    base = os.environ.get("ASSETS_DIR", "/app/assets")
    return {
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
        "provenance_ref": "lion-doc-01-footage-manifest.md",   # INTERNAL — never enters public text
    }
