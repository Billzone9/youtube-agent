# Footage-feasibility standard — prove the footage BEFORE writing the script

Companion to `visual-density-standard.md`, `house-voice-standard.md`, `vision-gate-standard.md`. This
is the doctrine we violated on the wolf and are fixing here: **source footage first, write to fit it**
(ROADMAP; spec §4.3/§71). A subject must pass a feasibility probe **before a word of script is written**.

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
- **Verdict on YIELD ALONE:** `FEASIBLE Y ≥ 20 · MARGINAL 12 ≤ Y < 20 · INFEASIBLE Y < 12` (Σn_min = 12,
  Σn_target × 1.25 = 20, for a 4-beat ~150s film — SPECIFY-1).
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
