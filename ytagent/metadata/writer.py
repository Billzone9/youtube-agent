"""Writer seam — turns a channel's config-driven voice + research into authored parts.

The voice is drawn ENTIRELY from channel config (build_voice_brief): a wildlife documentary, a kids'
channel, and a finance channel supply different config and the same code produces a different voice.
Nothing niche-specific lives here.

The concrete LLM writer is the swappable AI-provider layer (spec §4.4 = Slice 5). Until it is wired,
NullWriter is the only implementation and it RAISES — the autonomous path must never fabricate prose
(doctrine §4). For the lion proof we author by hand and feed assemble_description directly.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from .description import WriterUnavailable


@dataclass(frozen=True)
class VoiceBrief:
    niche: str
    purpose: str
    tone: str
    style: str
    primary_language: str
    seed_keywords: tuple[str, ...] = field(default_factory=tuple)


def build_voice_brief(channel: dict) -> VoiceBrief:
    """Assemble the per-channel style constraint from onboarding config (no hardcoded voice)."""
    cfg = channel.get("config") or {}
    voice = cfg.get("voice_profile") or {}
    return VoiceBrief(
        niche=cfg.get("niche", ""),
        purpose=cfg.get("purpose", ""),
        tone=cfg.get("tone", ""),
        style=voice.get("style", ""),
        primary_language=cfg.get("primary_language", "en"),
        seed_keywords=tuple(cfg.get("default_tags") or ()),
    )


class Writer(Protocol):
    def write(self, *, video: dict, channel: dict, research) -> dict:
        """Return authored parts: {title, opening, chapters, disclosure, tags}."""
        ...


class NullWriter:
    """No LLM wired. Never fabricates — raises so the caller falls back to manual authoring."""

    def write(self, *, video: dict, channel: dict, research) -> dict:
        raise WriterUnavailable("NullWriter cannot compose prose — wire an LLM Writer (Slice 5)")
