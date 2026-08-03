"""Shared httpx error helper — enforces `provider-error-standard.md`: when a raw httpx call fails,
carry the upstream provider's OWN response body through the exception instead of the bare
`raise_for_status()` (which raises the status line but drops the body that names the real cause)."""
from __future__ import annotations

import httpx


def raise_for_status_with_body(r: httpx.Response, context: str = "") -> None:
    """Raise on a non-2xx response INCLUDING the response body (the provider's actual message), so a
    caller/log sees why — not just the status code. No-op on success."""
    if r.is_success:
        return
    prefix = f"{context}: " if context else ""
    body = (r.text or "").strip()[:400]
    raise httpx.HTTPStatusError(
        f"{prefix}HTTP {r.status_code} for {r.request.method} {r.url}"
        + (f" — {body}" if body else ""),
        request=r.request, response=r)
