"""Authoring — the house-voice machinery (style spec, AI-tell scanner, script writer).

Channel-general: the voice comes from each channel's config + registered exemplars, never hardcoded
(see `house-voice-standard.md`). Pure logic where possible; the LLM provider is injected.
"""
from __future__ import annotations

from .style import STYLE_SPEC_VERSION, StyleSpec, compose_style
from .tells import TELLS_THRESHOLDS_VERSION, TellReport, scan_tells

__all__ = [
    "scan_tells", "TellReport", "TELLS_THRESHOLDS_VERSION",
    "compose_style", "StyleSpec", "STYLE_SPEC_VERSION",
]
