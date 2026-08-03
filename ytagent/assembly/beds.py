"""Claim-safe ambient bed library for credit-light Shorts (M1). The 0-credit reuse path: own/synthetic
ElevenLabs-generated beds (no Content ID even as a VOD).

CLAIM-SAFETY IS STRUCTURALLY ENFORCED, not documented-and-hoped: `check_source_clean` measures HISS, not
ORIGIN — it would pass a clean SOURCED track (the lion's sourced ambience failing the noise gate was luck,
not a control). So a bed is admissible ONLY if `beds-manifest.json` (committed, repo root) attests it as
`elevenlabs_generated` AND its bytes hash to the recorded sha256. A sourced/licensed track dropped into
assets/beds/ has no matching attested entry and is refused. `pick_bed` also rotates (no single bed on
every Short) and re-checks the noise gate. See beds-manifest.json + CLAUDE.md audio rules."""
from __future__ import annotations

import hashlib
import json
import os

from . import qc

_DEFAULT_ROOT = "assets/beds"
_MANIFEST = "beds-manifest.json"
_OK_ORIGINS = {"elevenlabs_generated"}     # own/generated only — NEVER sourced/licensed


def _manifest(manifest_path: str = _MANIFEST) -> dict:
    """{sha256 → entry} for beds attested with an allowed generated origin. Empty if no manifest."""
    if not os.path.exists(manifest_path):
        return {}
    data = json.load(open(manifest_path))
    return {e["sha256"]: e for e in data.get("beds", []) if e.get("origin") in _OK_ORIGINS}


def _sha256(path: str) -> str:
    return hashlib.sha256(open(path, "rb").read()).hexdigest()


def bed_library(root: str = _DEFAULT_ROOT, manifest_path: str = _MANIFEST) -> list[str]:
    """Absolute paths of ADMISSIBLE beds only: present in assets/beds/ AND byte-for-byte attested as
    generated in the committed manifest. A file with no matching attested hash is EXCLUDED (structural
    claim-safety) — not returned, so it can never reach a render. Sorted for deterministic rotation."""
    if not os.path.isdir(root):
        return []
    attested = _manifest(manifest_path)
    out = []
    for f in sorted(os.listdir(root)):
        if not f.lower().endswith((".mp3", ".wav", ".m4a")):
            continue
        p = os.path.join(root, f)
        if _sha256(p) in attested:                 # bytes match an attested generated-origin entry
            out.append(os.path.abspath(p))
    return out


def pick_bed(index: int, root: str = _DEFAULT_ROOT, *, verify: bool = True,
             manifest_path: str = _MANIFEST) -> str | None:
    """Rotate an ADMISSIBLE bed by `index` (e.g. the Short's sequence number) so consecutive Shorts
    differ. Returns None if the library is empty (caller then generates a fresh bed, ~520 cr). If
    `verify`, the picked bed must also pass the noise gate (belt-and-braces on top of the origin control)."""
    beds = bed_library(root, manifest_path)
    if not beds:
        return None
    chosen = beds[index % len(beds)]
    if verify and not qc.check_source_clean(chosen).ok:
        raise ValueError(f"bed {chosen!r} failed the noise gate — remove it from the library + manifest")
    return chosen
