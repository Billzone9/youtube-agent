"""Structural guard — a shot-brief must ask ONLY for footage a stock wildlife library can actually
provide. Archival footage, historical photographs, illustrations, maps, CGI, reenactments and the like
are unsourceable at ANY yield (the ivory-trade beat that killed the fresh-elephant run). This mirrors
`tells.scan_tells` and the pacing floor: a flagged brief triggers a BOUNDED regeneration inside the
ScriptWriter, so the doctrine is ENFORCED in code, not merely requested in a prompt — which is why the
other standards on this project hold and this one kept being violated.
"""
from __future__ import annotations

import re

# label → regex. Each pattern is written to catch the UNSOURCEABLE request while leaving ordinary
# wildlife-brief words ('old bull', 'standing still', 'a clearing') alone — calibrated so The Old Paths
# briefs pass clean and the ivory-trade brief fails (see scan_sourceability's calibration in the verify).
_UNSOURCEABLE = {
    "archival footage": r"\barchiv",
    "historical footage": r"\bhistoric(al)?\b.{0,20}\b(footage|film|video|photo|image|record)",
    "vintage/period footage": r"\b(vintage|antique|period|retro|old[- ]time)\b.{0,15}\b(footage|film|photo|photograph|image)",
    "photograph / still": r"\bphotograph|\bstill photo|\bold photos?\b|\bphotos?\b(?!\w)",
    "black-and-white / sepia": r"\bblack[- ]and[- ]white\b|\bblack ?& ?white\b|\bmonochrome\b|\bsepia\b",
    "illustration / artwork": r"\b(illustration|drawing|sketch|painting|artwork|engraving|woodcut|etching)\b",
    "map / graphic / diagram": r"\b(map|infographic|diagram|chart|graph|schematic)\b",
    "CGI / animation / render": r"\b(cgi|animation|animated|3d render|rendered|motion graphic)\b",
    "reenactment": r"\bre[- ]?enact|\bdramatis(ation|ed|e)\b|\bstaged reconstruction\b",
    "museum / document / press": r"\b(museum|newspaper|headline|document|manuscript|painting)\b",
}
# NOTE: "title card"/"text on screen" are deliberately NOT flagged — they are a rendering concern, not
# unsourceable FOOTAGE, and briefs legitimately say "no title card yet" (negations would false-fire).


def scan_unsourceable(text: str) -> list[str]:
    """Return the labels of any unsourceable-footage requests in a shot-brief (empty = clean)."""
    t = (text or "").lower()
    return [label for label, pat in _UNSOURCEABLE.items() if re.search(pat, t)]


def scan_briefs(beats_raw: list[dict]) -> list[tuple[int, list[str]]]:
    """(beat_index, flags) for every beat whose shot_brief asks for unsourceable footage."""
    out: list[tuple[int, list[str]]] = []
    for i, b in enumerate(beats_raw):
        hits = scan_unsourceable(b.get("shot_brief", ""))
        if hits:
            out.append((i, hits))
    return out
