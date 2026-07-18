# Visual density — multi-clip-per-beat, the house cutting standard (promoted deferred → REQUIRED)

## Context & verdict
Pass A proved the pipeline end to end (narration **perfect**), but the **visuals fail the house
standard**: one clip held 30+s per beat, and beat2/beat4 repeated the same clip (pixabay:62595). The
lion film is the calibration reference — **17 distinct clips across 7 beats, a fresh shot every
~10–15s, no clip reused**. This cut does NOT ship; Pass B is cancelled. This plan makes multi-clip-
per-beat a REQUIRED, enforced standard and re-makes the wolf to it.

**Why it happened (root cause, verified in code):** the binder emits ONE `Clip` per beat, and
`stage1.build_beat_fitted` STRETCHES/LOOPS that single clip to the whole narration length. The
assembler already has a multi-clip crossfade path (`stage1.build_beat` xfades N clips) and the spec
`Beat.clips` is already a tuple — the machinery exists; nothing feeds it more than one clip, and
nothing fits N clips to a measured narration length.

**The numbers make it concrete.** The wolf's four beats are long — measured narration
**37.2 / 43.0 / 37.3 / 39.5 s** (157 s total). At a ~10 s shot that is **~4 clips/beat ≈ 16 shots**,
right at the lion's scale (17). Density minimum (no shot > 15 s) = **≥3 clips per beat**.

## 1) Encode the VISUAL DENSITY standard (house standard + CLAUDE.md)
New doc **`visual-density-standard.md`** (sibling of `house-voice-standard.md` /
`public-facing-output-standard.md`), and a CLAUDE.md "Technical conventions" bullet pointing to it. The
standard, calibrated to the lion:
- A beat's visuals **must cut between multiple distinct clips** — never one clip stretched or looped
  past **~15 s**.
- **Target a shot change every ~8–15 s** (lion avg ~10–11 s; its beat1 ran 5 clips at 7–13 s each).
- **Shot-count rule:** a beat of narration length *L* seconds carries **≥ ⌈L/15⌉ distinct clips**
  (hard minimum) and **~⌈L/10⌉** (target).
- **No clip is reused within a video** — except a *deliberate, declared motif* (an explicit flag, not
  an accident). This is the beat2/beat4 failure, made structurally impossible.
- **Looping/large slow-down of a single clip to fill a beat is BANNED** (it is the visual tell we are
  removing); slight fit slow-down (≤1.15×) of an individual short shot is allowed.
- Calibration anchor: the locked lion film PASSES; the shipped wolf Pass A FAILS — exactly the two-
  sided calibration used for the AI-tell scanner and the noise gates.

## 2) Sourcing fills a beat with N distinct clips
Recommended approach: **one shot-brief per beat, source N distinct clips from it** (simpler and more
robust than per-shot briefs; reuses the existing ranker; a beat's N clips are the top-N *distinct*
wolf-in-snow shots — genuine shot variety without extra LLM calls or N× the NoMatch surface).
New `ytagent/sourcing/orchestrator.py`:
- **`source_clips_for_brief(conn, providers, *, brief, brief_ref, approx_seconds, …, n_target, n_min,
  exclude_ids: set) -> list[SourcedAsset] | NoMatch`** — build the query plan once, search, rank, then
  walk the eligible list downloading + gating, collecting **distinct** winners (distinct
  `(source, asset_id)`, skipping `exclude_ids`) until `n_target` are held. Returns the list if
  **≥ n_min** distinct clean clips were found; otherwise a `NoMatch` (density can't be met → fail
  loud, never one clip stretched). Each winner is cached + provenance-logged exactly as today.
- Keep the existing single-winner `source_for_brief` (used by `verify_slice4`, `source_shot_briefs`) —
  `source_clips_for_brief` is the N-clip generalisation, not a rewrite.
- **No-repeat guard lives here + in the conductor:** the conductor threads a video-wide
  `used_ids: set` into every beat's `exclude_ids`, and adds each beat's sourced ids after. Distinctness
  *within* a beat is guaranteed by construction. (Motif = a future explicit opt-in; default OFF.)

## 3) Binder + a multi-clip FITTER (narration still drives duration)
- **`stage1.build_beat_fitted(spec, beat, dst, *, duration)`** — generalise from single-clip to **K
  clips filling exactly `duration`**: split *L* into K slots ≈ `(L + (K−1)·xfade)/K`, clamp each to
  **≤15 s** (density) and a sane floor, set each `Clip.trim_out = trim_in + slot` (respecting the
  clip's available source length; a clip shorter than its slot keeps its length and the remainder
  redistributes to the last slot), then run the **existing** intra-beat xfade chain from `build_beat`.
  Total = Σ slots − Σ overlaps ≈ *L* (narration stays the single source of beat duration). The
  banned single-clip stretch/loop path is removed; a legitimate ≤1.15× slow of one short shot remains.
- **`assembly/binder.py`** — `bind_edit_spec(script, sourced, narration, …)` where
  `sourced` is now **`{beat.index → list[SourcedAsset]}`**: per beat build `Beat(clips=tuple(
  to_clip(a, …) for a in assets), …)` with absolute paths; the rest (narration, out_transition,
  fades) unchanged. `to_clip`'s cap stays a source cap; the fitter owns the per-shot slot.

## 4) The no-repeat guard across the whole video — see §2 (`used_ids` threaded through the conductor).

## 5) Density gate — enforced structurally + covered offline
- **`assembly/qc.py` (or a small `density.py`)**: `assert_visual_density(spec, narration_s: dict)` →
  raises **`VisualDensityError`** if any clips-beat with *L>15 s* has **< ⌈L/15⌉ clips**, or any single
  assigned slot **> 15 s + tol**, or any `(source, asset_id)` appears in **more than one** beat (no
  undeclared reuse). Called in `produce_video` **after bind, before the render** (fail before spending
  render time) and referenced by the standard doc.
- **`scripts/verify_e2e.py` gains offline checks (zero network/spend):** (a) a beat with **1 clip and
  ~30 s** narration **FAILS** `assert_visual_density` (the core regression Banks named); (b) a **3-clip
  ~30 s** beat PASSES with each shot ≤15 s; (c) the multi-clip fitter yields a master whose beat shows
  **≥3 shot boundaries** and duration ≈ Σ narration − Σ overlaps, audio present, 48 kHz noise-clean;
  (d) a reused asset id across two beats FAILS the gate. All prior verifies (Slice 1/Layer1/3/4/5) stay
  green; `verify_slice4`'s single-winner path is untouched.

## 6) Re-make the wolf to the standard — REUSING the perfect narration
The four narration mp3s **are recoverable** (`…/T/e2e-9ji13g78/narr_beat{1–4}.mp3`, durations above) —
**no TTS re-spend.** First step of the re-make **preserves** them to a durable
`assets/produced/wolf/narration/` (the temp dir is volatile). Then:
- A small **re-make path** (`produce.remake_from_narration(...)`, or a `--reuse-narration` branch of
  `prove_e2e`): take the preserved mp3s as the authoritative per-beat audio (their **measured** length
  drives each beat — `approx_seconds` not needed), **source N distinct clips per beat** via
  `source_clips_for_brief` with the no-repeat guard, **bind** (multi-clip), **assemble**, run the
  **density gate + noise gates**, author the description (or reuse job 29's), and submit for approval.
- **One honest wrinkle:** job 29 did not persist the full Script, so its four *shot-briefs* are gone
  (the narration audio Banks loved is intact; only the sourcing search-terms are lost). The re-make
  supplies a shot-brief per beat reconstructed from the known beat labels + topic — these steer
  sourcing ONLY and never touch the VO:
  - beat1 *Before the pack wakes* → grey wolf pack, snowy boreal forest before dawn, wolves resting in snow
  - beat2 *A life made for the cold* → grey wolf thick winter coat, walking/trotting through deep snow, blizzard
  - beat3 *Reading the snow* → grey wolf nose to the ground tracking, pack moving single file through snow
  - beat4 *The howl at the edge of dark* → grey wolf howling at dusk, wolf silhouette in twilight forest
- **Fallback (only if Banks prefers a fully-autonomous fresh reproduction):** re-run the whole
  pipeline → fresh script + fresh TTS. Cost stated up front: **~1,804 credits ≈ £2.40** (12% of the
  15k cap; marginal cash ≈ £0, subscription-covered). Default is **reuse** per Banks's instruction.

## 7) Persist script + narration going forward (so re-makes are free & reproducible)
So this wrinkle never recurs: `produce_video` writes **`assets/produced/<slug>/script.json`** (title,
beats incl. shot-brief/vo/approx, facts, provenance) and copies the narration mp3s beside it, and
records the artifact dir on the job. Future re-makes/format-variants reload the exact script + audio
with **zero LLM/TTS re-spend**. (Small, high-leverage; the E2E slice should have done it.)

## Files
**New:** `visual-density-standard.md`; (maybe) `ytagent/assembly/density.py`. **Edited:**
`ytagent/sourcing/orchestrator.py` (+`source_clips_for_brief`, no-repeat); `ytagent/sourcing/__init__.py`
(export); `ytagent/assembly/stage1.py` (`build_beat_fitted` → K clips); `ytagent/assembly/binder.py`
(`sourced` = list per beat); `ytagent/assembly/qc.py` (or `density.py`) (`assert_visual_density` +
`VisualDensityError`); `ytagent/produce.py` (N-clip sourcing + `used_ids` + density gate + script/
narration persistence + `remake_from_narration`); `scripts/verify_e2e.py` (density checks);
`scripts/prove_e2e.py` (reuse-narration branch); `CLAUDE.md` (+ standard bullet).

## Verification
- **Offline (`verify_e2e`, zero network/spend):** the four density checks in §5 + all prior verifies
  green.
- **Live re-make (gated):** Pass A on the re-made wolf — print each beat's **clip list + per-shot
  durations** (prove ~4 distinct shots/beat, each ≤15 s, none reused video-wide), master QC, noise
  clean, month-to-date. NO upload. Pass B (real private upload) only on Banks's word, once he approves
  the re-made cut's visuals.

## Expensive-to-retrofit (lock now)
1. `sourced` is **a list per beat** end-to-end (sourcing → binder → assembler).
2. **Narration length stays the single authoritative beat duration**, now split across K shot slots.
3. **No-repeat is structural** (a video-wide `used_ids`), not a lint.
4. **Density is a GATE** (`assert_visual_density`, fail-loud before render), not advice.
5. **Script + narration persisted per production** → re-makes/format-variants cost £0.

## Deliberately NOT in this slice
Per-shot-brief authoring by the writer (richer scene variety/motifs — a follow-up on top of §2);
declared motif reuse; multi-clip music score; 9:16; thumbnails; the budget governor. Keep this slice:
enforce visual density, re-make the wolf to the lion standard reusing its narration.

## Conventions / safety
Channel-general (wolf = data; the standard is niche-agnostic — it is *cutting rhythm*, not content).
Reuse the existing xfade/gate machinery; add only N-clip sourcing + the fitter + the guard + the gate +
persistence. No audible broadband noise (gates apply). Build/prove on the Mac; never touch the VPS/
ocean stream. Publishing + spending stay Telegram-gated; sourcing/assembly autonomous within budget.
Commit locally; push only on the ship-word. Tag shell blocks `[ON YOUR MAC]`; no `#` lines; end chains
with `&& echo "OK…" || echo "FAILED…"`. **No code until Banks approves this plan.**
