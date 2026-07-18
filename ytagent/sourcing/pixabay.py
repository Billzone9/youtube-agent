"""Pixabay video provider. Pixabay returns REAL comma-separated tags → keyword overlap works well
here. The video API has no orientation filter, so orientation is filtered client-side (and enforced
again by the gate). ToS asks that hits be cached ~24h — our permanent asset cache satisfies that.
"""
from __future__ import annotations

import httpx

from .base import Candidate, orientation_of

_BASE = "https://pixabay.com/api/videos/"
_TIMEOUT = httpx.Timeout(30.0, connect=15.0)


def _pick_rendition(videos: dict, tw: int, th: int) -> dict | None:
    renditions = [v for v in videos.values() if isinstance(v, dict) and v.get("url")]
    if not renditions:
        return None
    fits = [v for v in renditions if (v.get("width") or 0) >= tw and (v.get("height") or 0) >= th]
    if fits:
        return min(fits, key=lambda v: (v.get("width") or 0) * (v.get("height") or 0))
    return max(renditions, key=lambda v: (v.get("width") or 0) * (v.get("height") or 0))


class PixabayProvider:
    def __init__(self, api_key: str, *, target_w: int = 1920, target_h: int = 1080) -> None:
        self._key = api_key
        self._tw, self._th = target_w, target_h
        self._rate: dict = {}

    def name(self) -> str:
        return "pixabay"

    def rate_limit(self) -> dict:
        return dict(self._rate)

    async def healthcheck(self) -> bool:
        try:
            async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
                r = await client.get(_BASE, params={"key": self._key, "q": "test", "per_page": 3})
            return r.status_code == 200
        except Exception:  # noqa: BLE001
            return False

    async def search(self, query: str, *, orientation: str, min_duration: int,
                     per_page: int = 15) -> list[Candidate]:
        params = {"key": self._key, "q": query, "video_type": "film",
                  "per_page": max(3, per_page), "min_width": self._tw, "min_height": self._th}
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            r = await client.get(_BASE, params=params)
        self._rate = {"remaining": r.headers.get("X-RateLimit-Remaining"),
                      "reset": r.headers.get("X-RateLimit-Reset")}
        r.raise_for_status()
        out: list[Candidate] = []
        for h in r.json().get("hits", []):
            rendition = _pick_rendition(h.get("videos", {}), self._tw, self._th)
            if not rendition:
                continue
            w = int((h.get("videos", {}).get("large") or rendition).get("width") or rendition.get("width") or 0)
            ht = int((h.get("videos", {}).get("large") or rendition).get("height") or rendition.get("height") or 0)
            if orientation_of(w, ht) != orientation:      # no server-side orientation filter → do it here
                continue
            tags = tuple(t.strip() for t in (h.get("tags") or "").split(",") if t.strip())
            out.append(Candidate(
                source="pixabay", asset_id=str(h.get("id")), page_url=h.get("pageURL", ""),
                download_url=rendition["url"], licence="Pixabay Content License",
                width=w, height=ht, contributor=h.get("user"),
                duration=float(h.get("duration") or 0) or None, fps=None,
                title=", ".join(tags[:4]), tags=tags, raw=h,
            ))
        return out
