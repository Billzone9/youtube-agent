# YouTube Agent — Master Specification

> **Reconstruction note (2026-06-24).** The original `youtube-agent-spec.md` could not be
> recovered from either machine, so this version was rebuilt faithfully from our project
> conversations. The design, decisions, and economics below are accurate to what we agreed.
> Exact section numbering and some opening wording are reconstructed; passages I inferred are
> marked `[VERIFY]`. Please read it through and correct anything that doesn't match your intent
> — and flag anything missing (e.g. early ideas we discussed but may have dropped). From here,
> **this file in git is the canonical source of truth**, and we update it whenever the vision evolves.

---

## 1. Purpose & overview

A **powerful, persistent, fully autonomous** multi-channel YouTube agent whose single mission is to
**conquer YouTube and MAKE money, not consume it**. It runs **24/7, all year round**, managing every
channel Banks creates and hands to it — researching, scripting, producing (long-form **and**
short-form), localising, streaming, publishing, promoting, and managing each channel **end-to-end on
its own**. Banks is the creative director: the agent acts **autonomously by default** and requires his
approval **only for specific key actions** — publishing and spending money — surfaced via Telegram so
he stays in control without being in the loop on everything. This inversion is the point: an
**autonomous operator with two narrow human gates**, not a gated assistant that waits for permission
at each step. It is built **general** — any new channel is onboarded (an interview to learn its
purpose) and run by the same engine, each with its own purpose, tone, cadence, languages, and
strategy, and behaviour on one channel never auto-replicates to others. The agent is unique,
innovative, and relentless, and it wins through **genuine quality and variation** — the only approach
that both survives YouTube's inauthentic-content enforcement and actually grows an audience — never
templated mass output. The early months are explicitly investment.

## 2. Scope & channels  `[VERIFY wording]`

- Start with **one channel done well**, not many at once.
- Reach multilingual audiences (English primary; Spanish, German, French and more) by
  **localising one video**, not producing many (see §8).
- Channels known/planned:
  - **Calm ambient** (Phase 0, live): "Deep Blue Calm" ocean stream, `@azurehours-p7h`.
  - **Wildlife & nature documentaries** (Phase 1).
  - **Financial-news summary channel** (future): top/breaking world financial news, multilingual —
    must add **original analysis**, never re-read others' material (YMYL handling).
- Each channel keeps its own purpose, tone, cadence, languages, and strategy. Behaviour on one
  channel does **not** auto-replicate to others.

## 3. Honest economics

- YouTube monetisation is slow: AdSense needs **1,000 subscribers + 4,000 public watch-hours**
  first, then ramps over months.
- Revenue paths: AdSense once monetised, plus **affiliate, sponsorship, and digital/own products**.
- The agent optimises in two phases per channel: first **buy watch-hours cheaply**, then
  **maximise revenue per view** once monetised.
- The dashboard reports **spend vs. revenue per channel** so net position and trend are always visible.
- No promise of month-one profit — that's not how the platform's economics work. **Months 1–3 are investment.**

---

## 4. System architecture (components)

Each component is modular so providers and pieces can be swapped without rewrites.

### 4.1 Orchestrator (the brain)
Scheduler + job queue running per-channel "playbooks." Decides what to produce, when, and in what
order; dispatches jobs through the pipeline; enforces approval gates; records every decision and
outcome to the database.

### 4.2 Channel registry & onboarding interview
Per-channel config: niche, purpose/goal (in Banks's words), tone, cadence, target languages, voice
profile, monetisation strategy, approval policy. On handover of a new channel, the agent runs a
short **onboarding interview** (Telegram/dashboard) to capture purpose and tailor direction.

### 4.3 Production pipeline (modular stages)
- **Research** — deep, grounded research on the topic (web-grounded, not limited to YouTube's API search quota).
- **Script** — **footage-led**: written/adapted to the footage actually available, so the result
  looks real and stays coherent. Channel voice and style applied here.
- **Assets** — narration voice (chosen accent/gender/age), sourced footage (licensed/public-domain
  stock + selective AI B-roll), music/soundscapes, thumbnails.
- **Assemble + localise** — FFmpeg edit, thumbnail, metadata, and additional-language audio tracks (§8).

### 4.4 AI provider layer (swappable)
A single internal interface in front of multiple external services so the best/cheapest tool is
used per job and can be changed via config:
- Long-form reasoning, research synthesis, scriptwriting (e.g. Claude API).
- Web-grounded current-events research (e.g. Gemini) — important for the financial channel.
- A general web-search/research API so research isn't bottlenecked by YouTube's ~100 searches/day quota.
- Voice/narration + dubbing (e.g. ElevenLabs), with a per-channel voice profile.
- Footage/imagery via stock APIs, plus selective (cost-gated) generative video for shots stock can't provide.

### 4.5 Streaming engine
A separate long-running service for 24/7 channels. Supervised FFmpeg process that loops/rotates a
**library of pre-produced assets** (never continuous live generation), auto-restarts on failure,
and pings Telegram if the stream drops. Managed-service option (e.g. Restream) available.
**Proven self-hosted in Phase 0.**

### 4.6 Publishing layer & quota manager
YouTube Data API with **OAuth per channel**. Caching, automatic AI-disclosure, MLA track upload.
Quota note: search costs 100 units (~100/day) and is **shared per Google Cloud project across
channels** → use a **project-per-channel** structure plus caching.

### 4.7 Product discovery (monetisation)  `[VERIFY number]`
For each channel, the agent researches and recommends specific affiliate/own products that
genuinely fit the niche, with rationale and margin, for Banks's approval. A core money behaviour.

### 4.8 Dashboard — control cockpit  `[VERIFY number]`
Not read-only: the cockpit from which Banks reviews everything and steers the agent **without
touching code**. Every changeable thing is an input/toggle/button; it accepts the same commands
Telegram does (and more); the agent reacts live. Uses already-stored data, so ~no recurring cost —
ships minimal in Phase 0, enriched later. Surfaces (non-exhaustive):
- **Overview** — all-channel KPIs, sub/watch-hour progress, spend vs revenue + net ROI, weekly deltas, each channel's state.
- **Work engine** — live jobs and queue, pipeline stage per job, providers/models in use, live logs, time + cost accruing.
- **History & audit timeline** — filterable record of decisions, jobs, approvals, spends, publishes, and Banks's instructions.
- **Command console** — typed instructions; agent shows its interpretation and proposed action before acting (confirmation where gated).
- **No-code channel controls** — purpose/goal, cadence/times, languages, voice profile, approval policy, spend ceilings, monetisation strategy.
- **Channel deep-dive** — performance over time, geography/language, retention, traffic sources, top/bottom performers, content roadmap, asset library, stream status + loop playlist.
- **Approvals** — mirrors Telegram with video/thumbnail/script previews and one-click regenerate/tweak.

### 4.9 Data & learning loop  `[VERIFY number]`
See §7.

### 4.10 Cost & ROI governor
Every job **estimates its cost before running**; a hard governor enforces the progressive monthly
ceiling — **£200 (m1) → £350 (m2) → £500 (m3+)** — with per-job approval thresholds, and it can
never blow past budget on its own. Targets, not rigid walls: it may **propose** exceeding an
early-month figure only when ROI-justified, surfacing the overage for Banks's yes.

### 4.11 Marketing / promotion
The agent proposes growth/ad plans (cross-posting to TikTok/Shorts/Reels/Instagram, SEO/metadata,
thumbnail A/B concepts, paid-ad proposals with budget + projected reach). It surfaces the plan and
spend on Telegram; **Banks approves and executes any payment — the agent never spends on its own.**
Hard rule: **no buying views/subs/engagement** (against YouTube terms; the agent refuses). Legitimate promotion only.

### 4.12 Safety & compliance
Copyright screening (**original/licensed assets only**; no copyrighted shows/music; **editing
copyrighted material to evade detection is off the board entirely**). Authenticity/variation
enforcement (no templated mass output). Automatic AI disclosure. Stricter YMYL handling for the
future financial channel (original analysis only).

---

## 5. Content lifecycle (data flow)

1. Orchestrator selects the next job from a channel's playbook (**cost-checked first**).
2. Research → footage-led script → asset sourcing → assembly + localisation.
3. Output enters the **review queue**; agent sends a Telegram approval request with a preview.
4. On approval: publish to YouTube (with disclosure + language tracks) and/or add to the 24/7 stream library.
5. YouTube Analytics flow back into the data layer.
6. Weekly summary generated; insights tune the next round of jobs.

## 6. Human-in-the-loop & Telegram

- **Approval-gated** (require Banks's yes): publishing a video, going live, spending above the
  per-job threshold, any promotion/ad spend.
- **Autonomous** (no gate): research, scripting, asset generation within budget, queue management, analytics, reporting.
- Telegram delivers: approval prompts with inline buttons + preview link; alerts (stream down,
  budget warning, milestone reached); and accepts free-text instructions anytime.

## 7. Data, analytics & the learning loop

- **Stored:** every decision, content piece, cost, and outcome; plus ingested analytics.
- **Weekly report** (dashboard + Telegram digest): viewer geography/language, average watch
  time/retention, traffic sources, sub & watch-hour progress, spend vs revenue, top/bottom performers.
- **Learning:** correlates content attributes (topic, length, thumbnail style, voice, language mix)
  with performance and adjusts future production. Aggregated audience data also supports spotting "the next big thing."

## 8. Multilingual approach (MLA)

Default to YouTube **Multi-Language Audio**: one video, up to **6 language audio tracks**, one
upload, one analytics surface, one quota cost. Localisation is a **dubbing pipeline** (translate
script → generate language voice track → upload track), **not** video duplication. (Context: MLA
creators see 25%+ of watch time from non-primary languages; auto-dubbing expanded to 27 languages
as of Feb 2026.) Separate per-language channels remain an option for specific entertainment/market
cases, decided per channel rather than by default.

## 9. Tech stack (proposed)

- **Backend:** Python (FastAPI) for the API/orchestration service.
- **Queue/scheduler:** Celery + Redis for pipeline jobs and cadence.
- **Database:** PostgreSQL for state, decisions, analytics, learning data.
- **Media:** FFmpeg for assembly and 24/7 streaming.
- **Dashboard:** React + Tailwind front-end → FastAPI backend.
- **Telegram:** python-telegram-bot (or similar) for approvals/commands.
- **External APIs:** YouTube Data + Analytics, an LLM (e.g. Claude), a grounded-research model
  (e.g. Gemini), a voice API (e.g. ElevenLabs), and stock-footage APIs.
- **Packaging/deploy:** Docker containers behind an nginx reverse proxy on the VPS.
- *(Models, prices, and library versions are finalised at build time against current docs.)*

## 10. Deployment (Hostinger VPS)

The VPS hosts the orchestrator, dashboard, Telegram bot, database, and streaming engine. **Heavy AI
generation runs on cloud APIs (not the VPS)** to keep the 2-core box light. Open question:
self-hosted FFmpeg streaming (cheaper, needs supervision — proven Phase 0) vs a managed service
(~£30–40/mo). VPS sizing depends on how many simultaneous streams we run.

## 11. Phased roadmap

- **Phase 0 — Calm ambient stream (pipe-cleaner). DONE.** Rebranded channel; synthetic claim-proof
  soundscape; streaming engine + monitoring + Telegram backbone; live and banking watch-hours.
- **Phase 1 — Wildlife & nature (full production proof).** Build research → footage-led script →
  narration (chosen voice) → assembly → MLA dubbing → approval → publish. Produce long-form
  documentaries (~2–3 hrs) on a schedule (continent overviews → specialised topics → oceans →
  Arctic), bank a library (~60 days inventory), then run the channel's own 24/7 stream from it.
- **Phase 2 — Analytics, learning & marketing.** Turn on weekly reporting, the learning loop, the promotion module.
- **Phase 3 — Multi-channel scale.** Onboard further channels (e.g. financial news, which adds
  speed + original analysis + YMYL handling) via the onboarding interview, reusing the engine.

## 12. Risks & mitigations

- **Inauthentic-content demonetisation** → variation enforcement, genuine value, human creative direction, no templated mass output.
- **Copyright strikes** → strict screening; original/licensed assets only; no copyrighted shows/music;
  ambient soundscapes over melodic music; **log asset provenance** (per Phase 1 footage recon).
- **API quota exhaustion** → quota manager, caching, project-per-channel, external research API to spare YouTube search quota.
- **Cost overrun** → cost governor with hard ceiling + per-job approval thresholds.
- **Stream downtime** → supervised auto-restarting process + Telegram alerts (or managed service).
- **Audience mismatch on rebranded channel** → low risk for ambient (discovery-driven), but monitored.

## 13. Decisions locked & open questions

**Locked:**
- Self-hosted FFmpeg streaming (proven Phase 0).
- Mixed, agent-decided footage sourcing (licensed/public-domain stock + selective cost-gated generative B-roll).
- Progressive budget ceiling £200 → £350 → £500.
- Narrator default: a **deep, poetic British male voice** — adjustable. (A voice *character/style*,
  NOT a clone of any real, named narrator — see §4.12.)
- Copyrighted-content streaming is off the board entirely.
- MLA dubbing as the multilingual default.

**Open:**
- Self-hosted vs managed streaming as channels scale.
- Exact provider/model choices and prices (finalised at build time).
- MLA launch languages per channel (data-driven).

---

## 14. Confirmed additions (2026-06-30)

These extend and sharpen the design above. They are first-class platform capabilities, not
options. Each notes the existing sections it touches. From here they are part of the canonical spec.

### 14.1 General-platform framing (reaffirmed)
The agent is a GENERAL, multi-channel YouTube automation platform with a no-code control dashboard —
not a single-niche tool. Every channel Banks creates is onboarded and run by the same engine
(§1, §2, §4.2). The wildlife channel is the FIRST channel used to prove each capability; it is the
proving ground, not the product. All architecture must be channel-general (channel registry,
per-channel config, channel-scoped data) and dashboard-ready (config stored as data, editable with
no code) from the first build slice — never retrofitted.

### 14.2 ROI and ROAS (extends §3, §4.8, §4.10)
Reporting and the dashboard display BOTH ROI (overall net position: total revenue − all costs) and
ROAS (return on ad spend: revenue attributable to paid promotion ÷ ad spend). The cost/ROI governor
tracks ROAS on every paid campaign, not just total spend, so paid promotion is judged on the return
it actually produces. ROAS is reported per campaign and per channel.

### 14.3 All revenue streams tracked (extends §3, §4.8, §7)
True ROI/ROAS requires all income, not just AdSense. The agent tracks EVERY revenue stream — AdSense
(via YouTube Analytics), affiliate, sponsorship, and digital/own-product sales — via dashboard input
and/or integrations where available. The data model holds a revenue ledger keyed by channel and
stream; the dashboard shows revenue broken down by stream alongside the true net position.

### 14.4 Multiple content formats incl. native Shorts (extends §4.3, §4.8)
Beyond long-form, the agent produces native short-form vertical content (YouTube Shorts, and the
equivalent for enabled social platforms) as a first-class content type — short-form drives discovery
and views. The production pipeline supports multiple output formats and aspect ratios (16:9
long-form and 9:16 vertical) per channel; a channel's playbook can schedule both. Format mix is a
per-channel setting.

### 14.5 Competitor & trend analysis (extends §4.3 research, §7 learning, §4.8 dashboard)
The agent continuously monitors what is trending in each channel's niche and what competitors are
doing, and feeds that into what it decides to produce next. This is an always-on input to the
orchestrator's playbook, surfaced on the dashboard (trending topics, competitor activity, content
gaps/opportunities), and combined with the channel's own performance data in the learning loop.

### 14.6 Comment & community management (new component; gating per §6)
The agent reads and responds to comments and runs community-tab posts, per channel. Because
per-comment approval does not scale, the default is autonomous within guardrails — on-brand tone, no
commitments or claims it cannot keep, and escalate anything sensitive (complaints, legal, YMYL) to
Banks. The approval policy is configurable per channel (auto / draft-for-approval / off). Community
posts (polls, updates, image posts) are agent-drafted; gating is per channel.

### 14.7 Social cross-posting — per-channel, opt-in (extends §4.11)
YouTube is the PRIMARY platform for every channel. In addition, the agent can cross-post videos and
Shorts AND make native posts to TikTok, Instagram/Reels, and Facebook — but ONLY for channels where
Banks has enabled it. Social distribution is a per-channel setting: each channel specifies which
external platforms (if any) it publishes to. Some channels opt in (e.g. a kids' channel sharing
videos and Shorts widely); others stay YouTube-only (e.g. the Deep Blue Calm ambient stream, which
gains nothing from social cross-posting). A new channel defaults to none until Banks enables it. All
cross-posting still obeys the human gate on publishing and the no-buying-engagement rule (§4.11, §6).

### 14.8 Budget is global, not per-channel (clarifies §4.10)
The progressive monthly ceiling (£200 → £350 → £500) is a single GLOBAL cap across all channels
combined, not per channel. The governor tracks spend per channel for ROI/ROAS reporting, but the
hard ceiling it enforces is the global total. (Per-channel sub-limits may be added later as a
dashboard control, but the enforced wall is global.)

---

## 15. Public-facing output & the metadata performance loop

Full standard: `public-facing-output-standard.md` (canonical — read it in full). Core rule:
everything an audience sees (descriptions, titles, tags, chapter labels, community posts, social
captions) is viewer-first, on-brand, and contains **no internal engineering artifacts** — filenames,
repo paths, manifest references, job/video IDs, and QC numbers never reach public text; the internal
provenance/audit record and the public text are kept strictly separate (the fix for the lion-upload
`…-footage-manifest.md` leak). Descriptions are research-led (YouTube Analytics/Data signals +
web/trend research BEFORE writing) and SEO-driven to attract viewers and subscribers, length chosen
by research not template, in a per-channel voice from onboarding config, with a single graceful
one-line AI-disclosure at the bottom. Descriptions/titles are NOT fixed: once videos are public the
agent measures metadata performance (impressions, CTR, views, subscribers gained, search terms) and
adapts — but only on real public data, never fabricated. Built in two layers: research-led writing
now (Layer 1), the performance loop activated across the analytics slices when public data exists
(Layer 2), with Layer 1 laying the data fields now (as the cost/revenue ledgers were). Depends on the
YouTube Analytics access (now unlocked) and competitor/trend analysis (§14.5). See the standard doc
for the complete specification and the Layer-1 data obligations.
