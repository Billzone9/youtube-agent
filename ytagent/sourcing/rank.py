"""Metadata-only ranking. Honest limit: metadata gives duration/format/tags/title — NOT what the
footage actually looks like. So we score on keyword overlap + orientation + duration + resolution,
and if the best candidate scores below MATCH_THRESHOLD the shot-brief fails loudly (never padded).
Keyword overlap deliberately EXCLUDES the contributor name (a user named "Wildlife"/"Coverr" would
inflate every query).
"""
from __future__ import annotations

import re

from .base import Candidate, QueryPlan

MATCH_THRESHOLD = 0.45   # the must-term SUBJECT filter is the real guard now; the score bar just
#                          needs orientation + basic relevance (0.50 rejected genuine subject-correct
#                          clips — a wolf beat near-missed at 0.49; 0.45 accepts it, still fails the
#                          penguin's 0.44 beach clips). Subject correctness is enforced separately.
_W = re.compile(r"[a-z0-9]+")

# Metadata negative filter (free, before download): only a save-the-download pre-filter now that the
# vision gate's wild_ok makes the real captivity call — so it lists ONLY UNAMBIGUOUS captivity terms.
# Dropped (false-negative risk): 'sanctuary','rescue' (land DESIGNATION — reserves hold wild footage),
# 'farm','corral' (describe land, not the animal), 'pen' (a common ambiguous token). Per-channel
# configurable (channel.config.negative_terms); this is the conservative default.
DEFAULT_NEGATIVE_TERMS = frozenset({
    "zoo", "captive", "captivity", "enclosure", "cage", "caged", "aquarium", "fenced", "leash",
    "circus", "petting", "pet",
})


def _tokens(*texts: str) -> set[str]:
    out: set[str] = set()
    for t in texts:
        out.update(_W.findall((t or "").lower()))
    return out


def score_candidate(c: Candidate, plan: QueryPlan, *, target_w: int, target_h: int,
                    negative_terms=None) -> tuple[float, dict]:
    query_terms = _tokens(" ".join(plan.queries))
    haystack = _tokens(" ".join(c.tags), c.title, c.slug)   # tags + title + url-slug — NOT contributor

    # Hard subject requirement: a candidate that lacks the recurring subject term is disqualified
    # (this is what kills a "chicken" tagged with 'bird'/'chick' when the subject is 'penguin').
    must = set(plan.must_terms)
    if must and not (must & haystack):
        return 0.0, {"disqualified": "missing subject term", "must_terms": sorted(must)}

    # Negative-setting filter: an UNAMBIGUOUS captivity tag disqualifies cheaply (the vision gate makes
    # the nuanced call). Per-channel list; DEFAULT_NEGATIVE_TERMS when None.
    negs = (DEFAULT_NEGATIVE_TERMS if negative_terms is None else frozenset(negative_terms)) & haystack
    if negs:
        return 0.0, {"disqualified": "captive/man-made setting", "negative_terms": sorted(negs)}

    kw = (len(query_terms & haystack) / len(query_terms)) if query_terms else 0.0

    needed = max(3.0, min(float(plan.min_seconds), 15.0))   # clips get trimmed/held; enough for a slot
    if c.duration is None:
        dur = 0.5                                            # unknown duration — neither reward nor punish
    else:
        dur = 1.0 if c.duration >= needed else max(c.duration / needed, 0.0)

    res = 1.0 if (c.width >= target_w and c.height >= target_h) else 0.4

    # Keyword relevance DOMINATES (a zero-keyword clip must not pass on orientation/size alone), and a
    # wrong-orientation clip is nearly useless (it would crop to the wrong subject) → heavy multiplier.
    base = 0.70 * kw + 0.15 * dur + 0.15 * res
    orient_factor = 1.0 if c.orientation == plan.orientation else 0.30
    score = round(base * orient_factor, 4)
    return score, {"keyword": round(kw, 3), "orientation_match": c.orientation == plan.orientation,
                   "duration": round(dur, 3), "resolution": res,
                   "matched_terms": sorted(query_terms & haystack)}


def rank_candidates(cands: list[Candidate], plan: QueryPlan, *, target_w: int, target_h: int,
                    negative_terms=None) -> list[tuple[float, Candidate, dict]]:
    scored: list[tuple[float, Candidate, dict]] = []
    for c in cands:
        s, breakdown = score_candidate(c, plan, target_w=target_w, target_h=target_h,
                                       negative_terms=negative_terms)
        scored.append((s, c, breakdown))
    # sort by score desc; tie-break: higher resolution, then longer duration
    scored.sort(key=lambda t: (t[0], t[1].width * t[1].height, t[1].duration or 0.0), reverse=True)
    return scored
