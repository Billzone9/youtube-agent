"""The lion film's authored description — the wildlife-voice CALIBRATION REFERENCE (doctrine §2).

This is public text I authored in-session from web/trend research (primary keyword in the first
sentence; keyword-rich but not stuffed; poetic-surface / accurate-underneath, per the channel's
config voice). It lives here — not in artifacts.py next to QC numbers — as a `Description`, which by
construction cannot carry internal artifacts, and it is guard-checked when assembled. It is a
temporary seed until the Slice-5 LLM Writer generates such text per video; the moment that lands,
this becomes just the reference the writer is tuned against.

The internal record (file path, loudness, provenance) stays entirely in artifacts.lion_video_meta().
"""
from __future__ import annotations

from .chapters import Chapter
from .description import Description, assemble_description

# Audience-facing beat labels (internal "Beat N" numbering stripped) + real timestamps from the
# locked 6:34 cut. Public-safe: these are the on-screen navigation, nothing internal.
_LION_CHAPTERS = [
    Chapter("The kingdom and its sovereign", 0),
    Chapter("The lion at rest", 51),
    Chapter("The pride", 114),
    Chapter("The hunt", 178),
    Chapter("The cubs", 239),
    Chapter("The roar", 303),
    Chapter("Golden-hour close", 347),
]

_LION_OPENING = (
    "The lion rules the African savanna without rival. Under a sky that turns from gold to fire, "
    "this short wildlife documentary follows one pride across a single unhurried day on the plains "
    "— the drowsy heat of noon, the patient discipline of the hunt, the tumble of cubs learning "
    "their place, and the roar that rolls across the grasslands as the light fails.\n\n"
    "It is filmed as a calm, cinematic portrait rather than a chase, lingering on the small truths "
    "of lion life: the bonds that hold a pride together, the weight a lioness carries for them all, "
    "and the quiet authority of the animal we have long called the king of beasts. Settle in, turn "
    "the sound up, and let the savanna close in around you."
)

# One graceful, accurate line — narration + score are AI; footage is licensed stock (doctrine §2).
_LION_DISCLOSURE = "Narration and score are AI-assisted; all footage is licensed stock."

_LION_TAGS = (
    "lion", "lion documentary", "wildlife documentary", "african savanna", "lions", "lion pride",
    "nature documentary", "africa", "savanna", "big cats", "the hunt", "lion roar", "wildlife",
    "animals",
)

_LION_TITLE = "Lion — Lord of the Savanna"


def build_lion_reference() -> Description:
    """The clean, guard-checked lion Description (title + description + SEO tags)."""
    return assemble_description(
        title=_LION_TITLE,
        opening=_LION_OPENING,
        chapters=_LION_CHAPTERS,
        disclosure=_LION_DISCLOSURE,
        tags=_LION_TAGS,
    )
