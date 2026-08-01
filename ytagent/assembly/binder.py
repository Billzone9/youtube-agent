"""The script→EditSpec binder. Turns a written Script + its sourced clips + its TTS narration into an
IN-MEMORY EditSpec the assembler consumes (clips path). Narration length drives each beat's duration
(the assembler measures the narration and fits the clip to it); sourced clips fill the slots; asset
paths are absolute so the spec is location-independent (no JSON round-trip).
"""
from __future__ import annotations

import os
import re
from dataclasses import replace as dc_replace

from .spec import AudioMix, Beat, EditSpec, Sfx, Target, Transition


def _slug(title: str) -> str:
    return (re.sub(r"[^a-z0-9]+", "-", (title or "video").lower()).strip("-") or "video")[:48]


def bind_edit_spec(script, sourced: dict, narration: dict, *, target: Target | None = None,
                   fade_in: float = 1.5, fade_out: float = 2.0, cues: dict | None = None,
                   breathers: dict | None = None, bed: str | None = None,
                   bed_db: float = -30.0, sfx: tuple = ()) -> EditSpec:
    """`sourced`: {beat.index → SourcedAsset | list[SourcedAsset]}; `narration`: {beat.index → mp3}.
    A list gives the beat multiple distinct shots (the visual-density standard); the multi-clip fitter
    splits the narration across them. A lone asset is accepted for back-compat. Audio design (optional):
    `cues` {beat.index → MusicCue} attaches a per-beat score cue; `breathers` {beat.index → seconds}
    gives each beat a trailing music-only breather; `bed`/`sfx` layer the film-wide ambience + SFX."""
    from ..sourcing import to_clip                                # lazy: avoid the sourcing↔assembly cycle

    tgt = target or Target(fmt="16:9", w=1920, h=1080, fps=24)
    cues = cues or {}
    breathers = breathers or {}
    n = len(script.beats)
    beats = []
    for i, b in enumerate(script.beats):
        assets = sourced[b.index]
        assets = list(assets) if isinstance(assets, (list, tuple)) else [assets]
        clips = []
        for a in assets:
            clip = to_clip(a, approx_seconds=b.approx_seconds, cap=len(assets) == 1)
            clips.append(dc_replace(clip, src=os.path.abspath(clip.src)))   # location-independent
        trans = None if i == n - 1 else Transition(type="xfade", curve="fade", duration=0.8)
        # WORDLESS beat (a cold open): no narration mp3 → carry an EXPLICIT declared duration so the
        # fitter/density/audio use it instead of a measured narration length. A breather is meaningless
        # on a wordless beat (it is already all-score), so it never carries one.
        narr = narration.get(b.index)
        beats.append(Beat(name=f"beat{b.index}", clips=tuple(clips),
                          narration=os.path.abspath(narr) if narr else None,
                          duration=None if narr else float(b.approx_seconds),
                          music=cues.get(b.index),
                          breather_s=(float(breathers.get(b.index, 0.0)) if narr else 0.0),
                          out_transition=trans))
    mix = AudioMix(include_bed=bool(bed), bed=os.path.abspath(bed) if bed else None, bed_db=bed_db)
    return EditSpec(
        id=_slug(getattr(script, "title", "video")), source="clips", targets={tgt.fmt: tgt},
        beats=tuple(beats), audio_mix=mix, sfx=tuple(sfx), title_card=None,
        fade_in=fade_in, fade_out=fade_out, assets_root="/", active_format=tgt.fmt,
    )
