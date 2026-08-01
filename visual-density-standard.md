# Visual density standard — the house cutting rhythm

Companion to `house-voice-standard.md` (how it *sounds*) and `public-facing-output-standard.md` (what
the audience *reads*). This governs how a video *cuts* — its shot rhythm. It is channel-general: this
is cutting rhythm, not content, and applies to every channel and format. Enforced in code by
`ytagent/assembly/density.py` (`assert_visual_density`), a hard gate run before every render.

## The calibration reference — RECONCILED to the lion's ACTUAL cut (2026-08-01)
The standard is derived from the film that exists and was approved: the locked lion — **17 distinct
clips across 7 beats over 394s ≈ 2.4 clips/beat, ~23s average shot**. An earlier draft asserted "~10s
shots, 3–4 clips/beat"; that figure was an abstraction invented *after* the lion and never validated
against anything approved — and it was strict enough that the assembler would have REFUSED to render a
lion-density film. So the target is the lion's real density, not the abstraction. The wolf Pass-A cut —
**one clip carrying a beat**, and a clip reused across two beats — still FAILS. Those are the two-sided
calibration.

## The rules (hard, enforced)
1. **Cut between multiple distinct clips — HARD FLOOR: no single clip carries a beat.** A real beat
   (> `_FLOOR_BEAT_S` = 15s) holds **≥2 distinct clips**. This is the wolf's actual failure and the whole
   reason the gate exists. Looping or heavily slowing one clip to fill a beat is banned (a ≤1.15× fit
   slow-down of one short shot is fine).
2. **Shot rhythm ~23s (the lion), hard ceiling 30s.** Target a shot change about every **23 seconds**
   (`SHOT_TARGET_S`, the lion's average); no single shot exceeds **30s** (`SHOT_MAX_S`, a hard render-
   refusing ceiling); avoid cuts faster than ~3s (`SHOT_MIN_S`).
3. **LONG-HOLD FLAG (soft, review — not failure).** A shot longer than **15s** (`LONG_HOLD_S`) is
   FLAGGED in the density report, not rejected. The lion's long holds were HAND-cut with movement and
   slow-motion; a machine-selected STATIC clip held that long reads dead. So long holds must be reviewed
   and the script's shot briefs must favour clips with **internal movement** (a herd crossing, a calf
   running, dust in low sun) over static portraits, which sustain a long hold honestly.
4. **Shot-count rule.** A beat of *L* seconds holds **≥ max(2, ⌈L/30⌉)** distinct clips (the hard floor)
   and **~L/23** at the house rhythm. Feasibility thresholds derive from these at the FILM level
   (`film_thresholds`): floor = max(2·n_beats, ⌈runtime/30⌉), target = round(runtime/23) — a lion-length
   film (394s/7) → floor 14, target 17 (the lion's own clip count).
5. **No clip is reused within a video** — except a deliberate, declared motif.

## How it is enforced
- Sourcing fills each beat with **N distinct clips** (`source_clips_for_brief`), fail-loud if it cannot
  reach the beat's minimum — a beat is never padded with one stretched clip.
- The binder lays a beat's K clips end-to-end with crossfades; the narration's **measured** length
  stays the single source of beat duration, split across the shots (`even_slot(L, K)`).
- `assert_visual_density(spec, narration_s)` runs after bind, before render: it RAISES on a beat below
  the hard floor (a clip carrying a beat) or a reused clip; it **flags** (does not raise) long holds in
  `report["_long_holds"]` for review. A hard violation raises `VisualDensityError` and no render happens.

## Deliberately out of scope (for now)
Per-shot brief authoring by the script writer (richer scene variety and motifs — a follow-up that sits
on top of N-clip sourcing); declared-motif reuse plumbing (the gate already leaves the door open via
`motif_srcs`). The standard itself — rhythm, minimums, no-reuse — is fixed here.
