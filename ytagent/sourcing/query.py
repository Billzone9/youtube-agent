"""Shot-brief (prose) → a search plan. Orientation and min-duration are DETERMINISTIC (they come from
the target format and the beat's runtime — never ask the LLM for them). Only the fuzzy part —
prose → 2-4 keyword search phrases — optionally uses a cheap Haiku call, with a deterministic
keyword fallback so the slice degrades honestly without an LLM key.
"""
from __future__ import annotations

import json
import re

from .base import QueryPlan

_STAGE_DIR = re.compile(r"\*\([^)]*\)\*|\([^)]*\)")   # mirrors authoring/script._STAGE_DIR
_W = re.compile(r"[a-z][a-z-]+")
_ORIENT = {"16:9": "landscape", "9:16": "portrait"}

# Camera/framing + generic prose words to drop; SUBJECT nouns are kept.
_STOP = {
    "wide", "aerial", "sweeping", "ground", "level", "shot", "slow", "pan", "close", "closeup",
    "medium", "cut", "reveal", "frame", "view", "angle", "tilt", "zoom", "footage", "clip", "scene",
    "the", "a", "an", "and", "or", "of", "in", "on", "at", "to", "from", "into", "under", "over",
    "with", "then", "perhaps", "above", "below", "across", "against", "beginning", "still", "very",
    "no", "up", "its", "his", "her", "their", "first", "single", "one", "some", "more", "most",
    "faint", "dimming", "featureless", "vast", "dense", "small", "lone", "dark", "cold", "warm",
    "seen", "showing", "visible", "possible", "distant", "far", "near", "toward", "towards",
    "standing", "pressed", "together", "stretching", "colour", "color", "sky", "air", "light",
}


def _keywords(brief: str) -> tuple[str, ...]:
    """Deterministic fallback: keep subject words, prefer adjacent-noun bigrams, cap at 4 phrases."""
    text = _STAGE_DIR.sub(" ", brief).lower()
    words = [w for w in _W.findall(text) if w not in _STOP and len(w) > 2]
    phrases: list[str] = []
    seen: set[str] = set()
    for a, b in zip(words, words[1:]):        # adjacent kept-word bigrams (concrete subjects)
        p = f"{a} {b}"
        if p not in seen:
            seen.add(p)
            phrases.append(p)
        if len(phrases) >= 3:
            break
    if words and words[0] not in " ".join(phrases):
        phrases.append(words[0])
    return tuple(phrases[:4]) or (("footage",) if not words else (words[0],))


def _llm_queries(brief: str, llm) -> tuple[str, ...]:
    """One CHEAP (Haiku) call: prose → JSON list of 2-4 concrete search phrases."""
    from ..providers.base import CacheableBlock, LLMRequest, ModelTier

    system = (CacheableBlock(
        "Extract 2-4 short STOCK-FOOTAGE search phrases (2-3 words each: concrete subjects/nouns, "
        "no camera directions like 'wide'/'aerial'/'slow pan') from the shot description. "
        'Return STRICT JSON only: a list of strings, e.g. ["emperor penguin","ice shelf"].'),)
    resp = llm.complete(LLMRequest(tier=ModelTier.CHEAP, system=system,
                                   messages=({"role": "user", "content": _STAGE_DIR.sub(" ", brief)},),
                                   max_tokens=120, purpose="sourcing_query"))
    s = resp.text.strip()
    start, end = s.find("["), s.rfind("]")
    if start == -1 or end == -1:
        return _keywords(brief)
    try:
        qs = [str(x).strip() for x in json.loads(s[start:end + 1]) if str(x).strip()]
    except Exception:  # noqa: BLE001 — malformed model output → deterministic fallback
        return _keywords(brief)
    return tuple(qs[:4]) or _keywords(brief)


def build_query_plan(brief: str, *, approx_seconds: int, target_fmt: str, llm=None) -> QueryPlan:
    orientation = _ORIENT.get(target_fmt, "landscape")
    queries = _llm_queries(brief, llm) if llm is not None else _keywords(brief)
    return QueryPlan(queries=queries, orientation=orientation, min_seconds=int(approx_seconds or 0))
