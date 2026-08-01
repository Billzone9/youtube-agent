"""Music + SFX generation — swappable provider (ElevenLabs now). Factory returns None without a key so
the caller degrades honestly (ships the film without score/ambience), mirroring get_tts_provider.
"""
from __future__ import annotations

from .base import MusicProvider, MusicResult, MusicScopeError, MusicUnavailable

__all__ = ["get_music_provider", "MusicProvider", "MusicResult", "MusicScopeError", "MusicUnavailable"]


def get_music_provider(settings) -> MusicProvider | None:
    if not getattr(settings, "elevenlabs_api_key", None):
        return None
    from .elevenlabs import ElevenLabsMusic

    return ElevenLabsMusic(settings.elevenlabs_api_key)
