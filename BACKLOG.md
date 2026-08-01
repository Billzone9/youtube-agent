# YouTube Agent — Backlog

Deferred items, polish, and upgrade ideas. Nothing here blocks current work; we pull from it
deliberately. Add freely as ideas arise.

**Review cadence:** fortnightly.
**Next review:** 2026-07-08.
**Reminder mechanism:**
1. Claude checks the "Next review" date whenever we work and flags it if due (pull-based).
2. TODO (see below): a small server cron that pings Telegram every fortnight — a real
   time-based nudge using the bot we already run. Until that exists, the date field is the cue.

Status legend: `[ ]` open · `[~]` in progress · `[x]` done (move done items to the bottom)

---

## Phase 0 polish (non-blocking)
- `[ ]` Add more ocean clips to `~/youtube-agent/assets/clips/`, then rebuild for a longer loop
  (slim bitrate already baked into `build_master.sh`). Reduces visible repetition.
- `[ ]` On a future rebuild, optionally cap bitrate ~6800k to match YouTube's suggestion.
- `[ ]` Tidy the harmless duplicate Docker apt-source warning.
- `[ ]` Lengthen the master beyond the current 6-minute loop (overlaps with "add more clips").

## Infrastructure / friction
- `[ ]` Fix SSH key passphrase friction (macOS keychain integration) so connecting is seamless.
- `[ ]` Tidy old ended broadcasts from the YouTube Studio Content list.

## Process / tooling
- `[ ]` Build the backlog-review Telegram reminder cron (the time-based nudge described above).
- `[ ]` Store the project repo URL in Claude's memory once the repo exists, so Claude auto-knows
  where to read the roadmap/backlog/spec each session.
- `[ ]` Decide public vs private repo (recommendation: public, secrets gitignored — lets Claude
  read it directly; private means re-pasting files each session).

## Scheduler / playbook (Slice 6)
- `[ ]` **Footage availability must inform topic selection.** Before committing to a topic, the
  scheduler/playbook should PROBE library coverage — a cheap sourcing dry-run (search Pexels/Pixabay
  for the topic's core subject, count gate-eligible matches) — and avoid or re-shape topics the stock
  libraries can't dress. **Evidence (Slice 4 proof, 2026-07-18):** the emperor-penguin script sourced
  only **1/5 shot-briefs** — free Pexels/Pixabay have almost no emperor-penguin-in-Antarctic-winter
  footage, so 4/5 briefs failed loudly (correctly, not padded). Abundant subjects (lion, ocean,
  generic wildlife) have deep coverage; niche species/biomes may not. Topic choice should be
  coverage-aware, not just trend/interest-aware. (Also feeds the cost-gated generative-B-roll
  fallback decision for the rare must-have shot stock can't provide — spec §4.3.)

## Known defect (log, do not chase)
- `[x]` **Contradiction detector — false-fire — FIXED 2026-08-01.** The false-fire came from the
  `names_other` branch (`features_indicate` names something other than the subject, yet species
  accepts → flagged). When the film subject wasn't propagated into `Expect.subject` (scene-only briefs
  set it to 'herd'/'savanna'), the gate's correct `features_indicate="African elephant"` vs an
  `expect.subject` of 'herd' tripped it on every accepted clip (3–4/run). Dropped the branch:
  `contradiction = _indicates_subject(features_indicate, subject_noun) and species == CLEAR_MISMATCH`
  only — the real "recites the subject then rejects it" signal. Regression `[4d]` in verify_curation;
  the re-run logged **0 false-fires** (2 legitimate contradictions remained, on the kept branch).

## Small robustness (from the elephant slice, 2026-08-01)
- `[ ]` **ScriptWriter JSON extraction is fragile.** `_extract_json` failed on one elephant generation
  (unescaped char in a long VO → JSONDecodeError propagated; the retry loop only re-runs on AI-tell /
  pacing / runtime, not on a parse error). A re-run succeeded. Fix: catch the parse error inside the
  bounded retry loop (re-prompt "return STRICT valid JSON"), and/or a light JSON repair pass.

## Feasibility search reach (from the elephant slice, 2026-08-01)
- `[x]` **Search reach + structural depletion — FIXED 2026-08-01 (film-wide sourcing + allocation).**
  Root cause of the elephant Stage-1 short (beats 3–7 returned 0 verified, surfacing muskox/woolly
  sheep): scene-only briefs never name the animal, so `build_query_plan` extracted scene words
  ('herd'/'savanna') into `must_terms` — an off-subject clip tagged 'herd' passed the rank filter, and
  real elephants were never reached. Fixes: (1) `build_query_plan(subject=…)` FORCES the film subject
  into `must_terms` AND every query (`_enforce_subject`); (2) NEW `source_film()` gathers ONE film-wide
  verified pool (union of all beats' subject-anchored queries) then ALLOCATES to beats by fit — no
  earlier beat starves a later one (fixes the structural depletion); (3) real pagination (`page` on the
  providers + `_search_all`, `per_page=50`, `pages=2`). Wired into BOTH Stage-1 curation and the render
  path (`_source_all_beats`). Re-run: **all 7 beats PASS** — pool 1731 candidates → 157 eligible → 90
  verified → 52 clear + 6 reserve (32 gate-rejected incl. a lion and captive elephants) → 26 allocated.
  The muskox/sheep are gone (they now score 0.0). Regression `[6]` in verify_curation.

## Small robustness (from the film-wide elephant re-run, 2026-08-01)
- `[ ]` **One vision verdict came back unparseable/malformed** (pexels 35023064) — handled safely
  (defaulted to species+wild `clear_mismatch` → rejected, 1 of 90), but a malformed-JSON RETRY inside
  `vision_check` (as ScriptWriter now does) would recover the clip instead of discarding it.
- `[ ]` **`source_film` verify pass is slow** — `max_verify=90` × 3 Haiku frames each + downloads ran
  ~45 min wall-clock (network/API latency, not CPU). The pool was plenty deep by ~40 clips. Tune:
  early-stop once the clear pool comfortably exceeds Σ n_target (e.g. 1.5×), and/or cache vision
  verdicts by asset_id so re-runs don't re-pay. Not blocking; the run completed and all beats passed.

## Known defect — species discrimination WITHIN a family is unproven (from the feasibility slice, 2026-08)
- `[ ]` **BLOCKER before any look-alike subject (leopard/cheetah, small cats, most raptors).** Removing
  the morphology definitions fixed over-strictness, but the definition-free gate now reads the old coyote
  clip (142472) as a grey wolf, and the live calibration only tests CROSS-family discrimination (a lion
  is not a wolf — trivially easy). Within-family discrimination (wolf vs coyote, leopard vs cheetah) is
  therefore UNPROVEN. Elephants/giraffes/zebra have no look-alikes, so this does NOT block film #2 — but
  it must be solved (per-subject confusable list handed as DATA? a two-stage "is it X or the look-alike Y"
  prompt?) before any subject that shares a silhouette. Feasibility should also flag "look-alike risk" per
  subject so the playbook avoids these until it's solved.

## Vision gate — hardening (PROMOTED into the feasibility slice, 2026-07-31 — no longer deferred)
The two items below are now IN the feasibility slice (changing subject requires a channel-general gate):
- `[ ]` **VISION GATE IS NOT CHANNEL-GENERAL — fix before the SECOND subject (BLOCKER for subject #2).**
  `ytagent/sourcing/vision.py` hardcodes grey-wolf/coyote morphology in `_PROMPT_DEFINITIONS` **and** in
  the `_SYSTEM` prompt's examples. On an elephant or eagle film the gate is primed with canid examples,
  and `definition_echo` compares features against irrelevant (wolf/coyote) definitions → meaningless
  numbers. Violates "general platform, not a niche tool — channel-general from slice 1" (CLAUDE.md /
  ROADMAP). Fix: species definitions become **per-subject DATA derived from the brief** (the expected
  subject + its confusable look-alikes), not constants in code/prompt. Wildlife-general, not wolf-specific.
- `[ ]` **Consider REMOVING species definitions from the prompt entirely (candidate real fix for
  definition-echo).** The model can only RECITE because we handed it the script. If `_SYSTEM` asked it to
  describe what it SEES without supplying morphology definitions, there'd be no canned text to echo —
  possibly the real fix rather than measuring recitation after the fact. **Do not act yet:** the def-echo
  numbers on the ACCEPTED winners from the clean wolf Stage-1 run are the evidence for/against this;
  decide once that data is in.

## Phase 1 enablers (promote to ROADMAP when we start them)
- `[ ]` Build asset-provenance logging into the production pipeline (URL + contributor + license
  + timestamp per clip). Required by the footage-recon findings.
- `[ ]` Choose the ElevenLabs narration voice: a specific generic deep British male (NOT a clone
  of any real narrator). Set a per-video narration budget.
- `[ ]` Decide MLA launch languages — data-driven, start with 1–2 that the audience data justifies,
  not all at once (cost scales per language).
- `[ ]` Pick the grounded-research source for script fact-checking (spec names e.g. Gemini).

---

## Done
(empty — move completed items here with the date)
