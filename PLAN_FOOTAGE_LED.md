# Footage-led sourcing — fix the contaminated vision gate + a pre-scripting feasibility probe

## Context — the defect (Stage-1 evidence is VOID until this is fixed)
`_SETTING` in `query.py` conflates four axes into one bag — **season** (snow/winter/autumn),
**habitat** (forest/boreal/tundra/arctic/mountain/coast/ocean/desert), **time-of-day**
(dusk/dawn/twilight/night), **mood** (cold/dark/warm/misty). `Expect.from_plan` passes that whole bag
as `season`, and the vision prompt asks for ONE boolean over all of it. The wolf run handed the gate
`('snowy','boreal','forest','dawn','snow')` and demanded a single yes/no. So:
- a genuine wild wolf in deep snow filmed at **midday** fails on `dawn`;
- a genuine snowy wolf on open **tundra** fails on `forest`.
Those rejections say NOTHING about whether snowy-wolf footage exists. The two spot-checks (57275 green
forest, 27367 enclosure) were legitimate but tested the obvious axes; nobody checked whether clips died
on `dawn` or `boreal`. **"Free stock cannot source a wild winter wolf" is NOT established.**

Compounding bug — the pair query: `setting[0]` (whichever setting word came first in the brief, often
a habitat/mood) drives the single guaranteed subject+setting query; the other queries were
season-blind, so **3 of 4 wolf queries searched without any season term** → the candidate pool was
dominated by green footage before the gate ever ran.

Root cause is ORDERING. ROADMAP.md ("**Footage-led scripting: source footage first, write to fit it**")
and spec §4.3/§71 ("Script — footage-led: written/adapted to the footage actually available") already
require footage-first. The wolf was SCRIPTED first, then footage sought to fit a winter script. Item 4
encodes the missing pre-scripting stage so this can't recur.

**No code until Banks approves. All approved amendments still stand (incl. the 4,000 Music-credit
ceiling). No Stage 2 until a CLEAN Stage 1 is green and Banks says go.**

## APPROVED AMENDMENT + SPECIFICATIONS (2026-07-31 — override anything below they touch)

**AMENDMENT — axis requiredness is PER-BEAT, derived from the narration.** Globally-advisory habitat +
time-of-day swaps over-constraint for UNDER-constraint: beat4 "The howl at the edge of dark" locks the
time of day in the VO itself, so advisory time would let midday footage sit under a dusk narration —
the exact error this slice exists to prevent. Rule: **read each beat's narration text, determine which
axes it LOCKS, make those blocking FOR THAT BEAT ONLY.** Season stays blocking throughout. A beat whose
VO names no habitat leaves habitat advisory; a beat whose VO names no time leaves time advisory. Report
the **derived per-beat requiredness** in the Stage-1 output. This is measure-first applied to the
SCRIPT; it generalises to every film and is encoded in `footage-feasibility-standard.md` (Item 4).
- *Wolf caveat:* job 29 did not persist the VO text (only the mp3s), so the per-beat lock is derived
  from the viewer-facing **beat LABEL** (VO-level, not the brief, which over-names axes I wrote). Labels
  give: beat1 "Before the pack wakes" → **time (dawn) blocking**; beat4 "…edge of dark" → **time (dusk)
  blocking**; beats 2/3 name no time/habitat → time+habitat advisory; season blocking on all four.

**SPECIFY 1 — feasibility threshold (derived from the density standard).** Per beat
`n_min = min_clips(L)`, `n_target = max(target_clips(L), n_min+1)`. Wolf beats (37.2/43.0/37.3/39.5s):
**Σn_min = 12** (3 each), **Σn_target = 16** (4 each). Feasibility target **T = Σn_target × 1.25
(margin for the vision gate's rejection rate + unusable-but-passing clips) = 20**; floor **= Σn_min =
12**. The probe searches subject+season, finds `E` metadata-eligible candidates, vision-samples
`min(E, sample_n=10)`, gets pass-rate `p`, estimates yield **Y = p × E**. **FEASIBLE: Y ≥ 20 ·
MARGINAL: 12 ≤ Y < 20 · INFEASIBLE: Y < 12** (or E < 12 regardless of p). The 25% margin is the single
tunable; sample_n=10 bounds probe cost to ~10 vision calls.

**SPECIFY 2 — Stage-1 decision rule (fixed BEFORE the run, so the verdict isn't rationalised after):**
- **PASS (green):** every beat reaches `n_min` verified clips → proceed to Stage 2 on Banks's go.
- **MARGINAL → RE-BRIEF the short beats:** some beats green, others short, AND the shortfall is
  attributable to an **incidental per-beat constraint** (an over-tight habitat/time lock, or a narrow
  brief) — i.e. OTHER beats on the same subject+season succeeded, OR the short beat's dominant rejection
  axis is habitat/time, not species/wild/season. Action: loosen the over-tight lock / broaden that
  beat's brief and re-source ONLY those beats.
- **FAIL → SUBJECT or SEASON change (the A/B/C fork):** the shortfall is **subject×season scarcity** —
  species/wild/season is the dominant rejection axis across ≥half the beats, OR feasibility is
  INFEASIBLE (Y < 12). Free stock genuinely lacks the wild in-season subject; escalate to paid stock or
  change subject/season. No amount of re-briefing fixes a scarcity.

**SPECIFY 3 — vision-cost estimate (computed; stated before the clean Stage 1 runs).** Per beat
`n_target=4`, `max_attempts=n_target×3+10=22` → **worst case 88 vision calls** (4 beats); typical
~40–70 (fewer if in-season footage is found and n_target=4 is hit early; two axes now advisory means
more clips PASS, so winners arrive sooner). Each call = 3 frames @512px (~197 img-tok each) + system +
prompt ≈ **~1,070 input + ~150 output tokens**. Haiku 4.5 $1/$5 per Mtok, FX 0.79:
- typical ~50 calls ≈ **$0.095 ≈ £0.08** · high ~70 ≈ $0.13 ≈ £0.10 · worst-case 88 ≈ $0.16 ≈ **£0.13**.
Plus 4 query-plan Haiku calls (~£0.002). **Total ≈ £0.08–0.13; wall-clock ~15–30 min (download-bound,
sequential).** No Music, no downloads-cost (free stock). Comfortably within budget — the discipline is
to state it, not that it's large.


## Item 1 — SEPARATE THE AXES
- Split `_SETTING` into **`_SEASON`**, **`_HABITAT`**, **`_TIME_OF_DAY`**. **DROP the mood adjectives
  (cold/dark/warm/misty) from gating entirely** — unjudgeable from a frame, they belong nowhere near a
  pass/fail (they may still colour prose, never the gate).
- `QueryPlan` replaces the single `setting` with **`season`, `habitat`, `time_of_day`** tuples (each a
  distinct axis). `_llm_plan` returns them separately; the deterministic fallback classifies brief
  words by which list they hit.
- `vision.Expect` carries the three axes each with an explicit `required` flag. **Season is always
  required; habitat + time-of-day are required PER-BEAT** where the beat's narration/label locks them
  (the Amendment) — otherwise advisory. A `derive_axis_locks(text)` helper scans the beat text and
  returns which axes are locked.
- The vision gate judges each as a **separate boolean** — `species_ok, wild_ok, season_ok, habitat_ok,
  time_ok` — each with its own short reason, and `season_ok` is judged ONLY against the season terms
  (snow/winter), never habitat. `overall_ok = species_ok AND wild_ok AND (season_ok if required)`;
  advisory axes are reported, never block. The verdict **names which axis failed**.
- **Re-run the fixture calibration** and **ADD a fixture**: a genuinely wild, correct-species,
  in-season clip whose TIME-OF-DAY (or habitat) differs from the brief must **PASS** — proving an
  incidental-axis mismatch no longer rejects good footage. (Fixture sourced during the build; a wild
  snowy wolf in daylight against a "dawn" brief is the target.)

## Item 2 — FIX THE PAIR QUERY
- Pair on the **SEASON** term specifically (`season[0]`), never `setting[0]`.
- When the brief is **season-locked**, the **MAJORITY of queries must carry the season term** — the
  LLM prompt instructs it, and the deterministic builder enforces it (rewrite/augment so ≥⌈n/2⌉+1
  queries pair subject+season). Habitat/time-of-day may enrich individual queries but never replace the
  season pairing. This kills the "3 of 4 season-blind" pool contamination.

## Item 3 — RE-RUN STAGE 1 (clean evidence)
- Axes separated; **species + wild + season blocking on every beat; habitat + time-of-day blocking ONLY
  on the beats whose label/VO locks them** (the Amendment — beat1 time=dawn, beat4 time=dusk; others
  advisory).
- Report per beat: the **derived requiredness** (which axes were enforced), verified counts, AND a
  **per-axis rejection breakdown** (how many candidates died on species vs wild vs season vs the
  locked incidental axis). Then apply the SPECIFY-2 decision rule. Pennies of Haiku, **no Music spend**.

## Item 4 — FOOTAGE-FEASIBILITY PROBE (encoded as a standard)
- New `ytagent/sourcing/feasibility.py`: **`probe_feasibility(subject, *, season, habitat, providers,
  llm, sample_n=~8) -> FeasibilityVerdict`** — runs BEFORE scripting. Sample-search subject+season,
  vision-gate the small sample, return **per-axis pass rates**, an **estimated wild-in-season yield**,
  a **cost estimate** (the sample's Haiku pennies), and **`feasible: bool`** — **fails loud when a
  subject×season combination is unsupported** (yield below the SPECIFY-1 threshold: FEASIBLE Y≥T_target,
  MARGINAL floor≤Y<T_target, INFEASIBLE Y<floor). Cheap, read-mostly. The per-beat axis-lock rule (the
  Amendment) is encoded in `footage-feasibility-standard.md` here.
- Becomes a **required PRE-SCRIPTING stage** in the production flow (script only a topic whose footage
  is proven feasible), and later **feeds Slice 6's playbook** so the scheduler never commissions an
  unmakeable film (the BACKLOG coverage-probe lesson, now vision-verified not tag-counted).
- **`footage-feasibility-standard.md`** (pattern of `visual-density-standard.md` /
  `house-voice-standard.md`): the standard = footage-first, feasibility-gated before scripting;
  **known-bad fixture = this wolf-winter run; known-good = the lion's savanna**; cites ROADMAP
  "source footage first" + spec §4.3/§71. A CLAUDE.md bullet points to it.

## Item 5 — NEGATIVE-TERM REVIEW (justify or drop; per-channel, conservative default)
The vision gate's `wild_ok` is now the real captivity check, so the cheap metadata pre-filter should be
**minimal and unambiguous** — its only job is to save a download, never to pre-empt the gate on a
judgement call.
| Term | Verdict | Reason |
|---|---|---|
| zoo, cage, caged, aquarium, enclosure, captive, captivity, leash, circus, petting | **KEEP** | unambiguous captivity |
| corral, pen, farm | **DROP** | ambiguous/false-negatives — `pen` is a common token, `farm`/`corral` describe land not the animal |
| sanctuary, rescue | **DROP** | land DESIGNATION, not captivity — a great deal of genuinely wild footage is shot in reserves/sanctuaries |
| pet | **KEEP** (domestic) but channel-configurable |
Make `_NEGATIVE_TERMS` a **per-channel config value** (stored data, no code edit) with the conservative
KEEP-set as the default; the vision gate carries the nuanced captivity call.

## Item 6 — VISION GATE FAIL-OPEN — reasoning + recommendation
**Current behaviour:** no LLM → the gate is SKIPPED and the clip PASSES.
**Why it was written that way:** it mirrored the honest-degradation pattern of `get_llm_provider` /
`get_stock_providers` (missing key → `None`) and query planning (which falls back to deterministic
keywords). Under that lens, "no LLM → don't gate" looked consistent.
**Why that reasoning is wrong here:** query planning degrades to a WORSE-BUT-FUNCTIONAL path — it still
produces queries. The vision gate degrading to *pass-everything* is categorically different: it
**silently removes the content guarantee**, so captive/wrong-species/off-season footage flows in
UNSEEN and the film looks fine while being contaminated — the exact silent quality hole that fail-loud
exists to prevent, and the opposite of how the **noise gate** and **density gate** behave (they
HARD-fail). A silently-disabled quality gate is worse than none, because it reads as "checked".
**Recommendation — FAIL LOUD when the gate is required but unavailable:** curation REQUIRES an LLM for
the vision gate; `vision=True` + no LLM → **raise** a clear, actionable error ("vision gate required but
no LLM configured — set ANTHROPIC_API_KEY or pass vision=False"). Keep an **explicit** opt-out
(`vision=False`) for callers that knowingly forgo it (e.g. a non-wildlife channel), always **logged,
never silent**. Update `verify_curation` so the "no-LLM" case asserts a RAISE, and the honest-skip is
tested only via the explicit `vision=False` path.

## Files
`ytagent/sourcing/query.py` (axis split + pair fix), `ytagent/sourcing/base.py` (QueryPlan axes),
`ytagent/sourcing/vision.py` (Expect axes + per-axis prompt/verdict + fail-loud), `ytagent/sourcing/
rank.py` (minimal per-channel negative list), **new** `ytagent/sourcing/feasibility.py` +
`footage-feasibility-standard.md` + CLAUDE.md bullet, `scripts/verify_curation.py` (per-axis + pair
majority + fail-loud + minimal negatives), `scripts/verify_vision_fixtures.py` (+ incidental-axis
fixture), `scripts/prove_e2e.py` (Stage-1 per-axis breakdown), `tests/fixtures/vision/` (+ the new
pass fixture).

## Verification
- **Offline (`verify_curation`, zero spend):** season/habitat/time classified into the right axes;
  the pair query pairs on SEASON and the majority of season-locked queries carry it; the vision
  required-axis logic (season blocks, habitat/time advisory); the minimal negative list; **vision
  fail-loud when required + no LLM**, and the explicit `vision=False` skip. All prior verifies green.
- **Live calibration (`verify_vision_fixtures`):** real Haiku on all fixtures INCLUDING the new
  incidental-axis fixture (wild in-season clip, wrong time-of-day → PASS); fence→wild, coyote→species
  still FAIL.
- **Live clean Stage-1 (item 3):** per-beat verified counts + per-axis rejection breakdown. Then the
  A/B/C fork is decided on real evidence.

## Still standing
All approved amendments (structural breathers, measure-first, two-stage run, **4,000 Music-credit hard
ceiling**). Footage-feasibility becomes a required pre-scripting stage going forward. Channel-general;
synthetic/own audio only; gates hard-fail; build/prove on the Mac; publishing+spending Telegram-gated;
commit locally, **no push** until the ship-word.
