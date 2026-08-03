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
  It's retrospective, so it can be wired after the run, but the run must be TAGGED (a cohort marker on
  each Short) so the two cohorts are separable later. **Banks may adjust these thresholds now, before
  data — not after.**

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
  `PLAN_MARKETING_ARC.md`). The M1 default: **reused-bed Shorts + ~1 long-form/wk**, which fits.

## The build (file level)

- **Format spec** — extend the produce path for a `short` format: 9:16 (assembly `Target`/`for_format`
  already first-class), ~15–40s, footage-led (1 clip or a 2–3 clip micro-cut), bed from the reuse
  library (rotated), optional one-line hook (text overlay or ≤120-char TTS), `#Shorts`.
- **`ytagent/assembly/density.py`** — a Shorts-scaled density rule (a ≤40s vertical needs 1–3 clips, not
  the long-form ≥⌈L/15⌉); parameterise the existing gate by format rather than a second gate.
- **`ytagent/produce.py`** — a `produce_short` path (or a `format="short"` branch): bind a short EditSpec,
  pull a rotated bed from `assets/beds/`, skip/limit TTS, assemble 9:16, noise+density gates apply, submit
  to the Telegram card. Credit gate already covers the (small) spend.
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
