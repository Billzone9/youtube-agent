"""The public-facing Description + the two entry points into the pipeline.

Structural anti-leak: `Description` carries public `title`/`description`/`tags` ONLY. It is
*impossible* for a filename, provenance ref, or QC number to travel inside it — that is the primary
fix for the manifest-filename leak, not the guard (the guard is the belt-and-braces regression net).

Two entry points:
  * assemble_description(...) — DETERMINISTIC, no LLM. Enforces the shared structure (keyword-aware
    opening → timestamped chapters → a single one-line AI-disclosure at the very bottom) and runs the
    guard. This is the Layer-1-provable backbone and the permanent skeleton the LLM path feeds into.
  * generate_description(...) — the AUTONOMOUS seam (research → writer → assemble). The concrete LLM
    writer and research provider are deferred to Slice 5 (§4.4). Honest degradation: with no writer it
    raises WriterUnavailable — it NEVER emits a templated fake (doctrine §4 hard constraint).
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .chapters import Chapter, format_chapters
from .guard import assert_no_internal_artifacts


class WriterUnavailable(RuntimeError):
    """Raised when no concrete Writer is wired — the autonomous path must not fabricate prose."""


@dataclass(frozen=True)
class Description:
    """PUBLIC-facing metadata only. No provenance, paths, IDs, or QC — by construction."""

    title: str
    description: str
    tags: tuple[str, ...] = field(default_factory=tuple)

    def to_public_dict(self) -> dict:
        return {"title": self.title, "description": self.description, "tags": list(self.tags)}


def assemble_description(
    *,
    title: str,
    opening: str,
    chapters: list[Chapter],
    disclosure: str,
    tags: tuple[str, ...] | list[str] = (),
) -> Description:
    """Deterministically build a guard-clean Description from authored parts.

    Structure: opening → 'Chapters:' block → one blank line → the single disclosure line (bottom).
    """
    body = f"{opening.strip()}\n\n{format_chapters(chapters)}\n\n{disclosure.strip()}"
    title = title.strip()
    tags = tuple(t.strip() for t in tags if t and t.strip())
    # Guard EVERY public surface: title, the whole description (opening + chapter labels + disclosure),
    # and each tag. Hard-fails with the offending substrings if anything internal slipped in.
    assert_no_internal_artifacts(title, body, *tags)
    return Description(title=title, description=body, tags=tags)


def generate_description(video, channel, research, writer) -> Description:
    """Autonomous path: research the niche, have the Writer compose, then assemble + guard.

    Deferred to Slice 5. Wired now only as the seam so the architecture is visible and honest:
    with no concrete Writer this raises WriterUnavailable rather than inventing content.
    """
    if writer is None:
        raise WriterUnavailable(
            "no Writer configured — autonomous description generation is deferred to Slice 5; "
            "author manually via assemble_description in the meantime"
        )
    parts = writer.write(video=video, channel=channel, research=research)  # Slice 5 contract
    return assemble_description(
        title=parts["title"],
        opening=parts["opening"],
        chapters=parts["chapters"],
        disclosure=parts["disclosure"],
        tags=parts.get("tags", ()),
    )
