"""Stage 1 — raw clips → one normalized beat (the general video path future videos need).

Each source clip is trimmed (input -ss/-t), brought to the target frame by `normalize_clip`
(crop-to-format at its per-format focal point + optional Ken-Burns), then the clips are xfaded into a
single silent beat. Runs on demand for the ONE-beat capability proof (and the 9:16 variant); the lion
reproduction uses the pre-baked beats via stage2, not this.
"""
from __future__ import annotations

from . import ffmpeg
from .spec import Clip


def _clip_dur(clip: Clip, src_dur: float) -> float:
    end = clip.trim_out if clip.trim_out is not None else src_dur
    return max(round(end - clip.trim_in, 3), 0.1)


def build_beat(spec, beat, dst: str, *, intra_xfade: float = 0.6) -> str:
    """Render one beat's clips (in the spec's active format) into a silent normalized beat video."""
    tgt = spec.target
    clips = beat.clips
    if not clips:
        raise ValueError(f"beat {beat.name!r} has no clips to build from")

    args: list[str] = []
    fc: list[str] = []
    durs: list[float] = []
    for i, clip in enumerate(clips):
        src = spec.resolve(clip.src)
        p = ffmpeg.probe(src)
        dur = _clip_dur(clip, p["duration"])
        durs.append(dur)
        args += ["-ss", f"{clip.trim_in}", "-t", f"{dur}", "-i", src]
        vf = ffmpeg.normalize_clip(p["width"], p["height"], tgt, clip.focus_for(tgt.fmt),
                                   clip.effect, int(dur * tgt.fps))
        fc.append(f"[{i}:v]{vf}[c{i}]")

    # xfade the normalized segments; offset = running length − overlap
    if len(clips) == 1:
        vprev = "[c0]"
    else:
        vprev = "[c0]"
        acc = durs[0]
        for i in range(1, len(clips)):
            o = min(intra_xfade, durs[i] - 0.05, durs[i - 1] - 0.05)
            off = acc - o
            lbl = f"[x{i}]"
            fc.append(f"{vprev}[c{i}]xfade=transition=fade:duration={o:.3f}:offset={off:.3f}{lbl}")
            vprev = lbl
            acc = off + durs[i]

    args += [
        "-filter_complex", ";".join(fc), "-map", vprev, "-an",
        "-c:v", tgt.vcodec, "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p",
        "-r", str(tgt.fps), "-movflags", "+faststart",
    ]
    return ffmpeg.run(args, dst=dst)
