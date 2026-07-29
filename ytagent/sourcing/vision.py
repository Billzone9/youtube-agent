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


@dataclass(frozen=True)
class Expect:
    subject: str                       # what the animal/thing SHOULD be (e.g. 'grey wolf')
    wild: bool = True                  # must read as wild/natural (no captivity/man-made construction)
    season: tuple[str, ...] = ()       # expected season/setting terms (e.g. ('snow','winter')); () = any

    @classmethod
    def from_plan(cls, plan) -> "Expect":
        subject = plan.subject or (plan.must_terms[0] if plan.must_terms else "")
        return cls(subject=subject, wild=True, season=tuple(plan.setting))


@dataclass(frozen=True)
class VisionVerdict:
    overall_ok: bool
    species_ok: bool
    wild_ok: bool
    season_ok: bool
    reason: str = ""
    skipped: bool = False


_SYSTEM = (
    "You are a strict stock-footage QA checker for a WILD-animal documentary. You are shown a few frames "
    "sampled from ONE video clip, plus what the shot is SUPPOSED to contain. Judge ONLY what is visible. "
    "Return STRICT JSON only: {\"species_ok\": bool, \"wild\": bool, \"season_ok\": bool, \"reason\": "
    "str}. Rules: species_ok=true ONLY if the main animal clearly matches the expected subject — a "
    "similar-looking DIFFERENT species (e.g. a coyote, jackal or domestic dog when a grey wolf is "
    "expected) is false. wild=true ONLY if it looks genuinely wild/natural with NO sign of captivity or "
    "human construction — a fence, enclosure bars, cage, wall, building, zoo/park setting or manicured "
    "ground makes it FALSE. season_ok=true ONLY if the visible setting matches the expected "
    "season/setting; if no season is expected, return true. Be conservative: if unsure, return false "
    "with a short reason."
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


def vision_check(frames: list[str], *, expect: Expect, llm, channel_id=None, job_id=None) -> VisionVerdict:
    """Haiku-vision verdict for one clip's frames against `expect`. overall_ok = all REQUIRED axes pass
    (season required only when a season is expected). No LLM or no frames → SKIPPED (passes honestly)."""
    if llm is None or not frames:
        return VisionVerdict(True, True, True, True, reason="vision gate skipped (no LLM/frames)",
                             skipped=True)
    from ..providers.base import CacheableBlock, LLMRequest, ModelTier

    content: list[dict] = [_image_block(f) for f in frames]
    content.append({"type": "text", "text":
                    f"Expected subject: {expect.subject or 'the described wild animal'}. "
                    f"Expected season/setting: {', '.join(expect.season) or 'any'}. "
                    "Do ALL these frames match? Return the JSON verdict."})
    resp = llm.complete(LLMRequest(
        tier=ModelTier.CHEAP, system=(CacheableBlock(_SYSTEM),),
        messages=({"role": "user", "content": content},), max_tokens=250, purpose="vision_gate",
        channel_id=channel_id, job_id=job_id))
    s = resp.text.strip()
    a, b = s.find("{"), s.rfind("}")
    if a == -1 or b == -1:
        return VisionVerdict(False, False, False, False, reason=f"unparseable verdict: {s[:80]}")
    try:
        d = json.loads(s[a:b + 1])
    except Exception:  # noqa: BLE001
        return VisionVerdict(False, False, False, False, reason=f"malformed verdict JSON: {s[:80]}")
    species_ok = bool(d.get("species_ok", False))
    wild_ok = bool(d.get("wild", False))
    season_ok = bool(d.get("season_ok", False))
    required = [species_ok,
                wild_ok if expect.wild else True,
                season_ok if expect.season else True]
    return VisionVerdict(all(required), species_ok, wild_ok, season_ok,
                         reason=str(d.get("reason", ""))[:200])
