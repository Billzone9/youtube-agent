"""TTS — pure types + the provider interface. Kept separate from ytagent/providers/ (which is
LLM-token-shaped); TTS is per-character audio synthesis with its own cost model.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable


class TTSUnavailable(RuntimeError):
    """No TTS provider is configured (no key) — the caller degrades honestly, never fabricates audio."""


class TTSScopeError(RuntimeError):
    """The API rejected the request (401/403) — typically the key lacks the Text-to-Speech scope.
    A spend-capability change is human-only (add TTS scope / a TTS-scoped key)."""


@dataclass(frozen=True)
class TTSResult:
    path: str
    characters: int
    model: str
    voice_id: str
    request_id: str | None = None


@runtime_checkable
class TTSProvider(Protocol):
    def name(self) -> str: ...
    def synthesize(self, text: str, *, voice_id: str, dst: str, model: str) -> TTSResult: ...
