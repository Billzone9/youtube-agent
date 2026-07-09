# CLAUDE.md — YouTube Agent project

Operating rules, current state, and the build plan for Claude Code working in THIS repository
(`~/youtube-agent/`). **Read it fully at session start, then read `youtube-agent-spec.md` (including
the §14 additions) and `ROADMAP.md` in full.** This file is the entry point and the operating
contract; the spec holds the complete design; the roadmap holds the staged plan. This file gives the
scope and the rules and points to the spec for detail, so no fact lives in two places and drifts.
When unsure, STOP and ask Banks rather than guess.

Banks is the creative director with final approval over everything that publishes or spends. He is a
careful beginner: explain clearly, give copy-paste commands, go step by step.

---

## What you are building — READ THIS FIRST

**The heart of it: a powerful, persistent, FULLY AUTONOMOUS agent that runs YouTube channels
end-to-end on its own, 24/7, all year round.** Its mission is to conquer YouTube and MAKE money, not
consume it. It researches, scripts, produces (long-form AND short-form), localises, streams,
publishes, promotes, and manages each channel by itself. Banks is the creative director: **the agent
acts autonomously by DEFAULT and needs his approval ONLY for specific key actions — publishing and
spending money.** That inversion is the whole point — this is an autonomous operator with two narrow
human gates, NOT a gated assistant that waits for permission at every step. It is unique, innovative,
and relentless, and it wins through genuine quality and variation (what survives YouTube's
inauthentic-content enforcement and actually grows an audience), never templated mass output.

**The shape of it: a GENERAL, multi-channel platform with a no-code control dashboard** — NOT a
wildlife-documentary maker. Every channel Banks creates is onboarded (via an interview to learn its
purpose) and run by the **same engine**, each with its own purpose, tone, cadence, languages, and
strategy; behaviour never auto-replicates across channels. The wildlife channel is simply the **first
channel we use to prove each capability** — the proving ground, not the mission. Build nothing
wildlife-specific in code; wildlife is configuration.

The complete capability set you are building toward (full detail in `youtube-agent-spec.md`):
- **Multi-channel engine** — a channel registry + an onboarding interview for each new channel;
  per-channel purpose, tone, cadence, languages, voice, monetisation, approval policy. Behaviour
  never auto-replicates across channels. (§2, §4.2)
- **Production pipeline** — grounded research → footage-led script → assets (voice, footage, music,
  thumbnails) → FFmpeg assembly → MLA dubbing. (§4.3, §8)
- **Multiple formats incl. native vertical Shorts**, per channel — short-form drives discovery; the
  pipeline supports 16:9 long-form and 9:16 vertical, and a channel can schedule both. (§14.4)
- **Swappable AI-provider layer** — one internal interface in front of LLM / research / voice /
  footage providers, changeable by config. (§4.4)
- **Publishing + quota manager** — YouTube Data API, OAuth per channel, project-per-channel for
  quota, automatic AI disclosure. (§4.6)
- **Social cross-posting, per-channel opt-in** — cross-post videos and Shorts AND make native posts
  to TikTok, Instagram/Reels, Facebook, but ONLY for channels Banks enables. YouTube always primary;
  ambient channels (e.g. the ocean stream) stay YouTube-only; new channels default to none. (§14.7)
- **Comment & community management**, per channel — read/respond to comments, run community posts,
  autonomous within guardrails, gating configurable per channel. (§14.6)
- **Competitor & trend analysis** — always-on monitoring of niche trends and competitor activity,
  feeding what to produce next; surfaced on the dashboard. (§14.5)
- **Monetisation** — product discovery (affiliate/own products that fit each niche, §4.7) and
  tracking of **ALL revenue streams** (AdSense, affiliate, sponsorship, products), so the money
  picture is complete. (§14.3)
- **Cost & ROI/ROAS governor** — per-job cost estimate; a **GLOBAL** hard monthly ceiling across all
  channels (£200→£350→£500); reports **both ROI and ROAS**. (§4.10, §14.2, §14.8)
- **No-code control dashboard** — the cockpit to review and steer everything **without touching
  code**: overview, work engine, audit timeline, command console, no-code channel controls, channel
  deep-dive, approvals. Detailed data incl. ROI + ROAS and revenue by stream. (§4.8)
- **Learning loop** — correlate content attributes + competitor/trend signals with performance; tune
  future production. (§7)
- **24/7 streaming engine** for ambient/loop channels. (§4.5)
- **Safety & compliance** — claim-safe assets only, AI disclosure, variation enforcement, YMYL
  handling. (§4.12)

## Architecture principles — apply from the FIRST slice
These are how we avoid building a wildlife tool that has to be torn up later:
- **Channel-general.** A channels registry and per-channel config exist from day one. **Every** job,
  cost, revenue row, and analytic is keyed by channel. Nothing niche-specific is hard-coded —
  wildlife is data, not code.
- **Dashboard-ready.** Store all config as **data**, not code, so it is editable with no code edits.
  Capture rich, queryable events / decisions / costs / revenue so the dashboard and learning loop
  have something real to show later. The dashboard UI comes later; its foundations (controllable
  config + rich data) are laid now.
- **Controllable without code.** Anything Banks should be able to change — a channel's cadence,
  voice, languages, approval policy, enabled social platforms, spend posture — is a stored setting
  changed via dashboard/Telegram, never a code change.

## Isolation & scope — READ FIRST
- **Work ONLY inside `~/youtube-agent/`.** Never read, write, move, or delete anything outside it.
- **This is a PROJECT-level file** (`~/youtube-agent/CLAUDE.md`), never `~/.claude/CLAUDE.md`.
- **No global or system installs without asking.** Use a project-local Python virtualenv.
- **The production VPS (`31.97.119.33`) runs Banks's LIVE 24/7 ocean stream (`~/ocean-stream/`). Do
  NOT disrupt it.** The platform deploys to the VPS eventually, only via explicit, planned,
  Banks-approved steps, never risking the live stream. Build and prove on the Mac first.
- **Approval gate — HARD.** Pause and ask Banks before anything irreversible or external:
  publishing/uploading to YouTube or any social platform, sending any message (Telegram included),
  posting/replying as a channel, deleting files, spending money, or any network action that sends
  data off this machine.
- **Plan first.** For any multi-step task, work in plan mode: show the plan, wait for the go-ahead,
  then execute, verifying as you go.

## Current state (2026-06-30)
- **Phase 0 — DONE.** "Deep Blue Calm" ocean stream live 24/7 on the VPS. Do not touch it.
- **Phase 1.1 — DONE.** Proof-of-concept documentary "Lion — Lord of the Savanna": hand-built end to
  end, narrated, scored (3 claim-safe ElevenLabs Music cues), provenance reconciled and audited (17
  clips, every URL logged in `lion-doc-01-footage-manifest.md`), **reviewed and APPROVED by Banks**.
  Locked file: `assets/lion-doc-01/output/lion-doc-01_scored.mp4` (gitignored). **It is the
  platform's first test artifact — a known-good payload to run through the pipeline. Do not alter it.**
- **Agent code today = a skeleton only.** `docker-compose.yml` (Postgres + a Telegram-bot container)
  and `telegram_bot/bot.py` (only `/start` and `/ping`). Postgres is empty/unused. No orchestrator,
  job queue, approval flow, publishing, ledgers, or dashboard yet. That is what we now build.

## Your task — build the platform, in provable slices
Build it the way Phase 0 and the lion film succeeded: **the thinnest valuable, independently-testable
slice first, proven, then the next — never big-bang.** Add stack pieces (FastAPI/Celery/Redis/etc.
per spec §9) only when a slice needs them. Work each slice in plan mode first. The lion film is the
test artifact threaded through. Apply the architecture principles above from slice 1.

Immediate build path:
1. **SPINE + GATE.** A minimal orchestrator that records a finished video as a job, sends Banks a
   Telegram approval request with inline Approve/Reject buttons, and acts on his reply — recording
   every step. The DB schema must be **channel-general and dashboard-ready** from the start: a
   `channels` table, with jobs/videos/approvals AND a **cost ledger** AND a **revenue ledger** all
   keyed by channel. Publish action is a **DRY RUN** here (no credentials needed yet). Test with the
   lion film. Extend the existing `bot.py` and compose.
2. **REAL PUBLISHING.** YouTube Data API OAuth (per channel; **scoped** to the upload scope). Swap
   the dry-run for a real upload-on-approval. The lion film publishes to Banks's channel, behind his
   Telegram yes. Dependency: confirm WHICH channel and that it exists — ask Banks first.
3. **ASSEMBLY.** Reproduce the lion film's FFmpeg edit as an automated job; design for **multiple
   formats/aspect ratios** (long-form now, Shorts-ready). Lion film = reference output.
4. **ASSET SOURCING.** Automated claim-safe footage/audio sourcing + provenance logging per asset.
5. **SCRIPT + RESEARCH.** Footage-led script via the AI-provider layer + grounded research, with
   **competitor/trend monitoring** feeding the playbook.
6. **SCHEDULER / PLAYBOOK.** Decides what to produce next per channel (informed by trend/competitor
   data and performance); closes the loop to autonomy.

Layered in as slices need them (all part of the platform — see the inventory above): native
Shorts/multi-format production; social cross-posting (per-channel opt-in); comment & community
management; product discovery; all-revenue-stream tracking; the cost & ROI/ROAS governor (global
ceiling); the swappable AI-provider layer; MLA dubbing; the onboarding interview for new channels;
and the no-code dashboard once there is state worth showing.

Phase 1.2 in the roadmap (a small library by hand) is achieved THROUGH this build — the machine
produces the library. Do not hand-crank more documentaries as a separate step.

## Cost & revenue accounting — honest baseline from day one
The first month must account for money ALREADY committed, or the first ROI/ROAS numbers are
misleading — a wrong baseline is worse than no data. The ledgers (built into slice 1) must record:
- **Fixed/infrastructure costs:** VPS (~£120+/yr — record the cash outlay AND an amortised ~£10/mo);
  ElevenLabs subscription (monthly). So monthly net-ROI is honest without making month 1 look falsely bad.
- **Per-job API spend** (ElevenLabs music/TTS, footage APIs, LLM/research): logged per job and
  reconciled against live balances. ElevenLabs bills music **asynchronously** — per-call reads show 0
  and settle against the live balance afterward; reconcile against the balance, never the per-call read.
- **All revenue streams** (AdSense, affiliate, sponsorship, products), keyed by channel and stream.
The budget ceiling is **GLOBAL** across all channels (£200→£350→£500), not per channel. Every ROI and
ROAS figure must be net of real costs. Months 1–3 are investment (spec §3) — the goal is a true
baseline, not month-one profit.

## Spending & safety — structural, not behavioural
- Money the agent can spend is controlled **structurally**: scoped API keys with hard credit caps
  (what the key CAN'T do), not rules it is told to follow. The ElevenLabs key is scoped to Music with
  a per-key cap; future keys (footage, LLM, YouTube, social) follow the same least-privilege + cap
  pattern. Adding payment methods or upgrading plans stays a **manual, human-only** action.
- Anything that **actually spends money or publishes** stays a **HARD HUMAN GATE** (Telegram). This
  includes posting/replying as a channel and any social cross-post or paid promotion. Autonomous
  without a gate: research, scripting, asset generation within budget, queue management, analytics,
  trend/competitor monitoring, drafting (comments/posts), reporting. Never autonomous: publishing,
  spending above threshold, paid promotion, or buying views/subs/engagement (refused outright — §4.11).

## Technical conventions (hard-won — don't relearn these)
- **Synthetic / own audio only. Never licensed music** (Content ID risk — even free Pixabay/Pexels
  music carries claims that divert ad revenue).
- **FFmpeg:** `aeval` SEGFAULTS — never use it. `tremolo`'s minimum frequency is too fast for natural
  swells — use the `volume` filter with a sine expression. **Build to a temp file, then `mv`.** Verify
  outputs by exact byte-count before swapping.
- **Loudness:** master toward about **−14 LUFS** (YouTube normalization).
- **Mandatory noise check on EVERY render:** measure the noise floor; remove broadband hiss; report
  the noise floor in QC numbers.
- **Verify, don't assume.** After producing audio/video, measure it (duration, resolution, audio
  present, peak < 0 dBFS, noise floor) and report the numbers — Banks reviews by playing the file.
- **Build then deploy:** prove on the Mac, deploy artefacts to the VPS deliberately; heavy AI
  generation runs on cloud APIs, not the 2-core VPS (spec §10).

## Autonomous asset sourcing (human approval is the gate)
When building videos automatically you MAY search claim-safe sources (Pixabay, Freesound CC0-only,
stock-footage APIs), filter by written metadata + licence, download matches, and assemble the full
video WITHOUT per-asset approval — because Banks reviews and authorises every finished video, and
that review is the quality gate. Be honest about the limit: metadata gives duration/format/tags, not
how a file actually looks or sounds, so match on metadata + licence and rely on Banks's end review to
catch mismatches. **Always log provenance (URL, contributor, licence, timestamp). Never publish
without approval.**

## Project conventions
- **Provenance:** log URL + contributor + license + timestamp for any newly sourced asset; never
  fabricate a URL (derive from embedded asset IDs; flag what can't be verified).
- **Voice:** original/generic only — never clone a real, named narrator. Default: a deep, poetic
  British male; per-channel voice profile otherwise.
- **Script house style:** narration like a poet speaking the scene — vivid on the surface, accurate
  fact underneath. (Established with the lion film; adapt per channel.)
- **Secrets:** never commit; they live in `.env` (gitignored). Load with python-dotenv; never print,
  echo, log, or commit a secret.
- **Git:** commit locally freely; **do not push to the public remote without Banks's OK**; never
  commit secrets or media (both gitignored).
- **Two terminals, always tagged** `[ON THE SERVER]` / `[ON YOUR MAC]`; **no `#` comment lines in
  shell blocks**; **end command chains with** `&& echo "OK..." || echo "FAILED..."`.
- **Public-facing output** (full standard: `public-facing-output-standard.md`; spec §15 — read the
  doc in full before touching any metadata/description behaviour). Everything an audience sees —
  descriptions, titles, tags, chapter labels, community posts, social captions — is viewer-first,
  on-brand, and **never contains internal artifacts** (no filenames, repo paths, manifest references,
  job/video IDs, QC numbers). Public text is authored; the internal provenance/audit record is logged
  separately; they never mix. **Descriptions** are research-led (YouTube API signals + web/trend
  research *before* writing), SEO-rich to attract viewers/subscribers, length chosen by research not
  template, per-channel voice from onboarding config, with a single graceful AI-disclosure line at the
  bottom. Descriptions/titles are **not fixed**: once public, the agent measures metadata performance
  (impressions, CTR, views, subs gained, search terms) and adapts — but **only on real public data,
  never fabricated** — built in two layers: research-led writing now (Layer 1), performance loop
  activated across the analytics slices when public data exists (Layer 2). Build Layer 1's data model
  to capture initial metadata + reserve the metric fields now, as with the cost/revenue ledgers.

## When you need Banks
State plainly what you need and why; he gets a phone notification and will approve. Default to asking
whenever an action is irreversible, external, spends money, or is ambiguous. Plan first; execute on
his go-ahead.
