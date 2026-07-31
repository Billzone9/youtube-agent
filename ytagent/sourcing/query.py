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

# Setting words are SEPARATED into three distinct axes (never one bag) — each reaches the queries and
# is judged as its OWN boolean by the vision gate. Conflating them was the defect: a wild snowy wolf at
# midday must not be rejected for a 'dawn' brief, nor on tundra for a 'forest' brief.
_SEASON = {
    "snow", "snowy", "snowfall", "winter", "wintry", "ice", "icy", "frost", "frosty", "frozen",
    "blizzard", "autumn", "fall", "spring", "summer", "monsoon", "wet", "dry",
}
_HABITAT = {
    "forest", "boreal", "taiga", "woodland", "jungle", "rainforest", "tundra", "arctic", "desert",
    "savanna", "savannah", "grassland", "steppe", "mountain", "mountains", "alpine", "coast",
    "coastal", "beach", "ocean", "sea", "underwater", "reef", "river", "lake", "wetland", "swamp",
    "meadow", "prairie", "canyon", "valley",
}
_TIME_OF_DAY = {
    "dawn", "dusk", "twilight", "sunrise", "sunset", "daybreak", "nightfall", "night", "nocturnal",
    "midday", "noon", "morning", "afternoon", "evening", "daytime", "golden hour",
}
# Mood adjectives (cold/dark/warm/misty) are DELIBERATELY not an axis — unjudgeable from a frame, they
# belong nowhere near a pass/fail. They may still colour prose; they never gate.

_AXES = {"season": _SEASON, "habitat": _HABITAT, "time_of_day": _TIME_OF_DAY}


def _axis_terms(text: str, axis: str) -> tuple[str, ...]:
    """The distinct words of one axis present in `text`, in order of first appearance (deduped)."""
    vocab = _AXES[axis]
    out: list[str] = []
    for w in _W.findall(_STAGE_DIR.sub(" ", text or "").lower()):
        if w in vocab and w not in out:
            out.append(w)
    return tuple(out)


def derive_axis_locks(text: str) -> dict[str, tuple[str, ...]]:
    """Which setting axes a beat's narration/label LOCKS (names concretely). Season is treated as
    always-locked by the caller; habitat/time_of_day are locked per-beat ONLY when the text names them
    (the per-beat requiredness rule). Returns {axis: terms} for every axis the text mentions."""
    return {axis: t for axis in _AXES if (t := _axis_terms(text, axis))}


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


def _llm_plan(brief: str, llm) -> tuple[tuple[str, ...], str]:
    """One CHEAP (Haiku) call: prose → (search phrases, subject phrase). Subject is the single thing the
    shot is OF (e.g. 'grey wolf'). When a season is present the model is told MOST phrases must carry it
    (season-blind queries let out-of-season footage dominate the pool). Returns ((),'') on failure.
    (The season/habitat/time AXES are extracted deterministically by axis, not trusted to the model.)"""
    from ..providers.base import CacheableBlock, LLMRequest, ModelTier

    system = (CacheableBlock(
        "From the shot description, return STRICT JSON only: "
        '{"queries": [2-4 short stock-footage search phrases, 2-3 words, concrete nouns, no camera '
        'directions like "wide"/"aerial"/"slow pan". If the shot names a SEASON (snow, winter, summer…), '
        'the MAJORITY of phrases MUST include that season word, e.g. "wolf in snow", "snowy wolf pack"], '
        '"subject": "the single main visual subject in 1-2 words (the animal/thing the shot is OF)"}. '
        'Example: {"queries":["grey wolf snow","snowy wolf pack","wolf in winter forest"],'
        '"subject":"grey wolf"}.'),)
    resp = llm.complete(LLMRequest(tier=ModelTier.CHEAP, system=system,
                                   messages=({"role": "user", "content": _STAGE_DIR.sub(" ", brief)},),
                                   max_tokens=180, purpose="sourcing_query"))
    s = resp.text.strip()
    start, end = s.find("{"), s.rfind("}")
    if start == -1 or end == -1:
        return (), ""
    try:
        d = json.loads(s[start:end + 1])
        queries = tuple(str(x).strip() for x in d.get("queries", []) if str(x).strip())
        subject = " ".join(w for w in _W.findall(str(d.get("subject", "")).lower()) if len(w) > 2)
        return queries[:4], subject
    except Exception:  # noqa: BLE001 — malformed model output → deterministic fallback
        return (), ""


def _must_terms(queries: tuple[str, ...]) -> tuple[str, ...]:
    """The recurring SUBJECT term(s) — a candidate must contain at least one. Tokens appearing in ≥2
    queries (the common thread, e.g. 'penguin'); else the single most-frequent token."""
    from collections import Counter
    counts = Counter(t for q in queries for t in _W.findall(q.lower()) if len(t) > 2)
    recurring = tuple(t for t, n in counts.items() if n >= 2)
    if recurring:
        return recurring
    return (counts.most_common(1)[0][0],) if counts else ()


def _enforce_season_majority(queries: tuple[str, ...], must: tuple[str, ...], season: tuple[str, ...]
                             ) -> tuple[str, ...]:
    """When the brief is SEASON-LOCKED, a STRICT MAJORITY of the final queries must carry the season
    term (Item 2) — a mostly season-blind set lets out-of-season footage dominate the candidate pool.
    Pairs on the SEASON word specifically (not whichever setting word came first)."""
    if not (season and must):
        return queries[:4]
    s = season[0]
    subj = " ".join(must[:2])
    season_q = [q for q in queries if s in q]
    for v in (f"{subj} {s}", f"{s} {subj}", f"{subj} in {s}"):   # top up with subject+season pairings
        if v not in season_q:
            season_q.append(v)
    other_q = [q for q in queries if s not in q]

    n = min(4, max(3, len(queries)))                            # final query count
    need = n // 2 + 1                                            # strict majority must carry season
    final = season_q[:need]
    for q in other_q + season_q:                                # fill remaining slots (originals first)
        if len(final) >= n:
            break
        if q not in final:
            final.append(q)
    return tuple(final[:n])


def build_query_plan(brief: str, *, approx_seconds: int, target_fmt: str, llm=None) -> QueryPlan:
    orientation = _ORIENT.get(target_fmt, "landscape")
    season = _axis_terms(brief, "season")
    habitat = _axis_terms(brief, "habitat")
    time_of_day = _axis_terms(brief, "time_of_day")

    subject_phrase = ""
    if llm is not None:
        queries, subject_phrase = _llm_plan(brief, llm)
    else:
        queries = ()
    if not queries:                       # no LLM, or the call failed → deterministic fallback
        queries = _keywords(brief)

    subject_tokens = tuple(w for w in _W.findall(subject_phrase.lower()) if len(w) > 2)
    must = subject_tokens or _must_terms(queries)   # prefer the LLM subject; else the recurring token
    queries = _enforce_season_majority(queries, must, season)

    return QueryPlan(queries=queries, orientation=orientation, min_seconds=int(approx_seconds or 0),
                     must_terms=must, subject=subject_phrase or (must[0] if must else ""),
                     season=season, habitat=habitat, time_of_day=time_of_day)
