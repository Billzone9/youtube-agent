# Handover — M1 (credit-light Shorts, the A′ discovery engine)

**As of 2026-08-04, `origin/main` = `7daa285`.** Pick up fresh from here. Full spec:
`PLAN_M1_SHORTS.md`; arc context: `PLAN_MARKETING_ARC.md`. Run `make health` first (16→19 verifies).

## The decision that frames M1
Cadence is **discovery-weighted**: fortnightly long-form (~13,700 cr/mo) + **~4 Shorts/wk** (~23,600/mo,
~6,400 headroom), NOT weekly long-form (which alone is ~99% of the 30k recurring allowance). Shorts are
the discovery lever at 0 subs; long-form scales back up once discovery is PROVEN (the 8-week cohort
criterion in `PLAN_M1_SHORTS`). Sustainable cadence is ~1 long-form/wk max on the current £5 plan.

## Built + PROVEN this arc
- **A real Short reached the Telegram card end-to-end** (`scripts/prove_short_live.py`, job 514):
  source → bind → assemble → describe → submit. £0.0534 total, **ElevenLabs £0** (reused bed, no TTS) —
  the cost IS the vision. Dry-run; the stale card (approval 184) was VOIDED (pre-#Shorts description).
- `bind_short_spec` — 9:16 single-beat Short binder (footage + attested bed, explicit duration, no voice).
- **Claim-safe bed library** — `assets/beds/` (media gitignored) + **`beds-manifest.json`** (committed
  CONTROL): a bed is admissible only if attested `elevenlabs_generated` AND its bytes hash to the record.
  `beds.py` default-denies; `pick_bed` rotates. Origin is ENFORCED, not asserted.
- **Shorts density** — `assert_visual_density(short=True)`: floor relaxed to 1, `SHORTS_MAX_S=60`
  enforced inside the flag (can't disable density on long-form), no-reuse kept.
- **Silent+bed render is clean** — measured on real footage: hi16k −84.3 (under −47), 48 kHz (no 96k
  trap), −12.3 LUFS. `bed_db` unified to −30 (measured equal to −24). **LUFS asserted** (−14±2; <15s
  flagged untrustworthy).
- **Cross-video no-reuse** — `repo.sourcing.used_asset_ids(channel)` seeds the exclude set in
  `_source_all_beats`, so no clip repeats across videos (films + Shorts). Live: channel excludes 26 prior.
- **Sourcing bounded** — Shorts use `source_clips_for_brief` (single-beat, `max_attempts=n_target*3+10`),
  NOT `source_film`. Vision ~£0.05–0.10 typical, ≤£0.34 — a fraction of a film's ~£0.72.
- **Publish gate** — `youtube.assert_short_conditions`: a 9:16 upload is REFUSED unless vertical + ≤60s +
  #Shorts, on BOTH `publish()` and `update_public()` (the way channel_id is asserted). 16:9 = no-op. So
  YouTube can't silently file a Short as an ordinary vertical video and void the cohort.

## What REMAINS in M1 (the next session — touches scheduler + live publish; start fresh)
1. **`videos.cohort` migration** + propagate `format="short"` (job payload → ledger metadata) so
   `roi_report`/`estimate_vs_actual` SEPARATE Shorts from films (the cost ratio inverts).
2. **Unlisted cohort playlist writes** — `playlists.insert` + `playlistItems.insert`, own-uploaded-ids
   only (force-ssl review already recorded in BACKLOG). The YouTube-side cohort survival for Analytics.
3. **Short cost-estimator variant** — vision-dominant, else a Short is under-counted ~4× (film estimator's
   old error class).
4. **Playbook format-mix** — schedule Shorts + long-form per channel (§14.4).
5. **Fold `produce_short` into `produce.py`** — currently the runner `prove_short_live.py`; make it a real
   conductor function (append #Shorts to the description there — the gate requires it).
6. **Live PUBLISH of a Short** — needs the force-ssl re-auth + Banks's tap; deferred (nothing published yet).

## Open backlog (named)
- **Vision cache mirror** — `source_clips_for_brief` lacks the `vision_cache` that `source_film` has, so a
  re-seen clip re-PAYS vision (dominant Short cost). Mirror `vision_cache.get/put`. Also makes the
  `used_asset_ids` "release failed-job clips" predicate cost-free. (BACKLOG, marketing-arc section.)
- **Bed-manifest derivable origin** — the `beds-manifest.json` attestation is hand-written; when a bed is
  machine-generated, bind its entry to the ElevenLabs `request_id` + `cost_ledger` row (traceable, not
  claimed). Matters at channel #2 / automation. (BACKLOG.)
- **`_SHORT_MAX_S` = 60 vs YouTube's 180** — the publish gate asserts ≤60s (reliable classification +
  discovery sweet spot); YouTube allows Shorts to 180s. Bump the constant if longer Shorts are wanted.

## Boundary note
Stopped deliberately at a clean edge: a real Short proved end to end, the publish gate closed behind it,
the stale card voided. The remaining M1 work touches the scheduler and the live publish surface — the
wrong things to begin on a long context. Nothing is half-applied; `make health` is green.
