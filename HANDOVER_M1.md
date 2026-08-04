# Handover — M1 (credit-light Shorts, the A′ discovery engine)

**As of 2026-08-04.** `origin/main` = `27dcd60`; **3 local commits ahead, UNPUSHED** (`63e5385` item 5+3,
`768d629` item 1, `ae0a5c5` item 4 guards) — awaiting a ship-word. Run `make health` first. Full spec:
`PLAN_M1_SHORTS.md`; arc context: `PLAN_MARKETING_ARC.md`.

## The decision that frames M1
Discovery-weighted cadence: fortnightly long-form (~13,700 cr/mo) + **~4 Shorts/wk** (~23,600/mo, ~6,400
headroom), NOT weekly long-form (~99% of the 30k recurring). Shorts are the discovery lever at 0 subs;
long-form scales up once discovery is PROVEN (8-week cohort criterion). ~1 long-form/wk max on the £5 plan.

## Built + PROVEN
Earlier arc: `bind_short_spec`; enforced-origin claim-safe bed library (`beds-manifest.json` + `beds.py`
default-deny + rotation); Shorts density (`short=True` floor 1, `SHORTS_MAX_S=60` enforced); silent+bed
render clean on real footage (hi16k −84.3, 48 kHz, LUFS asserted −14±2); cross-video no-reuse
(`used_asset_ids` seeds the exclude); bounded sourcing (`source_clips_for_brief`, ~£0.05–0.34); publish
gate `assert_short_conditions` (9:16 → vertical+≤60s+#Shorts or refuse).

THIS session (the 3 unpushed commits):
- **`produce.produce_short` is a REAL conductor** (item 5) — create job (payload.format=short) → Short
  spend gate → attested rotated bed → bounded source → bind → assemble (density+noise) → assert LUFS →
  describe (+#Shorts) → submit. Straight-through (cheap enough to re-run). `prove_short_live` is a thin
  runner over it. LIVE: job 521 → **approval 188 on the card** (fresh, gate-valid; replaced the voided 184).
- **`estimate_short_cost`** (item 3) — vision-DOMINANT (Anthropic), ElevenLabs ≈ 0; the ratio inverts vs a
  film. Persisted at the gate. `estimate_vs_actual` separates Shorts (a `fmt` col) + footnotes the ~2×
  padding as BY-DESIGN.
- **`videos.cohort`** (item 1, migration 0018) — the two live long-forms BACKFILLED `m1-longform` (the
  baseline the Shorts get compared against); `produce_short`→`m1-shorts`, `produce_video`→`m1-longform`
  self-tag via `submit_video_for_approval(cohort=…)`.
- **Item-4 GUARDS** (built; wiring pending) — failure taxonomy (`BedUnavailableError`/`ProductionError`/
  `ShortQCError`, all distinct) + the RECURRING cadence gate (`credit_status(recurring_allowance=…)` →
  `remaining_recurring`; live 15,684 of 30,000, independent of the 5,684 key remaining).

## What REMAINS
1. **Item 4 WIRING — the scheduler consuming the guards (touches the component that runs UNATTENDED).**
   Playbook format-mix (Short vs long-form ticks) → call `produce_short` → route its exceptions per the
   taxonomy → apply the recurring cadence gate at commission. **Two REQUIREMENTS before building (below).**
2. **Item 2** — unlisted cohort playlist writes (`playlists.insert`+`playlistItems.insert`, own-ids only;
   force-ssl review recorded). Coupled to the live-publish surface — do near item 6.
3. **Item 6** — live PUBLISH of a Short (needs force-ssl re-auth + Banks's tap). Nothing published yet.

## Cadence wiring — REQUIREMENTS (resolve in the wiring, not after)
- **(note 1) The verify must assert the FAILING case, not the happy path.** Given a state where the KEY
  remaining is large (rollover-inflated) but RECURRING is exhausted, commissioning must PAUSE. A happy-path
  verify would pass even if the wiring read `remaining` instead of `remaining_recurring` — assert the pause.
- **(note 2, DECIDED) The cadence gate FAILS CLOSED on `credit_status` == None.** An unattended scheduler
  must NOT commission blind to the recurring budget → PAUSE cadence + alert. This is DELIBERATE and the
  OPPOSITE of the per-job key gate (which degrades OPEN — a blip mustn't halt an operator-invoked run).
  per-job = don't-block-on-a-blip; cadence = don't-over-commit-blind. Encode it, don't inherit degrade-open.
- **Failure routing (from the guards):** `BedUnavailableError` → BLOCK playbook + alert (config; never
  retry); `ProductionError` (NoMatch) → record + skip to next tick (ONE attempt, not the film 3×-subject
  retry that re-pays vision); `ShortQCError` (LUFS) → fail ONCE; network/5xx → transient backoff.

## Open backlog (named)
- **Vision cache mirror** — `source_clips_for_brief` lacks the `vision_cache` `source_film` has → re-pays
  vision on re-seen clips (the dominant Short cost). Mirror `vision_cache.get/put`.
- **Recalibrate the Short vision multiplier after ~5 real runs** — `estimate_short_cost` pads 2× n_target;
  job 521 ran ~1.3×. Don't tune on one point; drop toward ~1.4× after ~5 runs.
- **Bed-manifest derivable origin** — bind machine-generated beds to `request_id` + `cost_ledger`, not a
  hand-written attestation.
- **`_SHORT_MAX_S` = 60 vs YouTube's 180** — bump if longer Shorts are wanted.

## Boundary note
Three increments this session; the next is the scheduler, which runs unattended — it wants a fresh read,
not a rushed fourth. Nothing is half-applied; `make health` is green. The 3 commits are LOCAL — ship them
(and this handover) on the word, or the fresh session picks up from `27dcd60` + these commits by hash.
