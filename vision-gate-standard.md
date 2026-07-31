# Vision-gate standard — the content gate and its self-checks

Companion to `visual-density-standard.md` and `house-voice-standard.md`. Governs the sourcing VISION
GATE (`ytagent/sourcing/vision.py`): the Haiku-vision check that decides whether a downloaded clip
actually shows the right **species**, a genuinely **wild** setting, and the expected **season/habitat/
time**. Metadata can't see any of that; the gate is the real content check.

## Verdict shape — report the epistemic state, let POLICY decide the cost
- **Identity axes (species, wild) are THREE-WAY:** `clear_match | uncertain | clear_mismatch`. The
  prompt lists the observed features FIRST, names the species they indicate, THEN labels. It must NOT
  be pushed onto a yes/no — "when in doubt, say uncertain", never default to mismatch.
- **Setting axes (season, habitat, time) are boolean** against named terms; required per-beat by what
  the narration locks (season always; habitat/time only where the VO names them).
- **Determinism:** `temperature=0` (accepted on Haiku 4.5) + **majority-of-3** votes each label. A
  genuinely ~50/50 animal will still flip — that is the frame's ambiguity, not a gate defect.
- **Policy, not prompt, sets strictness** (`classify()`): `clear_mismatch` rejects; `clear_match`
  accepts; `uncertain` is held in RESERVE and drawn only to reach a beat's `n_min`, every uncertain
  clip used flagged per beat. Strictness is a dial, never a wording swing.

## SELF-CHECKS — the gate must be watched for reasoning failures (both counted; nonzero ⇒ do NOT conclude)
The gate is an LLM and fails in two mirror-image ways; both are cheap, permanent, automatic checks —
the same category. **When either fires, the gate's verdicts are not trustworthy evidence: recalibrate
before drawing ANY scarcity/feasibility conclusion (Stage-1 returns INCONCLUSIVE).**
1. **Evidence↔verdict CONTRADICTION** (`VisionVerdict.contradiction`). The model emits both the
   observed features and a `features_indicate` (the species those features point to). If
   `features_indicate` names the expected subject but the label is `clear_mismatch` (or names another
   species but the label is `clear_match`), it is **fighting its own evidence**. A `_NOT_CLEAN`
   qualifier list (`hybrid`, `dog`, `coyote`…) prevents "wolf-dog hybrid" false-positives. Hard signal.
2. **CLIP-vs-CLIP echo** (`detect_echo`, hard signal). Two DIFFERENT clips with near-identical features
   (SequenceMatcher ≥ 0.75) **but DIFFERENT species verdicts** — the gate gave different answers to the
   same-looking evidence. **Same-verdict near-identical features do NOT flag**: the density standard
   REQUIRES 3–4 accurate shots of the same subject per beat ("broad muzzle, blocky head" ×4 is correct
   by construction, not recitation) — flagging those would return INCONCLUSIVE on every legitimate film.
3. **DEFINITION-echo** (`definition_echo`, reported caution — NOT a hard block). The fraction of a
   prompt definition's content words present in a clip's `features` (containment). High
   (≥0.80) means the description **tracks the CANNED definition, not the specific image** — the failure
   that clip-vs-clip echo misses: it fires whether or not two clips recite the SAME definition. Measured
   on the wolf run, the ACCEPTED wolves recited the wolf definition at **0.85–1.0** (one verbatim) while
   the rejected coyotes tracked the coyote definition at 0.67 — i.e. the acceptances were the MORE
   recited. Because a real animal legitimately matches its own definition, this is **reported per clip
   (and per accepted winner), never auto-blocking**: it tells you how much to trust a PASS, not whether
   to run. A PASS built on definition-echoed acceptances is surfaced with a loud caveat.

## Calibration doctrine — two-sided, both axes, 3-frame, permanent fixtures
- Fixtures are **3-frame sets** (`tests/fixtures/vision/<name>/`, 25/50/75% like production), not single
  frames. Calibrate **species and wild with SEPARATE fixtures** and BOTH directions: a clear wrong-
  species (coyote → `clear_mismatch`) AND a clear right-species (a confirmed animal → `clear_match`); a
  clear-captive (fence → wild `clear_mismatch`) AND a clear-wild (savanna → wild `clear_match`). A
  clear animal in an enclosure (species `clear_match` / wild `clear_mismatch`) proves the axes are
  independent. `verify_vision_fixtures` asserts these on live Haiku; `measure_vision_variance` reports
  the run-to-run flip rate.
- **"The gate is right" is a valid outcome.** If a subject's only free-stock footage is captive/park
  (world B), the feasibility probe returning INFEASIBLE-on-wild is a legitimate, valuable result — not
  a gate to loosen. Do not tune until a wrong answer becomes a right one.

## Spend
Vision + query Haiku are the gate's only cost (footage downloads are free). Calibration/dev runs must
ledger their spend tagged `context=calibration` (`drain_dev_usage`), distinct from production spend.
