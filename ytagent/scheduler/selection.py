"""Subject selection — pick the next subject a channel should make, NEVER repeating one it has already
made or is mid-flight on, and (Amendment 3) bounding the domain proposal loop so it can't churn probe
cost on unmakeable ideas indefinitely.

`next_subject` returns a SubjectPick. The caller (the runner, 6c) probes the pick and records the
outcome (verdict + pool depth) to channel_subjects — this module only READS that history to decide.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass

from .. import repo

CONSECUTIVE_INFEASIBLE_CAP = 3   # Amendment 3: consecutive infeasible domain proposals before pausing
_PROPOSE_N = 6                   # candidates to ask the LLM for per domain call (dedup then take first)


@dataclass(frozen=True)
class SubjectPick:
    subject: str | None          # the chosen subject, or None when nothing can be offered
    source: str = "pool"         # "pool" | "domain"
    reason: str = ""             # pool | domain | pool_exhausted | cap_reached | no_novel_proposal | needs_llm


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip().lower())


async def next_subject(conn, playbook: dict, *, llm=None) -> SubjectPick:
    """Pick the next subject for a playbook's channel. Order: (1) the explicit `subject_pool`, skipping
    anything already offered/produced; (2) if the pool is exhausted and a `domain` is set, propose fresh
    candidates via the LLM — but ONLY while consecutive infeasible domain proposals stay under the cap.
    Returns a SubjectPick whose `subject` is None (with a reason) when nothing can be offered."""
    channel_id = playbook["channel_id"]
    used = await repo.subjects.used_subjects(conn, channel_id)

    # (1) explicit pool — first novel entry wins (order = Banks's priority)
    for s in (playbook.get("subject_pool") or []):
        if s and _norm(s) not in used:
            return SubjectPick(subject=s, source="pool", reason="pool")

    # (2) domain proposals (bounded)
    domain = (playbook.get("domain") or "").strip()
    if not domain:
        return SubjectPick(subject=None, reason="pool_exhausted")
    if await repo.subjects.trailing_infeasible(conn, channel_id, source="domain") >= CONSECUTIVE_INFEASIBLE_CAP:
        return SubjectPick(subject=None, reason="cap_reached")   # pause + ask Banks (Amendment 3)
    if llm is None:
        return SubjectPick(subject=None, reason="needs_llm")

    for cand in _propose_from_domain(llm, domain, _PROPOSE_N, avoid=used):
        if _norm(cand) not in used:
            return SubjectPick(subject=cand, source="domain", reason="domain")
    return SubjectPick(subject=None, reason="no_novel_proposal")


def _propose_from_domain(llm, domain: str, n: int, *, avoid: set[str]) -> list[str]:
    """One CHEAP LLM call: domain → up to `n` concrete, single-subject candidates (an animal/thing a
    documentary can be built around). Deterministic-fallback-free: on any parse failure returns []."""
    from ..providers.base import CacheableBlock, LLMRequest, ModelTier

    avoid_line = ("Do NOT propose any of these (already made/tried): "
                  + ", ".join(sorted(avoid)) + ".\n") if avoid else ""
    system = CacheableBlock(
        f"Propose {n} distinct, CONCRETE subjects for a nature/wildlife documentary in the domain "
        f"'{domain}'. Each is ONE specific animal or natural subject a film can be built around (e.g. "
        f"'African elephant', 'cheetah', not 'the savanna ecosystem'). Prefer subjects that stock "
        f"footage libraries actually cover. {avoid_line}"
        'Return STRICT JSON only: {"subjects": ["...", "..."]}.')
    try:
        resp = llm.complete(LLMRequest(tier=ModelTier.CHEAP, system=(system,),
                                       messages=({"role": "user", "content": domain},),
                                       max_tokens=200, purpose="subject_proposal"))
        s = resp.text.strip()
        d = json.loads(s[s.find("{"):s.rfind("}") + 1])
        return [str(x).strip() for x in d.get("subjects", []) if str(x).strip()][:n]
    except Exception:  # noqa: BLE001 — a bad proposal call yields nothing; the caller pauses honestly
        return []
