"""Sourcing — pure types + the swappable stock-provider interface (mirrors ytagent/providers/).

A `Candidate` is the ONE normalized shape both providers map to and that the ranker, gate, and
provenance logger depend on. `SourcedAsset | NoMatch` is the fail-loud return contract: a shot-brief
either resolves to a gate-passed, provenance-logged asset, or a `NoMatch` — never a padded bad clip.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable


class SourcingError(RuntimeError):
    """Loud failure base for the sourcing pipeline."""


def orientation_of(w: int, h: int) -> str:
    if not w or not h:
        return "square"
    r = w / h
    if r > 1.15:
        return "landscape"
    if r < 0.87:
        return "portrait"
    return "square"


@dataclass(frozen=True)
class Candidate:
    source: str                 # 'pexels' | 'pixabay'
    asset_id: str
    page_url: str               # authoritative human page → the provenance URL (never fabricated)
    download_url: str           # chosen rendition file ≥ target res (selected during normalization)
    licence: str                # 'Pexels License' | 'Pixabay Content License'
    width: int
    height: int
    contributor: str | None = None
    duration: float | None = None
    fps: float | None = None
    title: str = ""
    tags: tuple[str, ...] = ()
    raw: dict = field(default_factory=dict)   # verbatim API record — for audit / provenance recovery

    @property
    def orientation(self) -> str:
        return orientation_of(self.width, self.height)

    @property
    def slug(self) -> str:
        """The human-readable tail of the page URL (Pexels puts keywords there)."""
        return self.page_url.rstrip("/").rsplit("/", 1)[-1].replace("-", " ")


@dataclass(frozen=True)
class QueryPlan:
    queries: tuple[str, ...]    # 2-4 search phrases (the only fuzzy, LLM-assisted part)
    orientation: str            # from the target format — DETERMINISTIC
    min_seconds: int            # = beat.approx_seconds — DETERMINISTIC


@dataclass(frozen=True)
class GateResult:
    ok: bool
    probe: dict = field(default_factory=dict)
    noise: object | None = None      # qc.QCResult when the clip has audio, else None (silent = clean)
    reasons: tuple[str, ...] = ()


@dataclass(frozen=True)
class SourcedAsset:
    source: str
    asset_id: str
    local_path: str
    candidate: Candidate
    gate: GateResult
    provenance: dict
    score: float
    cached: bool = False


@dataclass(frozen=True)
class NoMatch:
    """A shot-brief that could not be satisfied — surfaced, never padded."""

    shot_brief_ref: str
    reason: str
    considered: tuple[tuple[float, str], ...] = ()   # (score, asset_id) — why nothing won


@runtime_checkable
class StockProvider(Protocol):
    def name(self) -> str: ...
    async def healthcheck(self) -> bool: ...
    async def search(self, query: str, *, orientation: str, min_duration: int,
                     per_page: int = 15) -> list[Candidate]: ...
    def rate_limit(self) -> dict: ...
