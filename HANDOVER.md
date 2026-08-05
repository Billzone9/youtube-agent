# Handover — current state of the build (2026-08-05)

Supersedes `HANDOVER_M1.md` (M1-era, stale). Read `CLAUDE.md` first (operating contract + standing
discipline), then this. `origin/main` = `63e2e9a`. Run `make health` (22/22 green; no spend by default).

## The frame: build-first, nothing publishes
The A′ marketing arc is **STOPPED**. Standing goal: **FINISH THE AGENT — every outstanding platform
component — and make sure the code works, BEFORE producing or publishing any further video.** Production
capability may be BUILT, not EXERCISED for output. Any plan whose payoff is publishing is out of scope
until Banks says the build is done. (Discipline is in `CLAUDE.md`.) Sequence approved in
`PLAN_AGENT_COMPLETION.md`.

## Armed state (must stay stated)
- The YouTube token carries `youtube.force-ssl` and resolves to `UCRkrZa2yjLLw-f67H2pYI2g` ("The Tales of
  Wildlife and Nature") — verified. So the machine CAN publish.
- **What prevents it:** (1) live publishing is now an EXPLICIT flag — `bot._build_publisher` returns the
  live publisher only when `YTAGENT_LIVE_PUBLISH=true` AND a token exists; **default OFF** (an armed
  token stays dry-run). (2) publish is a HARD Telegram gate. (3) the wildlife playbook is DISABLED. (4)
  publish approvals now EXPIRE after 7 days (`_PUBLISH_APPROVAL_TTL`). (5) the approval queue is empty.
- **Item 6 (live publish of a Short) is PARKED.** Resume trigger: *when the build is complete AND Banks
  decides to publish* — not a date, not a next step.

## Phase 0 — DONE (correctness & trust)
- **D1 hermetic verifies** — every DB verify leaves ZERO production rows (a polluting test suite is an
  accidental-upload path); enforced by a `make health` backstop. `verify-hermeticity-standard.md`.
- **D2 job terminal status + two implicit-state fixes** — produce jobs reach terminal `produced`
  (migration 0021); publish approvals EXPIRE at 7 days (migration 0022, `expired` state); live-publish is
  an explicit flag not a token inference.
- **D3 audio-design completeness guard** — `assert_audio_complete` fails on planned-then-missing audio;
  a DECLARED degradation (no provider/scope/ceiling) ships cleanly (`AudioDesign.declared`).
- **D4 dead-path removal** — `produce_from_sourced`/`remake_from_narration` + their hand-crank scripts
  deleted (only `run_production` is the real path).
- **D5 CI gate** — `.github/workflows/health.yml` seeds a baseline on ephemeral Postgres and runs the
  SAME `make health`; media-absent checks skip EXPLICITLY (skip ledger), so CI-green == local-green.

## Phase 1 — IN PROGRESS (intelligence that needs no publishing)
Order (approved): cost models → grounded research → competitor/trend → B8 safety; **dashboard LAST**.
- **Cost models — DONE.** `estimate_research_cost` (£0.28 CEILING, derived from the loop's hard caps),
  `estimate_trend_analysis_cost` (~£0.095/run), reusable `estimate_llm_gbp`. `PLAN_PHASE1_COSTS.md`.
- **Grounded research (A1) — WIRED, not yet live.** `authoring/grounding.py`: a bounded loop (caps
  enforced BEFORE each search; a cap → a declared degradation, ship partial facts), reconciled against
  the ledger's actual usage (`reconcile_research_usage` — an under-reporting provider is a caught
  defect), resume-idempotent (continue a crashed run, never re-search). Wired into `run_production` as
  `_st_research` BEFORE the script, gated by its OWN pre-gate (`_research_gate`) that quotes research
  before it spends; the main TTS/music gate is `include_research=False` (no double-count). Facts +
  partiality reach the writer (a partial set forbids ungrounded claims — accuracy is the house floor).
  Verified offline: `verify_grounding`, `verify_research_order`.
  **BLOCKED on:** the real Anthropic web-search `GroundedProvider` + a first live run — see the credits
  blocker below. Everything buildable/verifiable offline is done and green.
- **Competitor/trend analysis — NOT STARTED.** Needs an UNATTENDED-spend gate + a sub-budget (open
  decision below). Cost model exists.
- **B8 safety/compliance consolidation — NOT STARTED.**

## Blockers & open decisions (Banks)
- **Anthropic API is OUT OF CREDITS** — blocks live vision, live grounded research, and any live LLM.
  A Claude Pro/Max subscription does NOT cover it (API is per-token; settled in `CLAUDE.md`). Topping up
  the Anthropic API account is a manual, human-only billing action. Until then, live research can't run.
- **Trend-analysis sub-budget — OPEN DECISION (see `PLAN_PHASE1_COSTS.md`).** How much of the £200
  global monthly ceiling may UNATTENDED competitor/trend analysis consume before its gate pauses it?
  Stated, not chosen — it gates building the trend gate.
- **Analytics scope (Phase 2)** — B4 will need `youtube.analytics.readonly` (new consent + a `youtube.py`
  breadth review). Flagged, not yet actioned.
- **Dashboard scope** — read-only skeleton, built LAST; how full is open.

## Decisions settled this session (do not re-litigate)
- Live-publish is explicit, not credential-inferred (`YTAGENT_LIVE_PUBLISH`).
- Spending verifies are opt-in: `make health` never spends; `make health-live` / `HEALTH_LIVE=1` runs the
  live vision calibration. Gating a spending test on key-presence is the trap that drained the balance.
- Claude Max ≠ API (settled, in `CLAUDE.md`).
- Cadence budget gate: explicit `enforce_cadence_budget` flag (default ON) separate from
  `recurring_allowance` (the number); enabled + missing/unreadable number → PAUSE (fail closed).
- Per-job credit gate: KEEP fail-open on an unreadable balance (attended + 3 structural backstops: key
  hard cap, mid-run TTSQuotaError fail-fast, resume idempotency) — a stated decision, in the docstring.
- Credential-presence-as-decision sweep done: the remaining forks are correct capability-degradation;
  the three latent ones (publisher, armed cards, vision verify) are all fixed.

## Where to look
`CLAUDE.md` (contract) · `PLAN_AGENT_COMPLETION.md` (the approved sequence) · `PLAN_PHASE1_COSTS.md`
(cost models + the trend sub-budget question) · `BACKLOG.md` · the standards files (`*-standard.md`).
`make health` is the one "is it healthy" command (no spend); `make health-live` adds the paid vision
calibration.
