"""Per-asset provenance derived from filenames — INTERNAL record only (never public text).

Pexels/Pixabay downloads embed the asset id in the filename, so provenance can be recovered even for
clips swapped in ad-hoc: `14301979_3840_2160_24fps.mp4` → Pexels 14301979; bare `300312.mp4` →
Pixabay 300312. This sets `videos.provenance_ref`/`jobs.result`; the public-text guard keeps it out
of anything an audience sees.
"""
from __future__ import annotations

import os
import re

_ID = re.compile(r"^(\d+)")
_PEXELS_SHAPE = re.compile(r"_\d{3,4}_\d{3,4}_\d+fps", re.I)   # Pexels "_WxH_fps" naming


def asset_id_from_filename(name: str) -> str | None:
    stem = os.path.splitext(os.path.basename(name))[0]
    m = _ID.match(stem)
    return m.group(1) if m else None


def source_of(filename: str) -> str:
    """Heuristic: the Pexels download naming carries a _WxH_fps suffix; a bare numeric id is Pixabay."""
    return "pexels" if _PEXELS_SHAPE.search(os.path.basename(filename)) else "pixabay"


def source_url(asset_id: str, source: str) -> str:
    if source == "pexels":
        return f"https://www.pexels.com/video/{asset_id}/"
    return f"https://pixabay.com/videos/id-{asset_id}/"   # best-effort; reconcile against the manifest


_LICENSE = {"pexels": "Pexels License", "pixabay": "Pixabay Content License"}


def build_provenance(spec) -> list[dict]:
    """One record per unique source clip across all beats (which beats used it)."""
    seen: dict[str, dict] = {}
    for beat in spec.beats:
        for clip in beat.clips:
            fn = os.path.basename(clip.src)
            rec = seen.get(fn)
            if rec is None:
                src = source_of(fn)
                aid = asset_id_from_filename(fn)
                rec = {
                    "filename": fn, "asset_id": aid, "source": src,
                    "url": source_url(aid, src) if aid else None,
                    "license": _LICENSE.get(src), "contributor": None, "beats": [],
                }
                seen[fn] = rec
            if beat.name not in rec["beats"]:
                rec["beats"].append(beat.name)
    return list(seen.values())
