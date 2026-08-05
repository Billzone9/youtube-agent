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

from .script import Fact

# A1 grounded-research HARD CAPS — defined HERE (the enforcement site) and imported by scheduler.cost so
# the estimate is derived from the SAME constants the loop enforces. Kept in authoring (which imports
# nothing from scheduler) to avoid a scheduler↔produce↔grounding import cycle. The estimate is a CEILING:
# hitting a cap is a declared degradation, never more spend (PLAN_PHASE1_COSTS.md).
_RESEARCH_MAX_SEARCHES = 8          # ~6 expected; the cap bounds a stubborn subject
_RESEARCH_MAX_ITERATIONS = 4        # research rounds before we stop and ship partial facts
_RESEARCH_MAX_INPUT_TOKENS = 60_000   # cumulative input ceiling (2× the ~30k expected)
_RESEARCH_MAX_OUTPUT_TOKENS = 6_000


@dataclass(frozen=True)
class SearchOutcome:
    """One provider step. `input_tokens` and `searches` MUST come from the API response's own usage
    (`usage.input_tokens`, `server_tool_use.web_search_requests`) — NOT a guess — because the loop
    enforces the caps against them. A provider that under-reports here is caught by
    `reconcile_research_usage` against the cost ledger (the billed truth)."""
    facts: tuple[Fact, ...] = ()
    input_tokens: int = 0        # from usage.input_tokens (API), not estimated
    searches: int = 1            # from server_tool_use.web_search_requests (API), not assumed
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


class ResearchUnderReport(RuntimeError):
    """A provider spent MORE than it reported — the cap the loop enforced was against self-reported
    figures, so the ceiling was a hope. Caught by reconciling the loop's counted usage against the API's
    ACTUAL usage (billed tokens + server_tool_use.web_search_requests). A defect, not a soft warning."""


def reconcile_research_usage(rf: ResearchFacts, *, actual_input_tokens: int, actual_searches: int,
                            token_tolerance: int = 1_000) -> None:
    """Cross-check the bound. The loop counted what the provider REPORTED; `actual_*` come from the API
    response / cost ledger (the source of truth). If actual meaningfully EXCEEDS reported, the provider
    under-reported and the cap did not really bound the spend → raise. (Actual ≤ reported is fine — the
    estimate is a ceiling.) A small token tolerance absorbs rounding; searches must match exactly (a
    server-side search that reported as 0/1 is exactly the failure this catches)."""
    if actual_searches > rf.searches_used:
        raise ResearchUnderReport(
            f"provider ran {actual_searches} web searches but reported {rf.searches_used} — the search "
            f"cap was against self-reported figures; bound not honoured")
    if actual_input_tokens > rf.input_tokens + token_tolerance:
        raise ResearchUnderReport(
            f"provider billed {actual_input_tokens} input tokens but reported {rf.input_tokens} "
            f"(> {token_tolerance} tolerance) — token bound not honoured")


def gather_grounded_facts(
    subject: str, provider: GroundedProvider, *,
    max_searches: int = _RESEARCH_MAX_SEARCHES,
    max_iterations: int = _RESEARCH_MAX_ITERATIONS,
    max_input_tokens: int = _RESEARCH_MAX_INPUT_TOKENS,
    prior: "ResearchFacts | None" = None,
    on_step=None,
) -> ResearchFacts:
    """Bounded fact-gathering. The caps are enforced BEFORE each search — the loop stops AT a cap, never
    after paying past it. A cap → a `declared` entry + `complete=False`; a natural `done` → `complete=True`.

    RESUME (money-stage idempotency, like TTS): pass `prior` (a partial ResearchFacts reloaded from a
    crashed run) to CONTINUE from its `searches_used`/`input_tokens`/facts — already-done searches are
    never repeated, and because the caps count from the seeded totals, the crash+resume total still
    cannot exceed the ceiling. `on_step(partial)` is called after EACH search so the caller can persist
    progress, so a crash loses at most the in-flight search, not the whole run."""
    facts: list[Fact] = list(prior.facts) if prior else []
    declared: dict = {}
    searches_used = prior.searches_used if prior else 0     # seed from the reloaded run → caps continue
    input_tokens = prior.input_tokens if prior else 0
    complete = False

    remaining_iters = max_iterations - searches_used        # continue within the SAME iteration budget
    for _ in range(max(0, remaining_iters)):
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
        if on_step is not None:                            # persist progress → resume never re-searches
            on_step(ResearchFacts(facts=tuple(facts), declared={}, complete=False,
                                  searches_used=searches_used, input_tokens=input_tokens))
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
