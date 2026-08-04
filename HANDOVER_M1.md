# Handover — M1 (credit-light Shorts, the A′ discovery engine)

**As of 2026-08-04, `origin/main` = `9f1ecce`** — all M1-build commits shipped, in sync. Run `make health`
first. Full spec: `PLAN_M1_SHORTS.md`; arc context: `PLAN_MARKETING_ARC.md`.

## ⛔ MARKETING ARC STOPPED / ITEM 6 PARKED (2026-08-04) — READ FIRST
The A′ marketing arc is **STOPPED**. Banks's standing goal was never superseded: **FINISH THE AGENT —
every outstanding platform component — and make sure the code works, BEFORE producing or publishing any
further video.** A′ was approved as a plan, but its payoff requires publishing, so the build sequence
drifted to the edge of a live upload. That was drift, not a decision; it is corrected. No production, no
publishing, until Banks says the build is done. See the discipline note now in `CLAUDE.md`.

- **Item 6 (live publish) is PARKED, not done.** Nothing publishes. **Resume trigger (explicit, not a
  date, not a next step): _resume when the agent build is complete AND Banks decides to publish._**
- **ARMED STATE (this is now true and must be stated plainly).** The YouTube token carries
  `youtube.force-ssl` and resolves to `UCRkrZa2yjLLw-f67H2pYI2g` ("The Tales of Wildlife and Nature"),
  verified read-only against Google's `tokeninfo` + `channels.list`. So **the machine CAN publish where
  it previously could not** (`bot._build_publisher` returns a LIVE `YouTubePublisher` whenever a refresh
  token is set — it now is).
- **What still prevents a publish:** (1) the **HARD Telegram gate** — a real upload happens only on
  Banks's tap of a publish card, never autonomously; (2) the **wildlife playbook is DISABLED**
  (`enabled=false`, `state=idle`, `cadence.per_week=1`, `format_mix=["16:9"]`), so the scheduler
  commissions nothing; (3) **the approval queue is now EMPTY** — see the void below.
- **Nothing is scheduled to run unattended.** Confirmed: 0 enabled playbooks due, 0 pending approvals,
  0 non-terminal jobs.
- **QUEUE VOIDED (housekeeping, 2026-08-04).** Accumulated test/dev debris — **32 pending approvals, 33
  awaiting-approval publish jobs, 32 awaiting-approval videos, 9 stuck (assembling/running) jobs** — were
  terminal'd (approvals→rejected, jobs→cancelled, videos→rejected) in one DB-only transaction, audit
  event `housekeeping_void`. This included **approval 188 / job 521 / video 136** ("African Elephant"
  9:16, the M1 Short dry-run card): **VOIDED** — its purpose (prove `produce_short` reaches a real card)
  was served and verified; it was not left as an ambiguous pending publish. The two REAL published
  long-forms (`yGdNuUB5f_I`, `EY9DhJdnt_w`) and all lion dry-run artifacts were untouched. Note: the old
  Telegram cards may still show buttons, but a tap is now a **DB no-op** (`approvals.decide` only acts on
  `state='pending'`). Root cause to fix in the build: **the verify/supervised scripts create approvals +
  jobs and never clean them up** — make them hermetic/self-cleaning (like `verify_cohort_playlist`).
- **M1's built parts STAY** (`produce_short`, `videos.cohort`, the Short guards, the cadence wiring, the
  cohort playlist writes). They are agent CAPABILITY (done + verified), not hand-cranked output. Built ≠
  exercised: the capability may exist; it is simply not run for output until the build is done. Not unwound.

## The decision that frames M1
Discovery-weighted cadence: fortnightly long-form (~13,700 cr/mo) + **~4 Shorts/wk** (~23,600/mo, ~6,400
headroom), NOT weekly long-form (~99% of the 30k recurring). Shorts are the discovery lever at 0 subs;
long-form scales up once discovery is PROVEN (8-week cohort criterion). ~1 long-form/wk max on the £5 plan.

## Built + PROVEN
- **Short production**: `bind_short_spec`; enforced-origin claim-safe bed library (`beds-manifest.json` +
  `beds.py` default-deny + rotation); Shorts density (`short=True` floor 1, `SHORTS_MAX_S=60` enforced);
  silent+bed render clean on real footage (hi16k −84.3, 48 kHz, LUFS asserted −14±2); cross-video no-reuse
  (`used_asset_ids`); bounded sourcing (`source_clips_for_brief`, ~£0.05–0.34).
- **`produce.produce_short`** — a real conductor (create job → Short spend gate → attested rotated bed →
  bounded source → bind → assemble → assert LUFS → describe +#Shorts → submit). LIVE: jobs 514/521 → cards.
- **`estimate_short_cost`** — vision-DOMINANT; `estimate_vs_actual` separates Shorts + footnotes the ~2×
  padding as BY-DESIGN.
- **`videos.cohort`** (0018) — two live long-forms backfilled `m1-longform` (the baseline); new videos
  self-tag `m1-shorts`/`m1-longform`.
- **Publish gate** — `assert_short_conditions` (9:16 → vertical+≤60s+#Shorts or REFUSE), on publish + update_public.
- **CADENCE WIRING (item 4 — DONE, verified):**
  - **format-mix** (0019, `playbooks.format_mix`): `_pick_format` rotates the mix per commission; a 9:16
    tick routes to `_commission_short` (produce_short, no probe/script).
  - **recurring cadence gate** (`_recurring_gate`): paces a job's EL draw against `remaining_recurring`
    (30k − this-period usage), NOT the rollover-inflated key remaining; **FAILS CLOSED** on an unreadable
    read (pauses, doesn't commission blind). `Deps.recurring_allowance` from settings.
  - **Short failure routing**: BedUnavailable→BLOCK; NoMatch→skip ONE tick (no 3× vision re-pay);
    ShortQC→fail once; spend→pause; transient→next tick.
  - `verify_scheduler_run` [7]/[7b]/[8] assert the FAILING case, fail-closed-on-None, and the Short routing.

## The format_mix default — what it means for existing playbooks
`format_mix` defaults to `["16:9"]`, so **every existing playbook is UNCHANGED — it produces long-form
only.** The Shorts mix is OPT-IN per playbook: set `format_mix` (e.g. `["9:16","9:16","9:16","9:16","16:9"]`
for ~4:1) to make a playbook produce the A′ mix. No playbook produces Shorts until its `format_mix` is changed.

## Nothing runs unattended yet — the NEXT step is a DECISION, not a build
The **wildlife playbook is DISABLED** (`enabled=false`, `state=idle`, `cadence.per_week=1`,
`format_mix=["16:9"]`). So the scheduler produces nothing on its own right now. To turn on the A′ mix,
someone (Banks's call) decides + sets: `enabled=true`, a `format_mix` with 9:16 in it, a `cadence.per_week`
for the total item rate, and confirms `recurring_allowance` is right. **That is a configuration decision to
weigh, not code to write** — and it's the point at which the recurring gate + Short routing start mattering
in production. Don't flip it as a build step.

## What REMAINS in M1
1. **Item 6 — live PUBLISH of a Short** (needs force-ssl re-auth + Banks's tap). Nothing published yet.
   This is the FIRST live exercise of the cohort playlist write below (dry-run is a no-op). When it
   runs live, watch for a `cohort_playlist_failed` alert (see below) — that's the only way the marker
   can go missing, and it now tells you at the time.

## Cohort marker durability (folded into item 6, 2026-08-04)
The cohort playlist is **best-effort and does NOT raise** (a marker failure must never fail the
already-irreversible publish). But silence was the trap: a failed placement meant the video went
public, the DB said published, and the YouTube-side marker was absent — discovered eight weeks later
when the Analytics pull found members missing. So `_place_in_cohort_playlist` now **alerts Banks at the
time** on `cohort_playlist_failed` (Telegram `notify`), and the alert names the fallback. **The
`videos.cohort` column is the durable source of truth** — the YouTube playlist is a convenience mirror
for the Analytics pull, not the record. If a placement is ever missed, the video is unmarked
(`cohort_playlist_id` NULL), so a retry re-adds it, and `videos.cohort` reconstructs the cohort
regardless. verify_cohort_playlist asserts the alert fires on failure and stays silent on every success
/ no-op path.

## Item 2 — DONE (unlisted cohort playlist writes)
`youtube.py` gained `add_to_cohort_playlist` / `_add_to_cohort_playlist` (the ONLY `playlists.insert` +
`playlistItems.insert` call site) — confined exactly like `update_public`: inserts ONLY our own uploaded
`youtube_video_id` into ONLY our cohort playlist, creating ONE unlisted playlist if none exists; no
delete/list-others/branding. Storage: `cohort_playlists(channel_id, cohort, youtube_playlist_id)` +
`videos.cohort_playlist_id` marker (migration 0020); `repo/playlists.py` (`get`/`save`). Wiring:
`orchestrator._place_in_cohort_playlist` runs after the Phase-3 persist txn (network → OUTSIDE any held
txn), on a LIVE publish where the video has a `cohort` and isn't already placed; **best-effort — a dry
run is a no-op, and any failure is logged (`cohort_playlist_failed`), never fails the irreversible
publish.** Idempotent across the upload-private→make-public sequence (the marker). `DryRunPublisher`
returns None (touches nothing on YouTube). Verify `scripts/verify_cohort_playlist.py` (in `make health`):
Part A the confined write vs a fake google client (create-once/reuse/own-id-refusal/unlisted); Part B the
DB wiring (place-once, same-cohort reuse, idempotent skip, dry-run no-op, no-cohort skip, failure-logged).
The BACKLOG force-ssl review is marked implemented. NOT yet exercised live — item 6 is the first real run.

## Open backlog (named)
- **Vision cache mirror** — `source_clips_for_brief` lacks the `vision_cache` `source_film` has → re-pays
  vision on re-seen clips (the dominant Short cost). Mirror `vision_cache.get/put`.
- **Recalibrate the Short vision multiplier after ~5 real runs** — `estimate_short_cost` pads 2× n_target;
  live runs ~1.3×. Don't tune on one point.
- **Bed-manifest derivable origin** — bind machine-generated beds to `request_id` + `cost_ledger`.
- **`_SHORT_MAX_S` = 60 vs YouTube's 180** — bump if longer Shorts are wanted.

## Boundary note
Item 4 (the unattended scheduler) is done and verified; the remaining items touch `youtube.py` and the live
publish surface — the wrong things to start at high context. `make health` green; nothing half-applied.
