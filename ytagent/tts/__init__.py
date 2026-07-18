"""TTS narration — swappable provider (ElevenLabs now). Factory returns None without a key so the
caller degrades honestly (mirrors get_llm_provider / get_stock_providers).
"""
from __future__ import annotations

from .base import TTSProvider, TTSResult, TTSScopeError, TTSUnavailable

__all__ = ["get_tts_provider", "TTSProvider", "TTSResult", "TTSScopeError", "TTSUnavailable"]


def get_tts_provider(settings) -> TTSProvider | None:
    if not getattr(settings, "elevenlabs_api_key", None):
        return None
    from .elevenlabs import ElevenLabsTTS

    return ElevenLabsTTS(settings.elevenlabs_api_key)
