"""AI-tell scanner — an ADVISORY quality signal on generated prose.

This is NOT `guard.py`. `guard.py` is a hard publish-gate that refuses internal-artifact leaks;
this scanner FLAGS mechanical "AI tells" so the writer can regenerate or Banks can judge. It NEVER
mutates prose (silently editing would hide the tell and can mangle the voice).

CALIBRATION IS THE WHOLE POINT. The house voice (see `lion-doc-01-narration.md`) is deliberately
dense with em-dashes and rule-of-three cadences — those are the register, not tells. So the scanner
keys on OVERUSE relative to the exemplar's own baseline, plus a few tics the lion never commits
(exclamation marks, "not only… but also", generic explainer openers). Measured lion baseline:
2.50 em-dashes per 100 words, 0 exclamation marks. The acceptance test is that
`scan_tells(<lion narration>).flagged is False`. If it ever flags the lion, the thresholds are
wrong — not the lion. See `house-voice-standard.md`.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

TELLS_THRESHOLDS_VERSION = 1

# Lion narration measures 2.50 em-dashes/100 words; flag only genuine overuse well above the house
# voice. Presence of em-dashes is the register, never a tell.
_EM_DASH_PER_100W_MAX = 4.0

# Tics the lion never commits — any occurrence flags.
_NOT_ONLY_BUT_ALSO = re.compile(r"\bnot only\b[^.!?]*\bbut also\b", re.I)

# Generic explainer openers — checked only against the very start of the text (first ~160 chars).
_GENERIC_OPENERS = (
    "in this video", "in today's video", "we'll explore", "we will explore", "let's dive in",
    "let's take a look", "have you ever wondered", "welcome back", "today we're going to",
    "today we are going to", "join us as we", "in this documentary we",
)

# LLM lexical crutches — ADVISORY counts only (never gate); surfaced for human eyes.
_LEXICAL_CRUTCHES = (
    "delve", "tapestry", "testament to", "nestled", "in conclusion", "it's important to note",
    "it is important to note", "ultimately", "moreover", "furthermore", "a symphony of",
    "when it comes to", "the world of",
)

# Simple rule-of-three proxies — ADVISORY count only (the house voice USES tricola deliberately).
_TRICOLON = (
    re.compile(r"\b\w+,\s+\w+,\s+and\s+\w+\b", re.I),      # "a, b, and c"
    re.compile(r"\bthe\s+\w+,\s+the\s+\w+,\s+(?:and\s+)?the\s+\w+\b", re.I),  # "the x, the y, the z"
)


@dataclass(frozen=True)
class TellReport:
    words: int
    em_dashes: int
    em_dash_per_100w: float
    exclamations: int
    not_only_but_also: int
    generic_openers: tuple[str, ...]
    lexical_crutches: dict[str, int]   # advisory
    tricolon_count: int                # advisory
    flagged: bool
    reasons: tuple[str, ...] = field(default_factory=tuple)
    thresholds_version: int = TELLS_THRESHOLDS_VERSION


def scan_tells(text: str) -> TellReport:
    """Scan prose for mechanical AI tells. Gates on overuse + never-used tics; the rest is advisory."""
    text = text or ""
    words = len(text.split())
    em_dashes = text.count("—")
    per_100 = (em_dashes / words * 100) if words else 0.0
    exclamations = text.count("!")
    nob = len(_NOT_ONLY_BUT_ALSO.findall(text))

    head = text[:160].lower()
    openers = tuple(p for p in _GENERIC_OPENERS if p in head)

    low = text.lower()
    crutches = {c: low.count(c) for c in _LEXICAL_CRUTCHES if c in low}
    tricolon = sum(len(p.findall(text)) for p in _TRICOLON)

    reasons: list[str] = []
    if per_100 > _EM_DASH_PER_100W_MAX:
        reasons.append(f"em-dash overuse: {per_100:.2f}/100w > {_EM_DASH_PER_100W_MAX:.1f} "
                       f"(house baseline ~2.5)")
    if exclamations:
        reasons.append(f"exclamation marks: {exclamations} (documentary register uses none)")
    if nob:
        reasons.append(f"'not only… but also' scaffold: {nob}")
    if openers:
        reasons.append("generic explainer opener: " + ", ".join(f'"{o}"' for o in openers))

    return TellReport(
        words=words, em_dashes=em_dashes, em_dash_per_100w=round(per_100, 2),
        exclamations=exclamations, not_only_but_also=nob, generic_openers=openers,
        lexical_crutches=crutches, tricolon_count=tricolon, flagged=bool(reasons),
        reasons=tuple(reasons),
    )
