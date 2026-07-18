"""Offline (zero-network) verification for Slice 4 — no API, no downloads over the wire, no spend.

A FakeStockProvider returns canned candidates; the download step is monkeypatched to copy local
`ffmpeg lavfi`-generated clips (so the REAL gate runs). Proves: deterministic query fallback (no LLM),
metadata ranking + threshold, fail-loud NoMatch, the gate's SILENT-clip branch (passes) + hiss
rejection (→ next candidate → winner), the cache hit (winner not re-fetched), and logged provenance.

Run: POSTGRES_HOST=localhost POSTGRES_PORT=5433 ./.venv/bin/python -m scripts.verify_slice4
"""
from __future__ import annotations

import asyncio
import os
import shutil
import subprocess
import sys
import tempfile

import psycopg
from psycopg.rows import dict_row

from ytagent import repo
from ytagent.assembly.ffmpeg import FFMPEG
from ytagent.config import load_settings
from ytagent.metadata.guard import scan
from ytagent.migrations.runner import run_migrations
from ytagent.seed import run_seed
from ytagent.sourcing import NoMatch, SourcedAsset, orchestrator, to_clip
from ytagent.sourcing.base import Candidate
from ytagent.sourcing.gate import gate_download
from ytagent.sourcing.query import build_query_plan
from ytagent.sourcing.rank import MATCH_THRESHOLD, rank_candidates

PASS, FAIL = "✅", "❌"
_failures = 0


def check(label: str, ok: bool, detail: str = "") -> None:
    global _failures
    print(f"  {PASS if ok else FAIL} {label}{(' — ' + detail) if detail else ''}")
    if not ok:
        _failures += 1


def _lavfi(path: str, *, size: str, audio: str | None) -> None:
    args = [FFMPEG, "-y", "-f", "lavfi", "-i", f"color=c=gray:s={size}:d=3:r=24"]
    if audio:
        args += ["-f", "lavfi", "-i", audio, "-shortest", "-c:a", "aac"]
    else:
        args += ["-an"]
    args += ["-c:v", "libx264", "-pix_fmt", "yuv420p", path]
    subprocess.run(args, capture_output=True, check=True)


def _cand(source, aid, *, w, h, tags, dl, dur=12.0) -> Candidate:
    return Candidate(source=source, asset_id=aid,
                     page_url=f"https://example.test/{source}/{aid}/", download_url=dl,
                     licence="Test License", width=w, height=h, contributor="Tester",
                     duration=dur, tags=tuple(tags), title=" ".join(tags), raw={"id": aid})


class FakeProvider:
    def __init__(self, cands): self._cands = cands; self.searches = 0
    def name(self): return "fake"
    def rate_limit(self): return {}
    async def healthcheck(self): return True
    async def search(self, query, *, orientation, min_duration, per_page=15):
        self.searches += 1
        return list(self._cands)


async def run() -> None:
    settings = load_settings()
    run_migrations(settings)
    run_seed()
    work = tempfile.mkdtemp(prefix="slice4-")
    clean = os.path.join(work, "clean.mp4"); hissy = os.path.join(work, "hissy.mp4")
    portrait = os.path.join(work, "portrait.mp4")
    _lavfi(clean, size="1920x1080", audio=None)                       # landscape, SILENT
    _lavfi(hissy, size="1920x1080", audio="anoisesrc=color=white:amplitude=0.6:d=3")  # loud hiss
    _lavfi(portrait, size="1080x1920", audio=None)                    # wrong orientation

    conn = await psycopg.AsyncConnection.connect(settings.dsn(), row_factory=dict_row, autocommit=True)
    ch = await repo.channels.get_by_slug(conn, "wildlife")
    cache = os.path.join(work, "cache")
    # idempotent: drop any test rows from a prior run so the fetch/cache assertions are clean
    await conn.execute("DELETE FROM sourced_assets WHERE source='pixabay' AND asset_id IN ('hi','lo')")

    # monkeypatch the network download → copy the local clip; count fetches per asset
    fetches: list[str] = []
    async def fake_download(candidate, dst_dir, *, ext="mp4"):
        os.makedirs(dst_dir, exist_ok=True)
        dst = os.path.join(dst_dir, f"{candidate.asset_id}.mp4")
        shutil.copy(candidate.download_url, dst)
        fetches.append(candidate.asset_id)
        return dst
    orchestrator.download = fake_download

    try:
        print("[1] query plan: deterministic (no LLM), orientation + duration from code")
        plan = build_query_plan("Wide aerial shot of an emperor penguin colony on the Antarctic ice",
                                approx_seconds=40, target_fmt="16:9", llm=None)
        check("queries extracted deterministically", len(plan.queries) >= 1, str(plan.queries))
        check("orientation from 16:9 → landscape", plan.orientation == "landscape")
        check("min_seconds from the beat", plan.min_seconds == 40)
        check("9:16 → portrait", build_query_plan("x", approx_seconds=5, target_fmt="9:16").orientation == "portrait")

        print("[2] metadata ranking + threshold")
        p = build_query_plan("emperor penguin colony ice", approx_seconds=10, target_fmt="16:9")
        good = _cand("pixabay", "1", w=1920, h=1080, tags=["emperor", "penguin", "colony", "ice"], dl=clean)
        wrong_o = _cand("pixabay", "2", w=1080, h=1920, tags=["emperor", "penguin", "ice"], dl=portrait)
        off_topic = _cand("pixabay", "3", w=1920, h=1080, tags=["city", "traffic", "night"], dl=clean)
        ranked = rank_candidates([off_topic, wrong_o, good], p, target_w=1920, target_h=1080)
        check("best candidate is the on-topic landscape one", ranked[0][1].asset_id == "1",
              f"top={ranked[0][1].asset_id} score={ranked[0][0]}")
        check("on-topic clears MATCH_THRESHOLD", ranked[0][0] >= MATCH_THRESHOLD, str(ranked[0][0]))
        check("wrong-orientation scores below the winner",
              next(s for s, c, _ in ranked if c.asset_id == "2") < ranked[0][0])
        check("off-topic falls below threshold",
              next(s for s, c, _ in ranked if c.asset_id == "3") < MATCH_THRESHOLD)
        chicken = _cand("pixabay", "4", w=1920, h=1080, tags=["bird", "chick", "feather", "farm"], dl=clean)
        r_ch = rank_candidates([chicken], p, target_w=1920, target_h=1080)
        check("candidate MISSING the subject term is disqualified (the 'chicken' case)",
              r_ch[0][0] == 0.0, f"must_terms={p.must_terms} score={r_ch[0][0]}")

        print("[3] the gate: SILENT clip passes, HISS rejected, wrong orientation rejected")
        gs = gate_download(clean, orientation="landscape")
        check("clean SILENT landscape clip PASSES (no-audio branch)", gs.ok, str(gs.reasons))
        check("silent clip has no noise result (skipped, not failed)", gs.noise is None)
        gh = gate_download(hissy, orientation="landscape")
        check("hissy clip FAILS the gate (noise)", not gh.ok and any("noise" in r for r in gh.reasons),
              "; ".join(gh.reasons))
        gp = gate_download(portrait, orientation="landscape")
        check("portrait clip FAILS the gate (orientation)", not gp.ok and any("orientation" in r for r in gp.reasons))

        print("[4] orchestrator: rank → hiss rejected → next → clean winner (offline)")
        hi = _cand("pixabay", "hi", w=3840, h=2160, tags=["emperor", "penguin", "ice"], dl=hissy)   # ranks first (res)
        lo = _cand("pixabay", "lo", w=1920, h=1080, tags=["emperor", "penguin", "ice"], dl=clean)
        res = await orchestrator.source_for_brief(
            conn, [FakeProvider([hi, lo])], brief="emperor penguin on ice", brief_ref="penguin:beat1",
            approx_seconds=10, target_fmt="16:9", target_w=1920, target_h=1080, cache_dir=cache,
            channel_id=ch["id"])
        check("returned a SourcedAsset (not NoMatch)", isinstance(res, SourcedAsset))
        check("winner is the CLEAN clip (hiss skipped)", isinstance(res, SourcedAsset) and res.asset_id == "lo")
        check("both hiss and clean were fetched (hiss tried first, rejected)",
              "hi" in fetches and "lo" in fetches, str(fetches))
        check("provenance is LOGGED with authoritative fields",
              res.provenance["provenance_source"] == "logged" and res.provenance["url"]
              and res.provenance["licence"] and res.provenance["downloaded_at"])
        row = await repo.sourcing.get_by_asset(conn, "pixabay", "lo")
        check("winner stored in sourced_assets (gate_pass)", row is not None and row["gate_pass"])
        check("to_clip() yields an assembly Clip", to_clip(res, approx_seconds=10).src == res.local_path)

        print("[5] cache hit — the winner is not re-fetched")
        fetches.clear()
        res2 = await orchestrator.source_for_brief(
            conn, [FakeProvider([lo])], brief="emperor penguin on ice", brief_ref="penguin:beat1",
            approx_seconds=10, target_fmt="16:9", target_w=1920, target_h=1080, cache_dir=cache,
            channel_id=ch["id"])
        check("second call returns cached=True", isinstance(res2, SourcedAsset) and res2.cached)
        check("no network fetch on the cache hit", fetches == [], str(fetches))

        print("[6] fail-loud NoMatch (empty results) + provenance stays out of public text")
        nm = await orchestrator.source_for_brief(
            conn, [FakeProvider([])], brief="something with no footage", brief_ref="penguin:beat9",
            approx_seconds=10, target_fmt="16:9", target_w=1920, target_h=1080, cache_dir=cache,
            channel_id=ch["id"])
        check("empty results → NoMatch (never padded)", isinstance(nm, NoMatch), getattr(nm, "reason", ""))
        check("guard still bans a manifest/provenance ref from public text",
              bool(scan("footage provenance in lion-doc-01-footage-manifest.md")))
    finally:
        await conn.close()

    print(f"\n{'ALL PASSED' if _failures == 0 else str(_failures) + ' CHECK(S) FAILED'}")
    sys.exit(1 if _failures else 0)


if __name__ == "__main__":
    asyncio.run(run())
