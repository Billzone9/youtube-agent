"""Subject-terms validator (subject-terms-standard.md) — FLAG, never REJECT.

Decision: polysemy is a SEARCH-QUALITY property, not a correctness one. The lion run proceeded on the
bare term "lion" and still produced a usable film, and the 6c redesign deliberately removed pre-check
gates so that SOURCING decides, not a heuristic. So a bare polysemous term is flagged (warn + suggest a
disambiguation) and the commissioning decision is UNCHANGED. This makes the doctrine visible without a
gate that could block a viable subject.

Pure heuristic, no LLM (no per-commission spend): a bare single-token term in a curated homonym set.
Multi-word / qualified terms ("African lion savanna") are assumed disambiguated and pass clean.
"""
from __future__ import annotations

# Bare single-word animal names known to pull HOMONYMS or the wrong sense in stock search → the
# disambiguated form removes them (subject-terms-standard: "lion" also matched sea lion / statue). A
# starter set; extend as new ambiguous terms surface. Elephant is deliberately ABSENT (unambiguous).
_AMBIGUOUS = {
    "lion": "African lion savanna (wild)",
    "seal": "wild grey seal / harbour seal colony",
    "crane": "wild crane (bird) in wetland",
    "jaguar": "wild jaguar in rainforest",
    "puma": "wild puma / mountain lion",
    "kite": "red kite (bird of prey) in flight",
    "swallow": "barn swallow (bird) in flight",
    "cardinal": "northern cardinal (bird)",
    "turkey": "wild turkey (bird)",
    "buffalo": "African buffalo / wild bison (specify)",
}


def flag_if_ambiguous(term: str) -> dict | None:
    """Advisory only. Returns {"term","reason","suggestion"} for a bare polysemous single-token term,
    else None. NEVER blocks — the caller records it and proceeds; sourcing remains the gate."""
    t = (term or "").strip().lower()
    if not t or " " in t:                       # qualified / multi-word → assumed disambiguated
        return None
    suggestion = _AMBIGUOUS.get(t)
    if suggestion is None:
        return None
    return {"term": term,
            "reason": f"'{term}' is a bare polysemous search term — it also matches other senses "
                      f"(homonyms/captive footage), which thins the sourced pool.",
            "suggestion": suggestion}
