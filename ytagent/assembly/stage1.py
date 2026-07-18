"""Stage 1 — raw clips → one normalized beat (the general video path future videos need).

Each source clip is trimmed (input -ss/-t), brought to the target frame by `normalize_clip`
(crop-to-format at its per-format focal point + optional Ken-Burns), then the clips are xfaded into a
single silent beat. Runs on demand for the ONE-beat capability proof (and the 9:16 variant); the lion
reproduction uses the pre-baked beats via stage2, not this.
"""
from __future__ import annotations

from . import ffmpeg
from .density import INTRA_XFADE, SHOT_MAX_S, even_slot
from .spec import Clip

_SLOW_MAX = 1.25   # a single short shot may be slowed up to this × to reach its slot (mild, wildlife-
#                    safe); a bigger stretch reads as slow-motion, so the deficit moves to other clips


def _clip_dur(clip: Clip, src_dur: float) -> float:
    end = clip.trim_out if clip.trim_out is not None else src_dur
    return max(round(end - clip.trim_in, 3), 0.1)


def _assign_slots(avail: list[float], duration: float, o: float) -> list[float]:
    """Split `duration`s of beat across len(avail) crossfaded shots. Σ slots − overlaps = duration.
    Each shot aims for an even slot, capped at min(SHOT_MAX, its source × _SLOW_MAX); any deficit from a
    short clip is redistributed to clips with spare source. Raises if the clips can't fill the beat."""
    k = len(avail)
    total = duration + (k - 1) * o                          # Σ slots must equal this
    caps = [min(SHOT_MAX_S, a * _SLOW_MAX) for a in avail]
    if sum(caps) + 1e-6 < total:
        raise ValueError(f"clips too short to fill {duration:.1f}s across {k} shots "
                         f"(capacity {sum(caps) - (k - 1) * o:.1f}s) — source more/longer footage")
    slot = [min(even_slot(duration, k), caps[i]) for i in range(k)]
    for _ in range(k):                                      # redistribute the deficit to clips with room
        deficit = total - sum(slot)
        if deficit <= 1e-3:
            break
        room = [caps[i] - slot[i] for i in range(k)]
        avail_room = sum(room)
        if avail_room <= 1e-6:
            break
        for i in range(k):
            slot[i] += deficit * (room[i] / avail_room)
            slot[i] = min(slot[i], caps[i])
    return [round(s, 3) for s in slot]


def build_beat_fitted(spec, beat, dst: str, *, duration: float) -> str:
    """Render ONE beat to fill EXACTLY `duration`s of silent target-format video, the narration driving
    the beat. MULTI-CLIP (the house standard): the beat's K distinct shots are trimmed (or mildly
    slowed) to their slots and crossfaded — a fresh shot every ~`even_slot`s, no looping. A single-clip
    beat (short/back-compat) trims or mildly slows the one clip."""
    tgt = spec.target
    clips = beat.clips
    if not clips:
        raise ValueError(f"beat {beat.name!r} has no clips to build from")

    probes = [ffmpeg.probe(spec.resolve(c.src)) for c in clips]
    avail = [_clip_dur(c, p["duration"]) for c, p in zip(clips, probes)]
    o = INTRA_XFADE
    durs = _assign_slots(avail, duration, o) if len(clips) > 1 else [duration]

    args: list[str] = []
    fc: list[str] = []
    for i, (clip, p, d) in enumerate(zip(clips, probes, durs)):
        src = spec.resolve(clip.src)
        vf = ffmpeg.normalize_clip(p["width"], p["height"], tgt, clip.focus_for(tgt.fmt), clip.effect,
                                   int(d * tgt.fps))
        if avail[i] + 1e-3 >= d:                            # trim to the slot
            args += ["-ss", f"{clip.trim_in}", "-t", f"{d:.3f}", "-i", src]
            fc.append(f"[{i}:v]{vf}[c{i}]")
        else:                                               # slow this one shot to reach its slot
            factor = d / avail[i]
            args += ["-ss", f"{clip.trim_in}", "-t", f"{avail[i]:.3f}", "-i", src]
            fc.append(f"[{i}:v]setpts={factor:.5f}*PTS,{vf}[c{i}]")

    if len(clips) == 1:
        vprev = "[c0]"
    else:
        vprev, acc = "[c0]", durs[0]
        for i in range(1, len(clips)):
            ov = min(o, durs[i] - 0.05, durs[i - 1] - 0.05)
            off = acc - ov
            fc.append(f"{vprev}[c{i}]xfade=transition=fade:duration={ov:.3f}:offset={off:.3f}[x{i}]")
            vprev = f"[x{i}]"
            acc = off + durs[i]

    args += [
        "-filter_complex", ";".join(fc), "-map", vprev, "-t", f"{duration:.3f}", "-an",
        "-c:v", tgt.vcodec, "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p",
        "-r", str(tgt.fps), "-movflags", "+faststart",
    ]
    return ffmpeg.run(args, dst=dst)


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
