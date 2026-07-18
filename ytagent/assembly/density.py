"""Visual-density gate — the house cutting standard, enforced structurally (see visual-density-standard.md).

A beat must cut between multiple DISTINCT clips (a fresh shot every ~8-15s), never one clip stretched
or looped past ~15s, and no clip may be reused within a video (except a declared motif). Calibrated to
the lion film (17 clips / 7 beats). This is a GATE, not advice: `assert_visual_density` runs after the
binder builds the spec and BEFORE the render, so a too-sparse cut fails loud without wasting render time.

The per-shot slot maths live here so the fitter (`stage1.build_beat_fitted`) and the gate share ONE
definition and can never drift: K clips filling narration length L are laid end-to-end with
`INTRA_XFADE` crossfades, so each shot runs `even_slot(L, K)` seconds.
"""
from __future__ import annotations

import math

from . import ffmpeg

SHOT_MAX_S = 15.0     # a single shot must not exceed this — past it, the eye reads a held/looped clip
SHOT_MIN_S = 3.0      # a shot shorter than this reads as a nervous cut (soft floor; fitter caps K)
SHOT_TARGET_S = 10.0  # the house rhythm — aim a shot change about this often (lion avg ~10-11s)
INTRA_XFADE = 0.6     # crossfade between shots within a beat (matches stage1.build_beat)


class VisualDensityError(RuntimeError):
    """A cut violates the visual-density standard (too few clips, a shot too long, or a reused clip)."""


def even_slot(length_s: float, k: int) -> float:
    """Seconds each of K crossfaded shots runs to fill `length_s` of beat (Σ slots − overlaps = L)."""
    k = max(int(k), 1)
    return (length_s + (k - 1) * INTRA_XFADE) / k


def min_clips(length_s: float) -> int:
    """Fewest distinct shots a beat of `length_s` needs so no shot exceeds SHOT_MAX_S."""
    if length_s <= SHOT_MAX_S:
        return 1
    k = math.ceil(length_s / SHOT_MAX_S)
    while even_slot(length_s, k) > SHOT_MAX_S:   # crossfades lengthen each slot slightly — nudge up
        k += 1
    return k


def target_clips(length_s: float) -> int:
    """Preferred shot count for the house ~10s rhythm (never below the hard minimum)."""
    return max(min_clips(length_s), round(length_s / SHOT_TARGET_S) or 1)


def _length(spec, beat, narration_s: dict | None) -> float:
    if narration_s and beat.name in narration_s:
        return float(narration_s[beat.name])
    if beat.narration:
        return float(ffmpeg.probe(spec.resolve(beat.narration))["duration"])
    raise VisualDensityError(f"beat {beat.name!r}: no narration to measure beat length against")


def assert_visual_density(spec, narration_s: dict | None = None, *, motif_srcs: set | None = None) -> dict:
    """Raise VisualDensityError unless every clips-beat meets the standard. Returns a per-beat report
    on success. `narration_s`: optional {beat.name → seconds} (else measured from each beat.narration).
    `motif_srcs`: clip srcs explicitly allowed to recur (a deliberate motif); default none."""
    if spec.source != "clips":
        return {"skipped": f"source={spec.source!r} (prebaked beats are pre-cut)"}
    motif = motif_srcs or set()
    report, seen = {}, {}
    for beat in spec.beats:
        L = _length(spec, beat, narration_s)
        k = len(beat.clips)
        need = min_clips(L)
        if k < need:
            raise VisualDensityError(
                f"beat {beat.name!r}: {L:.1f}s of narration needs ≥{need} distinct clips "
                f"(~{target_clips(L)} for the house rhythm) but has {k} — a shot would hold "
                f"{even_slot(L, max(k,1)):.1f}s > {SHOT_MAX_S:.0f}s. Source more distinct footage.")
        for c in beat.clips:                                  # no clip reused across the video
            if c.src not in motif:
                prev = seen.get(c.src)
                if prev is not None and prev != beat.name:
                    raise VisualDensityError(
                        f"clip {c.src!r} reused in beats {prev!r} and {beat.name!r} — no reuse within "
                        f"a video except a declared motif.")
                seen[c.src] = beat.name
        report[beat.name] = {"length_s": round(L, 1), "clips": k, "min": need,
                             "target": target_clips(L), "shot_s": round(even_slot(L, k), 1)}
    return report
