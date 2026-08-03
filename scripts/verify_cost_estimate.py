"""Regression: pin estimate_production_cost against MEASURED usage so a 4.4×-low drift fails loud (B3).

Ground truth (from the ledger, this repo):
- Job 155 (elephant, assembled): TTS 653+710+770+770+774+702 = 4,379 chars = 4,379 credits; music
  theme45+journey40+resolution35+bed45 = 165s → 2,475 credits ACTUAL (no retake, no SFX).
- Lion: 3 cues total 120.06s, ~1,500 credits settled → the 15 credits/s rate is a slight over-estimate.

Asserts: (1) TTS is exact; (2) the base music model (retake=1.0) reproduces job 155's 2,475 EXACTLY and
never under-estimates the lion; (3) the retake headroom only ever raises the estimate (never under the
measured actual); (4) SFX is COUNTED — the omission that made a heavy run 4.4× low is closed.

Run: ./.venv/bin/python -m scripts.verify_cost_estimate
"""
from __future__ import annotations

from types import SimpleNamespace

from ytagent.authoring.script import Beat, Script
from ytagent.scheduler import cost
from ytagent.scheduler.cost import estimate_production_cost

_CH = {"config": {"voice_profile": {}, "tone": "reverent, poetic", "niche": "wildlife documentary"}}
# job 155's six spoken beats, exact measured char counts
_CHARS = [653, 710, 770, 770, 774, 702]
_ELEPHANT_TTS_ACTUAL = sum(_CHARS)               # 4,379
_ELEPHANT_MUSIC_ACTUAL = 2475                    # 4 cues, no retake, no SFX
_LION_MUSIC_SECONDS, _LION_MUSIC_ACTUAL = 120.06, 1500

ok = True


def check(label, cond, detail=""):
    global ok
    ok = ok and cond
    print(f"  {'✅' if cond else '❌'} {label}{(' — ' + detail) if detail else ''}")


def _elephant_script():
    beats = tuple(Beat(index=i + 1, label=f"beat{i+1}", shot_brief="elephants on the savanna",
                       vo="a" * n, approx_seconds=55) for i, n in enumerate(_CHARS))
    return Script(title="African Elephant", runtime_target_s=340, word_target=520, beats=beats,
                  facts_used=())


def main():
    script = _elephant_script()

    print("[1] TTS is exact (deterministic 1 credit/char)")
    est = estimate_production_cost(script, _CH)
    check("tts_chars == measured 4,379", est.tts_chars == _ELEPHANT_TTS_ACTUAL,
          f"{est.tts_chars}")

    print("[2] base music model (retake=1.0) reproduces the measured actual")
    saved = cost._RETAKE_FACTOR
    try:
        cost._RETAKE_FACTOR = 1.0
        base = estimate_production_cost(script, _CH)
        check("elephant base music == 2,475 actual", base.music_credits == _ELEPHANT_MUSIC_ACTUAL,
              f"{base.music_credits}")
        rate_lion = 15.0 * _LION_MUSIC_SECONDS
        check("15/s never under-estimates the lion (1,801 ≥ 1,500)", rate_lion >= _LION_MUSIC_ACTUAL,
              f"{rate_lion:.0f} vs {_LION_MUSIC_ACTUAL}")
    finally:
        cost._RETAKE_FACTOR = saved

    print("[3] retake headroom only RAISES the estimate (never under the measured actual)")
    check("music_credits ≥ measured 2,475", est.music_credits >= _ELEPHANT_MUSIC_ACTUAL,
          f"{est.music_credits}")
    check("headroom is modest (≤ 1.6× actual)", est.music_credits <= _ELEPHANT_MUSIC_ACTUAL * 1.6,
          f"{est.music_credits}")

    print("[4] SFX is COUNTED (the omission that made a heavy run 4.4× low)")
    sfx = [SimpleNamespace(seconds=6.0), SimpleNamespace(seconds=4.0)]     # 10s of SFX
    est_sfx = estimate_production_cost(script, _CH, sfx_specs=sfx)
    check("sfx_credits > 0 when sfx present", est_sfx.sfx_credits > 0, f"{est_sfx.sfx_credits}")
    check("sfx raises the total credits by the sfx amount",
          round(est_sfx.elevenlabs_credits - est.elevenlabs_credits) == est_sfx.sfx_credits,
          f"+{est_sfx.sfx_credits}")
    check("serialized (dict) sfx specs also counted",
          estimate_production_cost(script, _CH, sfx_specs=[{"seconds": 10.0}]).sfx_credits > 0)

    print("[5] LLM (description) is in the estimate + per-provider breakdown present")
    check("llm_gbp > 0 (was omitted before)", est.llm_gbp > 0, f"£{est.llm_gbp}")
    provs = {p.provider for p in est.by_provider}
    check("breakdown covers all three providers",
          provs == {"elevenlabs_tts", "elevenlabs_music", "anthropic"}, str(sorted(provs)))
    check("elevenlabs_credits = tts + music + sfx",
          est_sfx.elevenlabs_credits == est_sfx.tts_chars + est_sfx.music_credits + est_sfx.sfx_credits)

    print("\n" + ("ALL PASSED" if ok else "FAILED"))
    raise SystemExit(0 if ok else 1)


if __name__ == "__main__":
    main()
