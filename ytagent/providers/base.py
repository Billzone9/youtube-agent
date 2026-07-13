"""Provider layer — pure types (spec §4.4: one internal interface, providers swappable by config).

No SDK import, no DB. Cost levers (model routing, prompt caching, batch) are expressed in the REQUEST
type, not at call sites: a call site names a `ModelTier` and marks which system blocks are cacheable;
the concrete provider maps tier→model-id and translates cache markers to the vendor's API. Swapping
providers swaps the map, not the writers.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Protocol, runtime_checkable


class ModelTier(str, Enum):
    CHEAP = "cheap"       # routine/classification (tags) — Haiku
    QUALITY = "quality"   # prose (descriptions, scripts) — Sonnet
    PREMIUM = "premium"   # reserved for where it measurably earns it — Opus (wired, unused)


@dataclass(frozen=True)
class CacheableBlock:
    """A system block. `cache=True` marks the cache breakpoint (vendor prompt caching)."""

    text: str
    cache: bool = False


@dataclass(frozen=True)
class LLMRequest:
    tier: ModelTier
    system: tuple[CacheableBlock, ...]      # stable-prefix-first; cache marker on the last stable block
    messages: tuple[dict, ...]              # volatile per-video content — AFTER the cache breakpoint
    max_tokens: int
    purpose: str                            # "description" | "tags" | "script" — ledger label + audit
    batch: bool = False                     # dispatch hint (the runner decides; the writer doesn't)
    channel_id: int | None = None
    job_id: int | None = None


@dataclass(frozen=True)
class TokenUsage:
    input_tokens: int = 0
    output_tokens: int = 0
    cache_creation_input_tokens: int = 0
    cache_read_input_tokens: int = 0


@dataclass(frozen=True)
class LLMResponse:
    text: str
    model: str
    usage: TokenUsage
    request_id: str            # vendor request id — the ledger idempotency key (llm:{request_id})
    stop_reason: str = ""
    batch_id: str | None = None


@dataclass(frozen=True)
class UsageRecord:
    """What the provider pushes to the sink after a call — the async side drains it to the ledger."""

    purpose: str
    model: str
    tier: ModelTier
    usage: TokenUsage
    request_id: str
    channel_id: int | None = None
    job_id: int | None = None
    batch_id: str | None = None


@runtime_checkable
class UsageSink(Protocol):
    def record(self, rec: UsageRecord) -> None: ...


@runtime_checkable
class LLMProvider(Protocol):
    def complete(self, req: LLMRequest) -> LLMResponse: ...
    def count_tokens(self, req: LLMRequest) -> int: ...
    def submit_batch(self, reqs: list[LLMRequest]) -> str: ...
    def retrieve_batch(self, batch_id: str) -> dict[str, LLMResponse]: ...


class ListUsageSink:
    """A trivial in-memory sink: the sync writer records here; the async runner drains + ledgers it."""

    def __init__(self) -> None:
        self.records: list[UsageRecord] = []

    def record(self, rec: UsageRecord) -> None:
        self.records.append(rec)

    def drain(self) -> list[UsageRecord]:
        out = self.records[:]
        self.records.clear()
        return out
