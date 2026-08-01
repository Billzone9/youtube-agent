"""Music + SFX generation — pure types + the provider interface. Kept separate from ytagent/providers/
(LLM-token-shaped) and mirrors ytagent/tts/: per-second audio generation with a credits cost model.
Channel-general — nothing niche lives here; a film's cue prompts are DATA passed by the conductor.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable


class MusicUnavailable(RuntimeError):
    """No music provider is configured (no key) — the caller degrades honestly (ships without score)."""


class MusicScopeError(RuntimeError):
    """The API rejected the request (401/403) — the key lacks the Music (or Sound-Generation) scope.
    A spend-capability change is human-only (add the scope / a scoped key in the dashboard)."""


@dataclass(frozen=True)
class MusicResult:
    path: str
    seconds: float
    credits_est: float          # ElevenLabs bills asynchronously — this is an ESTIMATE (15 cr/s music)
    model: str
    kind: str = "music"         # "music" | "bed" | "sfx"
    request_id: str | None = None


@runtime_checkable
class MusicProvider(Protocol):
    def name(self) -> str: ...
    def generate(self, prompt: str, *, seconds: float, dst: str, model: str) -> MusicResult: ...
    def sound_effect(self, prompt: str, *, seconds: float, dst: str) -> MusicResult: ...
