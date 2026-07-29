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
    "faint", "dimming", "featureless", "vast", "dense", "small", "lone", "seen", "showing", "visible",
    "possible", "distant", "far", "near", "toward", "towards", "standing", "pressed", "together",
    "stretching", "colour", "color", "sky", "air", "light",
}

# Season/setting words are NOT dropped (they must reach the queries so wintery footage surfaces) and
# double as vision-gate season expectations. NOTE: removed from _STOP above ('cold','dark','warm').
_SETTING = {
    "snow", "snowy", "snowfall", "winter", "wintry", "ice", "icy", "frost", "frozen", "blizzard",
    "dusk", "dawn", "twilight", "night", "sunset", "sunrise", "autumn", "spring", "summer", "rain",
    "desert", "forest", "boreal", "tundra", "arctic", "mountain", "coast", "ocean", "underwater",
    "cold", "dark", "warm", "misty", "fog", "foggy",
}


def _setting_terms(brief: str) -> tuple[str, ...]:
    """Season/setting words present in the brief (snow/winter/dusk/…) — reach queries + vision expect."""
    toks = [w for w in _W.findall(_STAGE_DIR.sub(" ", brief).lower()) if w in _SETTING]
    out: list[str] = []
    for t in toks:
        if t not in out:
            out.append(t)
    return tuple(out)


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


def _llm_plan(brief: str, llm) -> tuple[tuple[str, ...], str, tuple[str, ...]]:
    """One CHEAP (Haiku) call: prose → (search phrases, subject phrase, setting terms). Subject is the
    single thing the shot is OF (e.g. 'grey wolf'); setting is the season/place (e.g. ['snow','winter'])
    so wintery footage surfaces and the vision gate knows what to expect. Returns ((),'',()) on failure."""
    from ..providers.base import CacheableBlock, LLMRequest, ModelTier

    system = (CacheableBlock(
        "From the shot description, return STRICT JSON only: "
        '{"queries": [2-4 short stock-footage search phrases, 2-3 words, concrete nouns, no camera '
        'directions like "wide"/"aerial"/"slow pan"; where the shot has a season/setting, include it in '
        'at least one phrase e.g. "wolf in snow"], "subject": "the single main visual subject in 1-2 '
        'words (the animal/thing the shot is OF)", "setting": ["season/place words like snow, winter, '
        'dusk, forest — [] if none"]}. '
        'Example: {"queries":["grey wolf snow","wolf pack winter forest"],"subject":"grey wolf",'
        '"setting":["snow","winter"]}.'),)
    resp = llm.complete(LLMRequest(tier=ModelTier.CHEAP, system=system,
                                   messages=({"role": "user", "content": _STAGE_DIR.sub(" ", brief)},),
                                   max_tokens=180, purpose="sourcing_query"))
    s = resp.text.strip()
    start, end = s.find("{"), s.rfind("}")
    if start == -1 or end == -1:
        return (), "", ()
    try:
        d = json.loads(s[start:end + 1])
        queries = tuple(str(x).strip() for x in d.get("queries", []) if str(x).strip())
        subject = " ".join(w for w in _W.findall(str(d.get("subject", "")).lower()) if len(w) > 2)
        setting = tuple(str(x).strip().lower() for x in d.get("setting", []) if str(x).strip())
        return queries[:4], subject, setting
    except Exception:  # noqa: BLE001 — malformed model output → deterministic fallback
        return (), "", ()


def _must_terms(queries: tuple[str, ...]) -> tuple[str, ...]:
    """The recurring SUBJECT term(s) — a candidate must contain at least one. Tokens appearing in ≥2
    queries (the common thread, e.g. 'penguin'); else the single most-frequent token."""
    from collections import Counter
    counts = Counter(t for q in queries for t in _W.findall(q.lower()) if len(t) > 2)
    recurring = tuple(t for t, n in counts.items() if n >= 2)
    if recurring:
        return recurring
    return (counts.most_common(1)[0][0],) if counts else ()


def build_query_plan(brief: str, *, approx_seconds: int, target_fmt: str, llm=None) -> QueryPlan:
    orientation = _ORIENT.get(target_fmt, "landscape")
    subject_phrase, setting = "", _setting_terms(brief)
    if llm is not None:
        queries, subject_phrase, llm_setting = _llm_plan(brief, llm)
        setting = tuple(dict.fromkeys(setting + llm_setting))   # union, brief-derived first, deduped
    else:
        queries = ()
    if not queries:                       # no LLM, or the call failed → deterministic fallback
        queries = _keywords(brief)

    subject_tokens = tuple(w for w in _W.findall(subject_phrase.lower()) if len(w) > 2)
    must = subject_tokens or _must_terms(queries)   # prefer the LLM subject; else the recurring token

    # Guarantee at least one query pairs subject + a setting term, so wintery/in-season footage surfaces
    # (the vision gate is the hard check, but a season-blind query set rarely returns any in-season clip).
    if setting and must:
        pair = f"{' '.join(must[:2])} {setting[0]}"
        if pair not in queries:
            queries = (queries + (pair,))[:4]

    return QueryPlan(queries=queries, orientation=orientation, min_seconds=int(approx_seconds or 0),
                     must_terms=must, subject=subject_phrase or (must[0] if must else ""), setting=setting)
