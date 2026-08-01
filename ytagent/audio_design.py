"""Documentary audio design — channel-general. Turns a written Script + the channel's tone into a
COMPACT set of reusable instrumental cues + one ambience bed (+ optional SFX), generates them through
the swappable music provider, NOISE-GATES every arrival (a hissy cue is never kept), LEDGERS each as a
reconciled=False estimate, and tracks cumulative credits against a HARD ceiling.

Nothing niche lives here: cue prompts are built from `channel['config']['tone']`/`niche` + the film
SUBJECT, and the per-beat assignment is positional (cold-open → theme, alternating theme/journey,
closing beat → a resolution swell — the lion's "3 compact cues reused" recipe). Degrades gracefully:
a failed bed/SFX/cue is dropped and logged, NEVER hard-fails the film; the disclosure manifest then
reflects only the layers that actually made it in.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field

from .assembly import qc
from .assembly.spec import MusicCue, Sfx
from .events import record_event
from .music import MusicScopeError

_CREDITS_PER_SEC = 15.0
_GBP_PER_CREDIT = 0.00133          # same unified-credit rate as TTS (subscription-prepaid)
_THEME_S, _JOURNEY_S, _RESOLVE_S, _BED_S = 45.0, 40.0, 35.0, 45.0
_BREATHER_S = 4.0                  # per-transition structural breather (music-only, no voice)


@dataclass(frozen=True)
class CueSpec:
    key: str
    prompt: str
    seconds: float
    beats: tuple[int, ...]         # beat indexes that use this cue
    in_db: float = -16.0


@dataclass(frozen=True)
class SfxSpec:
    prompt: str
    beat_index: int
    at_s: float
    seconds: float = 3.0
    level_db: float = -8.0


@dataclass
class AudioDesign:
    cues: dict = field(default_factory=dict)        # {beat.index → MusicCue}
    breathers: dict = field(default_factory=dict)   # {beat.index → seconds}
    bed: str | None = None
    sfx: tuple = ()                                  # tuple[Sfx]
    manifest: dict = field(default_factory=dict)    # contents → disclosure
    credits_spent: float = 0.0
    layers: list = field(default_factory=list)      # human-readable layer summary
    notes: list = field(default_factory=list)       # graceful-degradation log


def _tone(channel: dict) -> tuple[str, str]:
    cfg = channel.get("config") or {}
    return (cfg.get("tone") or "reverent, unhurried"), (cfg.get("niche") or "nature documentary")


def plan_cues(script, channel: dict) -> tuple[list[CueSpec], dict, float]:
    """Positional cue plan (prompts + per-beat assignment + breathers) — no generation, no spend.
    Returns (cue_specs, breathers{beat→s}, breather_s). The film SUBJECT = the script title's subject."""
    tone, niche = _tone(channel)
    subject = getattr(script, "title", "the subject")
    beats = list(script.beats)
    spoken = [b.index for b in beats if (b.vo or "").strip()]
    wordless = [b.index for b in beats if not (b.vo or "").strip()]
    last_spoken = spoken[-1] if spoken else (beats[-1].index if beats else 0)

    theme_beats, journey_beats = list(wordless), []
    for k, idx in enumerate(spoken):
        if idx == last_spoken:
            continue
        (theme_beats if k % 2 == 0 else journey_beats).append(idx)

    theme = CueSpec("theme", (
        f"A quiet, reverent instrumental cue for a {niche} — {tone}. Warm sustained strings and a solo "
        "woodwind over a soft low drone, spacious and unhurried, with plenty of room for a narrator. "
        "No vocals, no percussion, no melody hooks — a bed of feeling."), _THEME_S, tuple(theme_beats))
    journey = CueSpec("journey", (
        f"A darker, patient instrumental cue for a {niche} — {tone}. A low pulsing ostinato under soft "
        "strings, forward-moving but calm, room for a narrator. No vocals, no percussion hits."),
        _JOURNEY_S, tuple(journey_beats))
    resolution = CueSpec("resolution", (
        f"A rising, aching instrumental swell for a {niche} — {tone} — that settles into stillness at "
        "the end. Strings blooming then resolving to quiet. No vocals, no percussion."),
        _RESOLVE_S, (last_spoken,), -14.0)

    cues = [c for c in (theme, journey, resolution) if c.beats]
    breathers = {idx: _BREATHER_S for idx in spoken if idx != last_spoken}   # tail on the last is fade
    return cues, breathers, _BREATHER_S


def _bed_prompt(script, channel: dict) -> str:
    _, niche = _tone(channel)
    subject = getattr(script, "title", "the wild")
    return (f"A very soft, dark, textural natural-world ambience for a {niche} — low wind and distant "
            f"air, felt not heard. No melody, no percussion, no animal calls — pure atmosphere.")


async def _gen_gated(music, prompt, *, seconds, dst, kind, sound_effect=False):
    """Generate one cue/bed/sfx and NOISE-GATE it. On a hissy arrival: ONE regeneration with a
    cleaner-prompt nudge; if it still fails, return (None, note) so the caller drops the layer. Never
    keeps hiss. Returns (MusicResult|None, note|None)."""
    attempt_prompt = prompt
    last = ""
    for attempt in range(2):
        try:
            if sound_effect:
                res = music.sound_effect(attempt_prompt, seconds=seconds, dst=dst)
            else:
                res = music.generate(attempt_prompt, seconds=seconds, dst=dst)
        except MusicScopeError:
            raise                                           # scope is a LAYER-level signal — propagate
        except Exception as e:  # noqa: BLE001 — a transient API error must not kill the film
            last = f"generation error: {e}"
            continue
        clean = qc.check_source_clean(res.path)
        if clean.ok:
            return res, None
        if os.path.exists(res.path):
            os.remove(res.path)                              # a hissy cue is NEVER kept
        last = "; ".join(f"{n}: {d}" for n, ok, d in clean.checks if not ok)
        if attempt == 0:
            attempt_prompt = prompt + " Cleaner, softer, darker — absolutely no hiss or broadband noise."
    return None, f"{kind} dropped after 2 takes ({last})"


async def generate_audio(conn, music, script, *, channel: dict, job_id: int | None, workdir: str,
                         budget_credits: float, sfx_specs: list | None = None) -> AudioDesign:
    """Generate the cues + bed (+ optional SFX), gate + ledger each, track cumulative credits against
    `budget_credits` (HARD stop + log on reaching it). Graceful: any dropped layer is logged and the
    manifest reflects reality. `music` may be None (no key) → returns an empty design (narration-only)."""
    from . import repo

    d = AudioDesign()
    cue_specs, breathers, _ = plan_cues(script, channel)
    d.breathers = breathers
    manifest = {"narration": "AI text-to-speech", "footage": "licensed / CC-0 stock"}
    if music is None:
        d.notes.append("no music provider configured — shipped narration only")
        d.manifest = manifest
        return d

    os.makedirs(workdir, exist_ok=True)
    ch_id = channel["id"]
    spent = 0.0

    async def _ledger(res, cue):
        nonlocal spent
        spent += res.credits_est
        await repo.ledger.write_music_cost(
            conn, channel_id=ch_id, job_id=job_id, cue=cue, seconds=res.seconds,
            credits_est=res.credits_est, amount_gbp_est=round(res.credits_est * _GBP_PER_CREDIT, 4),
            request_id=res.request_id, model=res.model, kind=res.kind)

    # --- score cues ---
    made_music = False
    for spec in cue_specs:
        est = spec.seconds * _CREDITS_PER_SEC
        if spent + est > budget_credits:
            d.notes.append(f"credit ceiling {budget_credits:.0f} reached — skipped cue '{spec.key}'")
            continue
        try:
            res, note = await _gen_gated(music, spec.prompt, seconds=spec.seconds,
                                         dst=os.path.join(workdir, f"cue_{spec.key}.mp3"), kind=f"cue:{spec.key}")
        except MusicScopeError as e:
            d.notes.append(f"music scope blocked — shipped narration only ({e})")
            break
        if res is None:
            d.notes.append(note)
            continue
        await _ledger(res, spec.key)
        made_music = True
        for bidx in spec.beats:
            d.cues[bidx] = MusicCue(file=os.path.abspath(res.path), in_db=spec.in_db, fade_in=2.0, fade_out=3.0)
        d.layers.append(f"{spec.key} {spec.seconds:.0f}s @{spec.in_db}dB → beats {list(spec.beats)}")
    if made_music:
        manifest["music"] = "AI-generated instrumental score"
    else:
        d.breathers = {}                                    # no score → a breather would be dead air

    # --- ambience bed (degrades gracefully) ---
    bed_est = _BED_S * _CREDITS_PER_SEC
    if made_music and spent + bed_est <= budget_credits:
        try:
            res, note = await _gen_gated(music, _bed_prompt(script, channel), seconds=_BED_S,
                                         dst=os.path.join(workdir, "bed.mp3"), kind="bed")
            if res is not None:
                await _ledger(res, "bed")
                d.bed = os.path.abspath(res.path)
                d.layers.append(f"bed {_BED_S:.0f}s (crossfade-looped, ~-30dB)")
                manifest["ambience"] = "AI-generated"
            else:
                d.notes.append(note)
        except MusicScopeError as e:
            d.notes.append(f"bed skipped (scope): {e}")
    elif made_music:
        d.notes.append(f"credit ceiling — bed skipped")

    # --- SFX (optional, pre-flighted, degrades gracefully) ---
    sfx_out = []
    for i, sspec in enumerate(sfx_specs or []):
        est = sspec.seconds * _CREDITS_PER_SEC
        if spent + est > budget_credits:
            d.notes.append(f"credit ceiling — SFX '{sspec.prompt[:24]}' skipped")
            continue
        try:
            res, note = await _gen_gated(music, sspec.prompt, seconds=sspec.seconds,
                                         dst=os.path.join(workdir, f"sfx_{i}.mp3"), kind=f"sfx:{i}",
                                         sound_effect=True)
        except MusicScopeError as e:
            d.notes.append(f"SFX scope blocked — shipped without SFX ({e})")
            break
        if res is None:
            d.notes.append(note)
            continue
        await _ledger(res, f"sfx{i}")
        sfx_out.append(Sfx(file=os.path.abspath(res.path), beat=f"beat{sspec.beat_index}",
                           at_s=sspec.at_s, level_db=sspec.level_db))
        d.layers.append(f"sfx '{sspec.prompt[:28]}' @beat{sspec.beat_index}+{sspec.at_s}s")
    if sfx_out:
        manifest["sound effects"] = "AI-generated"
    d.sfx = tuple(sfx_out)

    d.credits_spent = spent
    d.manifest = manifest
    await record_event(conn, "audio_designed",
                       message=f"audio: {len(d.cues)} beats scored, bed={'yes' if d.bed else 'no'}, "
                               f"{len(d.sfx)} sfx, {spent:.0f} credits (ceiling {budget_credits:.0f})",
                       channel_id=ch_id, job_id=job_id,
                       data={"layers": d.layers, "notes": d.notes, "credits": spent, "manifest": manifest})
    return d
