"""The only module that shells out to ffmpeg/ffprobe. Enforces the hard-won CLAUDE rules
structurally: build to a temp file then atomic `os.replace`; verify size>0; never `aeval`; audio
swells via `volume` sine, never `tremolo`. The filtergraph builders are PURE strings (no I/O) so
they are unit-testable without rendering.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess

FFMPEG = shutil.which("ffmpeg") or "/opt/homebrew/bin/ffmpeg"
FFPROBE = shutil.which("ffprobe") or "/opt/homebrew/bin/ffprobe"


class FFmpegError(RuntimeError):
    pass


def run(args: list[str], *, dst: str, timeout: int = 3600) -> str:
    """Run `ffmpeg -y <args> <dst.tmp>`, then atomically move to `dst`. Returns `dst`.

    Writes a temp sibling and `os.replace`s it only after a clean exit + non-empty output, so a
    crashed/killed render never leaves a half-written file (and never touches a locked reference)."""
    tmp = f"{dst}.tmp.mp4"
    if os.path.exists(tmp):
        os.remove(tmp)
    proc = subprocess.run([FFMPEG, "-y", *args, tmp], capture_output=True, text=True, timeout=timeout)
    if proc.returncode != 0:
        tail = "\n".join(proc.stderr.strip().splitlines()[-15:])
        if os.path.exists(tmp):
            os.remove(tmp)
        raise FFmpegError(f"ffmpeg exit {proc.returncode}:\n{tail}")
    if not (os.path.exists(tmp) and os.path.getsize(tmp) > 0):
        raise FFmpegError("ffmpeg produced no output")
    os.replace(tmp, dst)
    return dst


def probe(path: str) -> dict:
    """Normalized ffprobe view: duration/width/height/fps/has_audio + raw streams/format."""
    proc = subprocess.run(
        [FFPROBE, "-v", "error", "-print_format", "json", "-show_format", "-show_streams", path],
        capture_output=True, text=True,
    )
    if proc.returncode != 0:
        raise FFmpegError(f"ffprobe failed for {path}: {proc.stderr.strip()}")
    data = json.loads(proc.stdout)
    streams = data.get("streams", [])
    v = next((s for s in streams if s.get("codec_type") == "video"), {})
    a = next((s for s in streams if s.get("codec_type") == "audio"), None)
    num, den = (v.get("r_frame_rate", "0/1").split("/") + ["1"])[:2]
    fps = round(float(num) / float(den), 3) if float(den) else 0.0
    dur = float(data.get("format", {}).get("duration") or v.get("duration") or 0.0)
    return {
        "duration": dur,
        "width": int(v.get("width", 0)),
        "height": int(v.get("height", 0)),
        "fps": fps,
        "has_audio": a is not None,
        "vcodec": v.get("codec_name"),
        "acodec": a.get("codec_name") if a else None,
        "streams": streams,
        "format": data.get("format", {}),
    }


# --- pure filtergraph builders (no I/O — unit-testable) ---------------------------------------

def crop_to_format(sw: int, sh: int, tw: int, th: int, focus: tuple[float, float]) -> str:
    """Cover-then-crop a source (sw×sh) into tw×th at a normalized focal point. When the source
    already matches the target aspect, just scale (no crop). `fx/fy` in [0,1]: 0=left/top, 1=right/
    bottom. This is where a center-crop would push an off-centre lion out of a 9:16 frame."""
    fx, fy = focus
    if sw and sh and abs(sw / sh - tw / th) < 1e-3:
        return f"scale={tw}:{th},setsar=1"
    return (
        f"scale={tw}:{th}:force_original_aspect_ratio=increase,"
        f"crop={tw}:{th}:(iw-{tw})*{fx:.4f}:(ih-{th})*{fy:.4f},setsar=1"
    )


def zoompan_expr(effect: dict | None, frames: int, w: int, h: int, fps: int) -> str | None:
    """A slow Ken-Burns push (zoompan) from z_from→z_to over `frames`. None when no effect."""
    if not effect or effect.get("type") != "zoompan":
        return None
    z0 = float(effect.get("z_from", 1.0))
    z1 = float(effect.get("z_to", 1.08))
    step = max((z1 - z0) / max(frames, 1), 0.0)
    return (
        f"zoompan=z='min(zoom+{step:.6f},{z1:.4f})':d={frames}"
        f":x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s={w}x{h}:fps={fps}"
    )


def normalize_clip(sw: int, sh: int, target, focus: tuple[float, float],
                   effect: dict | None, frames: int) -> str:
    """The -vf chain to bring one source clip to the target frame: crop-to-format → optional
    Ken-Burns → fps/pixel-format. Trims are applied by the caller via input -ss/-t."""
    parts = [crop_to_format(sw, sh, target.w, target.h, focus)]
    zp = zoompan_expr(effect, frames, target.w, target.h, target.fps)
    if zp:
        parts.append(zp)
    parts.append(f"fps={target.fps}")
    parts.append("format=yuv420p")
    return ",".join(parts)


def volume_sine(base: float, depth: float, period_s: float) -> str:
    """A slow, organic volume swell via the `volume` filter — NEVER `tremolo` (min freq too fast)
    and NEVER `aeval` (segfaults)."""
    return f"volume=volume='{base}+{depth}*sin(2*PI*t/{period_s})':eval=frame"
