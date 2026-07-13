"""LLMWriter — the concrete description Writer (fills the Layer-1 seam).

Implements the existing `metadata.writer.Writer` Protocol: `write(*, video, channel, research) ->
{title, opening, chapters, disclosure, tags}`, which flows UNCHANGED through
`generate_description → assemble_description → guard`. The provider is injected (§4.4 swappable), so
this is not Anthropic-specific. Neutral name on purpose. Not imported by `metadata/__init__.py` —
import it lazily where used, to avoid a cycle with `authoring`.

Cost levers: QUALITY (Sonnet) for prose, CHEAP (Haiku) for tags + chapter labels; the shared cached
style prefix is reused across both calls. The tell-scanner runs on the opening; on a flag the prose
call is retried (never edited). Honest research: when `research.available` is False the model is told
to work from niche knowledge and NOT claim it researched trends.
"""
from __future__ import annotations

import json

from ..authoring.style import STYLE_SPEC_VERSION, compose_style
from ..authoring.tells import TELLS_THRESHOLDS_VERSION, scan_tells
from ..providers.base import LLMRequest, ModelTier
from .chapters import Chapter
from .description import Description
from .writer import build_voice_brief

_MAX_TELL_RETRIES = 2

_PROSE_RULES = """\
TASK: write the public YouTube DESCRIPTION prose for one video, to the channel's standard.
- Open with a keyword-aware first sentence that puts the primary subject in the first ~40 characters
  and earns the click; then one or two engaging paragraphs. Weave keywords naturally — never stuff.
- Length is your judgement for the niche and topic — not a fixed template; typically ~120–220 words.
- End with a SINGLE, graceful one-line disclosure appropriate to an AI-assisted documentary whose
  footage is licensed stock (e.g. "Narration and score are AI-assisted; all footage is licensed stock.").
- NEVER include internal artifacts: filenames, paths, manifest/provenance references, IDs, QC numbers.
Return STRICT JSON only: {"title": str, "opening": str, "disclosure": str}. `opening` is the prose
BEFORE chapters (the paragraphs); do not include a chapter list or the disclosure inside `opening`."""

_TAGS_RULES = """\
TASK: propose YouTube SEO TAGS for this video. Return STRICT JSON: {"tags": [str, ...]}.
- ~12–15 tags: a few strong core terms + mostly specific, lower-competition long-tail phrases a small
  channel can rank for, matching the tone. Avoid bare high-competition heads alone.
- Accurate only — no claims the video doesn't support (e.g. do not tag "4k" unless told it is 4K)."""

_LABELS_RULES = """\
TASK: author one short, evocative CHAPTER LABEL per timestamp for this video (in order). Labels are
audience-facing navigation — no internal beat numbers, no runtime hints. Return STRICT JSON:
{"labels": [str, ...]} with exactly one label per provided timestamp, in order."""


def _extract_json(text: str) -> dict:
    """Parse the first JSON object in the model output (tolerates code fences / stray prose)."""
    s = text.strip()
    if s.startswith("```"):
        s = s.split("```", 2)[1]
        if s.lstrip().startswith("json"):
            s = s.lstrip()[4:]
    start, end = s.find("{"), s.rfind("}")
    if start == -1 or end == -1:
        raise ValueError(f"no JSON object in model output: {text[:200]!r}")
    return json.loads(s[start:end + 1])


def _render_exemplar(exemplar: Description | None) -> list[tuple[str, str]]:
    if exemplar is None:
        return []
    body = (
        f"Title: {exemplar.title}\n\n{exemplar.description}\n\n"
        f"Tags: {', '.join(exemplar.tags)}"
    )
    return [("a strong prior description (match this register, not its subject)", body)]


class LLMWriter:
    """Satisfies metadata.writer.Writer. Inject a provider (LLMProvider) and an optional exemplar."""

    def __init__(self, provider, *, exemplar: Description | None = None) -> None:
        self._p = provider
        self._exemplar = exemplar
        self.last_run: dict = {}   # provenance the caller stamps into video_metadata.research_notes

    def write(self, *, video: dict, channel: dict, research) -> dict:
        brief = build_voice_brief(channel)
        style = compose_style(brief, _render_exemplar(self._exemplar))
        topic = video.get("topic") or video.get("title") or ""
        available = getattr(research, "available", False)
        research_line = (
            "Research signals: none available — write from established niche knowledge; do NOT claim "
            "you researched current trends."
            if not available else
            f"Research signals (web/trend): {getattr(research, 'notes', '')}"
        )
        facts = video.get("facts") or ""
        user = (
            f"VIDEO SUBJECT: {topic}\n"
            f"{research_line}\n"
            + (f"Established facts to honour (accurate only): {facts}\n" if facts else "")
        )

        # --- prose (QUALITY), retried on an AI-tell flag ---
        prose, tell_report = None, None
        for _ in range(_MAX_TELL_RETRIES + 1):
            resp = self._p.complete(LLMRequest(
                tier=ModelTier.QUALITY, system=style.system_prefix(_PROSE_RULES),
                messages=({"role": "user", "content": user},), max_tokens=1024,
                purpose="description", channel_id=channel.get("id"),
            ))
            prose = _extract_json(resp.text)
            tell_report = scan_tells(prose.get("opening", ""))
            if not tell_report.flagged:
                break
            user += ("\nYour previous draft tripped the AI-tell scanner: "
                     + "; ".join(tell_report.reasons) + ". Rewrite avoiding these.")

        # --- tags (CHEAP) ---
        tags_resp = self._p.complete(LLMRequest(
            tier=ModelTier.CHEAP, system=style.system_prefix(_TAGS_RULES),
            messages=({"role": "user", "content": user},), max_tokens=400, purpose="tags",
            channel_id=channel.get("id"),
        ))
        tags = tuple(_extract_json(tags_resp.text).get("tags", []))

        # --- chapters: author LABELS over REAL timestamps the caller supplied; else omit ---
        chapters = self._author_chapters(video, style, channel)

        self.last_run = {
            "provider": type(self._p).__name__,
            "model_quality": getattr(resp, "model", None),
            "style_spec_version": STYLE_SPEC_VERSION,
            "tells_thresholds_version": TELLS_THRESHOLDS_VERSION,
            "tells_flagged": tell_report.flagged if tell_report else None,
            "research_available": bool(available),
        }
        return {
            "title": prose.get("title", ""),
            "opening": prose.get("opening", ""),
            "disclosure": prose.get("disclosure", ""),
            "chapters": chapters,
            "tags": tags,
        }

    def _author_chapters(self, video: dict, style, channel: dict):
        """`video['beats']` = [{start_seconds:int, hint:str}] from a real cut → author labels.
        Absent (a brand-new, uncut video) → return None so the description omits chapters."""
        beats = video.get("beats")
        if not beats:
            return None
        lines = "\n".join(f"- {int(b['start_seconds'])}s: {b.get('hint','')}" for b in beats)
        resp = self._p.complete(LLMRequest(
            tier=ModelTier.CHEAP, system=style.system_prefix(_LABELS_RULES),
            messages=({"role": "user", "content": f"Timestamps and beat hints:\n{lines}"},),
            max_tokens=300, purpose="tags", channel_id=channel.get("id"),
        ))
        labels = _extract_json(resp.text).get("labels", [])
        if len(labels) != len(beats):
            return None   # honest: mismatched labels → omit rather than mis-navigate
        return [Chapter(str(lbl), int(b["start_seconds"])) for lbl, b in zip(labels, beats)]
