# CLAUDE.md — YouTube Agent project

Project context and operating rules for Claude Code working in THIS repository (`~/youtube-agent/`).
Read it fully at session start. It is guidance, not an enforced wall — when unsure, STOP and ask
Banks rather than guess.

## Isolation & scope — READ FIRST
- **Work ONLY inside this directory** (`~/youtube-agent/`). Never read, write, move, or delete
  anything outside it. Other projects and agents live on this machine — do not touch them, their
  files, their git repos, or their configuration.
- **This is a PROJECT-level file.** It must live at the project root (`~/youtube-agent/CLAUDE.md`),
  never at `~/.claude/CLAUDE.md` — that would leak these rules into every other project.
- **No global or system changes.** Do not install global packages or alter system/global config that
  could affect other projects. Use a project-local virtual environment for Python. **Ask before any
  global or system-level install.**
- **The production VPS (`31.97.119.33`) runs Banks's LIVE 24/7 ocean stream. Do NOT touch it.**
  All current work is local to the Mac. Only interact with the VPS if a task explicitly says so, and
  never in a way that could disrupt the live stream.
- **Approval gate.** Pause and ask Banks before anything irreversible or external: publishing or
  uploading to YouTube, sending any message, deleting files, spending money, or any network action
  that sends data off this machine. Banks gets phone notifications and will respond.
- **Plan first.** For any multi-step task, work in plan mode: show the plan and wait for Banks's
  go-ahead before executing. Going slowly and checking is correct — Banks has said: step by step, no rush.

## What this project is
An autonomous, multi-channel YouTube agent (Banks = creative director). Don't restate the vision —
**read these files in this repo for full context:**
- `youtube-agent-spec.md` — the master spec (vision, architecture, economics, decisions).
- `ROADMAP.md` — the staged plan and the cross-cutting principles (follow them).
- `lion-doc-01-script.md` and `lion-doc-01-footage-manifest.md` — the current piece of work.

Canonical copy lives at https://github.com/Billzone9/youtube-agent (public, read-only to you).

## Current state
- **Phase 0 — DONE.** "Deep Blue Calm" ocean stream is live 24/7 on the VPS. **Do not touch it.**
- **Phase 1 — in progress: a ~10-minute lion documentary, as a proof of the whole pipeline.**
  - Footage: 20 clips selected, provenance logged (`lion-doc-01-footage-manifest.md`). Banks is
    downloading them into `assets/lion-doc-01/clips/`.
  - Script: approved (`lion-doc-01-script.md`); clean spoken text in `lion-doc-01-narration.md`.
  - Narration: Banks is generating it in ElevenLabs (voice "David – Deep Documentary Narrator",
    v3 model) and will place audio in `assets/lion-doc-01/narration/` as `beat1.mp3 … beat7.mp3`.

## Your task — finish the lion documentary, and ONLY this for now
Do not build the orchestrator, other phases, or other channels yet. **Prove this one film first.**

0. **Sync first.** Ensure this directory has the planning docs by syncing it with the GitHub repo
   above. Existing media folders (`assets/.../clips/`, etc.) are large and **gitignored** — that's
   expected; never commit media. If syncing git into this existing folder is non-trivial, show the
   plan and ask Banks before running anything.
1. **Check prerequisites** before assembling: footage in `assets/lion-doc-01/clips/`, narration in
   `assets/lion-doc-01/narration/`. If something is missing, tell Banks — do not improvise content.
2. **Build a synthetic ambient bed** (savanna wind / dry grass), generated — **never licensed
   audio** (claim-proof rule). A low, gentle bed to sit under the voice.
3. **Assemble with FFmpeg** into one final `.mp4`: footage cut to the seven script beats, slow
   Ken-Burns moves on clips, gentle crossfades, narration mixed over the ambient bed (bed low, voice
   clear), the roar clip's natural sound up in Beat 6, and a simple title card. Match the beat order
   and visual cues in `lion-doc-01-script.md`.
4. **Hand the final mp4 to Banks for review. Do NOT publish.**

## Technical conventions (hard-won — don't relearn these)
- **Synthetic / own audio only. Never licensed music** (Content ID risk).
- **FFmpeg gotchas:** the `aeval` filter SEGFAULTS — never use it. `tremolo`'s minimum frequency
  (0.1 Hz) is too fast for natural swells — use the `volume` filter with a sine expression instead.
- **Build to a temp file, then `mv` into place** — prevents corrupt output.
- **Verify, don't assume.** After producing audio/video, check it objectively (duration, resolution,
  audio present, peak below 0 dBFS / no clipping) and report the numbers. Banks cannot review by
  watching remotely — produce the file locally, give him the measurements, and let him play it.
- **Loudness target:** master the final mix toward about -14 LUFS (YouTube's normalization target).
- This task is entirely local; nothing runs on the VPS.

## Autonomous asset sourcing (human approval is the gate)
When building videos automatically, you MAY search claim-safe asset sources (Pixabay, Freesound
CC0-only, stock-footage APIs), filter candidates by their written metadata (title, tags, description)
and licence, download what matches, and assemble the full video — without pausing for approval on
each asset. This is allowed because Banks reviews and authorises every finished video before it goes
live; that final review is the quality gate. Be honest about the limit: metadata tells you a file's
duration, format, and tags, NOT what it actually sounds or looks like, so you cannot truly confirm an
asset "fits" from its data — match on metadata + licence, assemble, and rely on Banks's end-of-task
review to catch mismatches (e.g. a "savanna" track with traffic in it). Always log provenance (URL,
licence, timestamp) for every sourced asset. Never publish without Banks's explicit approval.

## Mandatory noise check on every render
FFmpeg output on this project has repeatedly carried broadband background hiss ("jet-engine" white
noise). On EVERY audio/video render you produce, check for it and remove it: measure the noise floor,
and if there is audible broadband hiss, fix the source (never bake in noisy synthetic noise beds; if
an ambience bed is used, prefer a real claim-safe recording, or filter a synthetic one with
highpass/lowpass and keep it low) or apply gentle denoise (e.g. afftdn, or highpass+lowpass), then
re-verify. Always report the noise floor in your QC numbers.

## Project conventions
- **Provenance:** log URL + contributor + license + timestamp for any newly sourced asset.
- **Voice:** original / generic only — never clone a real, named narrator.
- **Script house style:** poetic narration on the surface, accurate fact underneath.
- **Secrets:** never commit; they live in `.env` (gitignored). None are needed for this local task.
- **Git:** you may commit locally, but **do not push to the public remote without Banks's OK**, and
  never commit secrets or media (media is gitignored).

## When you need Banks
State plainly what you need and why; he gets a phone notification and will approve. Default to asking
whenever an action is irreversible, external, or ambiguous.
