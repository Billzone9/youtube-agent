"""Provider factory — only keyed providers join the pool; [] ⇒ the caller degrades honestly
(mirrors get_llm_provider → None). SDK/http imports are lazy so this file loads without a key.
"""
from __future__ import annotations

from .base import StockProvider


def get_stock_providers(settings) -> list[StockProvider]:
    providers: list[StockProvider] = []
    if getattr(settings, "pexels_api_key", None):
        from .pexels import PexelsProvider
        providers.append(PexelsProvider(settings.pexels_api_key))
    if getattr(settings, "pixabay_api_key", None):
        from .pixabay import PixabayProvider
        providers.append(PixabayProvider(settings.pixabay_api_key))
    return providers
