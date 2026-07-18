"""Pexels video provider. NOTE (honest limit): the /videos/search endpoint returns essentially no
tags — the searchable metadata is little more than the page-URL slug + the asset dimensions — so
keyword overlap is weak for Pexels (strong for Pixabay). Also: pexels.com (the website) 403s
programmatic requests from some IPs; `healthcheck()` probes the authenticated API endpoint and the
provider is dropped from the pool if it doesn't answer.
"""
from __future__ import annotations

import httpx

from .base import Candidate

_BASE = "https://api.pexels.com/videos"
_TIMEOUT = httpx.Timeout(30.0, connect=15.0)


def _pick_rendition(video_files: list[dict], tw: int, th: int) -> dict | None:
    mp4 = [f for f in video_files if (f.get("file_type") or "").endswith("mp4") and f.get("link")]
    if not mp4:
        return None
    fits = [f for f in mp4 if (f.get("width") or 0) >= tw and (f.get("height") or 0) >= th]
    if fits:   # smallest rendition that still meets the target
        return min(fits, key=lambda f: (f.get("width") or 0) * (f.get("height") or 0))
    return max(mp4, key=lambda f: (f.get("width") or 0) * (f.get("height") or 0))   # else the biggest


class PexelsProvider:
    def __init__(self, api_key: str, *, target_w: int = 1920, target_h: int = 1080) -> None:
        self._key = api_key
        self._tw, self._th = target_w, target_h
        self._rate: dict = {}

    def name(self) -> str:
        return "pexels"

    def rate_limit(self) -> dict:
        return dict(self._rate)

    def _headers(self) -> dict:
        return {"Authorization": self._key}

    async def healthcheck(self) -> bool:
        try:
            async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
                r = await client.get(f"{_BASE}/search", headers=self._headers(),
                                     params={"query": "test", "per_page": 1})
            return r.status_code == 200
        except Exception:  # noqa: BLE001
            return False

    async def search(self, query: str, *, orientation: str, min_duration: int,
                     per_page: int = 15) -> list[Candidate]:
        params = {"query": query, "orientation": orientation, "per_page": per_page}
        if min_duration:
            params["min_duration"] = int(min_duration)
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            r = await client.get(f"{_BASE}/search", headers=self._headers(), params=params)
        self._rate = {"remaining": r.headers.get("X-Ratelimit-Remaining"),
                      "reset": r.headers.get("X-Ratelimit-Reset")}
        r.raise_for_status()
        out: list[Candidate] = []
        for v in r.json().get("videos", []):
            rendition = _pick_rendition(v.get("video_files", []), self._tw, self._th)
            if not rendition:
                continue
            user = v.get("user") or {}
            page = v.get("url", "")
            out.append(Candidate(
                source="pexels", asset_id=str(v.get("id")), page_url=page,
                download_url=rendition["link"], licence="Pexels License",
                width=int(v.get("width") or rendition.get("width") or 0),
                height=int(v.get("height") or rendition.get("height") or 0),
                contributor=user.get("name"), duration=float(v.get("duration") or 0) or None,
                fps=None, title=page.rstrip("/").rsplit("/", 1)[-1].replace("-", " "),
                tags=(), raw=v,
            ))
        return out
