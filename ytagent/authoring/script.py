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

_MAX_RETRIES = 2
_WPM_TARGET = 130         # calm, unhurried narration — the house pace (see house-voice-standard.md)
_WPM_MAX = 140            # enforced per-beat upper bound; faster than this reads hurried
_STAGE_DIR = re.compile(r"\*\([^)]*\)\*|\([^)]*\)")   # *(beat)* and bare (stage direction) — NOT spoken


def _spoken(vo: str) -> str:
    """The spoken words only — stage directions like *(beat)* removed (they don't count toward pace)."""
    return re.sub(r"\s+", " ", _STAGE_DIR.sub("", vo)).strip()


def _pacing_violations(beats_raw: list[dict]) -> list[tuple[int, float, int, int]]:
    """Beats whose spoken VO exceeds the pace cap: (index, wpm, word_budget, approx_seconds)."""
    bad: list[tuple[int, float, int, int]] = []
    for i, b in enumerate(beats_raw):
        sec = int(b.get("approx_seconds", 0) or 0)
        if sec <= 0:
            continue
        spoken = len(_spoken(b.get("vo", "")).split())
        wpm = spoken / (sec / 60)
        if wpm > _WPM_MAX:
            bad.append((i, wpm, int(sec / 60 * _WPM_MAX), sec))
    return bad


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

    @property
    def spoken_words(self) -> int:
        return len(_spoken(self.vo).split())

    @property
    def wpm(self) -> float:
        return self.spoken_words / (self.approx_seconds / 60) if self.approx_seconds else 0.0


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
        return sum(b.spoken_words for b in self.beats)

    def to_narration(self) -> dict[str, str]:
        """Clean spoken text per beat (stage directions stripped) — the generation-ready narration."""
        return {f"beat{b.index}": _spoken(b.vo) for b in self.beats}


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
- PACE IS PART OF THE VOICE — calm and unhurried, ~{_WPM_TARGET} words per minute of narration, never
  above {_WPM_MAX}. For each beat, keep the SPOKEN VO within its approx_seconds at that rate: about
  {_WPM_TARGET}/60 ≈ 2.2 spoken words per second (e.g. a 40s beat ≈ 85–90 words, a 45s beat ≈ 95–100).
  Do not pad to fill time; let the *(beat)* pauses and the footage breathe. Stage directions like
  *(beat)* are not spoken and do not count toward the word budget.
- Target runtime ~{runtime_s}s; total SPOKEN VO ~{words} words; aim for about {n_beats} beats.
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
        words = int(runtime_target_s / 60 * _WPM_TARGET)
        available = getattr(research, "available", False)
        research_line = (
            "Research signals: none available — write from established niche knowledge; do NOT claim "
            "you researched current trends."
            if not available else f"Research signals (web/trend): {getattr(research, 'notes', '')}"
        )
        user = f"VIDEO SUBJECT: {topic}\n{research_line}"

        # Regenerate on an AI-tell flag OR a pacing overrun (a hurried beat breaks the voice), same
        # bounded-retry pattern for both.
        data, tell_report, pacing = None, None, []
        for _ in range(_MAX_RETRIES + 1):
            resp = self._p.complete(LLMRequest(
                tier=ModelTier.QUALITY, system=style.system_prefix(_rules(runtime_target_s, words, n_beats)),
                messages=({"role": "user", "content": user},), max_tokens=2000, purpose="script",
                channel_id=channel.get("id"),
            ))
            data = _extract_json(resp.text)
            beats_raw = data.get("beats", [])
            tell_report = scan_tells(" ".join(_spoken(b.get("vo", "")) for b in beats_raw))
            pacing = _pacing_violations(beats_raw)
            if not tell_report.flagged and not pacing:
                break
            problems = []
            if tell_report.flagged:
                problems.append("AI tells — " + "; ".join(tell_report.reasons))
            if pacing:
                problems.append(
                    f"too fast (keep ≤{_WPM_MAX} wpm) — " + "; ".join(
                        f"beat {i + 1} at {w:.0f} wpm, trim to ≤{bud} spoken words for its {sec}s"
                        for i, w, bud, sec in pacing))
            user += ("\nYour previous draft had problems: " + " | ".join(problems)
                     + ". Rewrite: keep the calm pace and the deliberate *(beat)* pauses, and SHORTEN "
                       "over-long beats rather than speeding up.")

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
            "wpm_target": _WPM_TARGET, "wpm_max": _WPM_MAX, "pacing_ok": not pacing,
            "research_available": bool(available),
        }
        return Script(
            title=data.get("title", topic), runtime_target_s=runtime_target_s, word_target=words,
            beats=beats, facts_used=facts, provenance=provenance,
        )
