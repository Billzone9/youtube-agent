# Diagnostic — why the SAME subject yielded 52 clear clips one day and 8 the next

> **RESOLVED (2026-08-02, slice 6b-bis).** Footage-led auto-scripting was wired in structurally
> (ScriptWriter now REQUIRES a probe-observed distribution; unsourceable content is scanned + regenerated
> in the bounded-retry loop). Re-running the SAME failed subject through the fixed path took it from
> **8 clear (FAILED) → 54 clear (PASS, all 7 beats)** — beating even the hand-written Old Paths (52).
> Proof: `scripts/prove_footage_led.py` (sourcing-only, no spend). Table at the bottom of this file.


Two `african elephant` productions, one week apart, same libraries, same gate, wildly different yield:

| run | job | date | pool candidates | eligible | clear | allocated | outcome |
|-----|-----|------|-----------------|----------|-------|-----------|---------|
| **The Old Paths** (probe-led) | 93 | 2026-08-01 | **1731** | **157** (9.1%) | **52** | 26 | full film |
| **African Elephant** (script-first) | 154 | 2026-08-02 | **871** | **18** (2.1%) | **8** | 9 | **FAILED at sourcing** |

**Verdict: (a) brief specificity, driving (b) query construction. NOT (c) rate-limiting. NOT (d)
no-repeat exclusion.** The failing run wrote its shot briefs FIRST and hoped the footage would match;
the successful run wrote its briefs TO a probe's observed footage distribution. This is the wolf
failure in a new place — the gap between what a script asks for and what sourcing can deliver.

---

## The evidence, as strings

### Shot briefs — the two scripts ask for DIFFERENT KINDS OF FOOTAGE

**The Old Paths (52 clear) — every beat is "the herd MOVING across savanna" — the commonest elephant
footage there is:**
- beat2: *"Wide and medium shots of the matriarch … walking at the front or flank of the herd …"*
- beat3: *"Wide shots of the herd strung out in loose column across open savanna — a long line of
  animals crossing dry, cracked earth or pale grass …"*
- beat5: *"Calves … moving within the herd, keeping pace, crowded close to their mothers …"*
- beat7: *"Evening golden-hour shots — the herd receding across open savanna toward the low sun …"*

**African Elephant (8 clear) — beats ask for macros, specific behaviours, and ARCHIVAL footage stock
libraries do not hold:**
- beat2: *"**Close shots of an elephant's eye — deep, amber-brown, alert** — intercut with a matriarch …"*
- beat3: *"**Slow-motion footage of elephants communicating** … a low-angle shot emphasising **throat and
  chest rumbles** …"*
- beat4: *"**Tight footage of a trunk at work**: stripping bark …, drinking …, dusting …, gently touching a calf …"*
- beat6: *"… old bull … contrasted with **archival-style footage or photographs suggesting the history of
  the ivory trade** (use carefully, ethically sourced)"*  ← **fundamentally unsourceable from stock wildlife libraries**
- beat7: *"habitat shaped by elephants — **toppled trees opening forest canopy, waterholes excavated in
  dry riverbeds, clearings browsed into grassland** …"*

### The queries those briefs generated (the mechanism, (b))

Same forced `must_terms` both runs (`african`, `elephant`) — so this is NOT a must_terms problem. The
difference is the SCENE WORDS:

| The Old Paths → broad, overlapping, high-yield | African Elephant → narrow, disjoint, low-yield |
|---|---|
| elephant herd golden hour savanna | elephant eye close up |
| elephant herd migration savanna dust | elephant trunk stripping bark |
| elephant herd moving together | elephant trunk drinking water |
| elephant herd walking dry terrain | elephant ears spread communication |
| elephant matriarch leading herd | elephant herd gathering rumbling |
| elephant dust dry savanna | elephant habitat damaged trees |
| elephant herd savanna sunrise | elephant resting shade worn tusks |
| elephant calf herd moving | old bull elephant tusks grazing |
| elephant herd emerging treeline | large tusks elephant pushing tree |
| elephant matriarch leading herd away | elephant young calf learning trunk |

~22 Old-Paths queries hammer ONE broad concept (herd + savanna + moving) from many angles → a **deep,
overlapping pool of common footage** (1731 candidates). The fresh queries each target a DIFFERENT narrow
scene → a **shallow pool per query, little overlap, much off-subject** (871 candidates, and only 2%
survive the rank threshold vs 9%).

### What the gate saw

- Old Paths candidates ranked **1.0** (queries matched candidate tags exactly). Fresh candidates ranked
  **0.65** (queries matched poorly — the footage on offer wasn't what the brief asked for).
- Fresh vision rejects were **off-subject**, pulled in by the narrow queries: *"Small … animal"*,
  *"Slender …"*, *"Spotted …"*, plus captive greys (`wild=clear_mismatch`). The specific scene words
  surfaced the wrong animals.

---

## The four hypotheses, ruled in / out with evidence

- **(a) brief specificity — CONFIRMED, the root cause.** The fresh script asked for eye macros, trunk
  close-ups, communication behaviour, archival ivory-trade footage, and ecological-impact shots — scenes
  the libraries lack. The successful script asked for the herd walking in savanna, which they are full of.
- **(b) query construction — CONFIRMED, the mechanism.** Downstream of (a): specific briefs → specific
  queries → half the candidates (871 vs 1731), a quarter the eligible rate (2% vs 9%), lower match
  scores (0.65 vs 1.0). Same must_terms both runs.
- **(c) rate-limiting / environmental — RULED OUT.** The failing run (2026-08-02) logged **0
  `sourcing.search_error`s**. (The *successful* day logged 11 and still got 52.) Not throttled.
- **(d) no-repeat exclusion starving reuse — RULED OUT, and it is NOT self-inflicted.** `_source_all_beats`
  calls `source_film` **without `exclude_ids`** (produce.py:89) — there is no cross-production exclusion.
  Already-sourced clips are **cache-hits** (reused, not skipped). The 8 fresh-clear clips
  (`20277028, 20277038, 18750380, 30972324, 31223127, 30972326`) have **zero overlap** with the
  original 26 — not because they were excluded, but because the different queries surfaced different
  candidates. **Our own no-repeat guard is NOT the cause; reuse of the same subject's footage works.**

---

## Why this is fatal for 6c specifically

6c autonomously commissions productions. A commissioning path that is **0-for-2 at sourcing on
auto-written scripts** is not autonomy — it is a scheduler for generating failure alerts. The
successful film was hand-adjacent: its script was written to a probe's OBSERVED setting distribution
(footage-led — the established doctrine). The auto-script path writes briefs first and hopes
(script-led). 6c must not be built on top of a script-first commissioning path.

---

## Candidate fixes (options + recommendation — NOT built, NOT tuned)

1. **★ RECOMMENDED — footage-led auto-scripting.** Before scripting, run `probe_feasibility` (it already
   reports the observed season/habitat/time/**shot-type** distribution). Feed that distribution into the
   ScriptWriter so briefs are written to what the library actually holds — exactly how *The Old Paths*
   was produced. This is the footage-feasibility doctrine, already proven, simply **not wired into the
   auto-script path.** It also reframes 6c: the scheduler commissions **probe → observed distribution →
   script-to-distribution → source**, never script-first. Biggest change, correct change, and 6c needs it.
2. **Brief-specificity constraint in the ScriptWriter.** Instruct it to pitch briefs at the "broad
   common scene" level and to NEVER ask for archival/historical/photograph/non-stock content (beat6's
   ivory-trade footage is unsourceable at any yield). Cheap, blunter; pairs well with (1) and is
   arguably a required sub-part of it.
3. **Per-beat feasibility gate after scripting.** Cheaply probe each beat's queries; regenerate any beat
   whose pool is too thin before committing. Adds cost + latency; treats the symptom, not the cause.
4. **Sourcing relaxation on shortfall.** When a beat is short, broaden its queries (keep subject, drop
   scene words). A band-aid that would dress beats with generic footage — cheapens the film; not a fix.

**Recommendation: (1) + (2) together** — write the script to the probe's observed distribution, and
forbid unsourceable content. That is the footage-led doctrine the elephant already proved, made
automatic, and it is a prerequisite input to 6c's design, not an optional polish.

**Also worth noting for the probe itself (already in BACKLOG):** the probe's small-sample yield
(giraffe MARGINAL/9-of-10) over-estimated the deep film-wide yield (5 clear/935). So (1) needs the
probe's *distribution* output (which was reliable), not its *headline verdict* (which was optimistic).

---

## PROOF (slice 6b-bis) — options 1 + 2 built structurally, re-run on the failed subject

Structural change: `ScriptWriter.write(footage_distribution=…)` is now a REQUIRED argument (no default →
a call without it fails loud) fed the probe's observed distribution; `authoring/sourceability.py`
flags archival/historical/photo/illustration/map/CGI/reenactment briefs and regenerates them in the same
bounded-retry loop as the AI-tell scanner. `_st_script` probes → distribution → writes, so the auto path
physically cannot regress to script-first. Same subject `african elephant`, sourcing-only, no spend:

| run | pool | eligible | clear | allocated | outcome |
|-----|------|----------|-------|-----------|---------|
| The Old Paths (probe-led, hand) | 1731 | 157 | 52 | 26 | full film |
| African Elephant (script-first) | 871 | 18 | **8** | 9 | **FAILED** |
| **FOOTAGE-LED (auto, fixed)** | 1702 | 85 | **54** | 21 | **PASS — all 7 beats 3/2** |

Observed distribution used: habitat savanna/grassland (dominant); time golden/dawn/dusk (dominant);
shots wide (dominant). New briefs came out broad ("a herd moving across savanna at golden hour"); new
queries broad ("elephant herd dry savanna", "elephant savanna golden hour", "elephant family moving
savanna"); the archival ivory-trade beat is gone. **The fix is sufficient — verified before 6c.**
