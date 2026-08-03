"""Claim-safe ambient bed library for credit-light Shorts (M1). The 0-credit reuse path: own/synthetic
ElevenLabs-generated beds (no Content ID even as a VOD), each verified clean by the noise gate before it
enters `assets/beds/` (see BEDS.md). `pick_bed` ROTATES across the library so no single bed is on every
Short — variation is a project principle. See visual-density-standard / CLAUDE.md audio rules."""
from __future__ import annotations

import os

from . import qc

_DEFAULT_ROOT = "assets/beds"


def bed_library(root: str = _DEFAULT_ROOT) -> list[str]:
    """Absolute paths of the curated claim-safe beds, sorted for deterministic rotation. Empty if none."""
    if not os.path.isdir(root):
        return []
    return [os.path.abspath(os.path.join(root, f)) for f in sorted(os.listdir(root))
            if f.lower().endswith((".mp3", ".wav", ".m4a"))]


def pick_bed(index: int, root: str = _DEFAULT_ROOT, *, verify: bool = True) -> str | None:
    """Rotate a bed by `index` (e.g. the Short's sequence number) so consecutive Shorts differ. Returns
    None if the library is empty (caller then generates a fresh bed, ~520 cr). If `verify`, the picked
    bed must still pass the noise gate (a corrupted/replaced file never reaches a render)."""
    beds = bed_library(root)
    if not beds:
        return None
    chosen = beds[index % len(beds)]
    if verify and not qc.check_source_clean(chosen).ok:
        raise ValueError(f"bed {chosen!r} failed the noise gate — remove it from the library (BEDS.md)")
    return chosen
