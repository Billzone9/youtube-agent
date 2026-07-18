# Visual density standard — the house cutting rhythm

Companion to `house-voice-standard.md` (how it *sounds*) and `public-facing-output-standard.md` (what
the audience *reads*). This governs how a video *cuts* — its shot rhythm. It is channel-general: this
is cutting rhythm, not content, and applies to every channel and format. Enforced in code by
`ytagent/assembly/density.py` (`assert_visual_density`), a hard gate run before every render.

## The calibration reference
The locked lion film — **17 distinct clips across 7 beats, a fresh shot roughly every 10–15 seconds**
(beat1 alone ran five clips at 7–13s each). That film PASSES this standard. The wolf Pass A cut — one
clip held 30+s per beat, and one clip reused across two beats — FAILS it. Those two are the two-sided
calibration, the same way the locked lion prose calibrated the AI-tell scanner and the clean lion
render calibrated the noise gates.

## The rules (hard, enforced)
1. **Cut between multiple distinct clips.** A beat's visuals are never one clip stretched or looped to
   fill the narration. Filling a beat by looping or heavily slowing a single clip is **banned** — it is
   the visual tell this standard removes. (A slight fit slow-down, ≤1.15×, of one individual short shot
   is fine.)
2. **Shot rhythm ~8–15s.** Target a shot change about every **10 seconds** (`SHOT_TARGET_S`); no single
   shot exceeds **15 seconds** (`SHOT_MAX_S`); avoid cuts faster than ~3s (`SHOT_MIN_S`) — a nervous
   flicker is as wrong as a held clip.
3. **Shot-count rule.** A beat carrying *L* seconds of narration holds **at least ⌈L/15⌉ distinct
   clips** (the hard minimum, so no shot exceeds 15s) and **about L/10** (the house target). Example: a
   40s beat → minimum 3, target ~4 distinct shots.
4. **No clip is reused within a video** — except a **deliberate, declared motif** (an explicit opt-in,
   never an accident). A clip appearing in two beats fails the gate.

## How it is enforced
- Sourcing fills each beat with **N distinct clips** (`source_clips_for_brief`), fail-loud if it cannot
  reach the beat's minimum — a beat is never padded with one stretched clip.
- The binder lays a beat's K clips end-to-end with crossfades; the narration's **measured** length
  stays the single source of beat duration, split across the shots (`even_slot(L, K)`).
- `assert_visual_density(spec, narration_s)` runs after bind, before render: it rejects any beat below
  its minimum clip count, any shot over 15s, and any clip reused across beats. A violation raises
  `VisualDensityError` and no render happens.

## Deliberately out of scope (for now)
Per-shot brief authoring by the script writer (richer scene variety and motifs — a follow-up that sits
on top of N-clip sourcing); declared-motif reuse plumbing (the gate already leaves the door open via
`motif_srcs`). The standard itself — rhythm, minimums, no-reuse — is fixed here.
