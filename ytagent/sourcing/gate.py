"""The input gate — a dirty or broken download NEVER enters a production. Reuses the Slice-3
primitives (ffmpeg.probe + qc.check_source_clean); adds a decode pass (truncation) and orientation/
duration checks.

CRITICAL: stock footage is usually SILENT (no audio stream). `qc.check_source_clean` measures the
noise floor and would report None → fail for a clip with no audio. So the noise gate runs ONLY when
the clip carries audio; a no-audio clip PASSES by construction (the assembler supplies narration +
music). Getting this wrong rejects every clean silent stock clip.
"""
from __future__ import annotations

import subprocess

from ..assembly import ffmpeg, qc
from .base import GateResult, orientation_of


def _decodes_ok(path: str) -> tuple[bool, str]:
    """Full decode to null — catches a truncated/corrupt file that still probes with a plausible header."""
    proc = subprocess.run(
        [ffmpeg.FFMPEG, "-v", "error", "-xerror", "-i", path, "-f", "null", "-"],
        capture_output=True, text=True,
    )
    return proc.returncode == 0, proc.stderr.strip().splitlines()[-1] if proc.stderr.strip() else ""


_MIN_CLIP_S = 2.0   # absolute floor — a shorter file is broken/truncated. ADEQUACY (long enough for a
#                     beat) is a RANKING concern, not a gate: the assembler holds/loops short clips.


def gate_download(path: str, *, orientation: str) -> GateResult:
    reasons: list[str] = []
    try:
        p = ffmpeg.probe(path)
    except ffmpeg.FFmpegError as e:
        return GateResult(ok=False, reasons=(f"unprobeable: {e}",))

    if not p["width"] or not p["height"]:
        reasons.append("no video stream")
    if p["width"] and orientation_of(p["width"], p["height"]) != orientation:
        reasons.append(f"orientation {orientation_of(p['width'], p['height'])} != {orientation}")
    if p["duration"] < _MIN_CLIP_S:
        reasons.append(f"too short/truncated ({p['duration']:.1f}s)")

    ok_decode, derr = _decodes_ok(path)
    if not ok_decode:
        reasons.append(f"decode error: {derr[:80]}")

    # noise gate — ONLY on clips that carry audio (silent stock footage is clean by construction)
    noise = None
    if p["has_audio"]:
        noise = qc.check_source_clean(path)
        if not noise.ok:
            bad = "; ".join(n for n, ok, _ in noise.checks if not ok)
            reasons.append(f"noise: {bad}")

    return GateResult(ok=not reasons, probe=p, noise=noise, reasons=tuple(reasons))
