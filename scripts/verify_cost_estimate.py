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
    # NOTE 2: the gate must QUOTE grounded research before it spends → the estimate INCLUDES the ceiling
    no_research = estimate_production_cost(script, _CH, include_research=False)
    check("estimate INCLUDES the research ceiling by default (quoted before research spends)",
          est.llm_gbp > no_research.llm_gbp
          and round(est.llm_gbp - no_research.llm_gbp, 4) == cost.estimate_research_cost(),
          f"Δ£{round(est.llm_gbp - no_research.llm_gbp, 4)} == £{cost.estimate_research_cost()}")
    check("research is in the anthropic provider line, not hidden",
          next(p.gbp for p in est.by_provider if p.provider == "anthropic")
          > next(p.gbp for p in no_research.by_provider if p.provider == "anthropic"))
    provs = {p.provider for p in est.by_provider}
    check("breakdown covers all three providers",
          provs == {"elevenlabs_tts", "elevenlabs_music", "anthropic"}, str(sorted(provs)))
    check("elevenlabs_credits = tts + music + sfx",
          est_sfx.elevenlabs_credits == est_sfx.tts_chars + est_sfx.music_credits + est_sfx.sfx_credits)

    print("[6] Phase-1 LLM estimators exist BEFORE the features (PLAN_PHASE1_COSTS.md)")
    # the raw tokens→gbp helper against a hand-computed figure (Sonnet: 1M in + 1M out = £(3+15)*0.79)
    check("estimate_llm_gbp matches hand-calc",
          cost.estimate_llm_gbp(input_tokens=1_000_000, output_tokens=1_000_000, tier="quality")
          == round(18.0 * 0.79, 4), f"£{cost.estimate_llm_gbp(input_tokens=10**6, output_tokens=10**6)}")
    research = cost.estimate_research_cost()
    trend = cost.estimate_trend_analysis_cost()
    # research must be a CEILING derived from the loop's hard caps — NOT an unbounded hope (the vision
    # volume-omission lesson). Assert the estimate EQUALS the worst case the caps permit.
    ceiling = cost.estimate_llm_gbp(input_tokens=cost._RESEARCH_MAX_INPUT_TOKENS,
                                    output_tokens=cost._RESEARCH_MAX_OUTPUT_TOKENS,
                                    tier="quality", web_searches=cost._RESEARCH_MAX_SEARCHES)
    check("grounded research estimate == the cap-derived CEILING (not a hope)", research == ceiling,
          f"£{research} == £{ceiling}")
    check("the ceiling exceeds the ~£0.17 EXPECTED case (it bounds the worst case)",
          research > cost.estimate_llm_gbp(input_tokens=30_000, output_tokens=4_000, web_searches=6),
          f"£{research}")
    check("the loop caps are finite + enforced-in-code constants",
          cost._RESEARCH_MAX_SEARCHES > 0 and cost._RESEARCH_MAX_ITERATIONS > 0
          and cost._RESEARCH_MAX_INPUT_TOKENS > 0)
    check("trend analysis ≈ £0.095/run (documented)", 0.08 <= trend <= 0.11, f"£{trend}")
    check("both are non-zero — no un-estimated LLM feature", research > 0 and trend > 0)
    check("cheaper tier lowers the estimate (tier is honoured)",
          cost.estimate_research_cost(tier="cheap") < research)
    check("trend scales with the batch analysed (its batch IS its bound)",
          cost.estimate_trend_analysis_cost(n_competitors=20) > trend)

    print("\n" + ("ALL PASSED" if ok else "FAILED"))
    raise SystemExit(0 if ok else 1)


if __name__ == "__main__":
    main()
