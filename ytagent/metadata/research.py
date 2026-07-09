"""Research seam — the two signals the description standard is written against (doctrine §2).

  * web_trend_research  — "the windshield": rising topics/phrasings from the open web. Available in
    principle now (done in-session for the lion); a runtime provider arrives with Slice 5.
  * youtube_signal_research — "the mirror": the channel's own search terms and what's performing,
    from the YouTube Analytics/Data API. GENUINELY UNAVAILABLE under the current upload-only OAuth
    scope, so it raises CapabilityUnavailable — a typed, honest lock, never empty-data-as-fact.

Honest-degradation rule (doctrine §4): a provider that has nothing returns an explicit
`available=False` ResearchResult; it does NOT return a plausible-looking empty result the writer
could mistake for real signal.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable


class CapabilityUnavailable(RuntimeError):
    """A research capability that needs a scope/integration we don't have yet."""


@dataclass(frozen=True)
class ResearchResult:
    source: str                                   # 'web_trend' | 'youtube_signal'
    available: bool
    keywords: tuple[str, ...] = field(default_factory=tuple)
    notes: str = ""


@runtime_checkable
class ResearchProvider(Protocol):
    def web_trend_research(self, niche: str, topic: str) -> ResearchResult: ...
    def youtube_signal_research(self, channel: dict) -> ResearchResult: ...


class UnavailableResearch:
    """The Layer-1 default: no runtime research provider is wired.

    The windshield honestly reports 'no signals' (the writer must then work from niche knowledge,
    not pretend it researched); the mirror is scope-locked and raises.
    """

    def web_trend_research(self, niche: str, topic: str) -> ResearchResult:
        return ResearchResult(
            source="web_trend", available=False,
            notes="no runtime web/trend provider (Slice 5); authored from in-session research",
        )

    def youtube_signal_research(self, channel: dict) -> ResearchResult:
        raise CapabilityUnavailable(
            "youtube_signal_research requires YouTube Analytics/Data read scope; current OAuth is "
            "upload-only (see spec §14.5 / Layer 2)"
        )
