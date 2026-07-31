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
Per the approved design (PLAN_FOOTAGE_LED Item 4 + SPECIFY-1 thresholds). `probe_feasibility(subject,
*, season, providers, llm, sample_n≈10)`:
- Sample-search the subject (+ season if the intended film is seasonal); measure the **candidate pool
  depth** E (metadata-eligible after negative filter + must-term + threshold); vision-gate a sample of
  `min(E, 10)`; compute **per-axis pass rates** (species / wild / season), the **estimated wild-in-
  season yield** `Y = p × E`, the **def-echo on the accepted reads** (the recitation check), and a
  verdict against the density-derived thresholds: **FEASIBLE Y ≥ 20 · MARGINAL 12 ≤ Y < 20 · INFEASIBLE
  Y < 12** (Σn_min=12, Σn_target×1.25=20). Fail loud INFEASIBLE when unsupported. Read-mostly; pennies of
  Haiku, **no Music, no TTS**.
- Run it on the **four Banks-approved subjects**; report per subject: pool depth E, per-axis pass rates,
  Y vs thresholds, def-echo on accepted reads, contradiction/echo counts, and FEASIBLE/MARGINAL/INFEASIBLE.
- Encode `footage-feasibility-standard.md` (wolf = known-bad; lion savanna = known-good) — feasibility is
  a required PRE-SCRIPTING stage; later feeds Slice 6's playbook so the scheduler never commissions an
  unmakeable film.

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
