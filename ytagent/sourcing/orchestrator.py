"""Sourcing orchestration — the fail-loud pipeline. Per shot-brief:
  build query plan → search all providers × queries → rank (metadata only) → take the top-K above
  MATCH_THRESHOLD → download each in rank order → gate → the FIRST clean winner wins (cached +
  provenance-logged). If nothing clears the threshold, results are empty, or every top-K candidate
  fails the gate → a `NoMatch` is returned (never a padded bad clip) and logged to events.
"""
from __future__ import annotations

import os

from .. import repo
from ..assembly import qc
from ..events import record_event
from .base import Candidate, GateResult, NoMatch, SourcedAsset
from .download import download
from .gate import gate_download
from .provenance import build_asset_provenance
from .query import build_query_plan
from .rank import MATCH_THRESHOLD, rank_candidates


async def _search_all(providers, plan, conn, channel_id) -> dict[tuple[str, str], tuple[Candidate, str]]:
    """{(source, asset_id): (candidate, query_that_found_it)} — deduped across providers × queries."""
    seen: dict[tuple[str, str], tuple[Candidate, str]] = {}
    for prov in providers:
        for q in plan.queries:
            try:
                cands = await prov.search(q, orientation=plan.orientation,
                                          min_duration=plan.min_seconds)
            except Exception as e:  # noqa: BLE001 — a failed search shouldn't kill the run
                await record_event(conn, "sourcing.search_error", message=f"{prov.name()} '{q}': {e}",
                                   channel_id=channel_id)
                continue
            await record_event(conn, "sourcing.search",
                               message=f"{prov.name()} '{q}' → {len(cands)}",
                               channel_id=channel_id, data={"remaining": prov.rate_limit()})
            for c in cands:
                seen.setdefault((c.source, c.asset_id), (c, q))
    return seen


async def _promote(conn, *, channel_id, job_id, candidate: Candidate, gate: GateResult, path: str,
                   score: float, brief_ref: str, query_used: str, cached: bool) -> SourcedAsset:
    prov = build_asset_provenance(candidate, gate, path)
    if not cached:
        await repo.sourcing.upsert(
            conn, channel_id=channel_id, source=candidate.source, asset_id=candidate.asset_id,
            job_id=job_id, url=candidate.page_url, contributor=candidate.contributor,
            licence=candidate.licence, local_path=path,
            width=gate.probe.get("width"), height=gate.probe.get("height"),
            duration_s=gate.probe.get("duration"), fps=gate.probe.get("fps"),
            orientation=candidate.orientation, title=candidate.title, tags=list(candidate.tags),
            size_bytes=os.path.getsize(path), checksum=qc.sha256(path), gate_pass=True,
            gate_report={"probe": gate.probe, "reasons": list(gate.reasons)},
            shot_brief_ref=brief_ref, query_used=query_used, api_response=candidate.raw,
        )
        await record_event(conn, "sourcing.sourced",
                           message=f"{brief_ref} ← {candidate.source}:{candidate.asset_id} (score {score})",
                           channel_id=channel_id, job_id=job_id, data={"url": candidate.page_url})
    return SourcedAsset(source=candidate.source, asset_id=candidate.asset_id, local_path=path,
                        candidate=candidate, gate=gate, provenance=prov, score=score, cached=cached)


async def _acquire(conn, *, channel_id, job_id, cand: Candidate, score: float, brief_ref: str,
                   query_used: str, cache_dir: str, orientation: str) -> SourcedAsset | None:
    """Resolve one ranked candidate to a clean SourcedAsset (cache hit or download+gate), or None if
    it can't be obtained. A rejected download is never kept."""
    row = await repo.sourcing.get_by_asset(conn, cand.source, cand.asset_id)
    if row and os.path.exists(row["local_path"]):            # cache hit — no network, no re-gate
        gate = GateResult(ok=True, probe=(row.get("gate_report") or {}).get("probe", {}))
        return await _promote(conn, channel_id=channel_id, job_id=job_id, candidate=cand, gate=gate,
                              path=row["local_path"], score=score, brief_ref=brief_ref,
                              query_used=query_used, cached=True)
    try:
        path = await download(cand, os.path.join(cache_dir, cand.source))
    except Exception as e:  # noqa: BLE001 — a failed download → caller tries the next candidate
        await record_event(conn, "sourcing.download_error",
                           message=f"{cand.source}:{cand.asset_id}: {e}", channel_id=channel_id)
        return None
    gate = gate_download(path, orientation=orientation)
    if gate.ok:
        return await _promote(conn, channel_id=channel_id, job_id=job_id, candidate=cand, gate=gate,
                              path=path, score=score, brief_ref=brief_ref, query_used=query_used,
                              cached=False)
    await record_event(conn, "sourcing.rejected",
                       message=f"{cand.source}:{cand.asset_id} gate fail: {'; '.join(gate.reasons)}",
                       channel_id=channel_id, data={"reasons": list(gate.reasons)})
    if os.path.exists(path):
        os.remove(path)   # a rejected download is never kept
    return None


async def _rank_eligible(conn, providers, plan, *, channel_id, target_w, target_h):
    """Search + rank + threshold. Returns (eligible[(score,cand,bd)], seen, considered_summary)."""
    seen = await _search_all(providers, plan, conn, channel_id)
    ranked = rank_candidates([c for c, _ in seen.values()], plan, target_w=target_w, target_h=target_h)
    considered = tuple((round(s, 3), c.asset_id) for s, c, _ in ranked[:8])
    eligible = [(s, c, bd) for s, c, bd in ranked if s >= MATCH_THRESHOLD]
    best = ranked[0][0] if ranked else 0.0
    return eligible, seen, considered, best


async def source_for_brief(conn, providers, *, brief: str, brief_ref: str, approx_seconds: int,
                           target_fmt: str, target_w: int, target_h: int, cache_dir: str,
                           channel_id: int, job_id: int | None = None, llm=None, top_k: int = 3
                           ) -> SourcedAsset | NoMatch:
    plan = build_query_plan(brief, approx_seconds=approx_seconds, target_fmt=target_fmt, llm=llm)
    eligible, seen, considered, best = await _rank_eligible(
        conn, providers, plan, channel_id=channel_id, target_w=target_w, target_h=target_h)
    if not eligible:
        reason = "no candidates" if best == 0.0 else f"best {best:.2f} < {MATCH_THRESHOLD}"
        await record_event(conn, "sourcing.no_match", message=f"{brief_ref}: {reason}",
                           channel_id=channel_id, job_id=job_id, data={"considered": list(considered)})
        return NoMatch(shot_brief_ref=brief_ref, reason=reason, considered=considered)

    for score, cand, _ in eligible[:top_k]:
        query_used = seen[(cand.source, cand.asset_id)][1]
        asset = await _acquire(conn, channel_id=channel_id, job_id=job_id, cand=cand, score=score,
                               brief_ref=brief_ref, query_used=query_used, cache_dir=cache_dir,
                               orientation=plan.orientation)
        if asset is not None:
            return asset

    reason = f"all top-{top_k} candidates failed the gate"
    await record_event(conn, "sourcing.no_match", message=f"{brief_ref}: {reason}",
                       channel_id=channel_id, job_id=job_id, data={"considered": list(considered)})
    return NoMatch(shot_brief_ref=brief_ref, reason=reason, considered=considered)


async def source_clips_for_brief(conn, providers, *, brief: str, brief_ref: str, approx_seconds: int,
                                 target_fmt: str, target_w: int, target_h: int, cache_dir: str,
                                 channel_id: int, job_id: int | None = None, llm=None,
                                 n_target: int, n_min: int, exclude_ids: set | None = None,
                                 ) -> list[SourcedAsset] | NoMatch:
    """Fill ONE beat with up to `n_target` DISTINCT clean clips for the visual-density standard.
    Walks the eligible list in rank order, skipping `exclude_ids` (video-wide no-repeat) and any id
    already taken for this beat, acquiring each until `n_target` are held. Returns the list if at least
    `n_min` distinct clips were obtained, else a `NoMatch` (a beat is NEVER padded with one stretched
    clip). Bandwidth-bounded so a thin brief can't download endlessly."""
    exclude = set(exclude_ids or ())
    plan = build_query_plan(brief, approx_seconds=approx_seconds, target_fmt=target_fmt, llm=llm)
    eligible, seen, considered, best = await _rank_eligible(
        conn, providers, plan, channel_id=channel_id, target_w=target_w, target_h=target_h)

    winners: list[SourcedAsset] = []
    taken: set[tuple[str, str]] = set()
    attempts, max_attempts = 0, n_target * 2 + 8
    for score, cand, _ in eligible:
        if len(winners) >= n_target or attempts >= max_attempts:
            break
        key = (cand.source, cand.asset_id)
        if key in exclude or key in taken:                   # no-repeat: video-wide + within-beat
            continue
        attempts += 1
        query_used = seen[key][1]
        asset = await _acquire(conn, channel_id=channel_id, job_id=job_id, cand=cand, score=score,
                               brief_ref=brief_ref, query_used=query_used, cache_dir=cache_dir,
                               orientation=plan.orientation)
        if asset is not None:
            winners.append(asset)
            taken.add(key)

    if len(winners) >= n_min:
        await record_event(conn, "sourcing.beat_sourced",
                           message=f"{brief_ref}: {len(winners)} distinct clips (min {n_min}, target {n_target})",
                           channel_id=channel_id, job_id=job_id,
                           data={"asset_ids": [w.asset_id for w in winners]})
        return winners
    reason = (f"only {len(winners)} distinct clips (need ≥{n_min}) — "
              + ("no candidates" if best == 0.0 else f"best {best:.2f}"))
    await record_event(conn, "sourcing.no_match", message=f"{brief_ref}: {reason}",
                       channel_id=channel_id, job_id=job_id, data={"considered": list(considered)})
    return NoMatch(shot_brief_ref=brief_ref, reason=reason, considered=considered)


async def source_shot_briefs(conn, providers, briefs, *, target_fmt: str, target_w: int, target_h: int,
                             cache_dir: str, channel_id: int, job_id: int | None = None, llm=None
                             ) -> list[SourcedAsset | NoMatch]:
    """`briefs` = iterable of (brief_ref, brief_text, approx_seconds)."""
    out: list[SourcedAsset | NoMatch] = []
    for brief_ref, brief, approx in briefs:
        out.append(await source_for_brief(
            conn, providers, brief=brief, brief_ref=brief_ref, approx_seconds=approx,
            target_fmt=target_fmt, target_w=target_w, target_h=target_h, cache_dir=cache_dir,
            channel_id=channel_id, job_id=job_id, llm=llm))
    return out
