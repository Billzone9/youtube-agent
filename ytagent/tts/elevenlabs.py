"""ElevenLabs Text-to-Speech. `POST /v1/text-to-speech/{voice_id}` returns mp3 bytes; written
atomically (temp → os.replace, mirroring ffmpeg.run). A 401/403 (the Music-only-scope case) maps to
TTSScopeError so the conductor aborts before any render spend with a clear human-action message.
"""
from __future__ import annotations

import os

import httpx

from .base import TTSQuotaError, TTSResult, TTSScopeError

_BASE = "https://api.elevenlabs.io/v1/text-to-speech"
_TIMEOUT = httpx.Timeout(120.0, connect=15.0)
# Documentary narration: steady, faithful to the voice, no stylistic drift.
_VOICE_SETTINGS = {"stability": 0.5, "similarity_boost": 0.8, "style": 0.0, "use_speaker_boost": True}


class ElevenLabsTTS:
    def __init__(self, api_key: str) -> None:
        self._key = api_key

    def name(self) -> str:
        return "elevenlabs"

    def synthesize(self, text: str, *, voice_id: str, dst: str, model: str) -> TTSResult:
        tmp = f"{dst}.part"
        headers = {"xi-api-key": self._key, "accept": "audio/mpeg", "content-type": "application/json"}
        body = {"text": text, "model_id": model, "voice_settings": _VOICE_SETTINGS}
        try:
            with httpx.Client(timeout=_TIMEOUT) as client:
                r = client.post(f"{_BASE}/{voice_id}", params={"output_format": "mp3_44100_128"},
                                headers=headers, json=body)
        except httpx.HTTPError as e:
            raise RuntimeError(f"ElevenLabs TTS request failed: {e}") from e
        if r.status_code in (401, 403):
            # surface ElevenLabs' ACTUAL reason — a 401 is either a real scope/auth failure OR the key's
            # hard credit cap being hit (`quota_exceeded`); they need different human actions, and the
            # old code discarded the body and always blamed scope (which misdiagnosed job 276).
            detail, code = "", ""
            try:
                d = r.json().get("detail") or {}
                detail = d.get("message") or ""
                code = (d.get("status") or d.get("code") or "").lower()
            except Exception:  # noqa: BLE001 — non-JSON body
                detail = r.text[:300]
            if code == "quota_exceeded":
                raise TTSQuotaError(
                    f"ElevenLabs key credit cap exhausted — {detail} Raise/reset the key's quota in the "
                    f"ElevenLabs dashboard (human-only spend change), then resume (no re-charge).")
            raise TTSScopeError(
                f"ElevenLabs {r.status_code}: {detail or 'the key likely lacks the Text-to-Speech scope'} "
                f"— add TTS scope (or a TTS-scoped key) in the ElevenLabs dashboard (human-only).")
        if r.status_code != 200:
            raise RuntimeError(f"ElevenLabs TTS HTTP {r.status_code}: {r.text[:200]}")
        content = r.content
        if not content:
            raise RuntimeError("ElevenLabs returned empty audio")
        with open(tmp, "wb") as fh:
            fh.write(content)
        os.replace(tmp, dst)
        return TTSResult(path=dst, characters=len(text), model=model, voice_id=voice_id,
                         request_id=r.headers.get("request-id"))
