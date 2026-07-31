"""The VISION GATE — the real content check metadata can't do. After a candidate passes the metadata
gate, sample a few frames and ask Haiku (vision) whether the footage actually MATCHES the shot: right
species, genuinely wild (no fence/zoo/enclosure), right season/setting. This is what would have caught
the wolf run's captive-fence clip and the coyote-not-a-wolf clip.

No provider change: the LLM provider forwards `messages` content unchanged, so we pass image blocks
(`{"type":"image","source":{"type":"base64",...}}`) alongside the text; `ModelTier.CHEAP` = Haiku,
which sees images. Degrades honestly: with no LLM the gate is SKIPPED (passes), like query planning.
"""
from __future__ import annotations

import base64
import json
import os
import subprocess
from dataclasses import dataclass

from ..assembly import ffmpeg

_N_FRAMES = 3
_SCALE = 512          # downscale frames — enough for species/setting, keeps vision tokens cheap


_SETTING_AXES = ("season", "habitat", "time_of_day")


class VisionUnavailable(RuntimeError):
    """The vision gate is REQUIRED but no LLM is configured (Item 6 fail-loud). A silently-skipped
    content gate is worse than none — it reads as 'checked' while passing off-brief footage unseen."""


@dataclass(frozen=True)
class Expect:
    subject: str                        # what the animal/thing SHOULD be (e.g. 'grey wolf')
    wild: bool = True                   # must read as wild/natural (no captivity/man-made construction)
    season: tuple[str, ...] = ()        # expected season terms (e.g. ('snow','winter'))
    habitat: tuple[str, ...] = ()       # expected habitat terms (e.g. ('forest','tundra'))
    time_of_day: tuple[str, ...] = ()   # expected time terms (e.g. ('dusk','twilight'))
    required: frozenset = frozenset({"season"})   # which SETTING axes BLOCK (species+wild always block)

    def terms(self, axis: str) -> tuple[str, ...]:
        return getattr(self, axis)

    @classmethod
    def from_plan(cls, plan, *, required=None) -> "Expect":
        """Build from a QueryPlan. `required` names the blocking setting axes (per-beat, from the VO
        locks); defaults to season-only when the plan names a season."""
        subject = plan.subject or (plan.must_terms[0] if plan.must_terms else "")
        req = frozenset(required) if required is not None else frozenset(
            {"season"} if plan.season else set())
        return cls(subject=subject, wild=True, season=tuple(plan.season), habitat=tuple(plan.habitat),
                   time_of_day=tuple(plan.time_of_day), required=req)


@dataclass(frozen=True)
class VisionVerdict:
    overall_ok: bool
    species_ok: bool
    wild_ok: bool
    season_ok: bool
    habitat_ok: bool = True
    time_ok: bool = True
    failed_axes: tuple[str, ...] = ()   # the REQUIRED axes that failed (why overall_ok is False)
    reason: str = ""
    skipped: bool = False


_SYSTEM = (
    "You are a strict stock-footage QA checker for a WILD-animal documentary. You are shown a few frames "
    "sampled from ONE video clip, plus what the shot is SUPPOSED to contain, broken out into SEPARATE "
    "axes. Judge EACH axis INDEPENDENTLY and ONLY from what is visible — never let one axis influence "
    "another (a correct wild animal in the wrong season is species_ok=true, season_ok=false). Return "
    "STRICT JSON only: {\"species_ok\": bool, \"wild\": bool, \"season_ok\": bool, \"habitat_ok\": bool, "
    "\"time_ok\": bool, \"reason\": str}. Rules: species_ok=true ONLY if the main animal clearly matches "
    "the expected subject — a similar-looking DIFFERENT species (coyote/jackal/domestic dog vs grey "
    "wolf) is false. wild=true ONLY if genuinely wild/natural with NO captivity or human construction "
    "(fence, bars, cage, wall, building, zoo/park, manicured ground → false). season_ok=true ONLY if the "
    "visible SEASON matches the expected season terms (judge season ALONE — snow/greenery/etc., not the "
    "habitat or time). habitat_ok=true ONLY if the visible HABITAT matches. time_ok=true ONLY if the "
    "visible TIME OF DAY / light matches. For any axis with NO expectation given, return true. Be "
    "conservative per axis: if an axis is unclear, false with a short reason naming WHICH axis."
)


def sample_frames(path: str, dst_dir: str, *, n: int = _N_FRAMES) -> list[str]:
    """Grab `n` evenly-spaced downscaled frames from the clip (skipping the very edges)."""
    try:
        dur = float(ffmpeg.probe(path)["duration"]) or 0.0
    except Exception:  # noqa: BLE001
        return []
    os.makedirs(dst_dir, exist_ok=True)
    out: list[str] = []
    for i in range(n):
        t = dur * ((i + 1) / (n + 1)) if dur > 0 else 0.0
        fp = os.path.join(dst_dir, f"vf_{i}.jpg")
        subprocess.run([ffmpeg.FFMPEG, "-y", "-ss", f"{t:.2f}", "-i", path, "-frames:v", "1",
                        "-vf", f"scale={_SCALE}:-1", "-q:v", "4", fp], capture_output=True)
        if os.path.exists(fp) and os.path.getsize(fp) > 0:
            out.append(fp)
    return out


def _image_block(fp: str) -> dict:
    with open(fp, "rb") as fh:
        data = base64.standard_b64encode(fh.read()).decode()
    return {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": data}}


def _expect_text(expect: Expect) -> str:
    lines = [f"Expected subject: {expect.subject or 'the described wild animal'} (species blocking).",
             "Expected wild/natural setting, no captivity (wild blocking)."]
    for axis in _SETTING_AXES:
        terms = expect.terms(axis)
        req = "BLOCKING" if axis in expect.required else "advisory"
        lines.append(f"Expected {axis.replace('_', ' ')}: {', '.join(terms) or 'any'} ({req}).")
    lines.append("Judge each axis independently and return the JSON verdict.")
    return "\n".join(lines)


def vision_check(frames: list[str], *, expect: Expect, llm, channel_id=None, job_id=None) -> VisionVerdict:
    """Haiku-vision verdict for one clip's frames against `expect`, judged PER AXIS. overall_ok =
    species AND wild AND every axis in `expect.required`. Advisory axes are reported, never block.
    No LLM or no frames → SKIPPED/pass (only reached via an EXPLICIT vision=False path; the required
    path fails loud upstream — see orchestrator.source_clips_for_brief / VisionUnavailable)."""
    if llm is None or not frames:
        return VisionVerdict(True, True, True, True, reason="vision gate skipped (no LLM/frames)",
                             skipped=True)
    from ..providers.base import CacheableBlock, LLMRequest, ModelTier

    content: list[dict] = [_image_block(f) for f in frames]
    content.append({"type": "text", "text": _expect_text(expect)})
    resp = llm.complete(LLMRequest(
        tier=ModelTier.CHEAP, system=(CacheableBlock(_SYSTEM),),
        messages=({"role": "user", "content": content},), max_tokens=300, purpose="vision_gate",
        channel_id=channel_id, job_id=job_id))
    s = resp.text.strip()
    a, b = s.find("{"), s.rfind("}")
    if a == -1 or b == -1:
        return VisionVerdict(False, False, False, False, failed_axes=("parse",),
                             reason=f"unparseable verdict: {s[:80]}")
    try:
        d = json.loads(s[a:b + 1])
    except Exception:  # noqa: BLE001
        return VisionVerdict(False, False, False, False, failed_axes=("parse",),
                             reason=f"malformed verdict JSON: {s[:80]}")
    species_ok = bool(d.get("species_ok", False))
    wild_ok = bool(d.get("wild", False))
    axis_ok = {"season": bool(d.get("season_ok", False)),
               "habitat": bool(d.get("habitat_ok", True)),
               "time_of_day": bool(d.get("time_ok", False if "time_ok" in d else True))}

    failed = []
    if not species_ok:
        failed.append("species")
    if expect.wild and not wild_ok:
        failed.append("wild")
    for axis in _SETTING_AXES:                       # only REQUIRED setting axes can fail the overall
        if axis in expect.required and not axis_ok[axis]:
            failed.append(axis)
    return VisionVerdict(
        overall_ok=not failed, species_ok=species_ok, wild_ok=wild_ok,
        season_ok=axis_ok["season"], habitat_ok=axis_ok["habitat"], time_ok=axis_ok["time_of_day"],
        failed_axes=tuple(failed), reason=str(d.get("reason", ""))[:200])
