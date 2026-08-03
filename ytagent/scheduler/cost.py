"""Per-job production cost ESTIMATE — the pre-flight number the 4→5 spend gate checks (per-job
threshold, rolling ceiling, and the ElevenLabs credit gate). A pre-flight estimate only, NOT the §4.10
ROI/ROAS governor.

Derived from MEASURED runs, not a guess (B3):
- **TTS** — deterministic: ElevenLabs bills 1 credit/char, and the char count is exact. Confirmed on
  job 155 (elephant): 6 beats, 653+710+770+770+774+702 = 4,379 chars = 4,379 credits.
- **Music/SFX** — 15 credits/s. Confirmed conservative: the lion's 3 cues total 120.06s → 1,801 est vs
  ~1,500 settled (a slight over-estimate, the intended bias); job 155's 4 cues (45+40+35+45s) = 2,475
  est == 2,475 actual.
- **Omissions this fixes (the source of the 4.4× a dev run showed, NOT a wrong rate):**
  (1) **SFX** — `generate_audio` spends on `sfx_specs`; the old estimate ignored them entirely.
  (2) **Retakes** — `_gen_gated` regenerates a hissy cue once (double bill); modelled as a headroom
      factor on music+sfx (`_RETAKE_FACTOR`), calibratable by the reconciler.
  (3) **LLM** — the description/tags spend (job 155: £0.0082 Anthropic) was never in the estimate.
The estimate is a deliberate slight OVER-estimate so the gate errs toward asking, never toward silently
overspending.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from ..audio_design import _BED_S, _CREDITS_PER_SEC, _GBP_PER_CREDIT, plan_cues

_CREDITS_PER_CHAR = 1.0
# generate_audio._gen_gated retakes a hissy cue ONCE → up to 2× on the cues that retake. A modest
# headroom over the clean-run cost (job 155 retook nothing → 1.0×). Calibrated by the reconciler as
# settled data accrues; kept small so a clean production isn't wildly over-quoted.
_RETAKE_FACTOR = 1.15
# Description + tags LLM, spent AFTER the gate (step 7). The SCRIPT LLM is already sunk by gate time.
# A conservative fixed estimate toward Sonnet description authoring (job 155 actual ≈ £0.008).
_DESC_LLM_GBP = 0.02


@dataclass(frozen=True)
class ProviderCost:
    provider: str            # "anthropic" | "elevenlabs_tts" | "elevenlabs_music"
    credits: float           # ElevenLabs credits; 0 for token-priced Anthropic
    gbp: float


@dataclass(frozen=True)
class CostEstimate:
    # kept for back-compat with the existing credit/spend gate + spend_estimate event
    tts_chars: int
    tts_gbp: float
    music_credits: float
    music_gbp: float
    total_gbp: float
    # B3 additions — per-provider, full coverage
    sfx_credits: float = 0.0
    sfx_gbp: float = 0.0
    llm_gbp: float = 0.0
    retake_factor: float = _RETAKE_FACTOR
    by_provider: tuple = field(default_factory=tuple)

    @property
    def elevenlabs_credits(self) -> float:
        """The credits that draw the key's cap — TTS + music + SFX. What the credit gate checks."""
        return self.tts_chars + self.music_credits + self.sfx_credits

    @property
    def total_credits(self) -> float:
        return self.elevenlabs_credits


def estimate_production_cost(script, channel: dict, *, sfx_specs=None) -> CostEstimate:
    """Estimate one production's FORWARD spend at the 4→5 gate: TTS of the spoken beats + planned music
    cues + bed + SFX (× retake headroom) + the description LLM. Uses the SAME cue plan the design stage
    generates, so the estimate tracks what actually gets spent."""
    # TTS — exact (1 credit/char)
    spoken = sum(len(t) for t in script.to_narration().values() if t.strip())
    tts_gbp = spoken * _CREDITS_PER_CHAR * _GBP_PER_CREDIT

    # Music cues + bed, with retake headroom
    cues, _breathers, _bs = plan_cues(script, channel)
    music_seconds = sum(c.seconds for c in cues) + _BED_S
    music_credits = music_seconds * _CREDITS_PER_SEC * _RETAKE_FACTOR
    music_gbp = music_credits * _GBP_PER_CREDIT

    # SFX — the omission that made a heavy run 4.4× low; count every planned sfx cue (obj or serialized dict)
    sfx_seconds = sum((s.get("seconds", 0.0) if isinstance(s, dict) else getattr(s, "seconds", 0.0))
                      for s in (sfx_specs or []))
    sfx_credits = sfx_seconds * _CREDITS_PER_SEC * _RETAKE_FACTOR
    sfx_gbp = sfx_credits * _GBP_PER_CREDIT

    llm_gbp = _DESC_LLM_GBP
    total_gbp = tts_gbp + music_gbp + sfx_gbp + llm_gbp

    by_provider = (
        ProviderCost("elevenlabs_tts", round(spoken * _CREDITS_PER_CHAR), round(tts_gbp, 4)),
        ProviderCost("elevenlabs_music", round(music_credits + sfx_credits),
                     round(music_gbp + sfx_gbp, 4)),
        ProviderCost("anthropic", 0.0, round(llm_gbp, 4)),
    )
    return CostEstimate(
        tts_chars=spoken, tts_gbp=round(tts_gbp, 4),
        music_credits=round(music_credits), music_gbp=round(music_gbp, 4),
        sfx_credits=round(sfx_credits), sfx_gbp=round(sfx_gbp, 4),
        llm_gbp=round(llm_gbp, 4), retake_factor=_RETAKE_FACTOR,
        total_gbp=round(total_gbp, 4), by_provider=by_provider)
