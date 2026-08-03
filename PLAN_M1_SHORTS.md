# PLAN — M1: credit-light Shorts pipeline + YouTube Shorts publish (arc slice 1)

**Status: PLAN, file-level. No build until Banks approves.** The A′ discovery centrepiece: produce
credit-light 9:16 Shorts through the machine, publish as YouTube Shorts behind the human gate. Reuses the
existing 9:16 assembly + publish; the new parts are the Short format/scripting, a Shorts density rule,
the playbook format-mix, and a claim-safe bed reuse library.

## Resolved before building (the three notes)

### 1. The 0-credit ambient bed is REAL — named + verified
- **Bed:** `assets/produced/reuse-elephant/work/audio/bed.mp3` (and `.../elephant/work/audio/bed.mp3`).
- **Claim-safe:** ElevenLabs-*generated* (own/synthetic output) — no third-party recording, so no Content
  ID match even though Shorts are VODs. This is the doctrine's "synthetic/own audio only" path, NOT
  licensed nature tracks (those are forbidden — CLAUDE.md). *One flag to confirm at build: that the
  current ElevenLabs plan's terms permit commercial VOD use of Music output; generative-owned is the
  standard claim-safe route, but verify the plan clause.*
- **Clean:** passes `qc.check_source_clean` — hi16k **−90.3 dB** (clean ≈ ≥ −47; far under). Verified live.
  For contrast the lion's *sourced* `nature-african-savanna-2.mp3` FAILS (hi16k −30.3, >16kHz noise) —
  so the reuse library is the ElevenLabs beds ONLY, never sourced ambience.
- **Build action:** seed a small claim-safe **bed library** `assets/beds/` (start with the 2 elephant
  beds, each ~45s so it covers a ≤40s Short by trim), each recorded with its noise numbers + provenance
  (own/ElevenLabs). **Rotate** across Shorts (variation is a project principle — never one bed on
  everything); generate a fresh bed (~520 cr) only when variety warrants it. So the 0-credit path holds
  for the bulk, with occasional paid variety — NOT a single bed reused forever.

### 2. Success criterion — pre-committed NOW (so it's evidence, not hindsight)
A′ exists to produce evidence for the tier-B decision, so the bar is set BLIND, before any data:
- **Cohort:** the first **~16 Shorts** (≈4/week × 4 weeks).
- **Window:** **~8 weeks** from first publish (Shorts distribution takes weeks; pulled retrospectively via
  YouTube Analytics once wired — the data survives, the threshold is fixed now).
- **PROVEN if, over the window:** Shorts-cohort impressions ≥ **3×** the long-form-cohort impressions
  (discovery reach) **AND** Shorts contribute ≥ **50%** of net-new subscribers (acquisition). Then Shorts
  are demonstrably the primary discovery channel → the tier-B "scale Shorts" case has evidence.
- **DISPROVEN if:** after ~16 Shorts over ~8 weeks, Shorts impressions and subscriber contribution are
  NOT materially above long-form → discovery isn't coming from Shorts; do NOT scale (no tier B); revisit
  format/thesis.
- **Floor (rule out "both zero"):** if the channel gains < ~25 subscribers total in the window, the test
  is INCONCLUSIVE — a content-quality problem, not a format one; don't read it either way.
- **Dependency:** measurement needs YouTube Analytics (Layer-2/B4 — a new OAuth scope + security review).
  It's retrospective, so it can be wired after the run, but the run must be TAGGED so the two cohorts are
  separable later. **Banks may adjust these thresholds now, before data — not after.**
- **WHERE THE COHORT TAG LIVES (stated before building — note 2).** Analytics reports on the *published*
  video, so the tag must be recoverable from the YouTube side, not only a local row:
  - **Primary join:** a new `videos.cohort` column (e.g. `"m1-shorts"` / `"m1-longform"`) alongside the
    `youtube_video_id` we already store. The retrospective Analytics pull queries metrics by that set of
    video IDs. Sufficient *while the DB persists*.
  - **YouTube-side survival (the actual requirement):** every cohort video is added to an **UNLISTED
    cohort playlist**. Playlist membership is retrievable via the Data API (`playlistItems.list`), so the
    cohort is reconstructable **from YouTube alone** if the DB is lost — and an unlisted playlist is NOT
    viewer-facing, so it never pollutes public metadata.
  - **NOT** in tags / title / description — `public-facing-output-standard` forbids internal artifacts in
    viewer-facing fields; a cohort marker there would be a leak.
  - **Build:** a `videos.cohort` migration + set it at publish; `playlistItems.insert` in the publish step
    (force-ssl already covers it). This is part of the submit/publish increment, not the binder.

### 3. The mix's actual monthly credit draw (both ends) — honest, and it's tight
Long-form ~1/week = ~4.33/mo × ~6,850 cr = **~29,660 cr/mo — nearly the entire 30,000 recurring on its
own.** So:
- **Reused-bed Shorts (0 cr) + 1 long-form/wk = ~29,660/mo → FITS (barely; ~340 headroom).** "Shorts
  don't compete with the long-form allowance" is true ONLY here.
- **Generated-bed Shorts (~520–640 cr) × 4/wk (~17/mo) = ~9,000–11,100/mo. + 1 long-form/wk = ~38,700–
  40,800/mo → OVER the 30,000 recurring by ~30%.** Here Shorts DO compete.
- **The real lever is the mix, and it's a trade inside 30k:** e.g. 1 long-form/**2 wk** (~13,700) + 4
  generated Shorts/wk (~9,900) = **~23,600/mo → fits with room.** So A′ within £5/mo means EITHER
  reused-bed Shorts at weekly long-form, OR generated-bed variety at a lower long-form cadence — not
  both at full tilt. Anything past that is the tier-B decision (unverified ~£15–20/mo, recorded in
  `PLAN_MARKETING_ARC.md`).

### MIX DECISION (2026-08-04) — discovery-weighted, NOT weekly long-form
**Landed mix: fortnightly long-form (~2/mo, ~13,700) + ~4 Shorts/wk → ~23,600/mo, ~6,400 headroom (21%).**
Rejected the weekly-long-form default (~29,660/mo, ~340 headroom / 1%). Reasoning: (1) A′ chose Shorts as
the discovery lever, so credits belong behind that bottleneck — not 99% on long-form, which is weak at
cold reach; (2) the watch-hour case for weekly long-form is circular — hours need views need discovery,
so at 0 subs more long-form banks inventory nobody sees; (3) the ~6,400 headroom funds bed variation
(anti-templating) + absorbs a retake/re-run, where ~340 breaks on one. The bed-library-once trick could
keep weekly long-form with free varied Shorts, but it doesn't justify spending 99% of the allowance on
the weak-reach channel before discovery is proven — so it's declined. **Long-form scales back UP once
discovery is proven (the success criterion) and/or tier B.** The M1 build targets this mix.

## The build (file level)

- **Format spec** — extend the produce path for a `short` format: 9:16 (assembly `Target`/`for_format`
  already first-class), ~15–40s, footage-led (1 clip or a 2–3 clip micro-cut), bed from the reuse
  library (rotated), optional one-line hook (text overlay or ≤120-char TTS), `#Shorts`.
- **`ytagent/assembly/density.py`** — a Shorts-scaled density rule (a ≤40s vertical needs 1–3 clips, not
  the long-form ≥⌈L/15⌉); parameterise the existing gate by format rather than a second gate.
- **`ytagent/produce.py`** — a `produce_short` path (or a `format="short"` branch): bind a short EditSpec,
  pull a rotated bed from `assets/beds/`, skip/limit TTS, assemble 9:16, noise+density gates apply, submit
  to the Telegram card. Credit gate already covers the (small) spend.
- **SOURCING — use the SINGLE-BEAT path, NOT `source_film` (checked — note 3).** `source_film` builds a
  film-wide pool and caps vision at `max_verify=90`, so a thin-footage Short could burn a whole film's
  vision budget (~£1.5+). `source_clips_for_brief` (one brief) is naturally bounded: `max_attempts =
  n_target*3+10` (≈19 for a 3-clip Short) and it stops early at `n_target` clear. So a Short's vision cost
  is **~£0.05–0.10 typical (stops at ~3 clear) and ≤~£0.34 worst-case — a fraction of the ~£0.72 film**
  (£0.72 ≈ 42 checks → ~£0.017/check; a Short is ~3–19 checks). The conductor sources a Short with
  `source_clips_for_brief(n_target=3, n_min=1)`, never `source_film`.
- **LUFS is asserted, not watched (note 2 earlier):** the render/QC must fail a Short whose master drifts
  past −14 ± 2 LUFS (proven in `prove_short_render`); below ~15s single-pass loudnorm's integrated measure
  is untrustworthy → use dual-pass or a floor before shipping sub-15s Shorts.
- **CROSS-VIDEO no-reuse — FIXED (note 2, this round).** The density no-reuse rule was within-spec only,
  so at Short volume (1–3 clips × 4/wk) the same striking clip could recur across Shorts. Now
  `repo.sourcing.used_asset_ids(channel)` returns every clip the channel has used across prior videos
  (from each non-failed job's allocation), and `_source_all_beats` seeds the exclude set with it — so NO
  clip repeats across videos, films and Shorts alike. The Short conductor passes the same set as
  `exclude_ids` to `source_clips_for_brief`. Proven live: channel 1 already excludes its 26 prior clips.
- **VISION spend is the dominant per-unit Short cost — make it VISIBLE, not absorbed (note 1).** Vision
  already lands in `cost_ledger` per-job (`_drain_llm` → `write_llm_cost(job_id)`), so a Short's ~£0.05–
  0.10 shows in roi_report's per-job LLM column. Two additions so it isn't mis-shaped: (a) TAG the Short
  produce job `format="short"` (payload + a metadata marker on the row) so roi_report / estimate_vs_actual
  can separate Shorts from films — the cost ratio INVERTS (ElevenLabs ≈ £0, Anthropic dominant), and at
  4/wk that's ~£3–5/mo of Anthropic that must be seen; (b) the cost ESTIMATOR needs a Short variant whose
  dominant term is the VISION estimate (`n_target` × per-check), else a Short is estimated at the film's
  fixed ~£0.02 LLM and estimate_vs_actual under-counts it ~4× — the exact error class the film estimator
  once had. Both land with the conductor's job-creation + a small roi_report/estimator format-awareness.
- **Publish** — `ytagent/youtube.py`: a Short is a <60s 9:16 upload with `#Shorts`; the existing
  `YouTubePublisher` insert path works with Shorts metadata + the AI-disclosure line + a cohort tag
  (metadata field) for the success measurement. Human-gated as always.
- **Playbook (§14.4 format mix)** — add a per-channel format-mix cadence (e.g. long-form per_week + shorts
  per_week) to the wildlife playbook; the scheduler commissions both. Keeps the ~1 long-form/wk default.
- **Prereq true-up** — set `config.py` `elevenlabs_key_credit_cap` fallback 15000 → 20000 (matches the
  live cap / the `.env` override) so the credit gate math is right without the override.
- **Scripting** — Shorts scripting is footage-led moment-selection, not poem-narration; house voice
  adapts (a hook or silence). Reuse the LLM writer with a short-format prompt.

## Verification (no film run; fits the 5,684 window)
- Offline: a `verify_shorts.py` — a short EditSpec assembles to a valid 9:16 master with a reused bed;
  Shorts density rule passes on 1–3 clips and fails on 0; the bed library's noise numbers are gate-clean;
  the credit estimate for a reused-bed Short is ~0 and a generated-bed Short ~520. Wire into `health.py`.
- Live proof (within budget): produce 1–2 credit-light Shorts to the Telegram card — ~0 cr (reused bed)
  to ~520 (fresh). Real publish on Banks's yes.

## Estimate (×3): ~1–2 sessions
Reuses 9:16 assembly + publish; new work is the short format/scripting, the density parameterisation, the
bed library, the playbook format-mix, and the config true-up. The success-measurement (analytics pull)
is a later slice — M1 only needs to TAG the cohort so the evidence is separable.
