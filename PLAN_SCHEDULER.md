# PLAN — Slice 6: Scheduler / Playbook (the autonomy loop)

Status: PLAN for approval. No code until Banks approves. Design follows spec §4.1 (orchestrator =
"scheduler + job queue running per-channel playbooks"), §5 (lifecycle: orchestrator selects the next
job, cost-checked first → produce → review queue → approval), §6 (gates), and the Slice-6 BACKLOG
coverage-probe lesson (topic choice must be coverage-aware).

## The one-sentence goal
Banks says **"make wildlife documentaries twice a week"** and the platform, unattended, selects a
subject the channel hasn't made, probes its footage feasibility, rejects and re-picks on its own if
infeasible, commissions the footage-led script, runs the existing produce pipeline, and stops at the
Telegram approval gate — surfacing to Banks ONLY the publish decision and any spend above threshold.

Today Banks hand-runs every step (choose subject → probe → script → curate → produce). Slice 6 makes
that chain run itself, per-channel, on a cadence, surviving restarts.

---

## Scope discipline (this is where drift risk is highest)

**IN:** playbook storage (data); subject selection + no-repeat; probe-gated commissioning; run-to-
approval through the EXISTING produce pipeline; cadence; the per-job spend gate; the production STATE
MACHINE that survives a restart; the polling runner; the failure/resumption routing.

**OUT — to BACKLOG, no exceptions** (these are B4+): analytics ingestion; learning from performance;
trend/competitor monitoring; ANY optimisation; Shorts / multi-format; multilingual. A defect found in
an existing subsystem while building this is LOGGED and stepped around, never fixed inline.

**Not new behaviour, just automated:** the scheduler calls the SAME `probe_feasibility` and
`produce_video` that already exist and are proven (lion + elephant, both public). Slice 6 adds the
selection + gating + cadence + resumable state machine ON TOP; it changes nothing inside the pipeline.

---

## Three things you asked me to get right

### 1. Queue technology — my honest answer: **Postgres-backed queue + one polling runner. Not Celery+Redis.**

You are right, and I'll say why rather than take your framing on faith. The spec's Celery+Redis (§174)
predates the Postgres schema; the schema (`jobs`: type/status/stage/payload/result/error + the events
audit trail) **already is a durable job queue.** For a channel producing ~2 videos/week (~3×10⁻⁴
jobs/sec):

- **Celery+Redis solves a problem we do not have** — high-throughput distributed dispatch across many
  workers. Adopting it now buys nothing and costs: a broker to run, a worker service to deploy, and a
  **second source of truth** (a job in Redis's queue AND a row in Postgres) that can drift — a new
  failure mode on the 2-core VPS that also runs your live ocean stream.
- **Postgres already gives everything the queue needs:** durability (a job's state is a committed row,
  so a crash/restart loses nothing), transactions (claim + state-change atomically), and safe
  concurrent claim via `SELECT … FOR UPDATE SKIP LOCKED`. That last is a textbook Postgres work-queue —
  crash-safe, no broker.
- **The runner** is a single async loop: every ~30s it (a) claims the next *due* playbook or in-flight
  job with `FOR UPDATE SKIP LOCKED`, (b) advances it ONE stage, (c) commits the new state, (d) sleeps.
  Cadence is a `next_run_at` timestamp on the playbook. One instance is plenty; SKIP LOCKED keeps it
  correct even if a second ever runs.

**When I'd change my mind (the honest threshold):** many channels rendering concurrently, or sub-minute
dispatch latency, or a need to scale renders horizontally across machines. None apply now. FastAPI +
Celery + Redis stay in the spec as the *at-scale* target; we adopt them **when load justifies, not
preemptively.** Building them now would be gold-plating a path we can't yet load-test.

So: **Postgres queue + polling runner.** If you want Celery later, the `jobs` rows are the exact
hand-off point — nothing built now is wasted.

### 2. Failure and resumption (this matters more than the happy path)

Two ideas make this tractable: (a) a **checkpointed state machine** — a production job advances through
named stages, each of which *persists its artifacts to disk and records the stage on the job row before
the next begins*; (b) **idempotent skip-on-resume** — re-entering a completed stage reuses its saved
artifact instead of re-doing it. The two stages that spend real money (TTS, music) are the ones that
MUST skip on resume, so a crash after spend never re-charges.

**Production stages** (checkpoint = `jobs.stage` + a `production_state` JSON on the job):

| # | stage | does | spend | on resume |
|---|-------|------|-------|-----------|
| 1 | `selected` | subject chosen, recorded in `channel_subjects` | — | re-pick only if not recorded |
| 2 | `probed` | `probe_feasibility`; verdict gates | ~pennies Haiku | re-probe (cheap) |
| 3 | `scripted` | footage-led script, persisted to `script.json` | ~pennies LLM | reload script.json |
| 4 | `sourced` | film-wide pool + allocation; clips cached on disk | free (Haiku vision) | reload allocation (asset-ids) |
| 5 | `narrated` | **TTS** the spoken beats, persisted mp3s | **£ TTS (first real money)** | **reload mp3s — never re-TTS** |
| 6 | `designed` | **music** cues+bed generated, persisted | **£ credits (big money)** | **reload cues — never re-gen** |
| 7 | `assembled` | render master (density+noise gates) | free compute | re-render (cheap, deterministic) |
| 8 | `submitted` | Telegram approval sent | — (human gate) | resend if not yet sent |

Resume = the runner reads the job's stage and re-enters at the first *incomplete* stage, rebuilding
from `production_state` (script path, allocation, narration paths, cue map, bed path). The **spend gate
sits between stage 4 and 5** — the last free moment before real money.

**Failure routing** (what retries, what advances, what stops):

| failure | class | action | reaches Banks? |
|---|---|---|---|
| Probe `INFEASIBLE` | expected | reject subject, mark it tried, pick next — no ask | no |
| Probe `INCONCLUSIVE-SHALLOW` | expected | ONE broadened re-probe; still shallow → reject, next | no |
| Probe `MARGINAL` | policy | `playbook.min_verdict` decides (default = FEASIBLE only → skip, next) | no |
| Sourcing shortfall (`ProductionError`, pre-TTS) | expected | fail job, pick next subject — **no spend lost** | no |
| Estimate > `per_job_threshold_gbp` | **gate** | PAUSE at stage 4→5, alert for **spend approval** | **YES (spend)** |
| TTS scope/401 (`TTSScopeError`) | config | **STOP the runner**, alert — nothing can be produced | **YES (blocker)** |
| TTS/music transient (5xx/network) | transient | retry ≤3 with backoff; then fail + alert | on give-up |
| Hissy music after 1 regen | quality | drop that layer, ship without (already handled) | no |
| Render / ffmpeg error | transient/bug | retry ≤1; then fail + alert; **resume reuses spent assets** | on give-up |
| Noise gate HARD-fail | quality | retry ≤1; then fail + alert — **never ship hiss** | on give-up |
| Machine sleep / mid-run restart | infra | job row holds `stage`; runner resumes at next stage, **no re-spend** | no |
| Subject pool exhausted | policy | pause the playbook, alert "pool empty — add subjects" | **YES** |
| MISPLACED upload (publish slice) | safety | already records + alerts | **YES** |

Retries use a `attempts` counter + `next_attempt_at` on the job so a poisoned job can't spin forever;
on exhausting retries the job goes `failed` with the error preserved (it already is — `jobs.error`) and
Banks is alerted once, not per-attempt. A `failed` production job never silently re-runs at full cost:
resumption is opt-in (the runner only resumes jobs in a resumable state, not `failed` ones, unless Banks
re-queues).

### 3. What Banks still controls (check this list against what you want to be asked)

**REACHES YOU (gated or alerted):**
1. **Publish** — every finished video → the existing Telegram approval (private upload; and, separately,
   public via the publish slice). Unchanged.
2. **Spend above threshold** — a job whose *estimated* cost (TTS chars + music credits, priced) exceeds
   `playbook.per_job_threshold_gbp` PAUSES before spending and asks. Below threshold: autonomous.
3. **Hard blockers (alert, not a routine ask):** TTS scope broken; a job that exhausted render/noise
   retries; subject pool exhausted; a MISPLACED upload.

**NEVER REACHES YOU (autonomous):** subject selection; probe verdicts; rejecting an infeasible subject
and advancing; script commissioning; sourcing (incl. a shortfall that advances to the next subject);
TTS/music *within* threshold; assembly; retries; stage transitions; cadence timing.

Every knob that decides *what you're asked* is **playbook DATA**, editable without code (dashboard/
Telegram later): `cadence`, `per_job_threshold_gbp`, `min_verdict`, `subject_pool`, `format`,
`approval_policy`. So you tune exactly what reaches you.

---

## Data model (all data, dashboard-ready; nothing niche in code)

- **`playbooks`** (new table, one per channel): `channel_id` FK, `enabled` bool, `cadence` jsonb
  (`{"per_week":2}` or a cron-ish spec), `subject_pool` jsonb (explicit list) and/or `domain` text
  (LLM proposes candidates when the pool empties), `format` text (`16:9` for now), `min_verdict` text
  (default `FEASIBLE`), `per_job_threshold_gbp` numeric, `runtime_target_s` int, `n_beats` int,
  `next_run_at` timestamptz, `state` text (`idle|producing|paused_spend|paused_pool|blocked`),
  `updated_at`. This is the scheduler's control surface. Cadence/approval already partly live in
  `channels.config`; the playbook is the *schedulable* policy and references the channel for voice/tone.
- **`channel_subjects`** (new): `channel_id`, `subject`, `status` (`selected|produced|infeasible|failed`),
  `job_id`, `verdict`, timestamps. Powers **no-repeat** (skip `produced`; cool-down `infeasible`) and
  gives the dashboard a real record of what each channel has attempted.
- **`jobs`** — REUSED as the queue. Add nothing structural; carry `production_state` in `jobs.result`
  (or `payload`) and use `stage` for the checkpoint. Add a small migration only for a retry counter
  (`attempts` int default 0, `next_attempt_at` timestamptz null) so the runner can back off.
- Migrations: `0011_playbooks.sql`, `0012_channel_subjects.sql`, `0013_job_attempts.sql`. Seed a
  wildlife playbook (disabled, empty pool) so the shape exists; Banks enables it.

---

## Components & files

**New:**
- `ytagent/scheduler/__init__.py` — the runner: `tick(conn, providers, tts, music, llm, notifier)` (one
  pass: due playbooks → create/advance jobs) and `run_forever()` (the poll loop). `python -m
  ytagent.scheduler` is the entrypoint.
- `ytagent/scheduler/selection.py` — `next_subject(conn, playbook)`: pick from `subject_pool` minus
  `channel_subjects.produced`; if pool exhausted and a `domain` is set, ask the LLM for N fresh
  candidates (deduped against history), else pause+alert.
- `ytagent/scheduler/state.py` — the production STATE MACHINE: `advance(conn, job, …)` runs the next
  stage, persisting `production_state`; idempotent skip-on-resume; the spend gate between 4→5.
- `ytagent/scheduler/cost.py` — `estimate_production_cost(script)` (TTS chars×rate + planned music
  credits×rate) for the spend gate. (A *per-job* estimate only — NOT the §4.10 ROI/ROAS governor.)
- `ytagent/repo/playbooks.py`, `ytagent/repo/subjects.py`.
- `scripts/verify_scheduler.py` — offline harness (fakes; simulates crash/resume, each failure branch).
- A `scheduler` service in `docker-compose.yml` (restart `unless-stopped`) — but **run/prove on the Mac
  first**; VPS deploy is a later, deliberate step that never risks the ocean stream. Renders run where
  the scheduler runs, so it stays on the Mac for now (the 2-core VPS is not for heavy ffmpeg).

**Edited (minimal, additive):**
- `ytagent/produce.py` — refactor `produce_video` into the stage functions the state machine drives
  (script / source / tts / design / assemble / submit), each reading+writing `production_state` so it
  can be resumed. This is the largest change and the heart of resumability. The single-shot
  `produce_video` stays as a thin wrapper (so existing runners/tests keep working).
- `ytagent/bot.py` — a `/playbook` command (and NL: "make wildlife documentaries twice a week" → set
  `cadence` + `enabled`, via a cheap LLM parse or a simple grammar) + surfacing the spend-approval and
  blocker alerts through the existing Notifier.

---

## Verification (offline, zero spend — the failure matrix is the test spec)

`scripts/verify_scheduler.py` with fakes (a fake probe returning each verdict; a fake produce whose
stages can be told to crash) proves: no-repeat selection; INFEASIBLE/SHALLOW/MARGINAL routing; a crash
mid-`designed` **resumes without re-spending** (the fake TTS/music assert they're called ONCE across a
crash+resume); the spend gate pauses above threshold and proceeds below; a poisoned job backs off then
fails+alerts once; cadence `next_run_at` advances; a full happy path reaches `submitted`. All existing
verifies stay green. A final **live unattended proof** (one real wildlife video, start to approval,
no human touch until the Telegram card) is the acceptance bar — gated behind Banks, run on the Mac.

---

## Honest session estimate

My estimates have run optimistic all project, so here is the real number: **3–4 sessions**, built as
provable sub-slices (each committed, each green before the next). The heart — resumability — is where
the work actually is; I'd rather prove it than rush it.

- **6a — Playbook + selection (data):** `playbooks`/`channel_subjects` tables + repos, `next_subject`
  with no-repeat, seed. Offline-verified. *(~1 session)*
- **6b — Resumable production state machine:** refactor `produce_video` into checkpointed stages +
  `production_state` + idempotent skip-on-resume + the spend estimate/gate. The big one; crash/resume
  is proven here. *(~1–1.5 sessions)*
- **6c — The polling runner + failure routing:** `tick`/`run_forever`, `FOR UPDATE SKIP LOCKED`,
  cadence, retries/backoff, the full failure matrix, restart survival. *(~1 session)*
- **6d — Control + integration:** the Telegram command ("twice a week"), spend/blocker alerts wired,
  end-to-end unattended proof on the Mac, the compose `scheduler` service. *(~0.5 session)*

Call it **3 sessions if 6b behaves, 4 if resumability needs a second pass** (likely — it's the part
with the most edge cases). I'd rather tell you 4 and deliver in 3 than the reverse.

---

## Scope-drift guards (I will hold these)
- The scheduler ORCHESTRATES existing, proven functions; it does not reach inside the pipeline to
  "improve" anything. Any pipeline defect found → BACKLOG, step around.
- No analytics/learning/trend/optimisation/Shorts/multilingual touches this slice, even if a stub looks
  cheap — they're B4+ and each is its own decision.
- Every control is data; nothing that decides cadence/subjects/thresholds/gates is hard-coded.
- Build and prove on the Mac; the VPS/ocean stream is untouched until a separate, deliberate deploy step.
- Publishing and above-threshold spend stay HARD human gates; everything else is autonomous within budget.
