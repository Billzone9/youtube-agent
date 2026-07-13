"""Provider factory — the one seam through which writers get an LLM (§4.4 swappable by config).

`get_llm_provider` returns None when no key is configured, so callers degrade honestly to NullWriter
(never fabricate) — exactly the Layer-1 pattern. LLM_PROVIDER selects the vendor (default anthropic).
"""
from __future__ import annotations

import os

from .base import (
    CacheableBlock,
    ListUsageSink,
    LLMProvider,
    LLMRequest,
    LLMResponse,
    ModelTier,
    TokenUsage,
    UsageRecord,
    UsageSink,
)

__all__ = [
    "get_llm_provider",
    "CacheableBlock",
    "ListUsageSink",
    "LLMProvider",
    "LLMRequest",
    "LLMResponse",
    "ModelTier",
    "TokenUsage",
    "UsageRecord",
    "UsageSink",
]


def get_llm_provider(settings, usage_sink: UsageSink) -> LLMProvider | None:
    """Build the configured LLM provider, or None when its key is absent (honest degradation)."""
    provider = os.environ.get("LLM_PROVIDER", "anthropic").lower()
    if provider == "anthropic":
        if not getattr(settings, "anthropic_api_key", None):
            return None
        from .anthropic_provider import AnthropicProvider  # lazy — imports the SDK

        return AnthropicProvider(settings, usage_sink)
    raise ValueError(f"unknown LLM_PROVIDER {provider!r}")
