"""The one concrete LLM provider (direct Claude API). Swap this out to change vendors (§4.4).

Owns the tier→model-id map (routing lives here, not at call sites) and translates the vendor-neutral
`LLMRequest` (cacheable system blocks, tier, batch flag) into the Anthropic Messages API. The SDK is
imported LAZILY so the rest of the package imports without `anthropic` installed and the FakeLLMProvider
unit path needs no SDK. The provider is DB-FREE: it pushes a `UsageRecord` to the injected sink; the
async runner drains that to the cost ledger.
"""
from __future__ import annotations

from .base import (
    CacheableBlock,
    LLMRequest,
    LLMResponse,
    ModelTier,
    TokenUsage,
    UsageRecord,
    UsageSink,
)

# Locked model IDs (spec §4.4 / plan). Opus is wired but nothing in Slice 5 routes to PREMIUM.
_TIER_MODEL = {
    ModelTier.CHEAP: "claude-haiku-4-5-20251001",
    ModelTier.QUALITY: "claude-sonnet-4-6",
    ModelTier.PREMIUM: "claude-opus-4-8",
}


def _system_blocks(system: tuple[CacheableBlock, ...]) -> list[dict]:
    blocks: list[dict] = []
    for b in system:
        block: dict = {"type": "text", "text": b.text}
        if b.cache:
            block["cache_control"] = {"type": "ephemeral"}
        blocks.append(block)
    return blocks


def _usage_from(u) -> TokenUsage:
    return TokenUsage(
        input_tokens=getattr(u, "input_tokens", 0) or 0,
        output_tokens=getattr(u, "output_tokens", 0) or 0,
        cache_creation_input_tokens=getattr(u, "cache_creation_input_tokens", 0) or 0,
        cache_read_input_tokens=getattr(u, "cache_read_input_tokens", 0) or 0,
    )


class AnthropicProvider:
    """Implements the LLMProvider Protocol. Never send temperature/top_p/budget_tokens/trailing
    assistant prefill — they 400 on Sonnet 4.6 / Opus 4.8."""

    def __init__(self, settings, usage_sink: UsageSink) -> None:
        import anthropic  # lazy — only when a live provider is actually constructed

        self._client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        self._sink = usage_sink

    def model_for(self, tier: ModelTier) -> str:
        return _TIER_MODEL[tier]

    def complete(self, req: LLMRequest) -> LLMResponse:
        model = self.model_for(req.tier)
        resp = self._client.messages.create(
            model=model,
            max_tokens=req.max_tokens,
            system=_system_blocks(req.system),
            messages=list(req.messages),
        )
        text = "".join(b.text for b in resp.content if getattr(b, "type", "") == "text")
        usage = _usage_from(resp.usage)
        request_id = getattr(resp, "_request_id", None) or resp.id
        self._sink.record(UsageRecord(
            purpose=req.purpose, model=model, tier=req.tier, usage=usage,
            request_id=request_id, channel_id=req.channel_id, job_id=req.job_id,
        ))
        return LLMResponse(
            text=text, model=model, usage=usage, request_id=request_id,
            stop_reason=getattr(resp, "stop_reason", "") or "",
        )

    def count_tokens(self, req: LLMRequest) -> int:
        """Input-token estimate for a pre-flight cost estimate (no generation)."""
        resp = self._client.messages.count_tokens(
            model=self.model_for(req.tier),
            system=_system_blocks(req.system),
            messages=list(req.messages),
        )
        return resp.input_tokens

    # --- Batch (50% off) — settled by a separate poll/reconcile CLI, not the interactive path. ---
    def submit_batch(self, reqs: list[LLMRequest]) -> str:
        requests = [
            {
                "custom_id": f"{r.purpose}-{i}",
                "params": {
                    "model": self.model_for(r.tier),
                    "max_tokens": r.max_tokens,
                    "system": _system_blocks(r.system),
                    "messages": list(r.messages),
                },
            }
            for i, r in enumerate(reqs)
        ]
        batch = self._client.messages.batches.create(requests=requests)
        return batch.id

    def retrieve_batch(self, batch_id: str) -> dict[str, LLMResponse]:
        out: dict[str, LLMResponse] = {}
        for result in self._client.messages.batches.results(batch_id):
            if result.result.type != "succeeded":
                continue
            msg = result.result.message
            text = "".join(b.text for b in msg.content if getattr(b, "type", "") == "text")
            usage = _usage_from(msg.usage)
            rid = getattr(msg, "id", result.custom_id)
            out[result.custom_id] = LLMResponse(
                text=text, model=msg.model, usage=usage, request_id=rid,
                stop_reason=getattr(msg, "stop_reason", "") or "", batch_id=batch_id,
            )
            self._sink.record(UsageRecord(
                purpose=result.custom_id, model=msg.model, tier=ModelTier.QUALITY,
                usage=usage, request_id=rid, batch_id=batch_id,
            ))
        return out
