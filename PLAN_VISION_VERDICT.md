# Vision gate — three-way verdict + policy-driven uncertainty (fix the OUTPUT SHAPE, not the wording)

## Context — why a third prompt edit is the wrong move
We swung permissive → strict, both times by editing wording against a fixture set that was one-sided at
that moment; a third wording edit will just swing again. The evidence: candidate #8 recited the textbook
wolf definition — *blocky head, broad muzzle, deep chest, long legs, short ears* — and still returned
`species=false`. The model GATHERED the evidence for wolf and CONCLUDED not-wolf. That strictness comes
from *"when in doubt say false"*, not from the image. The fix is the verdict's SHAPE: let the model
report its real epistemic state, and make a POLICY (a value I can dial) decide what uncertainty costs.

**No code until approved. No species-prompt change until Banks's frame adjudication (species AND wild).**
All prior amendments stand (4,000 Music-credit ceiling; two-stage run; per-beat requiredness). No Stage-1
run until the gate is calibrated both directions.

## ADDITION — the "THE GATE IS RIGHT" outcome path (this plan must NOT assume over-strictness)
There are THREE worlds, and adjudication decides which:
- **(A) Gate over-strict on SPECIES** — clear wolves are being called not-wolf by the "say false when
  unsure" push. Fix = the three-way shape below (§1–2); a confirmed wolf then reads `clear_match`.
- **(B) Gate correct, footage CAPTIVE** — the clips are park/habituated animals, not wild. Wolves are
  among the most camera-shy large predators; genuinely wild footage is hard and costly, and a tight
  close-up of a wolf is itself evidence of captivity. Then SPECIES may be `clear_match` while WILD is
  correctly `clear_mismatch` — nothing to tune. The **feasibility probe reporting INFEASIBLE on
  subject×WILD-availability is a LEGITIMATE, valuable result**, not a failure: free stock cannot supply a
  *wild* wolf documentary → the A/B/C fork (paid wildlife stock / change subject / change season), NOT
  loosen-the-gate. Build this branch explicitly: the Stage-1 decision names a WILD-dominant scarcity as
  "wild footage infeasible", distinct from a re-brief, and the feasibility probe can terminate INFEASIBLE.
- **(C) Genuinely ambiguous animal** — coyote/wolf boundary (the fence): `uncertain`, handled by policy.
"Loosen until wolves pass" is NOT the only acceptable ending; a true INFEASIBLE is a real finding.

## 1. THREE-WAY SPECIES VERDICT (keep the feature-first reasoning that works)
The vision JSON keeps `species_features` FIRST (the reasoning that already produces good descriptions),
then reports **`species: "clear_match" | "uncertain" | "clear_mismatch"`** instead of a boolean. Prompt
principle: *list the visible distinguishing features, then classify — clear_match (features clearly the
expected subject), clear_mismatch (features clearly a DIFFERENT species: coyote/jackal/dog/hybrid), or
**uncertain** (ambiguous, or you cannot confidently distinguish). Do NOT default to mismatch when unsure
— say uncertain.* This deletes the reject-by-default push without a wording tug-of-war.
- `VisionVerdict` carries `species` (three-way) + `species_features`; the boolean `species_ok` is
  DERIVED by policy (§2), not by the prompt. **majority-of-3** votes the three-way label (mode; a 3-way
  split → `uncertain`).
- **Wild axis:** apply the SAME three-way shape **iff Banks's adjudication shows `wild` is also
  over-strict** (all three wolves also failed `wild`; his read decides). Season/habitat/time stay
  boolean (they were stable and are genuinely binary against named terms).

## 2. POLICY decides what uncertainty COSTS (a value I can change, not a phrase)
In `source_clips_for_brief`, partition each acquired, content-checked clip:
- **clear_mismatch → always REJECT.** **clear_match → eligible to ACCEPT.**
- **uncertain → held in RESERVE.** A beat is filled from **clear matches first**; the reserve is drawn
  on ONLY if the beat cannot reach `n_min` from clear matches, cheapest-doubt-first, up to `n_min`.
- Every uncertain clip actually USED is **flagged per beat in the Stage-1 report** (count + ids +
  features), so Banks sees exactly how much of a film rests on doubtful footage.
- Strictness becomes **policy constants** (later per-channel): `UNCERTAIN_POLICY = "reserve"` (vs
  "reject"), and reserve fills to `n_min` (not `n_target`). Changing the dial never touches the prompt.
- Same policy for `wild` if it goes three-way (clear-captive reject, uncertain-captivity reserved+flagged).

## 3. CATCH THE SELF-CONTRADICTION AUTOMATICALLY (a cheap permanent diagnostic)
The model already emits `species_features` beside the verdict. Add a structured **`features_indicate:
"<the species the features point to>"`** to the JSON, then compare it to the verdict:
- `features_indicate` ≈ the expected subject BUT `species == clear_mismatch`, or `features_indicate` a
  DIFFERENT species BUT `species == clear_match` → an **internal inconsistency** (today's exact bug).
- Detect it, **log it loudly** (`sourcing.vision_contradiction`), and **count it in the Stage-1 report**
  (a nonzero count means the gate is fighting its own evidence — recalibrate before trusting any result).
- **Encode as a standard** in `footage-feasibility-standard.md` (new "Evidence↔verdict consistency"
  section): any gate that emits BOTH evidence and a verdict must be checked for consistency; contradictions
  are logged + counted, never silently accepted. This would have caught the over-correction on run 1.

## 4. TWO-SIDED CALIBRATION, BOTH DIRECTIONS, before any conclusion
Once Banks confirms ground truth on the three frames:
- The **confirmed wolf → `clear_match` on all 5 runs** AND the **coyote → `clear_mismatch` on all 5**.
  BOTH, or the gate is not calibrated (a one-sided pass proves nothing).
- **SPECIES and WILD are calibrated with SEPARATE fixtures** (they are independent axes — prove it in
  practice, not just in the prompt). The most useful positive-species fixture is a **clear wolf in an
  enclosure** = `species: clear_match` / `wild: clear_mismatch`: it validates species WITHOUT needing
  scarce wild footage, and proves the axes move independently. A frame that fails BOTH proves nothing
  about independence. Fixture matrix: clear-wolf-captive (species✓/wild✗), coyote (species✗), a genuinely
  WILD non-wolf if available (wild✓/species✗ e.g. the lion in savanna), the ambiguous fence (`uncertain`).
- **Rebuild ALL fixtures as 3-frame sets** (`tests/fixtures/vision/<name>/{0,1,2}.jpg`, sampled 25/50/75%
  like production) so the calibration measures the production path, not a single frame. Re-extract
  coyote/fence/lion; add the confirmed wolf. `verify_vision_fixtures` + `measure_vision_variance` load the
  triples. If a confirmed CLEAR wolf still won't reliably `clear_match`, the gate is still too strict →
  revisit §1 (NOT by re-tightening wording). If it `clear_match`es on species but `clear_mismatch`es on
  wild, that is world (B) — not a bug.

## 5. LEDGER GAP — calibration/dev spend must be tracked too
`verify_vision_fixtures`, `measure_vision_variance`, `source_wolf_fixture` each build a `ListUsageSink`
and never drain it — `_drain_llm` only runs in the produce paths, so today's Haiku spend is invisible to
the ledger. "Track everything for honest money data" includes the work to BUILD the thing.
- Add a shared `scripts/_devcost.py` (or `ytagent/repo/ledger.drain_dev_usage(conn, sink, pricing, *,
  context)`) that drains a sink to `cost_ledger` with **`metadata.context = "calibration"`** (and
  channel_id/job_id NULL), so calibration/dev spend is DISTINGUISHABLE from production spend in every
  report and ROI figure.
- Every script that makes live LLM calls opens a conn + drains in a `finally`. `source_wolf_fixture`
  (downloads are free, but its Haiku pre-screen, if any, counts) and the two vision scripts included.
- Reconcilable against the live Anthropic balance like the produce-path LLM spend.

## Files
**Edited:** `ytagent/sourcing/vision.py` (three-way species + optional wild + `features_indicate` +
contradiction detect + majority over three-way), `ytagent/sourcing/orchestrator.py` (reserve/accept
policy + per-beat uncertain flagging + contradiction count), `ytagent/produce.py` (curate_report surfaces
uncertain-used + contradictions), `scripts/verify_vision_fixtures.py` + `scripts/measure_vision_variance.py`
(3-frame triples, both-direction assertions, ledger drain), `scripts/source_wolf_fixture.py` (ledger drain),
`ytagent/repo/ledger.py` (`drain_dev_usage` + calibration tag), `footage-feasibility-standard.md`
(evidence↔verdict consistency standard). **New:** `tests/fixtures/vision/<name>/` 3-frame sets.

## Verification
- **Offline (`verify_curation`):** three-way→policy mapping (clear_match accept, clear_mismatch reject,
  uncertain reserved+flagged, filled to n_min only); the contradiction detector fires on a crafted
  features↔verdict mismatch; the ledger drain writes a `context=calibration` row (fake LLM, no network).
- **Live (`verify_vision_fixtures`, 3-frame):** confirmed wolf `clear_match` 5/5 AND coyote
  `clear_mismatch` 5/5 (both), lion accept, fence wild-handling, incidental-axis, diagnostic recorded,
  contradiction count = 0. `measure_vision_variance`: per-axis flip rate on the 3-frame fixtures.
- Ledger shows the calibration spend, tagged, separate from production.

## Locks / conventions
Strictness is POLICY (a dial), never prompt wording. The gate emits evidence + verdict + its own
features_indicate; consistency is checked and counted. Fixtures are 3-frame, calibrated BOTH directions.
Dev/calibration spend is ledgered and tagged. Channel-general; synthetic/own audio only; gates hard-fail;
build/prove on the Mac; commit locally, no push until the ship-word. **No code until Banks approves; no
species-prompt change until his adjudication of the three frames.**
