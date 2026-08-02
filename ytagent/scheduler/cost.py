"""Per-job production cost ESTIMATE — the number the 4→5 spend gate checks (per-job threshold and the
rolling ceiling). A pre-flight estimate only, NOT the §4.10 ROI/ROAS governor. Priced from the same
rates the ledger writes: TTS ≈ 1 credit/char, music ≈ 15 credits/s, ~£0.00133/credit (subscription
baseline). Deliberately a slight over-estimate (it counts the full planned cue set) so the gate errs
toward asking, never toward silently overspending."""
from __future__ import annotations

from dataclasses import dataclass

from ..audio_design import _BED_S, _CREDITS_PER_SEC, _GBP_PER_CREDIT, plan_cues

_CREDITS_PER_CHAR = 1.0


@dataclass(frozen=True)
class CostEstimate:
    tts_chars: int
    tts_gbp: float
    music_credits: float
    music_gbp: float
    total_gbp: float


def estimate_production_cost(script, channel: dict) -> CostEstimate:
    """Estimate £ for one production: TTS of the spoken beats + the planned music cues + bed. Uses the
    SAME cue plan the design stage will generate, so the estimate matches what actually gets spent."""
    spoken = sum(len(t) for t in script.to_narration().values() if t.strip())
    tts_gbp = spoken * _CREDITS_PER_CHAR * _GBP_PER_CREDIT

    cues, _breathers, _bs = plan_cues(script, channel)
    music_seconds = sum(c.seconds for c in cues) + _BED_S
    music_credits = music_seconds * _CREDITS_PER_SEC
    music_gbp = music_credits * _GBP_PER_CREDIT

    return CostEstimate(
        tts_chars=spoken, tts_gbp=round(tts_gbp, 4),
        music_credits=round(music_credits), music_gbp=round(music_gbp, 4),
        total_gbp=round(tts_gbp + music_gbp, 4))
