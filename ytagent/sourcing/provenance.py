"""Per-asset provenance — LOGGED from the authoritative API fields, never derived, never fabricated.
INTERNAL record only (the metadata/guard.py net keeps asset IDs / URLs / 'manifest' tokens out of any
public text). The API returns the real page URL, contributor, and licence, so every Slice-4 record is
`provenance_source='logged'` (unlike the Layer-1 manifest work, which had to derive from filenames).
"""
from __future__ import annotations

import os
from datetime import datetime, timezone

from .base import Candidate, GateResult


def build_asset_provenance(candidate: Candidate, gate: GateResult, path: str) -> dict:
    ts = datetime.now(timezone.utc)
    try:
        ts = datetime.fromtimestamp(os.path.getmtime(path), tz=timezone.utc)
    except OSError:
        pass
    return {
        "source": candidate.source,
        "asset_id": candidate.asset_id,
        "url": candidate.page_url,                       # authoritative page — never fabricated
        "contributor": candidate.contributor or "(see page)",
        "licence": candidate.licence,
        "downloaded_at": ts.isoformat(),
        "provenance_source": "logged",
        "local_path": path,
        "raw": candidate.raw,                            # verbatim API record → recovery without re-fetch
    }
