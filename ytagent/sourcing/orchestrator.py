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
from . import vision as _vision
from .query import build_query_plan
from .rank import MATCH_THRESHOLD, rank_candidates


async def _search_all(providers, plan, conn, channel_id, *, per_page: int = 15, pages: int = 1
                      ) -> dict[tuple[str, str], tuple[Candidate, str]]:
    """{(source, asset_id): (candidate, query_that_found_it)} — deduped across providers × queries ×
    pages. `pages`>1 walks the provider pagination (film-wide reach); a page returning nothing stops
    that query's paging early (no wasted calls past the tail)."""
    seen: dict[tuple[str, str], tuple[Candidate, str]] = {}
    for prov in providers:
        for q in plan.queries:
            for page in range(1, max(1, pages) + 1):
                try:
                    cands = await prov.search(q, orientation=plan.orientation,
                                              min_duration=plan.min_seconds, per_page=per_page, page=page)
                except Exception as e:  # noqa: BLE001 — a failed search shouldn't kill the run
                    await record_event(conn, "sourcing.search_error",
                                       message=f"{prov.name()} '{q}' p{page}: {e}", channel_id=channel_id)
                    break
                await record_event(conn, "sourcing.search",
                                   message=f"{prov.name()} '{q}' p{page} → {len(cands)}",
                                   channel_id=channel_id, data={"remaining": prov.rate_limit()})
                for c in cands:
                    seen.setdefault((c.source, c.asset_id), (c, q))
                if not cands:                                # past the tail — stop paging this query
                    break
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


async def _rank_eligible(conn, providers, plan, *, channel_id, target_w, target_h, negative_terms=None):
    """Search + rank + threshold. Returns (eligible[(score,cand,bd)], seen, considered_summary)."""
    seen = await _search_all(providers, plan, conn, channel_id)
    ranked = rank_candidates([c for c, _ in seen.values()], plan, target_w=target_w, target_h=target_h,
                             negative_terms=negative_terms)
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
                                 vision: bool = True, required_axes: frozenset | None = None,
                                 negative_terms=None, collect_verdicts: list | None = None,
                                 subject: str | None = None,
                                 ) -> list[SourcedAsset] | NoMatch:
    """Fill ONE beat with up to `n_target` DISTINCT clean, CONTENT-VERIFIED clips (visual-density
    standard). Walks the eligible list in rank order, skipping `exclude_ids` (video-wide no-repeat) and
    any id already taken; each acquired clip must also pass the VISION GATE (species/wild/season) when
    `vision` and an `llm` are available. Returns the list if ≥ `n_min` verified clips were obtained,
    else a `NoMatch` (a beat is NEVER padded with one stretched or off-brief clip)."""
    import tempfile

    if vision and llm is None:            # Item 6 — FAIL LOUD: a silently-skipped content gate is worse
        raise _vision.VisionUnavailable(  # than none. Only an EXPLICIT vision=False may skip it.
            "vision gate required but no LLM configured — set ANTHROPIC_API_KEY or pass vision=False.")

    exclude = set(exclude_ids or ())
    plan = build_query_plan(brief, approx_seconds=approx_seconds, target_fmt=target_fmt, llm=llm,
                            subject=subject)
    expect = _vision.Expect.from_plan(plan, required=required_axes)
    eligible, seen, considered, best = await _rank_eligible(
        conn, providers, plan, channel_id=channel_id, target_w=target_w, target_h=target_h,
        negative_terms=negative_terms)

    clear: list[SourcedAsset] = []                          # clear_match on every required axis → accept
    reserve: list[SourcedAsset] = []                        # 'uncertain' on an identity axis → held back
    verdicts: list[dict] = []
    taken: set[tuple[str, str]] = set()
    contradictions = 0
    attempts, max_attempts = 0, n_target * 3 + 10           # the gate rejects some, so allow more attempts
    for score, cand, _ in eligible:
        if len(clear) >= n_target or attempts >= max_attempts:
            break
        key = (cand.source, cand.asset_id)
        if key in exclude or key in taken:                   # no-repeat: video-wide + within-beat
            continue
        attempts += 1
        query_used = seen[key][1]
        asset = await _acquire(conn, channel_id=channel_id, job_id=job_id, cand=cand, score=score,
                               brief_ref=brief_ref, query_used=query_used, cache_dir=cache_dir,
                               orientation=plan.orientation)
        if asset is None:
            continue
        category = "clear"
        if vision and llm is not None:                       # CONTENT check — three-way identity + setting
            with tempfile.TemporaryDirectory(prefix="vgate-") as vd:
                frames = _vision.sample_frames(asset.local_path, vd)
                v = _vision.vision_check(frames, expect=expect, llm=llm,
                                         channel_id=channel_id, job_id=job_id)
            category, drivers = _vision.classify(v, expect)
            rec = {"asset_id": cand.asset_id, "url": cand.page_url, "category": category,
                   "species": v.species, "wild": v.wild, "season": v.season_ok, "habitat": v.habitat_ok,
                   "time": v.time_ok, "drivers": list(drivers), "contradiction": v.contradiction,
                   "features": v.features, "features_indicate": v.features_indicate,
                   "season_obs": v.season_observed, "habitat_obs": v.habitat_observed,
                   "time_obs": v.time_observed, "shot_type": v.shot_type,
                   "used": False, "reason": v.reason}
            verdicts.append(rec)
            if collect_verdicts is not None:
                collect_verdicts.append(rec)
            if v.contradiction:                              # gate fighting its own evidence — loud + counted
                contradictions += 1
                await record_event(conn, "sourcing.vision_contradiction",
                                   message=f"{brief_ref} ⚠ {cand.source}:{cand.asset_id} — features "
                                           f"'{v.features_indicate}' vs species={v.species}: {v.reason}",
                                   channel_id=channel_id, job_id=job_id, data={"verdict": rec})
            if category == "reject":
                await record_event(conn, "sourcing.vision_reject",
                                   message=f"{brief_ref} ✗ {cand.source}:{cand.asset_id} — "
                                           f"{','.join(drivers)}: {v.reason}",
                                   channel_id=channel_id, job_id=job_id, data={"verdict": rec})
                continue
        (clear if category == "clear" else reserve).append(asset)
        taken.add(key)

    # SELF-CHECKS on the gate's reasoning (not the footage): (a) CLIP-vs-CLIP echo — near-identical
    # features but DIFFERENT verdicts (same evidence, different answer); (b) DEFINITION-echo — features
    # reciting a canned definition rather than describing the image. Both surfaced; (a) is a hard signal.
    echo_pairs = _vision.detect_echo(
        [(v["asset_id"], v.get("features", ""), v.get("species")) for v in verdicts])
    if echo_pairs:
        await record_event(conn, "sourcing.prompt_echo",
                           message=f"{brief_ref}: {len(echo_pairs)} near-identical features across "
                                   "DIFFERENT verdicts — gate gave different answers to the same evidence",
                           channel_id=channel_id, job_id=job_id, data={"pairs": echo_pairs})

    # POLICY: fill from CLEAR first; draw the UNCERTAIN reserve ONLY to reach n_min, flagging each used.
    winners = clear[:n_target]
    uncertain_used: list[str] = []
    if len(winners) < n_min:
        for asset in reserve:
            if len(winners) >= n_min:
                break
            winners.append(asset)
            uncertain_used.append(asset.asset_id)
    used_ids = {w.asset_id for w in winners}
    for rec in verdicts:                                     # mark which verdicts became winners
        rec["used"] = rec["asset_id"] in used_ids

    if len(winners) >= n_min:
        await record_event(conn, "sourcing.beat_sourced",
                           message=f"{brief_ref}: {len(winners)} clips ({len(clear)} clear, "
                                   f"{len(uncertain_used)} uncertain-used; min {n_min}, target {n_target}; "
                                   f"{contradictions} contradiction, {len(echo_pairs)} echo)",
                           channel_id=channel_id, job_id=job_id,
                           data={"asset_ids": [w.asset_id for w in winners],
                                 "uncertain_used": uncertain_used, "contradictions": contradictions,
                                 "echo_pairs": echo_pairs, "verdicts": verdicts})
        return winners
    n_reject = sum(1 for v in verdicts if v["category"] == "reject")
    n_unc = sum(1 for v in verdicts if v["category"] == "uncertain")
    reason = (f"only {len(clear)} clear + {n_unc} uncertain (need ≥{n_min}) — "
              + ("no candidates" if best == 0.0 else f"best {best:.2f}")
              + (f", {n_reject} rejected by the gate" if n_reject else "")
              + (f", {contradictions} contradiction(s)" if contradictions else "")
              + (f", {len(echo_pairs)} prompt-echo" if echo_pairs else ""))
    await record_event(conn, "sourcing.no_match", message=f"{brief_ref}: {reason}",
                       channel_id=channel_id, job_id=job_id,
                       data={"considered": list(considered), "verdicts": verdicts,
                             "contradictions": contradictions, "echo_pairs": echo_pairs})
    return NoMatch(shot_brief_ref=brief_ref, reason=reason, considered=considered)


import re as _re

_FIT_W = _re.compile(r"[a-z][a-z-]+")
_FIT_STOP = frozenset((
    "the", "and", "with", "into", "from", "that", "this", "then", "over", "under", "across", "toward",
    "towards", "shot", "wide", "medium", "close", "closeup", "slow", "pan", "aerial", "drone", "view",
    "angle", "footage", "clip", "scene", "held", "available", "movement", "moving", "walking", "essential",
    "required", "throughout", "welcome", "sense", "show", "showing", "against", "front", "behind",
))


def _fit_tokens(text: str) -> set[str]:
    return {w for w in _FIT_W.findall((text or "").lower()) if len(w) > 3 and w not in _FIT_STOP}


def _fit_score(asset: SourcedAsset, brief_tokens: set[str]) -> int:
    """How well a verified clip suits a beat: overlap of the clip's tags/title with the beat's content
    words. All clips already PASS species+wild, so this only steers WHICH beat each goes to — it never
    rejects. Ties are broken by the clip's own match score (handled by the caller's stable sort)."""
    c = asset.candidate
    ct = _fit_tokens(" ".join(c.tags)) | _fit_tokens(c.title)
    return len(brief_tokens & ct)


def _allocate_pool(pool: list[SourcedAsset], beats: list[dict]) -> dict[int, list[SourcedAsset]]:
    """Distribute ONE verified film-wide pool across beats so none is starved. Two passes: first bring
    EVERY beat up to its n_min (neediest-first, best-fit), then fill toward n_target. A clip is used
    once. Best-fit steers a 'calf' clip to the calf beat, a 'dusk' clip to the closing beat — but every
    clip fits the film (all passed species+wild), so an imperfect fit still lands somewhere useful."""
    tokens = {b["index"]: _fit_tokens(b["brief"]) for b in beats}
    assigned: dict[int, list[SourcedAsset]] = {b["index"]: [] for b in beats}
    remaining = list(pool)                                   # pool is pre-sorted best-score-first
    for phase in ("n_min", "n_target"):
        moved = True
        while moved and remaining:
            moved = False
            for b in beats:
                cap = b[phase]
                if len(assigned[b["index"]]) >= cap or not remaining:
                    continue
                best = max(remaining, key=lambda a: _fit_score(a, tokens[b["index"]]))
                assigned[b["index"]].append(best)
                remaining.remove(best)
                moved = True
    return assigned


async def source_film(conn, providers, *, subject: str, beats: list[dict], target_fmt: str,
                      target_w: int, target_h: int, cache_dir: str, channel_id: int,
                      job_id: int | None = None, llm=None, required_axes: frozenset | None = None,
                      negative_terms=None, per_page: int = 50, pages: int = 2, max_verify: int = 90,
                      exclude_ids: set | None = None) -> tuple[dict[int, list[SourcedAsset]], dict]:
    """FILM-WIDE sourcing + allocation — the structural fix for beat-by-beat depletion. `beats` is a
    list of {index, label, brief, n_min, n_target, approx_seconds}. Builds ONE candidate pool from the
    UNION of every beat's SUBJECT-ANCHORED query set (the film subject is forced into every query, so a
    scene-only brief like 'the herd crossing' can no longer surface muskox/sheep), searched with deeper
    per_page + pagination for reach, verifies each DISTINCT candidate through the vision gate exactly
    ONCE (species+wild; setting OBSERVED, not gated — the script is written to the distribution), then
    ALLOCATES the verified pool across beats by fit so no earlier beat starves a later one. Returns
    (allocation {index: [SourcedAsset]}, report)."""
    import tempfile

    if llm is None:
        raise _vision.VisionUnavailable(
            "vision gate required but no LLM configured for source_film — set ANTHROPIC_API_KEY.")
    exclude = set(exclude_ids or ())
    expect = _vision.Expect(subject=subject, required=frozenset(required_axes or ()))

    # 1) UNION query set across beats (each plan carries the FILM subject), searched wide + deep.
    union: dict[tuple[str, str], tuple[Candidate, str]] = {}
    orientation = "portrait" if target_fmt == "9:16" else "landscape"
    for b in beats:
        plan = build_query_plan(b["brief"], approx_seconds=int(b.get("approx_seconds") or 0),
                                target_fmt=target_fmt, llm=llm, subject=subject)
        seen = await _search_all(providers, plan, conn, channel_id, per_page=per_page, pages=pages)
        for k, v in seen.items():
            union.setdefault(k, v)

    # 2) Rank the whole pool against the FILM subject, keep everything above threshold.
    film_plan = build_query_plan(subject, approx_seconds=0, target_fmt=target_fmt, subject=subject)
    ranked = rank_candidates([c for c, _ in union.values()], film_plan,
                             target_w=target_w, target_h=target_h, negative_terms=negative_terms)
    eligible = [(s, c) for s, c, _ in ranked if s >= MATCH_THRESHOLD]
    considered = tuple((round(s, 3), c.asset_id) for s, c in eligible[:12])

    # 3) Verify each DISTINCT candidate ONCE (species+wild). clear → pool; uncertain → reserve.
    clear: list[SourcedAsset] = []
    reserve: list[SourcedAsset] = []
    verdicts: list[dict] = []
    contradictions = 0
    verified = 0
    for score, cand in eligible:
        if verified >= max_verify:
            break
        key = (cand.source, cand.asset_id)
        if key in exclude:
            continue
        asset = await _acquire(conn, channel_id=channel_id, job_id=job_id, cand=cand, score=score,
                               brief_ref=f"film:{subject}", query_used=union[key][1],
                               cache_dir=cache_dir, orientation=orientation)
        if asset is None:
            continue
        verified += 1
        with tempfile.TemporaryDirectory(prefix="vgate-") as vd:
            frames = _vision.sample_frames(asset.local_path, vd)
            v = _vision.vision_check(frames, expect=expect, llm=llm, channel_id=channel_id, job_id=job_id)
        category, drivers = _vision.classify(v, expect)
        rec = {"asset_id": cand.asset_id, "url": cand.page_url, "category": category,
               "species": v.species, "wild": v.wild, "season": v.season_ok, "habitat": v.habitat_ok,
               "time": v.time_ok, "drivers": list(drivers), "contradiction": v.contradiction,
               "features": v.features, "features_indicate": v.features_indicate,
               "season_obs": v.season_observed, "habitat_obs": v.habitat_observed,
               "time_obs": v.time_observed, "shot_type": v.shot_type, "score": round(score, 3),
               "reason": v.reason}
        verdicts.append(rec)
        if v.contradiction:
            contradictions += 1
            await record_event(conn, "sourcing.vision_contradiction",
                               message=f"film:{subject} ⚠ {cand.source}:{cand.asset_id} — features "
                                       f"'{v.features_indicate}' vs species={v.species}: {v.reason}",
                               channel_id=channel_id, job_id=job_id, data={"verdict": rec})
        if category == "reject":
            await record_event(conn, "sourcing.vision_reject",
                               message=f"film:{subject} ✗ {cand.source}:{cand.asset_id} — "
                                       f"{','.join(drivers)}: {v.reason}",
                               channel_id=channel_id, job_id=job_id, data={"verdict": rec})
            continue
        (clear if category == "clear" else reserve).append(asset)

    # 4) ALLOCATE. Fill n_min from CLEAR first; only if the clear pool is short do we draw the reserve.
    beats = sorted(beats, key=lambda b: b["index"])
    alloc = _allocate_pool(clear, beats)
    total_min = sum(b["n_min"] for b in beats)
    if sum(len(v) for v in alloc.values()) < total_min and reserve:   # top up shortfall with reserve
        alloc = _allocate_pool(clear + reserve, beats)

    echo_pairs = _vision.detect_echo(
        [(v["asset_id"], v.get("features", ""), v.get("species")) for v in verdicts])
    accepted_ids = {a.asset_id for v in alloc.values() for a in v}
    for rec in verdicts:
        rec["used"] = rec["asset_id"] in accepted_ids

    beat_reports = []
    for b in beats:
        got = alloc[b["index"]]
        got_recs = [next((r for r in verdicts if r["asset_id"] == a.asset_id), {}) for a in got]
        beat_reports.append({
            "beat": b["index"], "label": b.get("label", ""), "narration_s": round(b.get("approx_seconds", 0), 1),
            "n_min": b["n_min"], "n_target": b["n_target"], "verified": len(got),
            "clear": sum(1 for r in got_recs if r.get("category") == "clear"),
            "reached_min": len(got) >= b["n_min"],
            "accepted": [{"asset_id": a.asset_id, "url": a.candidate.page_url} for a in got],
            "verdicts": got_recs,
        })

    n_reject = sum(1 for v in verdicts if v["category"] == "reject")
    report = {
        "subject": subject, "pool_candidates": len(union), "eligible": len(eligible),
        "verified": verified, "clear": len(clear), "reserve": len(reserve), "rejected": n_reject,
        "contradictions": contradictions, "echo_pairs": echo_pairs, "considered": list(considered),
        "verdicts": verdicts, "beats": beat_reports,
        "all_reached_min": all(br["reached_min"] for br in beat_reports),
        "allocated_total": sum(len(v) for v in alloc.values()),
    }
    await record_event(conn, "sourcing.film_pool",
                       message=f"film:{subject}: pool {len(union)} → {len(eligible)} eligible → "
                               f"{len(clear)} clear + {len(reserve)} reserve ({n_reject} rejected, "
                               f"{contradictions} contradiction) → allocated {report['allocated_total']}",
                       channel_id=channel_id, job_id=job_id,
                       data={k: report[k] for k in ("pool_candidates", "eligible", "verified", "clear",
                                                    "reserve", "rejected", "contradictions")})
    return alloc, report


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
