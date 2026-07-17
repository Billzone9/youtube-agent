"""The EditSpec — a declarative, format-aware assembly timeline, stored as DATA (JSON).

Channel-general: nothing lion-specific lives here; the lion is one `edit_spec.json`. Format is a
first-class axis (`targets` map) so 9:16 is not an expensive retrofit, and every clip carries a
per-format focal point so a Shorts crop keeps the subject in frame. Asset paths in the JSON are
relative to the spec file's directory.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field, replace


@dataclass(frozen=True)
class Target:
    fmt: str            # "16:9" | "9:16"
    w: int
    h: int
    fps: int
    lufs: float = -14.0
    tp_dbfs: float = -1.0
    vcodec: str = "libx264"
    acodec: str = "aac"
    abitrate_k: int = 192
    asr: int = 48000    # audio sample rate — MUST be forced: loudnorm silently upsamples to 96k,
    #                     which injects broadband high-freq hiss (see house rule in CLAUDE.md)


@dataclass(frozen=True)
class Clip:
    src: str
    trim_in: float = 0.0
    trim_out: float | None = None
    effect: dict | None = None                      # e.g. {"type":"zoompan","z_from":1.0,"z_to":1.08,"pan":"center"}
    focus: dict = field(default_factory=dict)       # {"16:9":[fx,fy], "9:16":[fx,fy]} normalized

    def focus_for(self, fmt: str) -> tuple[float, float]:
        fx, fy = (self.focus.get(fmt) or [0.5, 0.5])
        return float(fx), float(fy)


@dataclass(frozen=True)
class Transition:
    type: str = "xfade"     # "xfade" | "fade" | "none"
    curve: str = "fade"     # xfade transition name
    duration: float = 1.0


@dataclass(frozen=True)
class MusicCue:
    file: str
    in_db: float = -16.0
    fade_in: float = 2.0
    fade_out: float = 3.0


@dataclass(frozen=True)
class Sfx:
    file: str
    beat: str
    at_s: float = 0.0
    level_db: float = -6.0


@dataclass(frozen=True)
class AudioMix:
    narration_db: float = 0.0
    music_db: float = -16.0
    duck: dict = field(default_factory=lambda: {"threshold": 0.05, "ratio": 8, "attack": 5, "release": 300})
    include_bed: bool = False
    bed: str | None = None


@dataclass(frozen=True)
class TitleCard:
    text: str
    style: dict = field(default_factory=dict)
    start_s: float = 0.0
    duration: float = 4.0


@dataclass(frozen=True)
class Beat:
    name: str
    prebaked: str | None = None          # Stage-2 fast input (already carries its mix)
    narration: str | None = None
    music: MusicCue | None = None
    clips: tuple[Clip, ...] = ()
    out_transition: Transition | None = None


@dataclass(frozen=True)
class EditSpec:
    id: str
    source: str                          # "beats" | "clips" — which stage is authoritative
    targets: dict[str, Target]
    beats: tuple[Beat, ...]
    audio_mix: AudioMix
    sfx: tuple[Sfx, ...] = ()
    title_card: TitleCard | None = None
    fade_in: float = 0.0                 # master fade-from-black (video + audio), seconds
    fade_out: float = 0.0                # master fade-to-black (video + audio), seconds
    assets_root: str = "."               # dir the JSON lives in; relative asset paths resolve here
    active_format: str = "16:9"

    @property
    def target(self) -> Target:
        return self.targets[self.active_format]

    def for_format(self, fmt: str) -> "EditSpec":
        if fmt not in self.targets:
            raise KeyError(f"no target for format {fmt!r}; have {list(self.targets)}")
        return replace(self, active_format=fmt)

    def resolve(self, path: str) -> str:
        """Absolute path for an asset referenced (relatively) in the spec."""
        return path if os.path.isabs(path) else os.path.normpath(os.path.join(self.assets_root, path))


def _target(fmt: str, d: dict) -> Target:
    return Target(fmt=fmt, w=d["w"], h=d["h"], fps=d["fps"], lufs=d.get("lufs", -14.0),
                  tp_dbfs=d.get("tp_dbfs", -1.0), vcodec=d.get("vcodec", "libx264"),
                  acodec=d.get("acodec", "aac"), abitrate_k=d.get("abitrate_k", 192),
                  asr=d.get("asr", 48000))


def _clip(d: dict) -> Clip:
    return Clip(src=d["src"], trim_in=d.get("trim_in", 0.0), trim_out=d.get("trim_out"),
                effect=d.get("effect"), focus=d.get("focus", {}))


def _beat(d: dict) -> Beat:
    m = d.get("music")
    t = d.get("out_transition")
    return Beat(
        name=d["name"], prebaked=d.get("prebaked"), narration=d.get("narration"),
        music=MusicCue(**m) if m else None,
        clips=tuple(_clip(c) for c in d.get("clips", [])),
        out_transition=Transition(**t) if t else None,
    )


def load_spec(path: str) -> EditSpec:
    """Load + validate an EditSpec JSON. Asset paths resolve relative to the file's directory."""
    with open(path) as fh:
        d = json.load(fh)
    targets = {fmt: _target(fmt, td) for fmt, td in d["targets"].items()}
    if not targets:
        raise ValueError("edit spec has no targets")
    am = d.get("audio_mix", {})
    tc = d.get("title_card")
    spec = EditSpec(
        id=d["id"], source=d.get("source", "beats"), targets=targets,
        beats=tuple(_beat(b) for b in d["beats"]),
        audio_mix=AudioMix(narration_db=am.get("narration_db", 0.0), music_db=am.get("music_db", -16.0),
                           duck=am.get("duck", AudioMix().duck), include_bed=am.get("include_bed", False),
                           bed=am.get("bed")),
        sfx=tuple(Sfx(**s) for s in d.get("sfx", [])),
        title_card=TitleCard(**tc) if tc else None,
        fade_in=d.get("fade_in", 0.0),
        fade_out=d.get("fade_out", 0.0),
        assets_root=os.path.dirname(os.path.abspath(path)),
        active_format=d.get("default_format", next(iter(targets))),
    )
    _validate(spec)
    return spec


def _validate(spec: EditSpec) -> None:
    if spec.active_format not in spec.targets:
        raise ValueError(f"default_format {spec.active_format!r} not in targets")
    if not spec.beats:
        raise ValueError("edit spec has no beats")
    for b in spec.beats:
        if spec.source == "beats" and not b.prebaked:
            raise ValueError(f"beat {b.name!r}: source='beats' requires a prebaked path")
        if spec.source == "clips" and not b.clips:
            raise ValueError(f"beat {b.name!r}: source='clips' requires clips")
