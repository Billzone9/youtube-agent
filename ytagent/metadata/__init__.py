"""Public-facing metadata generation (doctrine: public-facing-output-standard.md).

Pure logic — no DB, no Telegram, no google libs — so it imports cleanly anywhere. The DB side lives
in ytagent/repo/metadata.py; the versioned rows it writes are sourced from a `Description` here.
"""
from __future__ import annotations

from .chapters import Chapter, format_chapters, validate_chapters
from .description import (
    Description,
    WriterUnavailable,
    assemble_description,
    generate_description,
)
from .guard import InternalArtifactError, assert_no_internal_artifacts, scan
from .research import CapabilityUnavailable, ResearchResult, UnavailableResearch
from .writer import NullWriter, VoiceBrief, build_voice_brief

__all__ = [
    "Chapter",
    "format_chapters",
    "validate_chapters",
    "Description",
    "assemble_description",
    "generate_description",
    "WriterUnavailable",
    "InternalArtifactError",
    "assert_no_internal_artifacts",
    "scan",
    "CapabilityUnavailable",
    "ResearchResult",
    "UnavailableResearch",
    "NullWriter",
    "VoiceBrief",
    "build_voice_brief",
]
