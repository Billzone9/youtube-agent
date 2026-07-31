"""Source candidate clips for a POSITIVE wild-grey-wolf calibration fixture. Searches the providers,
downloads several candidates, samples 3 frames each (the production path) into the scratchpad for human
review. Prints the shortlist with URLs. NOT a fixture chooser — Banks confirms which frames become the
fixture after viewing.

Run: POSTGRES_HOST=localhost POSTGRES_PORT=5433 ./.venv/bin/python -m scripts.source_wolf_fixture
"""
from __future__ import annotations

import asyncio
import os

from ytagent.config import load_settings
from ytagent.sourcing import get_stock_providers
from ytagent.sourcing.download import download
from ytagent.sourcing.vision import sample_frames

_OUT = ("/private/tmp/claude-501/-Users-banks-youtube-agent/"
        "821efde2-81e4-4c45-a72a-39a1c8a46be5/scratchpad/wolf_candidates")
_QUERIES = ["grey wolf snow", "wild wolf winter", "wolf pack snow", "grey wolf forest"]
_MAX = 10


async def main():
    settings = load_settings()
    providers = [p for p in get_stock_providers(settings) if await p.healthcheck()]
    if not providers:
        print("no stock providers configured")
        return
    os.makedirs(_OUT, exist_ok=True)

    seen, cands = set(), []
    for prov in providers:
        for q in _QUERIES:
            try:
                found = await prov.search(q, orientation="landscape", min_duration=5)
            except Exception as e:  # noqa: BLE001
                print(f"  search {prov.name()} '{q}' failed: {e}")
                continue
            for c in found:
                key = (c.source, c.asset_id)
                if key in seen:
                    continue
                seen.add(key)
                cands.append((q, c))
    print(f"found {len(cands)} distinct candidates; downloading up to {_MAX} + sampling 3 frames each\n")

    n = 0
    for q, c in cands:
        if n >= _MAX:
            break
        try:
            path = await download(c, os.path.join(_OUT, "clips"))
        except Exception as e:  # noqa: BLE001
            continue
        d = os.path.join(_OUT, f"{c.source}_{c.asset_id}")
        frames = sample_frames(path, d, n=3)
        if len(frames) < 2:
            continue
        n += 1
        print(f"[{n}] {c.source}:{c.asset_id}  q='{q}'  {c.width}x{c.height} {c.duration}s")
        print(f"     {c.page_url}")
        print(f"     tags: {', '.join(c.tags[:10])}")
        print(f"     frames: {d}/")
    print(f"\nsampled {n} candidates into {_OUT}/")


if __name__ == "__main__":
    asyncio.run(main())
