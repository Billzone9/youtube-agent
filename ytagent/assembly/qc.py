"""Measurement + comparison. `measure()` returns a dict SHAPE-IDENTICAL to
`ytagent.artifacts.lion_video_meta()` (plus a real sha256 checksum — the comment there says checksum
is "deferred to the assembly slice"; this is it), so an assembled artifact drops straight into the
existing `submit_video_for_approval(video_meta=...)` path. Byte-exact reproduction is impossible;
`compare()` checks structure + QC within tolerance, and `vmaf()` gives an objective similarity score.
"""
from __future__ import annotations

import hashlib
import os
import re
import subprocess
from dataclasses import dataclass, field

from . import ffmpeg


def _fmt_label(w: int, h: int) -> str:
    if not h:
        return "?"
    ar = w / h
    if abs(ar - 16 / 9) < 0.05:
        return "16:9"
    if abs(ar - 9 / 16) < 0.05:
        return "9:16"
    return f"{w}:{h}"


def sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def integrated_loudness(path: str) -> tuple[float | None, float | None]:
    """(integrated LUFS, true-peak dBFS) via the ebur128 meter — the honest measurement."""
    proc = subprocess.run(
        [ffmpeg.FFMPEG, "-hide_banner", "-i", path, "-af", "ebur128=peak=true", "-f", "null", "-"],
        capture_output=True, text=True,
    )
    err = proc.stderr
    lufs = _last_float(re.findall(r"I:\s*(-?\d+(?:\.\d+)?)\s*LUFS", err))
    peak = _last_float(re.findall(r"Peak:\s*(-?\d+(?:\.\d+)?)\s*dBFS", err))
    return lufs, peak


def noise_floor_db(path: str) -> float | None:
    """High-band (>8 kHz) MEAN volume — the mandatory noise-floor check. Mean (not max): broadband
    hiss raises the floor, whereas max just catches legitimate musical transients (cymbals, air).
    The locked reference measures −33.8 dB here (the figure recorded in artifacts.py)."""
    proc = subprocess.run(
        [ffmpeg.FFMPEG, "-hide_banner", "-i", path, "-af", "highpass=f=8000,volumedetect",
         "-f", "null", "-"],
        capture_output=True, text=True,
    )
    m = re.search(r"mean_volume:\s*(-?\d+(?:\.\d+)?)\s*dB", proc.stderr)
    return float(m.group(1)) if m else None


def _last_float(xs) -> float | None:
    return float(xs[-1]) if xs else None


def measure(path: str, *, provenance_ref: str | None = None) -> dict:
    """QC dict shaped exactly like artifacts.lion_video_meta()."""
    p = ffmpeg.probe(path)
    lufs, peak = integrated_loudness(path)
    return {
        "file_path": path,
        "format": _fmt_label(p["width"], p["height"]),
        "duration_s": round(p["duration"], 3),
        "width": p["width"],
        "height": p["height"],
        "fps": int(round(p["fps"])),
        "loudness_lufs": lufs,
        "peak_dbfs": peak,
        "noise_floor_db": noise_floor_db(path),
        "size_bytes": os.path.getsize(path),
        "checksum": sha256(path),
        "provenance_ref": provenance_ref,
    }


@dataclass(frozen=True)
class QCTolerance:
    duration_s: float = 1.5          # crossfade rounding
    loudness_target: float = -14.0
    loudness_tol: float = 1.0
    peak_ceiling: float = 0.0        # must be < 0
    peak_floor: float = -3.0         # sane lower bound
    noise_floor_max: float = -30.0   # >8kHz ≤ this = no broadband hiss


@dataclass
class QCResult:
    ok: bool
    checks: list[tuple[str, bool, str]] = field(default_factory=list)


def compare(measured: dict, reference: dict, tol: QCTolerance = QCTolerance()) -> QCResult:
    """Check the measured artifact against the reference within tolerance. Res/fps exact; the rest
    within bands (byte-exact is impossible)."""
    checks: list[tuple[str, bool, str]] = []

    def add(name, ok, detail=""):
        checks.append((name, bool(ok), detail))

    add("width", measured["width"] == reference["width"],
        f"{measured['width']} vs {reference['width']}")
    add("height", measured["height"] == reference["height"],
        f"{measured['height']} vs {reference['height']}")
    add("fps", measured["fps"] == reference["fps"], f"{measured['fps']} vs {reference['fps']}")
    dd = abs(measured["duration_s"] - reference["duration_s"])
    add("duration", dd <= tol.duration_s, f"Δ{dd:.2f}s (≤{tol.duration_s})")
    lu = measured.get("loudness_lufs")
    add("loudness", lu is not None and abs(lu - tol.loudness_target) <= tol.loudness_tol,
        f"{lu} LUFS (target {tol.loudness_target}±{tol.loudness_tol})")
    pk = measured.get("peak_dbfs")
    add("peak", pk is not None and tol.peak_floor <= pk < tol.peak_ceiling,
        f"{pk} dBFS (want [{tol.peak_floor},{tol.peak_ceiling}))")
    add("audio_present", measured.get("loudness_lufs") is not None, "")
    nf = measured.get("noise_floor_db")
    add("noise_floor", nf is not None and nf <= tol.noise_floor_max,
        f"{nf} dB (>8kHz, ≤{tol.noise_floor_max})")
    return QCResult(ok=all(c[1] for c in checks), checks=checks)


def band_mean_db(path: str, hz: int) -> float | None:
    """Mean level in the band above `hz` (highpass + volumedetect) — broadband hiss lives up here."""
    proc = subprocess.run(
        [ffmpeg.FFMPEG, "-hide_banner", "-i", path, "-af", f"highpass=f={hz},volumedetect",
         "-f", "null", "-"],
        capture_output=True, text=True,
    )
    m = re.search(r"mean_volume:\s*(-?\d+(?:\.\d+)?)\s*dB", proc.stderr)
    return float(m.group(1)) if m else None


def noise_report(path: str) -> dict:
    """Multi-band noise picture: audio sample rate + high-band mean energy at 8/10/16 kHz."""
    p = ffmpeg.probe(path)
    sr = 0
    for s in p["streams"]:
        if s.get("codec_type") == "audio":
            sr = int(s.get("sample_rate") or 0)
            break
    return {
        "sample_rate": sr,
        "hi8k_db": band_mean_db(path, 8000),
        "hi10k_db": band_mean_db(path, 10000),
        "hi16k_db": band_mean_db(path, 16000),
    }


@dataclass(frozen=True)
class NoiseThresholds:
    """Calibrated to Banks's ear: the LOCKED reference passes, the hissy (96k) render fails.
    Reference `_scored.mp4`: 48000 Hz, >16k −47.0 dB, >8k −33.8 dB.
    Hissy `_assembled.mp4` (loudnorm→96k): 96000 Hz, >16k −42.7 dB."""

    expected_sample_rate: int = 48000
    hi16k_max_db: float = -45.0      # scored −47.0 PASS · hissy −42.7 FAIL (the resampling-hiss catch)
    hi8k_max_db: float = -28.0       # loose broadband guard (clean ≈ −33.8; a gross hiss exceeds this)


# Looser bands for raw SOURCES (they get resampled during assembly, so no output-rate check; only a
# gross-hiss guard). A clean source beat measures ≈ −45.6 dB >16k; a grossly noisy one is far hotter.
SOURCE_THRESHOLDS = NoiseThresholds(expected_sample_rate=0, hi16k_max_db=-38.0, hi8k_max_db=-24.0)


def noise_gate(report: dict, tol: NoiseThresholds = NoiseThresholds()) -> QCResult:
    """PASS/FAIL a file's noise picture. No render with audible broadband noise may ever be kept
    (house rule, CLAUDE.md). `expected_sample_rate=0` skips the rate check (for raw sources)."""
    checks: list[tuple[str, bool, str]] = []
    if tol.expected_sample_rate:
        sr = report.get("sample_rate")
        checks.append(("sample_rate", sr == tol.expected_sample_rate,
                       f"{sr} Hz (want {tol.expected_sample_rate}; loudnorm→96k = broadband hiss)"))
    h16 = report.get("hi16k_db")
    checks.append((">16kHz noise", h16 is not None and h16 <= tol.hi16k_max_db,
                   f"{h16} dB (≤{tol.hi16k_max_db})"))
    h8 = report.get("hi8k_db")
    checks.append((">8kHz noise", h8 is not None and h8 <= tol.hi8k_max_db,
                   f"{h8} dB (≤{tol.hi8k_max_db})"))
    return QCResult(ok=all(c[1] for c in checks), checks=checks)


def check_source_clean(path: str, tol: NoiseThresholds = SOURCE_THRESHOLDS) -> QCResult:
    """The INPUT gate — QC a source clip/beat/audio for gross noise before assembly, so a dirty input
    never enters (and silently degrades) a production. Looser than the output gate; no rate check."""
    return noise_gate(noise_report(path), tol)


def vmaf(candidate: str, reference: str, *, seconds: float | None = None) -> float | None:
    """Objective similarity of `candidate` vs `reference` via libvmaf. None if it can't run.
    `seconds` limits both inputs to a leading window (a fast spot-check — full-length VMAF on a
    6.5-min 1080p pair is minutes of decode)."""
    limit = ["-t", str(seconds)] if seconds else []
    try:
        proc = subprocess.run(
            [ffmpeg.FFMPEG, "-hide_banner", *limit, "-i", candidate, *limit, "-i", reference, "-lavfi",
             "[0:v]settb=AVTB,setpts=PTS-STARTPTS[d];[1:v]settb=AVTB,setpts=PTS-STARTPTS[r];"
             "[d][r]libvmaf", "-f", "null", "-"],
            capture_output=True, text=True, timeout=1800,
        )
        m = re.search(r"VMAF score:\s*(\d+(?:\.\d+)?)", proc.stderr)
        return float(m.group(1)) if m else None
    except Exception:  # noqa: BLE001 — VMAF is a best-effort objective aid, never gating infra
        return None
