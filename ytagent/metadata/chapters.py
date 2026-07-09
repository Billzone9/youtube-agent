"""Chapters — public-safe navigation derived from audience-facing beat labels + real timestamps.

Only the label and start time are public. Internal beat numbering ("Beat 1 —") and runtime hints
("(~70s)") are stripped by whoever builds the Chapter list; the labels themselves must pass the
guard. YouTube's chapter rules are enforced here so a malformed list fails loudly, not on upload.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Chapter:
    label: str
    start_seconds: int


def _stamp(seconds: int) -> str:
    """M:SS, or H:MM:SS past an hour — YouTube accepts both; first must be 0:00."""
    h, rem = divmod(int(seconds), 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def validate_chapters(chapters: list[Chapter]) -> None:
    """Enforce YouTube's rules: ≥3 chapters, first at 0:00, strictly increasing, each ≥10s long."""
    if len(chapters) < 3:
        raise ValueError(f"need at least 3 chapters for YouTube chapters, got {len(chapters)}")
    if chapters[0].start_seconds != 0:
        raise ValueError(f"first chapter must start at 0:00, got {chapters[0].start_seconds}s")
    for prev, cur in zip(chapters, chapters[1:]):
        if cur.start_seconds - prev.start_seconds < 10:
            raise ValueError(
                f"chapters must be ≥10s apart: '{prev.label}' -> '{cur.label}' "
                f"({prev.start_seconds}s -> {cur.start_seconds}s)"
            )


def format_chapters(chapters: list[Chapter]) -> str:
    """Render the 'Chapters:' block (validated first)."""
    validate_chapters(chapters)
    lines = "\n".join(f"{_stamp(c.start_seconds)} {c.label}" for c in chapters)
    return f"Chapters:\n{lines}"
