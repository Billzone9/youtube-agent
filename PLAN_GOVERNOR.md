# PLAN — B3: the cost governor, with teeth

**Status: PLAN ONLY. No code until Banks approves.** Scope is the GOVERNOR only — accurate estimates,
a real pre-flight across all providers, threshold/ceiling approvals that BLOCK, and honest ROI
presentation. **NOT in scope:** analytics ingestion, learning loop, dashboard (those are B4/B5).

The infrastructure exists (`cost_ledger`, `budget_status`, `estimate_production_cost`, the
`SpendGatePause` states, `approve_spend`) but it **reports rather than governs**. This turns each piece
from advisory into enforcing.

---

## The core reframe (why the numbers are untrustworthy today)
Every per-call TTS/music row is written `reconciled=False` — an ESTIMATE. Only two things in the whole
ledger are actually settled (`reconciled=true`): the lion's music (1,500 credits / £2.00) and a bulk
dev/calibration block (46 music calls / 29,625 credits / £39.41). **So we have been comparing estimates
to estimates.** The "predicted 900, used 3,988" Banks saw is the estimate vs the *settled balance* —
the only ground truth. The governor cannot have teeth until the estimate is derived from, and pinned
against, settled actuals.

---

## Item 1 — FIX THE CREDIT ESTIMATOR FIRST (the keystone)
An estimator 4.4× low makes every gate downstream decorative. Three concrete causes, all visible in the
code/ledger today:

1. **SFX omitted.** `estimate_production_cost` counts `plan_cues` (theme/journey/resolution) + one bed.
   `generate_audio` *also* spends on `sfx_specs` (`music.sound_effect`) — never estimated.
2. **Retakes omitted.** `_gen_gated` regenerates a hissy cue once (bills twice); the estimate counts one
   take. Bed and each cue can each retake.
3. **Async settlement never reconciled.** Music bills asynchronously; per-call reads are estimates that
   settle later against the balance. Nothing reconciles them, so the seconds×15 model was never validated.

### Ground-truth data to derive from (measured, this repo)
| run | job | TTS chars (actual) | music credits | settled? |
|---|---|---|---|---|
| Lion | 29 | 1,804 | 1,500 | **reconciled £2.00** |
| Elephant "The Old Paths" | 99 / 155 | 4,379 | 2,475 (4 cues) | estimate only |
| This production | 276 | 4,364 (1,387 for the 2 voiced beats) | 2,475 planned | never ran music |
| Dev/calibration music | — | — | 29,625 over 46 calls (≈644/call) | **reconciled £39.41** |

### Plan
- **Reconcile to get truth first.** Build a one-shot **balance-reconciliation pass**
  (`scripts/reconcile_elevenlabs.py` + `repo.ledger.reconcile_*`): read the ElevenLabs balance
  before/after, or settle the outstanding `reconciled=False` rows against the live `character_count`
  delta, and stamp the real per-call credits. This yields the true credits-per-second (music) and
  per-char (TTS) rates. TTS is deterministic (1 credit/char, char count exact) — expected ≈ accurate.
  Music is where the multiplier lives (retakes + async).
- **Re-derive the model** in `scheduler/cost.py` from the reconciled rates, covering **TTS + music +
  SFX + a retake factor** (a measured expected-regeneration multiplier, not a guess). Keep the
  deliberate slight over-estimate bias (err toward asking).
- **Regression test** (`scripts/verify_cost_estimate.py`): pin `estimate_production_cost` against the
  measured actuals for the lion and elephant scripts within a stated tolerance (e.g. ±20%), so an
  estimate that drifts 4.4× fails CI. Include an SFX-bearing script fixture so the SFX term is covered.
- **Deliverable of item 1:** a estimator whose prediction for the elephant script lands within tolerance
  of the 2,475 (once reconciled) and whose SFX/retake terms are exercised by the test.

## Item 2 — PER-JOB PRE-FLIGHT ACROSS ALL PROVIDERS, RECORDED
One combined pre-flight number, in **£ and in provider credits**, at the 4→5 gate, persisted for
estimate-vs-actual audit.
- **Extend `CostEstimate`** to a per-provider breakdown: Anthropic LLM (script + description tokens,
  priced from `platform_settings.llm_pricing`), ElevenLabs TTS (chars→credits), ElevenLabs Music+SFX
  (credits). Totals in **£ and credits**. LLM is currently NOT in the production estimate — add it
  (script-writing + description tokens are real per-job spend).
- **Record the estimate against the job**: a `cost_estimate` row (or reuse the `spend_estimate` event +
  a persisted estimate on `jobs.result`) capturing the full breakdown at gate time, so afterwards we can
  compare it to the settled ledger for that `job_id`. This is the "see systematically how wrong we are"
  requirement — every job carries its own estimate-vs-actual.
- **A reconciliation report** (`scripts/estimate_vs_actual.py`): per job, estimated £/credits vs settled
  £/credits, so the drift is auditable in aggregate, not per incident.

## Item 3 — THRESHOLD APPROVALS THAT ACTUALLY GATE
Today: the scheduler pauses the playbook (`paused_spend`/`paused_ceiling`) and sends a plain text
`_alert`; `approve_spend(job_id)` exists but nothing wires a Telegram button to it or auto-resumes. The
direct path (`resume_job`) just raises and prints. Make both thresholds BLOCK with an actionable gate.
- **Spend-approval CARD** (not a plain alert): reuse the inline-keyboard approval mechanism
  (`notifier.approval_callback_data` + the bot's callback handler) to send an **Approve / Reject** card
  carrying the **full breakdown** (per-provider £ + credits, the threshold or ceiling it breached,
  month-to-date). This is a NEW approval `type` (`spend_approve`) distinct from `publish`/`publish_public`.
- **Approve → resume.** The bot's callback handler, on approve, calls `approve_spend(job_id)` (sets
  `spend_approved=True`) and re-enqueues/resumes the job so it proceeds WITHOUT re-charging voiced
  beats / generated music (the resume idempotency already guarantees this). Reject → the job stays
  paused, playbook stays `paused_*`.
- **Both gates**: `per_job` (estimate > `per_job_threshold_gbp`) and `ceiling` (month-to-date + estimate
  > global ceiling). The credit gate (already shipped) routes the same way. All three PAUSE-and-ASK,
  none proceed-and-report.
- **The direct/manual path** honours the same gate (raises `SpendGatePause`, surfaces the card) so a
  hand-run production can't bypass it.

## Item 4 — HONEST ROI REPORTING
The numbers are right; the presentation misleads (Banks alarmed by "£15.54 MTD" when £14.59 was seeded
fixed cost). Separate the three buckets the ledger already distinguishes.
- **Buckets, from existing fields:**
  - **Fixed / infrastructure** — `category IN ('infrastructure','subscription')` (VPS capital + amortised,
    ElevenLabs subscription). Separate the **capital cash outlay** (`is_amortised=false`, e.g. the annual
    VPS £115) from the **amortised monthly accrual** (`is_amortised=true`) so month-1 isn't distorted.
  - **Production spend** — `category='ai_generation' AND metadata.context='production'`.
  - **Calibration / development spend** — `metadata.context='calibration'` **plus the untagged legacy
    `ai_generation` rows** (167 rows / £63.69 predate context tagging — treat as calibration/dev, and
    note the assumption; optionally backfill a `context` on them in a migration).
- **New reporting surface** (`repo.ledger.roi_breakdown` + a report script; extend `budget_status`):
  returns the three buckets split, production-only net (revenue − production spend), and total operating
  net — so ROI/ROAS is quoted against **production** spend, not against seeded fixed cost.
- **The sub-penny footnote** (CLAUDE.md known-lossy window): the report carries a standing footnote that
  LLM spend before 2026-07-31 is understated by sub-penny rounding (pre-migration-0007), reconcile
  against the live Anthropic USD balance — early data is footnoted, not presented as clean.
- **No fabrication:** revenue stays whatever the revenue ledger actually holds (£0 today) — the report
  never invents it.

---

## Files (anticipated; for review, not yet written)
- **Edit:** `ytagent/scheduler/cost.py` (re-derive model: TTS+music+SFX+retake, per-provider breakdown,
  add LLM); `ytagent/budget.py` (bucketed view); `ytagent/repo/ledger.py`
  (`reconcile_*`, `roi_breakdown`, persist estimate); `ytagent/scheduler/runner.py` +
  `telegram_bot/bot.py` + `ytagent/orchestrator.py`/`notifier.py` (spend-approval card + callback →
  `approve_spend` → resume); `ytagent/produce.py` (surface the full breakdown at the gate).
- **New:** `scripts/reconcile_elevenlabs.py`, `scripts/verify_cost_estimate.py` (regression),
  `scripts/estimate_vs_actual.py`, `scripts/roi_report.py`. Possibly a migration to backfill `context`
  on legacy `ai_generation` rows.

## Verification
- Estimator regression pins lion + elephant (+ an SFX fixture) within tolerance — fails on 4.4× drift.
- Gate tests: estimate over `per_job_threshold` → card sent, job PAUSED, approve → resumes without
  re-charge, reject → stays paused; same for ceiling. (Extends `verify_scheduler_run`.)
- ROI report shows the three buckets separately on the real ledger; the £14.59-fixed vs production split
  is visible; footnote present.
- Full offline suite stays green; no live spend needed except the one-shot balance reconciliation
  (read-only against the ElevenLabs balance).

## Risks / decisions for Banks
- **Reconciliation method**: settle outstanding rows via a before/after balance delta requires a quiet
  window (no other spend) to attribute cleanly; alternative is to accept the per-call estimates as the
  model and only correct the SFX+retake terms. Recommend the balance pass once, to anchor the model.
- **Legacy untagged spend (£63.69)**: treat as calibration/dev (recommended) or backfill a real context.
- **Approval UX**: spend card is a new approval type; confirm the Approve/Reject + resume flow is what
  you want (vs a typed `/approve <job>` command).

## Out of scope (explicit)
Analytics ingestion, learning loop, dashboard — B4/B5. This plan makes the money numbers TRUE and the
gates BLOCK; it does not add new data pipelines or UI.
