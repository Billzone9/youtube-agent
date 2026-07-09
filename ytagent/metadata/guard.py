"""The no-internal-artifact guard.

IMPORTANT: this guard is a REGRESSION NET, not the primary fix. The primary fix is structural — the
`Description` type (description.py) carries public fields ONLY, and provenance/QC/paths are logged to
the internal record (events/DB) instead of the public text. The guard exists so that if some future
code path (a manual override, an import, a careless edit) ever tries to push an internal artifact
into a public field, publishing HARD-FAILS instead of leaking it — exactly the failure that put
`lion-doc-01-footage-manifest.md` into the lion's live description.

It targets artifact *shapes* (filenames, repo paths, ID tokens, QC units, internal status labels),
tuned NOT to ban legitimate disclosure vocabulary — "licensed stock", "AI-assisted", and naming
ElevenLabs/Pexels/Pixabay as sources are all fine. On a hit it raises with the offending substrings;
it never silently scrubs (that would hide the bug and can mangle real prose).
"""
from __future__ import annotations

import re

_UUID = r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"

# (label, pattern). Labels make the raised error legible ("filename: lion-doc-01-footage-manifest.md").
_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("file extension", re.compile(r"\b[\w./-]+\.(?:md|mp4|mov|txt|json|sql|py|wav|mp3|srt|csv|log|yml|yaml)\b", re.I)),
    ("manifest/doc stem", re.compile(r"\blion-doc-\d+\b|-footage-manifest\b|-edit-plan\b|-narration\b|\bmanifest\b|\bprovenance\b", re.I)),
    ("repo/os path", re.compile(r"(?:^|\s)(?:/app/|assets/|ytagent/|scripts/)[\w./-]*", re.I)),
    ("uuid", re.compile(_UUID)),
    ("job/video id", re.compile(r"\b(?:job|video)\s*#?\s*\d+\b", re.I)),
    ("assignment token", re.compile(r"\b\w+_?id\s*=", re.I)),
    ("qc unit", re.compile(r"\b\d+(?:\.\d+)?\s*(?:LUFS|dBFS|dBTP)\b|\bnoise[ _]floor\b|\bchecksum\b|\bsha256\b|\b\d{4,}\s*bytes\b|\bsize_bytes\b", re.I)),
    ("filename fps token", re.compile(r"_\d+fps\b", re.I)),
    ("internal status label", re.compile(r"\bawaiting_approval\b|\bpublished_dryrun\b|\bdry[_ ]run\b|\bidempotency\b|\b\d+\s*credits\b", re.I)),
]


class InternalArtifactError(ValueError):
    """Raised when public-facing text contains an internal engineering artifact."""

    def __init__(self, matches: list[str]) -> None:
        self.matches = matches
        super().__init__(
            "internal artifact(s) in public text — refusing: " + "; ".join(matches)
        )


def scan(*texts: str) -> list[str]:
    """Return a list of 'label: offending-substring' for every artifact shape found. Empty = clean."""
    hits: list[str] = []
    for text in texts:
        if not text:
            continue
        for label, pat in _PATTERNS:
            for m in pat.finditer(text):
                frag = m.group(0).strip()
                if frag:
                    hits.append(f"{label}: {frag}")
    return hits


def assert_no_internal_artifacts(*texts: str) -> None:
    """Raise InternalArtifactError if any public text carries an internal artifact shape."""
    hits = scan(*texts)
    if hits:
        raise InternalArtifactError(hits)
