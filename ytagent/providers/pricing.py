"""Token usage → GBP, from prices held as DATA in platform_settings (not code constants).

Four buckets per Anthropic billing: fresh input (full), output (full), cache READ (~0.1× input),
cache WRITE/creation (~1.25× input). Prices are per-million tokens in USD; convert with the stored
USD→GBP FX rate. The pricing dict shape (seeded by seed.py under platform_settings key 'llm_pricing'):

    {"anthropic": {"claude-sonnet-4-6": {"input":3.0,"output":15.0,
                                         "cache_read":0.30,"cache_write_5m":3.75,"currency":"USD"}, ...},
     "fx": {"USD_GBP": 0.79, "as_of": "2026-07-13"}}
"""
from __future__ import annotations

from decimal import Decimal

from .base import TokenUsage

_PER_MILLION = Decimal(1_000_000)


def _d(v) -> Decimal:
    return Decimal(str(v))


def usage_to_gbp(usage: TokenUsage, model: str, pricing: dict) -> dict:
    """Return {amount_gbp, amount_usd, fx_rate, breakdown} for one call. Raises if the model/price
    is missing — we never guess a price into the ledger."""
    providers = pricing.get("anthropic") or {}
    price = providers.get(model)
    if price is None:
        raise KeyError(f"no price for model {model!r} in platform_settings.llm_pricing")
    fx = pricing.get("fx") or {}
    fx_rate = _d(fx.get("USD_GBP"))
    if not fx_rate:
        raise KeyError("no USD_GBP fx rate in platform_settings.llm_pricing")

    usd = (
        _d(usage.input_tokens) * _d(price["input"])
        + _d(usage.output_tokens) * _d(price["output"])
        + _d(usage.cache_read_input_tokens) * _d(price.get("cache_read", price["input"]))
        + _d(usage.cache_creation_input_tokens)
        * _d(price.get("cache_write_5m", _d(price["input"]) * _d("1.25")))
    ) / _PER_MILLION

    amount_usd = usd.quantize(Decimal("0.000001"))
    amount_gbp = (amount_usd * fx_rate).quantize(Decimal("0.01"))
    return {
        "amount_gbp": amount_gbp,
        "amount_usd": amount_usd,
        "fx_rate": fx_rate,
        "breakdown": {
            "input_tokens": usage.input_tokens,
            "output_tokens": usage.output_tokens,
            "cache_read_input_tokens": usage.cache_read_input_tokens,
            "cache_creation_input_tokens": usage.cache_creation_input_tokens,
        },
    }
