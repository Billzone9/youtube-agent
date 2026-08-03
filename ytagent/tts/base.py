"""TTS — pure types + the provider interface. Kept separate from ytagent/providers/ (which is
LLM-token-shaped); TTS is per-character audio synthesis with its own cost model.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable


class TTSUnavailable(RuntimeError):
    """No TTS provider is configured (no key) — the caller degrades honestly, never fabricates audio."""


class TTSScopeError(RuntimeError):
    """The API rejected the request with a hard 401/403 that a retry won't fix — the key lacks the
    Text-to-Speech scope, or (subclass below) its credit cap is exhausted. Either way the remedy is a
    human-only spend-capability change (add TTS scope / a TTS-scoped key / raise the key's cap)."""


class TTSQuotaError(TTSScopeError):
    """The key's HARD CREDIT CAP is exhausted (ElevenLabs 401 `quota_exceeded`). This is the structural
    spend control working as designed — the key cannot spend past its cap. NOT transient: never retry.
    Resuming after Banks raises/resets the key's quota re-charges nothing already voiced (idempotent)."""


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
