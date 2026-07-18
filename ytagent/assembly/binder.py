"""The script→EditSpec binder. Turns a written Script + its sourced clips + its TTS narration into an
IN-MEMORY EditSpec the assembler consumes (clips path). Narration length drives each beat's duration
(the assembler measures the narration and fits the clip to it); sourced clips fill the slots; asset
paths are absolute so the spec is location-independent (no JSON round-trip).
"""
from __future__ import annotations

import os
import re
from dataclasses import replace as dc_replace

from ..sourcing import to_clip
from .spec import AudioMix, Beat, EditSpec, Target, Transition


def _slug(title: str) -> str:
    return (re.sub(r"[^a-z0-9]+", "-", (title or "video").lower()).strip("-") or "video")[:48]


def bind_edit_spec(script, sourced: dict, narration: dict, *, target: Target | None = None,
                   fade_in: float = 1.5, fade_out: float = 2.0) -> EditSpec:
    """`sourced`: {beat.index → SourcedAsset}; `narration`: {beat.index → narration mp3 path}."""
    tgt = target or Target(fmt="16:9", w=1920, h=1080, fps=24)
    n = len(script.beats)
    beats = []
    for i, b in enumerate(script.beats):
        clip = to_clip(sourced[b.index], approx_seconds=b.approx_seconds)
        clip = dc_replace(clip, src=os.path.abspath(clip.src))    # location-independent
        trans = None if i == n - 1 else Transition(type="xfade", curve="fade", duration=0.8)
        beats.append(Beat(name=f"beat{b.index}", clips=(clip,),
                          narration=os.path.abspath(narration[b.index]), music=None,
                          out_transition=trans))
    return EditSpec(
        id=_slug(getattr(script, "title", "video")), source="clips", targets={tgt.fmt: tgt},
        beats=tuple(beats), audio_mix=AudioMix(), sfx=(), title_card=None,
        fade_in=fade_in, fade_out=fade_out, assets_root="/", active_format=tgt.fmt,
    )
