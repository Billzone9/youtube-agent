"""Grounded research — gather EXTERNAL, verified facts a script is built on, with a HARD-BOUNDED loop.

Two properties, both structural:

1. BOUNDED WHERE THE SPEND HAPPENS (not checked after). The caps (searches / iterations / input tokens)
   are the SAME constants the cost estimate uses (`scheduler.cost._RESEARCH_MAX_*`), and they are
   enforced BEFORE each search and each iteration — the loop can never start the search that would
   breach a cap, so a run cannot exceed the quoted ceiling. Hitting a cap is a DECLARED degradation
   (mirroring `AudioDesign.declared`): ship the facts gathered so far, recorded in `declared`.

2. A DEGRADED SET CONSTRAINS THE SCRIPT (accuracy is the house floor). `ResearchFacts.complete` tells
   the writer whether the fact set is whole or PARTIAL. `research_directive()` turns it into the prompt
   block the writer is bound by: list the verified facts, and when partial, forbid backfilling ungrounded
   claims — use sensory/atmospheric description where facts run out, never fabricate. Fewer facts → a
   more descriptive, less claim-dense script, never an invented one.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

from ..scheduler.cost import (_RESEARCH_MAX_INPUT_TOKENS, _RESEARCH_MAX_ITERATIONS,
                              _RESEARCH_MAX_SEARCHES)
from .script import Fact


@dataclass(frozen=True)
class SearchOutcome:
    """One provider step: the facts it found + what it cost + whether the subject is now covered."""
    facts: tuple[Fact, ...] = ()
    input_tokens: int = 0
    searches: int = 1            # searches this step consumed
    done: bool = False           # the provider judges the subject sufficiently researched


@runtime_checkable
class GroundedProvider(Protocol):
    def search(self, subject: str, *, gathered: tuple[Fact, ...]) -> SearchOutcome: ...


@dataclass(frozen=True)
class ResearchFacts:
    facts: tuple[Fact, ...] = ()
    declared: dict = field(default_factory=dict)     # capability→reason; non-empty ⇒ PARTIAL
    complete: bool = True                            # False ⇒ a cap stopped it (partial set)
    searches_used: int = 0
    input_tokens: int = 0

    @property
    def partial(self) -> bool:
        return not self.complete


def gather_grounded_facts(
    subject: str, provider: GroundedProvider, *,
    max_searches: int = _RESEARCH_MAX_SEARCHES,
    max_iterations: int = _RESEARCH_MAX_ITERATIONS,
    max_input_tokens: int = _RESEARCH_MAX_INPUT_TOKENS,
) -> ResearchFacts:
    """Bounded fact-gathering. The caps are enforced BEFORE each search — the loop stops AT a cap, never
    after paying past it. A cap → a `declared` entry + `complete=False`; a natural `done` → `complete=True`."""
    facts: list[Fact] = []
    declared: dict = {}
    searches_used = 0
    input_tokens = 0
    complete = False

    for _ in range(max_iterations):                       # iteration cap: cannot START a run past it
        if searches_used >= max_searches:                 # search cap — checked BEFORE the spend
            declared["research"] = f"capped at {max_searches} searches — partial ({len(facts)} facts)"
            break
        if input_tokens >= max_input_tokens:              # input cap — checked BEFORE the spend
            declared["research"] = f"input cap {max_input_tokens} tokens reached — partial ({len(facts)} facts)"
            break
        out = provider.search(subject, gathered=tuple(facts))   # THE SPEND happens here, after the checks
        searches_used += out.searches
        input_tokens += out.input_tokens
        facts.extend(out.facts)
        if out.done:
            complete = True
            break
    else:                                                 # ran the full iteration budget with no `done`
        declared["research"] = f"reached max {max_iterations} iterations — partial ({len(facts)} facts)"

    return ResearchFacts(facts=tuple(facts), declared=declared, complete=complete,
                         searches_used=searches_used, input_tokens=input_tokens)


def research_directive(rf: ResearchFacts) -> str:
    """The prompt block the ScriptWriter is bound by. Lists the verified facts and, when the set is
    PARTIAL, forbids backfilling ungrounded claims — so a degraded fact set makes the script MORE
    descriptive, never more inventive. No facts at all → an explicit 'work from niche knowledge, do not
    fabricate specifics' instruction (mirrors the existing research-unavailable line)."""
    if not rf.facts:
        return ("GROUNDED FACTS: none were gathered. Do NOT invent statistics, dates, or cite sources. "
                "Write from general niche knowledge and sensory description only.")
    lines = [f"- {f.claim}" for f in rf.facts]
    head = f"GROUNDED FACTS ({len(rf.facts)} verified — every factual claim MUST be supported by these):"
    body = head + "\n" + "\n".join(lines)
    if rf.partial:
        body += ("\n\nThis fact set is PARTIAL (research was capped: "
                 f"{rf.declared.get('research', 'incomplete')}). Do NOT add facts beyond the list to fill "
                 "the gap. Where the facts run out, use sensory, atmospheric description — never assert an "
                 "unverified claim, statistic, or source. Accuracy over completeness.")
    return body
