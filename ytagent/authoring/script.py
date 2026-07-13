"""Footage-led narration script generation.

Mirrors the house reference `lion-doc-01-script.md`: a script is a sequence of BEATS, each pairing a
visual direction with the voice-over, plus a facts-used/accuracy block (fact underneath, poetry on
top). `Script.to_narration()` reproduces the `script.md → narration.md` step in code (clean per-beat
spoken text for TTS).

SLICE-5 SCOPE — `footage=None` ONLY. No footage is sourced yet (Slice 4), so each beat's visual
direction is a SHOT-BRIEF the writer OUTPUTS (the shots to source), never a consumed input. The
`footage` parameter is the visible seam for Slice 4 (bind VO to real clip ids); no binder is built
here. This keeps the script footage-led in *form* without pretending footage exists.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

from ..providers.base import LLMRequest, ModelTier
from .style import STYLE_SPEC_VERSION, compose_style
from .tells import TELLS_THRESHOLDS_VERSION, scan_tells

_MAX_TELL_RETRIES = 2
_WORDS_PER_SECOND = 1.8   # calm narration with pauses/ambience (lion ≈ this, generous headroom)
_STAGE_DIR = re.compile(r"\*\([^)]*\)\*|\([^)]*\)")   # *(beat)* and bare (stage direction)


@dataclass(frozen=True)
class Fact:
    claim: str
    established: bool


@dataclass(frozen=True)
class Beat:
    index: int
    label: str
    shot_brief: str    # desired visuals to source (OUTPUT — footage isn't bound yet)
    vo: str            # narration (may carry sparing stage directions like *(beat)*)
    approx_seconds: int


@dataclass(frozen=True)
class Script:
    title: str
    runtime_target_s: int
    word_target: int
    beats: tuple[Beat, ...]
    facts_used: tuple[Fact, ...]
    provenance: dict = field(default_factory=dict)

    @property
    def word_count(self) -> int:
        return sum(len(b.vo.split()) for b in self.beats)

    def to_narration(self) -> dict[str, str]:
        """Clean spoken text per beat (stage directions stripped) — the generation-ready narration."""
        out: dict[str, str] = {}
        for b in self.beats:
            clean = _STAGE_DIR.sub("", b.vo)
            clean = re.sub(r"\s+", " ", clean).strip()
            out[f"beat{b.index}"] = clean
        return out


def _extract_json(text: str) -> dict:
    s = text.strip()
    if s.startswith("```"):
        s = s.split("```", 2)[1]
        if s.lstrip().startswith("json"):
            s = s.lstrip()[4:]
    start, end = s.find("{"), s.rfind("}")
    if start == -1 or end == -1:
        raise ValueError(f"no JSON object in model output: {text[:200]!r}")
    return json.loads(s[start:end + 1])


def _rules(runtime_s: int, words: int, n_beats: int) -> str:
    return f"""\
TASK: write a short FOOTAGE-LED documentary narration script for one video, in the channel voice.
- Structure as BEATS. Each beat has: a short LABEL; a SHOT-BRIEF describing the visuals to source for
  it (desired shots — footage is not yet sourced, so brief the shots, don't assume specific clips);
  VO (the narration — sparing stage directions like *(beat)* for pauses are allowed); approx_seconds.
- Footage-led: write the VO to what each shot would show; keep beats fittable to real clips.
- Fact underneath, poetry on top: every claim accurate; list facts_used with established=true/false so
  uncertain claims are flagged for approval — never fabricate a fact or invent a statistic.
- Target runtime ~{runtime_s}s; total VO ~{words} words; aim for about {n_beats} beats.
Return STRICT JSON only:
{{"title": str,
  "beats": [{{"label": str, "shot_brief": str, "vo": str, "approx_seconds": int}}],
  "facts_used": [{{"claim": str, "established": bool}}]}}"""


class ScriptWriter:
    """Inject a provider (LLMProvider) and an optional house-script exemplar (text)."""

    def __init__(self, provider, *, exemplar_text: str | None = None) -> None:
        self._p = provider
        self._exemplar = exemplar_text

    def write(self, *, topic: str, channel: dict, research, runtime_target_s: int = 150,
              n_beats: int = 4, footage=None) -> Script:
        if footage is not None:
            raise NotImplementedError("footage-bound scripting arrives with Slice 4; use footage=None")
        # build the voice brief without importing metadata.writer at module load (avoid cycles)
        from ..metadata.writer import build_voice_brief

        brief = build_voice_brief(channel)
        exemplars = [("house narration script", self._exemplar)] if self._exemplar else []
        style = compose_style(brief, exemplars)
        words = int(runtime_target_s * _WORDS_PER_SECOND)
        available = getattr(research, "available", False)
        research_line = (
            "Research signals: none available — write from established niche knowledge; do NOT claim "
            "you researched current trends."
            if not available else f"Research signals (web/trend): {getattr(research, 'notes', '')}"
        )
        user = f"VIDEO SUBJECT: {topic}\n{research_line}"

        data, tell_report = None, None
        for _ in range(_MAX_TELL_RETRIES + 1):
            resp = self._p.complete(LLMRequest(
                tier=ModelTier.QUALITY, system=style.system_prefix(_rules(runtime_target_s, words, n_beats)),
                messages=({"role": "user", "content": user},), max_tokens=2000, purpose="script",
                channel_id=channel.get("id"),
            ))
            data = _extract_json(resp.text)
            all_vo = " ".join(b.get("vo", "") for b in data.get("beats", []))
            tell_report = scan_tells(all_vo)
            if not tell_report.flagged:
                break
            user += ("\nYour previous draft tripped the AI-tell scanner: "
                     + "; ".join(tell_report.reasons) + ". Rewrite avoiding these.")

        beats = tuple(
            Beat(index=i + 1, label=b.get("label", ""), shot_brief=b.get("shot_brief", ""),
                 vo=b.get("vo", ""), approx_seconds=int(b.get("approx_seconds", 0) or 0))
            for i, b in enumerate(data.get("beats", []))
        )
        facts = tuple(
            Fact(claim=f.get("claim", ""), established=bool(f.get("established", False)))
            for f in data.get("facts_used", [])
        )
        provenance = {
            "provider": type(self._p).__name__, "model": getattr(resp, "model", None),
            "style_spec_version": STYLE_SPEC_VERSION,
            "tells_thresholds_version": TELLS_THRESHOLDS_VERSION,
            "tells_flagged": tell_report.flagged if tell_report else None,
            "research_available": bool(available),
        }
        return Script(
            title=data.get("title", topic), runtime_target_s=runtime_target_s, word_target=words,
            beats=beats, facts_used=facts, provenance=provenance,
        )
