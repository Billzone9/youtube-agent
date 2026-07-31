# Footage-feasibility FIRST — pick a subject the wild footage can actually support

## The decision (settled)
The wolf is abandoned as the proving subject. The clean Stage-1 read **0 verified clips on all four
beats, reached by two gate implementations that share almost no code** — a conclusion that survives a
full rewrite is the FOOTAGE talking, not the gate. The two best clips are settled by eye, not by any
detector: **57275 is a green forest (not winter); 27367 is an enclosure (captive)**. No tuning changes
those. Wolves are elusive, mostly park-filmed, and share a silhouette with three other canids. The lion
worked on 17 clips / 7 beats because savanna megafauna are abundantly filmed IN THE WILD and a lion is
unmistakable. **The subject was the problem, not the machine.** The wolf narration stays on disk; if a
wolf ever becomes feasible on a PAID library we revisit it — it is not the road to the second film.

This slice does what the footage-led doctrine (ROADMAP "source footage first, write to fit it"; spec
§4.3/§71) has always required and we have never once run in the right order: **prove footage feasibility
BEFORE writing a word of script.**

**No code until Banks approves this plan AND picks the four subjects. Commit locally, no push until the
ship-word.**

## Part 1 — Make the gate CHANNEL-GENERAL + REMOVE the definitions (promotes both backlog items)
Changing subject forces both fixes; the wolf run gave the evidence for the second.
- **Channel-general (BLOCKER for subject #2).** `_PROMPT_DEFINITIONS` and the `_SYSTEM` examples hardcode
  grey-wolf/coyote morphology. On an elephant film the gate is primed with canids and `definition_echo`
  compares against irrelevant definitions. Species expectations become **per-subject DATA** — the
  expected subject + its plausible confusables (look-alikes) — derived from the brief/subject, passed on
  `Expect`, never constants in code or prompt. Wildlife-general.
- **Remove the morphology definitions from `_SYSTEM` entirely (act on the def_echo=1.0 evidence).** The
  clean run's only `clear_match` wolves (27367, 57275) both scored **def_echo = 1.0** — verbatim
  recitation of the definition we handed the model. The fix is to stop handing it: `_SYSTEM` asks the
  model to **describe what it SEES** (muzzle, ears, build, coat, size cues) and name the species those
  features indicate, WITHOUT being given any morphology template. With no script there is nothing to
  echo. `definition_echo` becomes a check against the DERIVED per-subject expectation text (or is
  retired if nothing is handed to the model — decided by whether the reworked gate still recites).
- **Re-calibrate after (both directions, no definitions handed):** the coyote fixture must still
  `clear_mismatch` and the lion fixture must still `clear_match` when the gate is given only the subject
  name ("grey wolf" / "lion"), not its morphology. If they don't hold, the removal went too far — but
  the hypothesis (BACKLOG-2) is that an honest describe-what-you-see gate discriminates BETTER, not
  worse, because it stops reciting. `measure_vision_variance` confirms stability; calibration spend
  ledgered `context=calibration`.

## Part 2 — Build `probe_feasibility` and run it on FOUR subjects BEFORE any script

**REFINEMENT 1 (approved) — the probe is EXPLORATORY, NOT pass/fail against a pre-chosen season.**
Supplying a season at probe time ("elephant in the dry season") is the wolf error one step earlier —
deciding the setting, then asking if it exists. So: **no season/habitat/time is supplied as an
expectation at probe time; SPECIES and WILD are the only identity axes checked.** The gate instead
**OBSERVES and reports** each clip's season / habitat / time-of-day / shot-type as free labels, and the
probe aggregates the **DISTRIBUTION** (with depth per bucket) across the wild-and-correct-species pool.
The **FEASIBLE/MARGINAL/INFEASIBLE verdict is computed on wild-and-correct-species YIELD ALONE**; the
setting distribution is reported ALONGSIDE it as the raw material the script will be written to. An
elephant pool that is overwhelmingly dry-season waterhole midday is not a failure — **that is the film,
and the script gets written to it.** This is what footage-led means.

`probe_feasibility(subject, *, providers, llm, sample_n≈10)` (per PLAN_FOOTAGE_LED Item 4 + SPECIFY-1):
- Search the subject (season-agnostic queries); measure **pool depth E** (eligible after negative +
  must-term + threshold); vision-gate a sample of `min(E, 10)` on **species + wild only**; compute the
  **species / wild pass rates**, the **wild-and-correct-species yield** `Y = p × E`, and the verdict:
  **FEASIBLE Y ≥ 20 · MARGINAL 12 ≤ Y < 20 · INFEASIBLE Y < 12** (Σn_min=12, Σn_target×1.25=20).
- Report the **setting DISTRIBUTION** over the passing clips: season {snow:n, dry:n, wet:n, unclear:n},
  habitat, time-of-day, shot-type — the raw material for footage-led scripting.
- With the morphology definitions removed from the prompt (Part 1), **`definition_echo` is RETIRED**
  (nothing is handed to recite); the **clip-echo** (near-identical features across DIFFERENT verdicts)
  and **contradiction** self-checks remain and are reported.
- Run on the **four approved subjects**; report per subject the above + FEASIBLE/MARGINAL/INFEASIBLE.
- Encode `footage-feasibility-standard.md` (wolf = known-bad; lion savanna = known-good) — a required
  PRE-SCRIPTING stage; later feeds Slice 6's playbook.

**REFINEMENT 2 (approved) — probe all four, but RANK only the three TERRESTRIAL subjects for film #2.**
Humpback footage is largely aerial-drone/underwater — different grade, motion and shot grammar, against
a density standard tuned entirely on terrestrial cuts. If film #2 were the whale, a problem could be
feasibility OR the assembler meeting water for the first time and we could not tell which. So the whale
is probed for DATA but **excluded from the film-#2 ranking**; it becomes the **Phase-2 cross-biome
generalisation test**, run deliberately as that question, never smuggled in as film #2. Film #2 is
chosen from **elephant / giraffe / zebra** on the probe data.

## Part 3 — Only a FEASIBLE subject earns a script (then the full documentary-standard slice)
Once a subject returns FEASIBLE, write a **footage-led** script to what the probe ACTUALLY found (its
real pool, seasons, shot types), then run the full documentary-standard slice — curation, structural
breathers, score, ambience, SFX — against the lion benchmark. Not before.

## THE FOUR CANDIDATE SUBJECTS I propose (Banks picks) — abundant WILD footage + visually unambiguous
Chosen on the lion's criteria, not the wolf's: safari/ocean megafauna that stock libraries film heavily
IN THE WILD, with a silhouette no other species shares. Deliberately EXCLUDED: any canid (wolf lesson);
spotted cats (cheetah↔leopard confusable — the same silhouette trap); small/elusive species; niche
biome specialists (the penguin-coverage lesson).
1. **African elephant** — the safest bet. Unmistakable (trunk, tusks, ears, bulk); no confusable species;
   an enormous WILD free-stock pool (waterholes, savanna, herds); suits the reverent voice.
2. **Giraffe** — unmistakable by definition; abundant wild safari footage; distinctive movement and
   scale give a cinematographer plenty; zero look-alikes.
3. **Zebra** — unmistakable stripes; abundant wild herd/plains footage; strong graphic subject; no
   confusable non-zebra.
4. **Humpback whale** — a DIFFERENT biome to prove the pipeline generalises beyond savanna; iconic and
   heavily wild-filmed (breaches, flukes, ocean docs); ties to the ocean theme; unmistakable when
   breaching. (Alternates if you prefer: brown bear at a salmon run, or plains bison — both abundant,
   both a touch more confusable than the four above.)

## Verification
- Offline: the reworked gate's per-subject Expect + describe-only prompt; `definition_echo` against the
  derived expectation; the density-compat + fixture tests still green.
- Live: fixture re-calibration (coyote reject / lion accept with NO morphology handed); the four-subject
  probe report. Full regression sweep green.

## Conventions / safety
Channel-general (subject is DATA; nothing niche in code — this slice removes the last wolf-specific
constants). Feasibility is a required pre-scripting gate henceforth. Pennies of Haiku only; no Music, no
TTS, no upload. Build/prove on the Mac. Commit locally; **no push until the ship-word.**
