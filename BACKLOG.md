# YouTube Agent — Backlog

Deferred items, polish, and upgrade ideas. Nothing here blocks current work; we pull from it
deliberately. Add freely as ideas arise.

**Review cadence:** fortnightly.
**Next review:** 2026-07-08.
**Reminder mechanism:**
1. Claude checks the "Next review" date whenever we work and flags it if due (pull-based).
2. TODO (see below): a small server cron that pings Telegram every fortnight — a real
   time-based nudge using the bot we already run. Until that exists, the date field is the cue.

Status legend: `[ ]` open · `[~]` in progress · `[x]` done (move done items to the bottom)

---

## Phase 0 polish (non-blocking)
- `[ ]` Add more ocean clips to `~/youtube-agent/assets/clips/`, then rebuild for a longer loop
  (slim bitrate already baked into `build_master.sh`). Reduces visible repetition.
- `[ ]` On a future rebuild, optionally cap bitrate ~6800k to match YouTube's suggestion.
- `[ ]` Tidy the harmless duplicate Docker apt-source warning.
- `[ ]` Lengthen the master beyond the current 6-minute loop (overlaps with "add more clips").

## Infrastructure / friction
- `[ ]` Fix SSH key passphrase friction (macOS keychain integration) so connecting is seamless.
- `[ ]` Tidy old ended broadcasts from the YouTube Studio Content list.

## Process / tooling
- `[ ]` Build the backlog-review Telegram reminder cron (the time-based nudge described above).
- `[ ]` Store the project repo URL in Claude's memory once the repo exists, so Claude auto-knows
  where to read the roadmap/backlog/spec each session.
- `[ ]` Decide public vs private repo (recommendation: public, secrets gitignored — lets Claude
  read it directly; private means re-pasting files each session).

## Scheduler / playbook (Slice 6)
- `[ ]` **Footage availability must inform topic selection.** Before committing to a topic, the
  scheduler/playbook should PROBE library coverage — a cheap sourcing dry-run (search Pexels/Pixabay
  for the topic's core subject, count gate-eligible matches) — and avoid or re-shape topics the stock
  libraries can't dress. **Evidence (Slice 4 proof, 2026-07-18):** the emperor-penguin script sourced
  only **1/5 shot-briefs** — free Pexels/Pixabay have almost no emperor-penguin-in-Antarctic-winter
  footage, so 4/5 briefs failed loudly (correctly, not padded). Abundant subjects (lion, ocean,
  generic wildlife) have deep coverage; niche species/biomes may not. Topic choice should be
  coverage-aware, not just trend/interest-aware. (Also feeds the cost-gated generative-B-roll
  fallback decision for the rare must-have shot stock can't provide — spec §4.3.)

## Phase 1 enablers (promote to ROADMAP when we start them)
- `[ ]` Build asset-provenance logging into the production pipeline (URL + contributor + license
  + timestamp per clip). Required by the footage-recon findings.
- `[ ]` Choose the ElevenLabs narration voice: a specific generic deep British male (NOT a clone
  of any real narrator). Set a per-video narration budget.
- `[ ]` Decide MLA launch languages — data-driven, start with 1–2 that the audience data justifies,
  not all at once (cost scales per language).
- `[ ]` Pick the grounded-research source for script fact-checking (spec names e.g. Gemini).

---

## Done
(empty — move completed items here with the date)
