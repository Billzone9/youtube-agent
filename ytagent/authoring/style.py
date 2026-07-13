"""The style spec — the house voice as a reusable, channel-general prompt artifact.

`compose_style(voice_brief, exemplars)` merges channel-general craft rules + the banned-tics list
(this file) with the per-channel `VoiceBrief` (from config) and the channel's few-shot exemplars,
into a `StyleSpec` the writers turn into cacheable system blocks. The lion voice never appears here —
it enters only as a `VoiceBrief` (config) + registered exemplar text (data). See `house-voice-standard.md`.
"""
from __future__ import annotations

from dataclasses import dataclass

from ..providers.base import CacheableBlock

STYLE_SPEC_VERSION = 1

# §1 — the positive register (channel-general craft; the *voice* comes from the per-channel brief).
POSITIVE_REGISTER = """\
You write documentary narration and prose in a matured, unhurried, vintage-documentary register:
poetic on the surface, accurate underneath. Follow these craft rules (the specific VOICE is set by
the channel brief below — adopt it, do not default to any one channel's flavour):
- Write to the footage: every line earns its place beside a shot; prefer the concrete, seen detail
  over abstraction. The words serve the picture.
- Fact underneath, poetry on top: every claim must be accurate and defensible; lyricism heightens a
  truth, never invents one. Flag anything uncertain rather than smoothing it over.
- Earn cadence, don't manufacture it: repetition, the short sentence, the held pause arise from
  meaning — tools of emphasis, not a template to fill.
- Restraint: the plain sentence and the silence are instruments; not every line needs ornament.
- Match the channel's voice from its brief; do not import another channel's imagery or diction."""

# §2 — the negative constraints. Kept in step with ytagent/authoring/tells.py (which measures them).
BANNED_TICS = """\
Avoid these mechanical "AI tells" — they mark machine-made prose:
- No exclamation marks (the documentary register uses none).
- No "not only … but also" scaffolding.
- No generic explainer openers: "In this video…", "we'll explore", "Have you ever wondered",
  "Welcome back", "today we're going to", "let's dive in".
- Do not manufacture rule-of-three lists as filler; a triad must carry meaning, not decorate. (The
  house voice DOES use deliberate tricola — the test is meaning, not the device.)
- Avoid LLM lexical crutches: "delve", "tapestry", "testament to", "nestled", "it's important to
  note", "ultimately", "moreover"/"furthermore" as connective filler, "a symphony of", "when it
  comes to".
- Em-dashes are welcome as the house voice uses them — but do not lean on them as a tic on every
  line; vary your punctuation.
- No tacked-on morals or summaries ("in conclusion", "ultimately this shows"). Show; don't explain."""


@dataclass(frozen=True)
class StyleSpec:
    version: int
    house_rules: str                        # global, byte-identical across channels (cacheable prefix)
    voice_brief: str                        # per-channel rendered brief (last stable block → cache mark)
    exemplars: tuple[tuple[str, str], ...]  # (label, text) few-shot references, per-channel

    def system_prefix(self, task_rules: str) -> tuple[CacheableBlock, ...]:
        """The ordered, cacheable system blocks: global rules → task rules → exemplars → voice brief.
        Volatile per-video content goes in the request's `messages`, AFTER this prefix. The cache
        breakpoint is the last stable block (the voice brief)."""
        blocks: list[CacheableBlock] = [
            CacheableBlock(self.house_rules),
            CacheableBlock(task_rules),
        ]
        for label, text in self.exemplars:
            blocks.append(CacheableBlock(f"# Reference exemplar — {label}\n{text}"))
        blocks.append(CacheableBlock(self.voice_brief, cache=True))
        return tuple(blocks)


def _render_brief(voice_brief) -> str:
    vb = voice_brief
    kw = ", ".join(vb.seed_keywords) if vb.seed_keywords else "(none)"
    return (
        "# Channel voice brief (adopt this voice)\n"
        f"- Niche: {vb.niche}\n"
        f"- Purpose: {vb.purpose}\n"
        f"- Tone: {vb.tone}\n"
        f"- Narrator style: {vb.style}\n"
        f"- Language: {vb.primary_language}\n"
        f"- Seed keywords: {kw}"
    )


def compose_style(voice_brief, exemplars: list[tuple[str, str]] | None = None) -> StyleSpec:
    """Assemble a StyleSpec from the per-channel VoiceBrief + optional (label, text) exemplars."""
    house = f"{POSITIVE_REGISTER}\n\n{BANNED_TICS}"
    return StyleSpec(
        version=STYLE_SPEC_VERSION,
        house_rules=house,
        voice_brief=_render_brief(voice_brief),
        exemplars=tuple(exemplars or ()),
    )
