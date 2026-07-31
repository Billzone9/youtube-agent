"""Footage-feasibility probe — run BEFORE writing a word of script (the footage-led doctrine: source
first, write to fit). EXPLORATORY, not pass/fail against a pre-chosen setting: it supplies NO season/
habitat/time expectation; SPECIES and WILD are the only identity axes gated. It measures the candidate
POOL DEPTH, the wild-and-correct-species YIELD (against density-derived thresholds), and REPORTS the
DISTRIBUTION of the seasons / habitats / times / shot-types the pool actually contains — the raw
material a footage-led script is then written to. An overwhelmingly dry-season-midday pool is not a
failure; that is the film.

Thresholds (SPECIFY-1, a 4-beat ~150s film): Σn_min = 12 (floor), Σn_target × 1.25 = 20 (target).
"""
from __future__ import annotations

import os
import re
import tempfile
from dataclasses import dataclass, field

from ..assembly.density import film_thresholds, max_beats_for_yield
from ..events import record_event
from . import vision as _vision
from .base import QueryPlan
from .download import download
from .gate import gate_download
from .query import build_query_plan
from .rank import MATCH_THRESHOLD, rank_candidates

# Pool depth E measures SEARCH REACH, not library depth: a shallow E means "search harder", not
# "subject unavailable". Below this, the verdict is INCONCLUSIVE-SHALLOW (broaden + re-probe before
# believing any INFEASIBLE) — zebra returned 8 for one of the most-filmed animals on the plains.
MIN_POOL_DEPTH = 15

# Broad-mode query expansion — subject × scene vocabulary, to widen search reach past a narrow plan.
_SCENE_TERMS = ("", "herd", "wild", "safari", "savanna", "grassland", "africa", "walking", "running",
                "waterhole", "close up", "calf", "family", "portrait", "dust", "sunset")


def _broad_plan(subject: str, target_fmt: str) -> QueryPlan:
    s = subject.lower()
    head = [w for w in re.findall(r"[a-z]+", s) if len(w) > 2][-1:] or [s]
    short = head[0]                                   # 'african elephant' → 'elephant' (a wider net)
    queries = list(dict.fromkeys([s] + [f"{short} {t}".strip() for t in _SCENE_TERMS]))[:14]
    orient = "portrait" if target_fmt == "9:16" else "landscape"
    return QueryPlan(queries=tuple(queries), orientation=orient, min_seconds=8,
                     must_terms=(short,), subject=subject)

# Loose keyword buckets for the observed free-text setting labels → a readable distribution.
_SEASON_BUCKETS = {"snow/winter": ("snow", "winter", "frost", "ice"), "dry": ("dry",),
                   "wet/green": ("wet", "green", "lush", "monsoon", "rain"), "autumn": ("autumn", "fall")}
_HABITAT_BUCKETS = {"savanna/grassland": ("savanna", "savannah", "grassland", "plain", "steppe"),
                    "forest/woodland": ("forest", "wood", "jungle", "taiga"),
                    "waterhole/river": ("waterhole", "water hole", "river", "lake", "wetland", "swamp"),
                    "coast/ocean": ("coast", "ocean", "sea", "beach", "marine", "underwater"),
                    "tundra/arctic": ("tundra", "arctic", "snow"), "desert": ("desert", "arid"),
                    "mountain": ("mountain", "alpine"), "scrub/bush": ("scrub", "bush", "shrub")}
_TIME_BUCKETS = {"golden/dawn/dusk": ("golden", "dawn", "dusk", "sunrise", "sunset", "twilight"),
                 "day": ("day", "midday", "noon", "bright", "daylight"), "night": ("night", "nocturnal")}
_SHOT_BUCKETS = {"wide": ("wide", "establish", "landscape"), "medium": ("medium",),
                 "close": ("close",), "aerial/drone": ("aerial", "drone", "overhead"),
                 "underwater": ("underwater", "submerged")}


def _bucket(observed: str, buckets: dict) -> str:
    o = (observed or "").lower()
    for name, kws in buckets.items():
        if any(k in o for k in kws):
            return name
    return "unclear"


def _distribution(verdicts: list, axis_key: str, buckets: dict) -> dict:
    dist: dict = {}
    for v in verdicts:
        b = _bucket(v.get(axis_key, ""), buckets)
        dist[b] = dist.get(b, 0) + 1
    return dict(sorted(dist.items(), key=lambda kv: -kv[1]))


@dataclass
class FeasibilityReport:
    subject: str
    pool_depth: int                 # E — eligible candidates after negative/must-term/threshold
    sampled: int
    species_match: int
    wild_match: int
    both_match: int                 # wild AND correct-species (the yield basis)
    yield_est: float                # Y = (both_match / sampled) × E
    verdict: str                    # FEASIBLE | MARGINAL | INFEASIBLE | INCONCLUSIVE-SHALLOW
    thresholds: dict = field(default_factory=dict)     # floor/target for the intended film shape
    max_beats: int = 0              # most beats Y sustains at target density (the film length it supports)
    broad: bool = False
    season_dist: dict = field(default_factory=dict)
    habitat_dist: dict = field(default_factory=dict)
    time_dist: dict = field(default_factory=dict)
    shot_dist: dict = field(default_factory=dict)
    contradictions: int = 0
    echo_pairs: int = 0
    verdicts: list = field(default_factory=list)


def _verdict(y: float, E: int, floor: int, target: int) -> str:
    if E < MIN_POOL_DEPTH:          # search reach, not library depth — broaden before believing INFEASIBLE
        return "INCONCLUSIVE-SHALLOW"
    return "FEASIBLE" if y >= target else ("MARGINAL" if y >= floor else "INFEASIBLE")


async def probe_feasibility(conn, providers, subject: str, *, llm, channel_id, sample_n: int = 10,
                            target_fmt: str = "16:9", target_w: int = 1920, target_h: int = 1080,
                            cache_dir: str = "assets/sourced", broad: bool = False,
                            runtime_s: float = 394.0, n_beats: int = 7,
                            per_page: int = 15) -> FeasibilityReport:
    """`runtime_s`/`n_beats` default to the LION BENCHMARK (6:34, 7 beats) so the verdict is judged
    against the bar we must stand next to; `broad=True` widens search reach (subject × scene vocabulary,
    higher per_page)."""
    thr = film_thresholds(runtime_s, n_beats)
    plan = (_broad_plan(subject, target_fmt) if broad
            else build_query_plan(subject, approx_seconds=8, target_fmt=target_fmt, llm=llm))
    pp = max(per_page, 40) if broad else per_page

    seen: dict = {}
    for prov in providers:
        for q in plan.queries:
            try:
                cands = await prov.search(q, orientation=plan.orientation,
                                          min_duration=plan.min_seconds, per_page=pp)
            except Exception:  # noqa: BLE001
                continue
            for c in cands:
                seen.setdefault((c.source, c.asset_id), (c, q))
    ranked = rank_candidates([c for c, _ in seen.values()], plan, target_w=target_w, target_h=target_h)
    eligible = [(s, c) for s, c, _ in ranked if s >= MATCH_THRESHOLD]
    E = len(eligible)

    verdicts: list = []
    with tempfile.TemporaryDirectory(prefix="probe-") as work:
        for i, (score, cand) in enumerate(eligible):
            if len(verdicts) >= sample_n:
                break
            try:
                path = await download(cand, os.path.join(cache_dir, cand.source))
            except Exception:  # noqa: BLE001
                continue
            if not gate_download(path, orientation=plan.orientation).ok:
                continue
            frames = _vision.sample_frames(path, os.path.join(work, f"c{i}"))
            v = _vision.vision_check(frames,               # NO setting expectation — species+wild only
                                     expect=_vision.Expect(subject=subject, required=frozenset()),
                                     llm=llm, channel_id=channel_id)
            verdicts.append({"asset_id": cand.asset_id, "url": cand.page_url, "species": v.species,
                             "wild": v.wild, "season": v.season_observed, "habitat": v.habitat_observed,
                             "time": v.time_observed, "shot": v.shot_type, "features": v.features,
                             "contradiction": v.contradiction, "reason": v.reason})

    sampled = len(verdicts)
    species_match = sum(1 for v in verdicts if v["species"] == _vision.CLEAR_MATCH)
    wild_match = sum(1 for v in verdicts if v["wild"] == _vision.CLEAR_MATCH)
    both = [v for v in verdicts if v["species"] == _vision.CLEAR_MATCH and v["wild"] == _vision.CLEAR_MATCH]
    p = (len(both) / sampled) if sampled else 0.0
    Y = round(p * E, 1)
    echo = _vision.detect_echo([(v["asset_id"], v["features"], v["species"]) for v in verdicts])

    report = FeasibilityReport(
        subject=subject, pool_depth=E, sampled=sampled, species_match=species_match,
        wild_match=wild_match, both_match=len(both), yield_est=Y,
        verdict=_verdict(Y, E, thr["floor"], thr["target"]), thresholds=thr, broad=broad,
        max_beats=max_beats_for_yield(Y, thr["beat_len_s"]),
        season_dist=_distribution(both, "season", _SEASON_BUCKETS),
        habitat_dist=_distribution(both, "habitat", _HABITAT_BUCKETS),
        time_dist=_distribution(both, "time", _TIME_BUCKETS),
        shot_dist=_distribution(both, "shot", _SHOT_BUCKETS),
        contradictions=sum(1 for v in verdicts if v["contradiction"]), echo_pairs=len(echo),
        verdicts=verdicts)
    await record_event(conn, "feasibility.probed",
                       message=f"{subject}: pool {E}, sampled {sampled}, wild+species {len(both)} "
                               f"→ Y≈{Y} → {report.verdict}",
                       channel_id=channel_id, data={"subject": subject, "verdict": report.verdict,
                                                    "pool_depth": E, "yield": Y})
    return report
