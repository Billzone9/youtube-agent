"""Assembly — the automated FFmpeg edit (channel-general; the lion is DATA, in edit_spec.json).

Pure builders + measurement import cleanly without rendering; the render modules
(stage1/stage2/audio/assembler) shell out to ffmpeg only when actually assembling.
"""
from __future__ import annotations

from . import audio, ffmpeg, provenance, qc, stage1, stage2
from .assembler import AssemblyResult, assemble
from .spec import EditSpec, load_spec

__all__ = [
    "load_spec", "EditSpec", "assemble", "AssemblyResult",
    "ffmpeg", "qc", "provenance", "stage1", "stage2", "audio",
]
