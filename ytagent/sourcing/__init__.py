"""Asset sourcing — claim-safe stock footage for a video's shot-briefs (channel-general).

Swappable stock providers (Pexels/Pixabay) behind one interface; metadata-only ranking with a
fail-loud `NoMatch`; every download run through the Slice-3 input gates; logged (never fabricated)
provenance; permanent caching. The only spend is the pennies of optional Haiku query extraction —
downloads are free.
"""
from __future__ import annotations

from .base import Candidate, NoMatch, QueryPlan, SourcedAsset, SourcingError, StockProvider
from .factory import get_stock_providers
from .orchestrator import source_for_brief, source_shot_briefs

__all__ = [
    "get_stock_providers", "source_for_brief", "source_shot_briefs", "to_clip",
    "SourcedAsset", "NoMatch", "Candidate", "QueryPlan", "StockProvider", "SourcingError",
]


def to_clip(asset: SourcedAsset, *, approx_seconds: int):
    """A sourced asset → an assembly EditSpec Clip (the downstream seam; orientation is gate-guaranteed
    to match the target, so a centre focal point is safe)."""
    from ..assembly.spec import Clip

    dur = asset.candidate.duration or approx_seconds
    return Clip(src=asset.local_path, trim_in=0.0,
                trim_out=min(float(dur), float(approx_seconds or dur)),
                effect=None, focus={"16:9": [0.5, 0.5], "9:16": [0.5, 0.5]})
