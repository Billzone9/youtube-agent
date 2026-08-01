"""ElevenLabs Music + Sound-Generation. Both return mp3 bytes, written atomically (temp → os.replace,
mirroring tts/elevenlabs.py). A 401/403 maps to MusicScopeError so the conductor degrades gracefully
(ship without that layer) instead of failing the film. Synthetic → claim-safe (CLAUDE.md: never
licensed music); every generated cue is noise-gated by the CONDUCTOR on arrival, not here.
"""
from __future__ import annotations

import os

import httpx

from .base import MusicResult, MusicScopeError

_MUSIC = "https://api.elevenlabs.io/v1/music"
_SFX = "https://api.elevenlabs.io/v1/sound-generation"
_TIMEOUT = httpx.Timeout(300.0, connect=15.0)   # generation is slow; give it room
_CREDITS_PER_SEC = 15.0                          # ElevenLabs Music pricing (plan §156)


class ElevenLabsMusic:
    def __init__(self, api_key: str) -> None:
        self._key = api_key

    def name(self) -> str:
        return "elevenlabs"

    def _headers(self) -> dict:
        return {"xi-api-key": self._key, "accept": "audio/mpeg", "content-type": "application/json"}

    def _post(self, url: str, *, body: dict, dst: str, seconds: float, model: str, kind: str
              ) -> MusicResult:
        tmp = f"{dst}.part"
        try:
            with httpx.Client(timeout=_TIMEOUT) as client:
                r = client.post(url, params={"output_format": "mp3_44100_128"},
                                headers=self._headers(), json=body)
        except httpx.HTTPError as e:
            raise RuntimeError(f"ElevenLabs {kind} request failed: {e}") from e
        if r.status_code in (401, 403):
            raise MusicScopeError(
                f"ElevenLabs {r.status_code}: the key lacks the {kind} scope — add the scope "
                f"(or a scoped key) in the ElevenLabs dashboard (human-only spend change).")
        if r.status_code != 200:
            raise RuntimeError(f"ElevenLabs {kind} HTTP {r.status_code}: {r.text[:200]}")
        content = r.content
        if not content:
            raise RuntimeError(f"ElevenLabs {kind} returned empty audio")
        with open(tmp, "wb") as fh:
            fh.write(content)
        os.replace(tmp, dst)
        return MusicResult(path=dst, seconds=float(seconds), credits_est=round(seconds * _CREDITS_PER_SEC),
                           model=model, kind=kind, request_id=r.headers.get("request-id"))

    def generate(self, prompt: str, *, seconds: float, dst: str, model: str = "music_v1") -> MusicResult:
        """One instrumental cue/bed. force_instrumental → no vocals (documentary score)."""
        body = {"prompt": prompt, "music_length_ms": int(round(seconds * 1000)),
                "model_id": model, "force_instrumental": True}
        kind = "bed" if "ambience" in prompt.lower() or "bed" in prompt.lower() else "music"
        return self._post(_MUSIC, body=body, dst=dst, seconds=seconds, model=model, kind=kind)

    def sound_effect(self, prompt: str, *, seconds: float, dst: str) -> MusicResult:
        """One claim-safe SFX via sound-generation (synthetic). Same 401/403 → MusicScopeError path so a
        blocked scope degrades gracefully (ship without the SFX)."""
        body = {"text": prompt, "duration_seconds": float(seconds), "prompt_influence": 0.5}
        return self._post(_SFX, body=body, dst=dst, seconds=seconds, model="sound_v2", kind="sfx")
