# YouTube Agent — Operational Roadmap

**Purpose:** the staged, checkable plan so this project never runs out of Claude's memory.
The full vision is the canonical `youtube-agent-spec.md` (commit it here too). This file is
the working roadmap; `BACKLOG.md` holds deferred items and upgrade ideas.

**How we keep it current:** this file and `BACKLOG.md` live in git. Claude reads them at the
start of a session; we update them on every decision. No secrets ever go in this repo —
stream key and bot token stay in the server `.env` (gitignored).

Status legend: `[x]` done · `[~]` in progress · `[ ]` not started

---

## Phase 0 — Calm ambient stream (DONE)

`[x]` "Deep Blue Calm" ocean stream live 24/7, public, handle `@azurehours-p7h`.
`[x]` Self-hosted FFmpeg on Hostinger KVM 2 VPS (`banks@31.97.119.33`, `~/ocean-stream/`).
`[x]` Docker Compose: `ocean-stream` + `ocean-watcher`, `restart: unless-stopped`. Reboot-resilience tested.
`[x]` Fully synthetic, claim-proof audio (brown+pink noise, volume-filter sine swell, 14s).
`[x]` Persistent SCHEDULED broadcast (auto-start OFF, auto-stop OFF, DVR off, Normal latency, Default key).
`[x]` Telegram DOWN/UP health pings.
`[x]` SEO title, tags, multilingual descriptions set.

Polish items (non-blocking) live in `BACKLOG.md`.

---

## Phase 1 — Wildlife & nature documentaries (full-production proof)

Goal (spec §11): build the research → footage-led script → narration → FFmpeg assembly →
MLA dubbing → Telegram approval → publish pipeline. Produce a library, then run the
channel's own 24/7 stream from it.

### 1.0 Footage recon
`[x]` Confirm permissively-licensed wildlife footage exists at quantity and quality.
  - Verdict: GREEN. Pexels + Pixabay both carry thousands of 4K wildlife clips, free for
    commercial use, no attribution required. Multiple sources, not a single dependency.
  - Caveat A: free platforms do NOT verify uploader ownership and give $0 indemnification.
    Mitigation -> log provenance (URL, contributor, license, timestamp) for EVERY clip.
  - Caveat B: never use their music (Content ID magnet). Keep audio synthetic, like Phase 0.
  - Licensing nuance: clips may not be redistributed "standalone"; a narrated, edited doc is
    a clear new work, so we're clean. The eventual 24/7 stream loops EDITED docs, not raw clips.

### 1.1 Hand-crank ONE documentary, end to end (the proof) — do this BEFORE any orchestrator
Rationale: Phase 0 won by proving the plumbing cheaply first. Phase 1's hard part is whether
the creative output is actually good. Prove that by hand before investing weeks in automation.
Build on the Mac (Phase 0 pattern), deploy artefacts to the VPS.

`[ ]` Pick launch topic (recommended: single-species lion; alt: "Wildlife of Africa").
`[ ]` Gather candidate footage from Pexels/Pixabay; log provenance JSON per clip.
`[ ]` Write a footage-led script: narration fits what the footage actually shows.
`[ ]` Fact-check the script against a grounded-research source (no hallucinated animal facts).
`[ ]` Generate narration: a GENERIC original deep British male voice (ElevenLabs). NOT a clone
      of any real, named narrator — that violates ToS and is an impersonation/legal problem.
`[ ]` Assemble in FFmpeg: slow Ken-Burns moves, crossfades, narration over a synthetic ambient
      bed, simple lower-thirds.
`[ ]` (Optional) Produce one dubbed language version to prove the MLA step.
`[ ]` Send to Telegram for review; publish as a normal video only on approval.
`[ ]` Review result honestly: is it good enough that people would watch? Decide go / iterate.

### 1.2 Build a small library
`[ ]` Produce a handful of docs following the spec's arc (continent overviews -> specialised topics).
`[ ]` Each one still goes through the approval gate; enforce variation (no templated sameness).

### 1.3 Build the orchestrator (only after 1.1 proves the output is good)
`[ ]` Automate the proven pipeline per spec §9: FastAPI + Celery + Redis + PostgreSQL, FFmpeg,
      python-telegram-bot, swappable AI-provider layer, stock-footage APIs.
`[ ]` Wire the cost governor (see principles) and per-job cost estimation.
`[ ]` No-code dashboard cockpit (React + Tailwind) as scope allows.

### 1.4 Channel's own 24/7 stream
`[ ]` Loop the edited documentary library into a persistent stream, reusing the hardened Phase 0
      streaming engine and monitoring.

---

## Phase 2 — Analytics, learning & marketing
`[ ]` Weekly reporting, the learning loop, the promotion module (spec §11).

## Phase 3 — Multi-channel scale
`[ ]` Onboard further channels (e.g. financial news, which adds speed + original analysis + YMYL
      handling) via the onboarding interview, reusing the same engine (spec §11).

---

## Cross-cutting principles (carry these always)

- **Claim-proof audio:** synthetic / own audio only. Never licensed music.
- **Provenance logging:** record URL + contributor + license + timestamp for every sourced asset.
- **Voice = original, not impersonation:** generic deep British male; never clone a real narrator.
- **Footage-led scripting:** source footage first, then write to fit it. Selective, cost-gated AI
  generation only for the rare must-have shot — never whole AI-generated videos.
- **Human approval gate:** nothing publishes without a Telegram approve.
- **Genuine value + variation:** no templated mass output (anti-demonetisation, spec §12).
- **Cost governor:** progressive ceiling £200 (m1) -> £350 (m2) -> £500 (m3+); per-job estimate;
  ROI-justified overage only with explicit yes (spec §4.10, §13.3).
- **Build then deploy:** prove on the Mac, deploy artefacts to the VPS; keep the 2-core box light
  (heavy AI generation runs on cloud APIs, not the VPS — spec §10).
- **Verify, don't assume.** Measure (frames, byte counts, audio numbers) rather than trust.
- **Two terminals, always tagged** `[ON THE SERVER]` / `[ON YOUR MAC]`; no `#` lines in shell
  blocks; end chains with `&& echo "OK..." || echo "FAILED..."`.
