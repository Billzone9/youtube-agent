"""Atomic, size-checked download. Streams to a `.part` sibling, verifies the byte count against
Content-Length (truncation guard), then `os.replace` — a half-written file is never promoted (mirrors
the assembler's temp→replace discipline).
"""
from __future__ import annotations

import os

import httpx

from .base import Candidate, SourcingError

_TIMEOUT = httpx.Timeout(60.0, connect=15.0)


async def download(candidate: Candidate, dst_dir: str, *, ext: str = "mp4") -> str:
    """Download `candidate.download_url` into `dst_dir/{asset_id}.{ext}`. Returns the final path."""
    os.makedirs(dst_dir, exist_ok=True)
    dst = os.path.join(dst_dir, f"{candidate.asset_id}.{ext}")
    tmp = f"{dst}.part"
    written = 0
    expected: int | None = None
    async with httpx.AsyncClient(timeout=_TIMEOUT, follow_redirects=True) as client:
        async with client.stream("GET", candidate.download_url) as resp:
            resp.raise_for_status()
            cl = resp.headers.get("content-length")
            expected = int(cl) if cl and cl.isdigit() else None
            with open(tmp, "wb") as fh:
                async for chunk in resp.aiter_bytes(1 << 16):
                    fh.write(chunk)
                    written += len(chunk)
    if written == 0:
        _rm(tmp)
        raise SourcingError(f"empty download for {candidate.source}:{candidate.asset_id}")
    if expected is not None and written != expected:
        _rm(tmp)
        raise SourcingError(
            f"truncated download {candidate.source}:{candidate.asset_id} "
            f"({written} of {expected} bytes)")
    os.replace(tmp, dst)
    return dst


def _rm(path: str) -> None:
    if os.path.exists(path):
        os.remove(path)
