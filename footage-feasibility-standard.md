# Footage-feasibility standard — prove the footage BEFORE writing the script

Companion to `visual-density-standard.md`, `house-voice-standard.md`, `vision-gate-standard.md`,
`footage-coverage-standard.md`. This is the doctrine we violated on the wolf and are fixing here:
**source footage first, write to fit it** (ROADMAP; spec §4.3/§71). A subject must pass a feasibility
probe **before a word of script is written**.

> **READ FIRST — a subject's feasibility is bounded by what the free libraries actually stock.** The
> probe measures OUR pool, but the deeper constraint is structural: free stock libraries hold *wild*
> footage for the African elephant and mostly *captive* (zoo/park) footage for most other charismatic
> megafauna, while genuinely-wild herd animals are thinly stocked. A big pool is NOT evidence of a
> makeable film — it can be a deep pool of zoo footage the wild-gate will reject. See
> **`footage-coverage-standard.md`** for the three coverage classes and the evidence. Choose subjects
> against that reality, and trust `source_film`'s real clear count over any probe estimate.

## Why (the wolf, the known-bad fixture)
The wolf was SCRIPTED first — a northern-winter narration — and only then did we ask whether wild winter
wolf footage existed. It did not: 0 verified clips across four beats, a result that survived TWO gate
implementations sharing almost no code (the footage talking, not the gate). The two best clips were a
green forest and an enclosure, settled by eye. Wolves are elusive, mostly park-filmed, and share a
silhouette with three other canids. **The subject was the problem, not the machine — and the probe would
have said so in pennies, before any script, TTS or score.** The lion (known-good) is the opposite:
savanna megafauna, abundantly filmed IN THE WILD, unmistakable — 17 clips across 7 beats.

## The probe is EXPLORATORY, not pass/fail against a pre-chosen setting
Supplying a season at probe time ("elephant in the dry season") repeats the wolf error one step earlier
— deciding the setting, then asking if it exists. So `probe_feasibility(subject)`:
- Supplies **NO season/habitat/time expectation**. **SPECIES and WILD are the only identity axes gated**
  (with the definition-free, channel-general gate — the subject NAME only, no morphology handed).
- Measures **pool depth E** (candidates eligible after the negative filter + must-term + threshold), and
  the **wild-and-correct-species yield** on a sample: `Y = (wild ∧ species clear_match ÷ sampled) × E`.
- **Verdict on YIELD ALONE**, against thresholds that SCALE WITH THE INTENDED FILM (not hardcoded from
  the wolf): `density.film_thresholds(runtime_s, n_beats)` gives `floor = Σn_min` and
  `target = Σn_target × 1.25` from the density standard for that shape. `FEASIBLE Y ≥ target · MARGINAL
  floor ≤ Y < target · INFEASIBLE Y < floor`. (Wolf 157s/4b → 12/20; lion 394s/7b → 28/52.) The probe
  also reports **`max_beats`** — the longest film the yield sustains at target density — so the target
  LENGTH is chosen from what the footage supports, not assumed.

- **POOL DEPTH IS SEARCH REACH, NOT LIBRARY DEPTH.** E counts what OUR queries surfaced, not what exists
  (zebra — among the most-filmed plains animals — returned a pool of 8: a query-construction artifact).
  So below `MIN_POOL_DEPTH` (15) the verdict is **`INCONCLUSIVE-SHALLOW`**, NOT INFEASIBLE: broaden the
  queries (subject × scene vocabulary, higher per_page — `broad=True`) and re-probe before ANY INFEASIBLE
  is believed. Slice 6's playbook must treat INCONCLUSIVE-SHALLOW as "search harder", never "skip the
  subject" — else good subjects are silently lost forever.
- **REPORTS the setting DISTRIBUTION** over the passing clips — season / habitat / time-of-day /
  shot-type, with depth per bucket. This is the raw material the footage-led script is written to. **An
  elephant pool that is overwhelmingly dry-season waterhole midday is not a failure — that is the film.**
- Reports the gate self-checks (contradiction, clip-echo). Read-mostly; pennies of Haiku, no Music, no TTS.

## Order of operations (required)
1. **Probe** candidate subjects → FEASIBLE/MARGINAL/INFEASIBLE + setting distributions.
2. Only a **FEASIBLE** subject earns a **footage-led script**, written to the distribution the probe found.
3. Then the full documentary-standard slice (curation, structural breathers, score, ambience, SFX)
   against the lion benchmark.
Never scripted-first. Later this probe feeds Slice 6's playbook so the scheduler never commissions an
unmakeable film. Choose subjects on the lion's criteria — abundantly wild-filmed and visually
unambiguous (no silhouette shared with look-alikes; the wolf/coyote and cheetah/leopard traps excluded).
