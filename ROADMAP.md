# YouTube Agent — Operational Roadmap

**Purpose:** the staged, checkable plan so this project never runs out of Claude's memory.
The full vision is the canonical `youtube-agent-spec.md` (with the §14 additions). This file is the
working roadmap; `BACKLOG.md` holds deferred items and upgrade ideas.

> **North star — read before the phases below.** We are building a **powerful, persistent, FULLY
> AUTONOMOUS** multi-channel YouTube agent that runs channels **end-to-end on its own, 24/7, all year
> round** — mission: **conquer YouTube and make money, not consume it.** It acts autonomously by
> DEFAULT and needs Banks's approval **only for key actions (publishing and spending)** — an
> autonomous operator with two narrow human gates, NOT a gated assistant. It is a **general,
> multi-channel platform with a no-code control dashboard**, not a single niche; every channel is
> onboarded and run by the same engine. The phases below build that platform; **the wildlife channel
> is the first channel used to prove each capability — the proving ground, not the mission.**
> Architecture is channel-general and dashboard-ready from the first slice (see `CLAUDE.md`).

**How we keep it current:** this file and `BACKLOG.md` live in git; Claude reads them at session
start; we update them on every decision. No secrets in the repo — they stay in `.env` (gitignored).

Status legend: `[x]` done · `[~]` in progress · `[ ]` not started

---

## Phase 0 — Calm ambient stream (DONE)

`[x]` "Deep Blue Calm" ocean stream live 24/7, public, `@azurehours-p7h`.
`[x]` Self-hosted FFmpeg on Hostinger KVM 2 VPS (`banks@31.97.119.33`, `~/ocean-stream/`).
`[x]` Docker Compose (`ocean-stream` + `ocean-watcher`, `restart: unless-stopped`); reboot-resilient.
`[x]` Fully synthetic, claim-proof audio; persistent SCHEDULED broadcast (auto-stop OFF).
`[x]` Telegram DOWN/UP health pings; SEO title, tags, multilingual descriptions.

Polish items (non-blocking) live in `BACKLOG.md`.

---

## Phase 1 — Build the platform, proven on the first content channel

The agent's general engine is built and proven here, using **wildlife & nature documentaries as the
first channel**. Pipeline being proven (spec §4, §9): research → footage-led script → narration →
FFmpeg assembly → MLA dubbing → Telegram approval → publish, plus the platform capabilities in §14.

### 1.0 Footage recon — DONE
`[x]` Confirmed permissively-licensed wildlife footage exists at quantity/quality (Pexels + Pixabay,
  thousands of 4K clips, free for commercial use). Mitigations locked: log provenance for every clip;
  never use their music (Content ID magnet); a narrated, edited doc is a clear new work.

### 1.1 Hand-crank ONE documentary, end to end (creative proof) — DONE
The proof that the creative output can be genuinely good, done by hand before automating.
`[x]` "Lion — Lord of the Savanna": footage-led script, ElevenLabs narration ("David"), FFmpeg
  assembly (7 beats, Ken-Burns, crossfades, synthetic savanna bed, synced roar, title card), and a
  3-cue claim-safe ElevenLabs score mixed under the voice. `lion-doc-01_scored.mp4`.
`[x]` Provenance reconciled and audited — 17 clips, every source URL logged in
  `lion-doc-01-footage-manifest.md` (swapped clips recovered from embedded Pexels asset IDs).
`[x]` Reviewed by Banks: APPROVED. The film is LOCKED — do not alter it.
`[ ]` Publish — DEFERRED BY DESIGN. Use this film as the known-good TEST ARTIFACT for the publishing
  slice (1.3 → slice 2), so publishing is proven through the machine, not done by hand.

**Learnings from 1.1 (carry forward):** compact thematic cues + FFmpeg volume automation, loop/reuse
over over-generating; ElevenLabs bills music ASYNCHRONOUSLY (reconcile against live balance); spend
control is STRUCTURAL (scoped key + per-key cap); the lion score cost ~1,500 credits (~£2) — claim
-safety, not cost, was the constraint; never fabricate a provenance URL (derive from asset IDs).

### 1.2 Build a small library — folded into 1.3
Not a separate hand-cranked step. Once the assembly/sourcing/script slices work, the **agent**
produces the library — each video through the approval gate, with variation enforced (spec §12).

### 1.3 Build the platform engine — IN PROGRESS (the current focus)
Automate the proven pipeline AND stand up the platform capabilities, in thin, independently-provable
slices (never big-bang). Add stack pieces only when a slice needs them; plan mode before each slice;
the lion film is the test artifact; apply the channel-general + dashboard-ready architecture from
slice 1. (Full brief: `CLAUDE.md`.)

`[ ]` **Slice 1 — Spine + gate.** Channel-general, dashboard-ready Postgres schema (`channels`;
  jobs/videos/approvals; **cost ledger** AND **revenue ledger**, all keyed by channel); Telegram
  approval with inline Approve/Reject for a finished video; orchestrator records every step. Publish
  = DRY RUN (no credentials yet). Test with the lion film.
`[ ]` **Slice 2 — Real publishing.** YouTube Data API OAuth (scoped to upload). Real
  upload-on-approval; the lion film goes live behind Banks's yes. (Dependency: which channel, and it exists.)
`[ ]` **Slice 3 — Assembly.** Reproduce the lion edit as an automated job; design for **multiple
  formats/aspect ratios** (long-form now, native Shorts-ready). Lion film = reference output.
`[ ]` **Slice 4 — Asset sourcing.** Automated claim-safe footage/audio sourcing + per-asset provenance.
`[ ]` **Slice 5 — Script + research.** Footage-led script via the AI-provider layer + grounded
  research, with **competitor/trend monitoring** feeding the playbook.
`[ ]` **Slice 6 — Scheduler / playbook.** Decides what to produce next per channel (informed by
  trend/competitor data + performance); closes the loop to autonomy.

Platform capabilities layered in as slices need them (all first-class — spec §4, §14):
`[ ]` Native Shorts / multi-format production (§14.4).
`[ ]` Social cross-posting — per-channel opt-in to TikTok/Instagram-Reels/Facebook; YouTube always
  primary; ambient channels stay YouTube-only (§14.7).
`[ ]` Comment & community management — per channel, autonomous within guardrails, gating configurable (§14.6).
`[ ]` Competitor & trend analysis — always-on, feeding the playbook and the dashboard (§14.5).
`[ ]` Product discovery (affiliate/own products per niche) (§4.7) and **all-revenue-stream tracking**
  (AdSense, affiliate, sponsorship, products) (§14.3).
`[ ]` Cost & ROI/ROAS governor — per-job estimate + **GLOBAL** monthly ceiling (£200→£350→£500);
  reports ROI **and** ROAS; ledgers seeded with fixed costs so month-1 data is honest (§4.10, §14.2, §14.8).
`[ ]` Swappable AI-provider layer (§4.4); MLA dubbing (§8); onboarding interview for new channels (§4.2).
`[ ]` No-code dashboard cockpit (React + Tailwind) — overview, work engine, audit timeline, command
  console, no-code channel controls, channel deep-dive, approvals; ROI + ROAS and revenue by stream (§4.8).

### 1.4 First channel's own 24/7 stream
`[ ]` Loop the edited documentary library into a persistent stream, reusing the hardened Phase 0
  streaming engine and monitoring.

---

## Phase 2 — Analytics, learning & marketing (deepening)
`[ ]` Full weekly reporting, the learning loop at depth, the marketing/promotion module with ROAS
  measurement per campaign (spec §7, §4.11, §14.2). (Foundations are laid earlier; this is where they mature.)

## Phase 3 — Multi-channel scale
`[ ]` Onboard further channels via the onboarding interview, reusing the same engine — e.g. a kids'
  channel (social cross-posting on, Shorts-heavy) or a financial-news channel (speed + original
  analysis + YMYL handling). Because the architecture is channel-general from slice 1, this is
  configuration, not a rebuild.

---

## Cross-cutting principles (carry these always)

- **General platform, not a niche tool:** channel-general architecture from slice 1; wildlife is the
  first tenant/proving ground, never the mission.
- **No-code control:** every changeable thing (cadence, voice, languages, approval policy, enabled
  social platforms, spend posture) is stored data, changed via dashboard/Telegram — never code.
- **Claim-proof audio:** synthetic/own audio only; never licensed music (even free Pixabay/Pexels
  music carries Content ID claims that divert ad revenue).
- **Provenance logging:** URL + contributor + license + timestamp for every sourced asset; never
  fabricate a URL.
- **Voice = original, not impersonation:** generic deep British male by default; never clone a real narrator.
- **Footage-led scripting:** source footage first, write to fit it; selective cost-gated AI
  generation only for a rare must-have shot — never whole AI-generated videos.
- **Script voice (house style):** poet speaking the scene — vivid surface, accurate fact underneath.
- **Human approval gate:** nothing publishes, posts/replies as a channel, or spends on promotion
  without a Telegram approve.
- **Spending is structural, not behavioural:** scoped API keys with hard caps; adding payment or
  upgrading plans is manual, human-only.
- **Budget is GLOBAL** across all channels (£200→£350→£500), not per channel; per-channel spend is
  tracked for ROI/ROAS reporting.
- **Track everything for honest money data:** all revenue streams + fixed/sunk costs in the ledgers,
  so first-month ROI **and ROAS** are real, not misleading.
- **Genuine value + variation:** no templated mass output (anti-demonetisation, spec §12).
- **Build then deploy:** prove on the Mac, deploy to the VPS deliberately; heavy AI generation on
  cloud APIs, not the 2-core VPS.
- **Verify, don't assume:** measure (frames, byte counts, audio numbers) rather than trust.
- **Build in provable slices:** thinnest valuable, testable piece first — never big-bang.
- **Two terminals, always tagged** `[ON THE SERVER]` / `[ON YOUR MAC]`; no `#` lines in shell
  blocks; end chains with `&& echo "OK..." || echo "FAILED..."`.
