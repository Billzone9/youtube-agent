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
import re
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


CLEAR_MATCH, UNCERTAIN, CLEAR_MISMATCH = "clear_match", "uncertain", "clear_mismatch"
_LABELS = (CLEAR_MATCH, UNCERTAIN, CLEAR_MISMATCH)


@dataclass(frozen=True)
class VisionVerdict:
    # IDENTITY axes are THREE-WAY (the model reports its epistemic state; POLICY decides what it costs):
    species: str = UNCERTAIN            # clear_match | uncertain | clear_mismatch (vs expected subject)
    wild: str = UNCERTAIN              # clear_match(=wild) | uncertain | clear_mismatch(=captive)
    # SETTING axes stay boolean (binary against named terms):
    season_ok: bool = True
    habitat_ok: bool = True
    time_ok: bool = True
    features: str = ""                 # species_features (what the model SAW)
    features_indicate: str = ""        # the species those features point to (for the contradiction check)
    contradiction: bool = False        # features_indicate ↔ species verdict disagree (fighting its evidence)
    reason: str = ""
    skipped: bool = False


_SYSTEM = (
    "You are a QA checker for a WILD-animal documentary. You are shown a few frames from ONE clip plus "
    "what the shot is SUPPOSED to contain, broken into axes. Judge each axis ONLY from what is visible, "
    "and judge the SETTING axes (season, habitat, time) independently of each other and of the animal.\n"
    "Report your real EPISTEMIC STATE — do NOT force a yes/no when the image is ambiguous. Return STRICT "
    "JSON only, in THIS ORDER (reason BEFORE labelling):\n"
    '{"species_features": "<distinguishing features you SEE: muzzle length/breadth, head & body '
    'size/frame, ear size relative to head, leg length, coat/markings>", '
    '"features_indicate": "<the species those features most point to, 1-2 words>", '
    '"species": "clear_match" | "uncertain" | "clear_mismatch", '
    '"wild_evidence": "<captivity signs you SEE (fence, bars, cage, enclosure, wall, building, collar, '
    'leash, manicured/compacted ground) OR open natural terrain>", '
    '"wild": "clear_match" | "uncertain" | "clear_mismatch", '
    '"season_ok": bool, "habitat_ok": bool, "time_ok": bool, "reason": str}.\n'
    "SPECIES: name the features, then the species they indicate, then label — clear_match = the features "
    "CLEARLY match the expected subject; clear_mismatch = they CLEARLY indicate a DIFFERENT species "
    "(coyote/jackal/domestic dog/wolf-dog hybrid when a grey wolf is expected); uncertain = ambiguous, or "
    "you cannot confidently distinguish. A grey wolf has a long broad muzzle, large blocky head, heavy "
    "deep-chested frame, long legs, ears short relative to the head; a coyote/jackal is smaller and "
    "slighter with a narrow pointed muzzle and large ears. Do NOT default to clear_mismatch when unsure — "
    "say uncertain. If the features you listed match the expected subject, do NOT label clear_mismatch.\n"
    "WILD: clear_match = clearly wild/natural, no sign of captivity or human construction; clear_mismatch "
    "= clear captivity signs (fence/bars/cage/enclosure/wall/building/collar/leash/manicured ground); "
    "uncertain = ambiguous. SEASON/HABITAT/TIME: true iff the visible setting matches the expected terms; "
    "for any of these three with NO expectation given, return true."
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
    lines = [f"Expected subject (species): {expect.subject or 'the described wild animal'}.",
             "Expected setting: WILD/natural (no captivity)."]
    for axis in _SETTING_AXES:
        terms = expect.terms(axis)
        req = "BLOCKING" if axis in expect.required else "advisory"
        lines.append(f"Expected {axis.replace('_', ' ')}: {', '.join(terms) or 'any'} ({req}).")
    lines.append("Return the JSON verdict.")
    return "\n".join(lines)


_SAMPLES = 3   # majority-of-N per axis: temperature=0 alone still flips a borderline call, and a wrong
#                identity call is the worst error, so vote the label. Odd N → clean mode.


def _label(v) -> str:
    return v if v in _LABELS else UNCERTAIN


def _head_noun(subject: str) -> str:
    toks = [w for w in re.findall(r"[a-z]+", (subject or "").lower()) if len(w) > 2]
    return toks[-1] if toks else ""


# qualifiers that mean "NOT a clean match" even when the subject noun appears (e.g. 'wolf-dog hybrid'
# contains 'wolf' but is not a grey wolf) — used so the contradiction check doesn't false-positive.
_NOT_CLEAN = ("hybrid", "cross", "coyote", "jackal", "domestic", "dog", "mix", "captive")


def _indicates_subject(features_indicate: str, noun: str) -> bool:
    fi = (features_indicate or "").lower()
    if not noun or not re.search(rf"\b{re.escape(noun)}\b", fi):
        return False
    return not any(w in fi for w in _NOT_CLEAN)


def _single_call(frames: list[str], expect: Expect, llm, *, channel_id, job_id) -> dict | None:
    """One vision call → raw axis labels/booleans + evidence, or None on an unparseable reply."""
    from ..providers.base import CacheableBlock, LLMRequest, ModelTier

    content: list[dict] = [_image_block(f) for f in frames]
    content.append({"type": "text", "text": _expect_text(expect)})
    resp = llm.complete(LLMRequest(
        tier=ModelTier.CHEAP, system=(CacheableBlock(_SYSTEM),),
        messages=({"role": "user", "content": content},), max_tokens=500, purpose="vision_gate",
        channel_id=channel_id, job_id=job_id, temperature=0))    # deterministic-ish; voting covers the rest
    s = resp.text.strip()
    a, b = s.find("{"), s.rfind("}")
    if a == -1 or b == -1:
        return None
    try:
        d = json.loads(s[a:b + 1])
    except Exception:  # noqa: BLE001
        return None
    return {"species": _label(str(d.get("species", UNCERTAIN))),
            "wild": _label(str(d.get("wild", UNCERTAIN))),
            "season": bool(d.get("season_ok", True)), "habitat": bool(d.get("habitat_ok", True)),
            "time_of_day": bool(d.get("time_ok", True)),
            "features": str(d.get("species_features", "")).strip(),
            "features_indicate": str(d.get("features_indicate", "")).strip(),
            "reason": str(d.get("reason", "")).strip()}


def _majority_label(labels: list[str]) -> str:
    """Mode of the three-way labels; no strict majority (e.g. a 3-way split) → UNCERTAIN (the middle)."""
    best = max(_LABELS, key=lambda lab: labels.count(lab))
    return best if labels.count(best) > len(labels) / 2 else UNCERTAIN


def _setting_ok(v: "VisionVerdict", axis: str) -> bool:
    return {"season": v.season_ok, "habitat": v.habitat_ok, "time_of_day": v.time_ok}[axis]


def classify(v: "VisionVerdict", expect: Expect) -> tuple[str, tuple]:
    """Map a three-way verdict to a POLICY category for one beat's required axes:
      'reject'    — a required SETTING axis is false, or a required IDENTITY axis is clear_mismatch.
      'uncertain' — not rejected, but a required identity axis is 'uncertain' (→ held in reserve).
      'clear'     — every required axis clear_match/true (→ eligible to accept).
    Returns (category, axes-that-drove-it)."""
    setting_fail = tuple(ax for ax in _SETTING_AXES if ax in expect.required and not _setting_ok(v, ax))
    if setting_fail:
        return "reject", setting_fail
    reject_ax, uncertain_ax = [], []
    for ax in ("species", "wild"):
        if ax == "wild" and not expect.wild:
            continue
        label = getattr(v, ax)
        if label == CLEAR_MISMATCH:
            reject_ax.append(ax)
        elif label == UNCERTAIN:
            uncertain_ax.append(ax)
    if reject_ax:
        return "reject", tuple(reject_ax)
    if uncertain_ax:
        return "uncertain", tuple(uncertain_ax)
    return "clear", ()


def vision_check(frames: list[str], *, expect: Expect, llm, samples: int = _SAMPLES,
                 channel_id=None, job_id=None) -> VisionVerdict:
    """Haiku-vision verdict for one clip against `expect`, judged per axis by MAJORITY of `samples`
    calls (temperature=0 + vote). IDENTITY axes (species, wild) are THREE-WAY — the verdict REPORTS the
    epistemic state; POLICY (orchestrator) decides what clear_match/uncertain/clear_mismatch cost. Also
    flags a self-CONTRADICTION (features point to the subject but the label rejects it, or vice versa).
    No LLM or no frames → SKIPPED (only via an EXPLICIT vision=False path; the required path fails loud
    upstream)."""
    if llm is None or not frames:
        return VisionVerdict(species=CLEAR_MATCH, wild=CLEAR_MATCH, reason="skipped (no LLM/frames)",
                             skipped=True)
    calls = [c for c in (_single_call(frames, expect, llm, channel_id=channel_id, job_id=job_id)
                         for _ in range(max(1, samples))) if c is not None]
    if not calls:
        return VisionVerdict(species=CLEAR_MISMATCH, wild=CLEAR_MISMATCH,
                             reason="unparseable/malformed vision verdict(s)")

    species = _majority_label([c["species"] for c in calls])
    wild = _majority_label([c["wild"] for c in calls])
    season_ok = sum(c["season"] for c in calls) > len(calls) / 2
    habitat_ok = sum(c["habitat"] for c in calls) > len(calls) / 2
    time_ok = sum(c["time_of_day"] for c in calls) > len(calls) / 2

    rep = next((c for c in calls if c["species"] == species), calls[0])   # a call agreeing with the mode
    # CONTRADICTION: the listed evidence points to the expected subject but the label rejects it (today's
    # bug), or points elsewhere yet the label accepts. Detected from features_indicate vs the subject.
    noun = _head_noun(expect.subject)
    indicates_subject = _indicates_subject(rep["features_indicate"], noun)
    names_other = bool(rep["features_indicate"]) and not indicates_subject and bool(noun) \
        and not re.search(rf"\b{re.escape(noun)}\b", rep["features_indicate"].lower())
    contradiction = (indicates_subject and species == CLEAR_MISMATCH) \
        or (names_other and species == CLEAR_MATCH)

    agree = sum(1 for c in calls if c["species"] == species)
    reason = (f"[{agree}/{len(calls)} agree species={species}] "
              + (f"[features:{rep['features'][:90]}→{rep['features_indicate']}] " if rep["features"] else "")
              + rep["reason"])
    return VisionVerdict(species=species, wild=wild, season_ok=season_ok, habitat_ok=habitat_ok,
                         time_ok=time_ok, features=rep["features"],
                         features_indicate=rep["features_indicate"], contradiction=contradiction,
                         reason=reason[:300])
