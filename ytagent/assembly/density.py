"""Visual-density gate — the house cutting standard, enforced structurally (see visual-density-standard.md).

RECONCILED to the LION BENCHMARK (2026-08-01): the target density is the lion film's ACTUAL cut — 17
clips / 7 beats / 394s ≈ 2.4 clips per beat, ~23s average shot — NOT the abstract 10s figure derived
afterwards and never validated. A beat must still cut between multiple DISTINCT clips with NO clip
reused within a video, and the HARD FLOOR that exists because of the wolf remains: **no single clip may
carry a beat** (≥2 clips for any real beat). A shot longer than `LONG_HOLD_S` is FLAGGED for review (not
failed) — the lion's long holds were HAND-cut with movement/slow-mo; a machine-held static portrait
that long reads dead, so long holds want internal-movement footage. This is a GATE run after the binder
and BEFORE the render.

The per-shot slot maths live here so the fitter (`stage1.build_beat_fitted`) and the gate share ONE
definition and can never drift: K clips filling narration length L are laid end-to-end with
`INTRA_XFADE` crossfades, so each shot runs `even_slot(L, K)` seconds.
"""
from __future__ import annotations

import math

from . import ffmpeg

SHOT_MAX_S = 30.0     # HARD ceiling for one shot — past it the render is refused (with ≥2/beat, caps a
#                       ~60s beat at 2 clips). Reconciled from the lion (whose sparsest holds ran ~this).
SHOT_MIN_S = 3.0      # a shot shorter than this reads as a nervous cut (soft floor; fitter caps K)
SHOT_TARGET_S = 23.0  # the house rhythm — the LION's actual average shot (17 clips / 394s ≈ 23.2s)
LONG_HOLD_S = 15.0    # a shot longer than this is FLAGGED for review (soft) — needs internal movement to
#                       sustain the hold honestly (the lion's long holds were hand-cut, not static)
_FLOOR_BEAT_S = 15.0  # a beat longer than this must have ≥2 clips — the HARD FLOOR (the wolf's failure)
INTRA_XFADE = 0.6     # crossfade between shots within a beat (matches stage1.build_beat)


class VisualDensityError(RuntimeError):
    """A cut violates the visual-density standard (a beat carried by too few clips, or a reused clip)."""


def even_slot(length_s: float, k: int) -> float:
    """Seconds each of K crossfaded shots runs to fill `length_s` of beat (Σ slots − overlaps = L)."""
    k = max(int(k), 1)
    return (length_s + (k - 1) * INTRA_XFADE) / k


def min_clips(length_s: float) -> int:
    """The HARD FLOOR — fewest distinct shots a beat needs: never 1 for a real beat (no clip carries a
    beat), and enough that no shot exceeds SHOT_MAX_S."""
    if length_s <= _FLOOR_BEAT_S:
        return 1
    k = max(2, math.ceil(length_s / SHOT_MAX_S))   # ≥2: the wolf's one-clip-per-beat failure is banned
    while even_slot(length_s, k) > SHOT_MAX_S:      # crossfades lengthen each slot slightly — nudge up
        k += 1
    return k


def target_clips(length_s: float) -> int:
    """Preferred shot count at the house rhythm (the lion's ~23s shots); never below the hard floor."""
    return max(min_clips(length_s), round(length_s / SHOT_TARGET_S) or 1)


def film_thresholds(runtime_s: float, n_beats: int) -> dict:
    """Feasibility thresholds as a FUNCTION of the intended film shape, computed at the FILM level from
    the reconciled (lion) density so per-beat rounding doesn't distort them:
      floor  = the HARD minimum shots — ≥2/beat AND enough that no shot exceeds SHOT_MAX_S,
      target = the house-rhythm shots — a cut every ~SHOT_TARGET_S across the film (lion 394s → ~17).
    The wild+correct-species YIELD is FEASIBLE ≥ target, MARGINAL floor ≤ Y < target, INFEASIBLE < floor.
    """
    n = max(int(n_beats), 1)
    beat_len = runtime_s / n
    floor = max(2 * n, math.ceil(runtime_s / SHOT_MAX_S))
    target = max(floor, round(runtime_s / SHOT_TARGET_S))
    return {"runtime_s": round(runtime_s, 1), "n_beats": n, "beat_len_s": round(beat_len, 1),
            "n_min_per_beat": min_clips(beat_len), "n_target_per_beat": max(target_clips(beat_len), 2),
            "floor": floor, "target": target}


def max_beats_for_yield(yield_est: float, beat_len_s: float) -> int:
    """The most beats a pool of `yield_est` wild+correct-species clips sustains at the house rhythm for
    beats of `beat_len_s` — i.e. the film length the footage actually supports."""
    per_beat = beat_len_s / SHOT_TARGET_S            # ~2.4 clips/beat at lion density for a 56s beat
    return int(yield_est / per_beat) if per_beat else 0


def _length(spec, beat, narration_s: dict | None) -> float:
    if narration_s and beat.name in narration_s:
        return float(narration_s[beat.name])
    if beat.narration:
        return float(ffmpeg.probe(spec.resolve(beat.narration))["duration"])
    if beat.duration:                                 # WORDLESS beat (cold open) — declared, not measured
        return float(beat.duration)
    raise VisualDensityError(f"beat {beat.name!r}: no narration or declared duration to measure against")


def assert_visual_density(spec, narration_s: dict | None = None, *, motif_srcs: set | None = None) -> dict:
    """Raise VisualDensityError unless every clips-beat meets the standard. Returns a per-beat report
    on success. `narration_s`: optional {beat.name → seconds} (else measured from each beat.narration).
    `motif_srcs`: clip srcs explicitly allowed to recur (a deliberate motif); default none."""
    if spec.source != "clips":
        return {"skipped": f"source={spec.source!r} (prebaked beats are pre-cut)"}
    motif = motif_srcs or set()
    report, seen, long_holds = {}, {}, []
    for beat in spec.beats:
        L = _length(spec, beat, narration_s)
        k = len(beat.clips)
        need = min_clips(L)
        if k < need:                                          # HARD floor — no clip carries a beat
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
        shot_s = round(even_slot(L, k), 1)
        if shot_s > LONG_HOLD_S:                              # SOFT — flag for review, do not fail
            long_holds.append((beat.name, shot_s))
        report[beat.name] = {"length_s": round(L, 1), "clips": k, "min": need,
                             "target": target_clips(L), "shot_s": shot_s,
                             "long_hold": shot_s > LONG_HOLD_S}
    if long_holds:                                            # surfaced, not raised (needs movement, review)
        report["_long_holds"] = [{"beat": b, "shot_s": s} for b, s in long_holds]
    return report
