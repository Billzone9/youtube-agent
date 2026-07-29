# Documentary standard — footage curation + full audio design (one consolidated slice)

## Context & acceptance bar
The re-made wolf fixed the cutting rhythm (16 distinct shots, 4/beat, no reuse) but fails the
DOCUMENTARY standard two ways: (a) footage is off-brief — snowless clips, a captive **fence** (frame
t6), a **coyote** not a wolf (frame t140); (b) it is wall-to-wall narration — **no music, no ambience,
no SFX, no breathers**. The lion film is the standard: layered score, ducking, a breath where the music
carries. **Acceptance bar: the re-made wolf must stand next to the lion.** One consolidated slice,
reusing the preserved narration (£0 TTS).

## APPROVED AMENDMENTS (2026-07-29 — these override anything below they touch)
1. **BREATHERS ARE STRUCTURAL (primary acceptance criterion).** Sidechain release during inter-sentence
   pauses is a gain-lift, NOT a breather, and will not clear the bar. The binder inserts **deliberate
   music-only gaps in the timeline**: a **cold open** (3–5s of picture + score before the first word)
   and a **3–5s music-only gap at each beat transition** (picture + score, no narration). Narration is
   untouched (£0 TTS) — this is an EDIT-level change (extra picture/score time), not re-synthesis. See
   revised §2e.
2. **MEASURE FIRST.** `ffprobe` the actual per-beat narration + breather durations BEFORE choosing any
   cue length; cue lengths follow the MEASURED timeline, not the plan's estimates (§2b/§2c numbers are
   ceilings for budgeting only). The bed is generated **long enough to span the film** OR
   **crossfade-looped so no seam is audible**. Noise-gate failure path is explicit: **one regeneration
   with an adjusted prompt, then fail loud reporting credits spent.** The **bed degrades gracefully**
   like SFX — a failed bed NEVER hard-fails the film (ship score+breathers without it, log the omission).
3. **TWO-STAGE LIVE RUN.** **Stage 1** = curation + vision gate ONLY, **zero music spend**; report per
   beat whether `n_min` content-verified clips were reached, with the verdicts, then **STOP** for Banks.
   **Stage 2** = generate cues + bed, ONLY after Stage 1 is green and Banks says go.
4. **BUDGET: hard ceiling 4,000 Music credits incl. retakes** (not the 2,250 estimate). Track cumulative
   generated credits; on reaching 4,000 **hard-stop and report** (no further generation).

**Build order (this session):** Part 1 (curation) + the offline verifications + the permanent
fence/coyote/wild-wolf calibration fixtures FIRST. Commit locally, NO push until the ship-word.

---

## Part 1 — FOOTAGE CURATION (only wild, in-season, correct-species footage survives)
Three tightenings, cheapest filter first, the vision gate last:

**1a. Season/setting terms reach the queries.** `sourcing/query.py`: the shot-brief already carries
"snow"/"winter"/"dusk"; ensure they SURVIVE into the search phrases (today `_must_terms` keeps only the
recurring subject, e.g. "wolf", so "snow" can be dropped). Add an explicit `setting` field to the LLM
query plan (`_llm_plan` returns queries + subject + **setting terms** like `["snow","winter forest"]`)
and guarantee at least one query pairs subject+setting (e.g. "wolf snow"). Deterministic fallback keeps
brief adjectives it currently drops (snow/winter/dusk) when they name a season/setting.

**1b. Negative-tag filter (metadata, free).** `sourcing/rank.py`: disqualify a candidate whose
tags/title/slug contain a **negative term** — `fence, zoo, captive, enclosure, aquarium, cage, farm,
pet, leash, circus, sanctuary`. Cheap, kills the obvious captive clips before download (t6's fence).
Configurable per channel later; a sensible default now.

**1c. The VISION GATE (Haiku vision — the real content check).** New `sourcing/vision.py`:
`vision_check(frames, *, expect) -> VisionVerdict`. After a candidate passes the metadata gate
(`gate_download`), sample **2–3 frames** (ffmpeg at ~25%/50%/75%) and send them to **Haiku vision**
(the provider already forwards `messages` content blocks unchanged — an image block is
`{"type":"image","source":{"type":"base64","media_type":"image/jpeg","data": …}}`; `ModelTier.CHEAP`
= Haiku, which sees images — **no provider change**). Strict-JSON verdict against the brief's
expectations: `{species_ok, wild_ok, season_ok, overall_ok, reason}` where
`expect = {subject:"grey wolf", wild:true, season:"winter/snow"}` derived from the brief. A candidate
that fails any required check is REJECTED (try the next ranked candidate). Wired INTO
`source_clips_for_brief` so a beat still fails loud if it can't reach `n_min` **content-verified**
clips. Cost: Haiku vision, ~2–3 small frames per considered clip — pennies; logged as `ai_generation`.
- **Calibration (two-sided, per the AI-tell/noise doctrine):** tune the prompt + required checks so
  the saved **wild snowy wolf frames PASS** and **this run's fence frame (t6) FAILS `wild_ok`** and
  **coyote frame (t140) FAILS `species_ok`**. Save those three frames as durable calibration fixtures.

---

## Part 2 — DOCUMENTARY AUDIO DESIGN (score + ambience + breathers + SFX)
Study reference: `lion-doc-01-edit-spec.json` + `assets/lion-doc-01/music/PROVENANCE.md`. The lion's
recipe: **3 compact instrumental cues reused across beats**, static per-beat `in_db` levels + a 2s/3s
fade on the opener, **sidechain ducking** (threshold 0.05, ratio 8, attack 5, release 300), one SFX at
a timestamp. Reproduce that recipe for the wolf — synthetic/own audio only (CLAUDE.md), noise-gated.

**2a. Music provider (mirror the TTS seam).** New `ytagent/music/` (kept out of `providers/`, like
`tts/`): `base.py` (`MusicResult{path, seconds, credits_est, model, request_id}`, `MusicProvider`
Protocol, `MusicScopeError` for 401/403); `elevenlabs.py` — `POST https://api.elevenlabs.io/v1/music`,
body `{prompt, music_length_ms, force_instrumental:true}`, `?output_format=mp3_44100_128`, model
`music_v1`, atomic temp→`os.replace` (mirror `tts/elevenlabs.py`); `__init__.get_music_provider(settings)
→ None` without a key. Ledger: `repo/ledger.write_music_cost(...)` mirroring `write_tts_cost` —
`ai_generation` / provider `"ElevenLabs Music"` / **`reconciled=False`** estimate (async billing),
`metadata={estimate, seconds, credits}`, idempotency `music:{job_id}:{cue}`. **Every generated cue is
noise-gated (`qc.check_source_clean`) on arrival** — a hissy cue HARD-fails (this is exactly why the
lion's hand-made bed was rejected).

**2b. The wolf cue plan (compact cues, reused, per-beat levels).** Generate wolf-specific instrumental
cues (never reuse the lion's — variation is the point):
- `theme` (~45s, ~675 cr) — "quiet, reverent winter-wilderness score, solo cello over warm sustained
  strings and a soft low drone, spacious, room for a narrator" → beats 1 & 3.
- `cold` (~35s, ~525 cr) — darker, patient, low pulsing ostinato → beat 2 (the journey through snow).
- `dusk_swell` (~30s, ~450 cr) — a rising, aching swell settling into stillness → beat 4 (the howl).
Set per-beat via `MusicCue(file, in_db=-16, fade_in, fade_out)` in the binder (music_db −16, the swell
beat −14, matching the lion). The clips-path binder currently sets `music=None`; it now attaches the
cue for each beat.

**2c. Ambience bed (claim-safe, noise-gated).** Generate ONE soft continuous bed via ElevenLabs Music
(`bed` — "very soft, dark, textural winter-forest wind ambience, no melody, no percussion, felt not
heard") at a LOW fixed level (~−30 dB). **Amendment 2:** generate the bed **long enough to span the
measured film length** (so no repeat is needed) OR **crossfade-loop it (`acrossfade`) so no seam is
audible** — never a hard-cut loop. Synthetic → claim-safe; **noise-gated on arrival**. **Noise-gate
failure path (explicit):** one regeneration with an adjusted (softer/darker) prompt; if it fails again,
**fail the bed gracefully** — ship score+breathers WITHOUT the bed and log the omission + credits spent.
A failed bed NEVER hard-fails the film. `EditSpec.audio_mix.include_bed=true` + `bed=<path>` (fields
already exist, unused in the clips path).

**2d. The mix machinery (reuse Slice 3 ducking; add bed + SFX at master level).** Per-beat audio is
already narration + ducked music (`assembly/audio.rebuild_beat_audio`, sidechaincompress) — used now
that beats carry a cue. Add `assembly/audio.master_audio_finish(master, spec)`: over the joined master
audio, `amix` the **bed** (looped to length, low) + **SFX** (`adelay` to each `Sfx.at_s`), then
`loudnorm` + **`aresample=48000`** (the mandatory anti-96k-hiss step) → remux with the master video
(`-c:v copy`). Runs only when a bed/SFX exist (the lion `join_prebaked` path stays untouched). The
OUTPUT noise gate is the backstop (a hissy finish HARD-fails + is deleted).

**2e. Breathers — STRUCTURAL (Amendment 1; the primary acceptance criterion).** No narration change
(the VO is preserved) — this is an EDIT-level change to the TIMELINE. The binder inserts deliberate
music-only stretches where narration is ABSENT (not merely quieter):
- **Cold open:** a 3–5s beat0 of picture + score before the first word (a sourced establishing shot; no
  narration track on this beat → `build_beat_audio` renders score-only for it).
- **Per-transition breather:** at each beat boundary, a 3–5s music-only gap — implemented by giving each
  beat a short **trailing breather segment** (extra fitted picture time with NO narration under it) so
  the beat's video runs `narration_len + breather`, and the beat's audio is narration for the first
  part then score/bed alone for the breather. The narration mp3 is unchanged; the beat is simply LONGER
  than its narration by the breather. Sidechain ducking still applies under the spoken part; the
  breather is genuine silence-of-voice where score+bed carry the picture.
- **Music-led tail:** a closing breather after the last word into the `fade_out`.
Total added runtime ≈ cold-open + (n_beats−1)×breather + tail (~15–25s over the 157s VO) — this drives
the MEASURED timeline the cue lengths follow (Amendment 2). `build_beat_audio`/`rebuild_beat_audio` gain
a `breather_s` so a beat's audio = ducked narration+music for `narration_len`, then music(+bed) for the
breather; `build_beat_fitted` already fills any target duration, so the extra picture time is free.

**2f. SFX where the scene earns it (claim-safe).** The wolf earns ONE: a lone **howl** under beat4's
"howl at the edge of dark" (place it in a narration gap so it reads, not clashes). Source claim-safe:
ElevenLabs **sound-generation** (`POST /v1/sound-generation`, synthetic → claim-safe, one provider) —
**flag: verify the key's scope with a tiny pre-flight call (like TTS); if 401/403, either add scope
(human) or fall back to a Freesound CC0-only fetch**. Degrade gracefully: if SFX is unavailable, ship
score+bed+breathers and log the omission (never fail the film for a missing howl). Provenance logged.

---

## Part 3 — Accurate disclosure (reflect actual contents)
The disclosure is authored by `metadata/llm_writer.py`; today it hard-says "Narration and score are
AI-assisted…" even when there's no score. Drive it from a **contents manifest** the conductor passes
(narration: AI TTS; score + ambience: AI-generated; SFX: AI-generated or CC0; footage: licensed stock)
so the line states only what's actually present — e.g. "Narration, music and ambience are AI-generated;
sound effects and footage are licensed/CC-0 stock." The metadata guard still scrubs internal artifacts.

---

## Part 4 — Re-make the wolf to the documentary standard
`remake_from_narration` gains an audio-design stage: reuse the four preserved narration mp3s (**£0
TTS**); re-source footage through the curation gates (Part 1); generate the cues + bed (Part 2a–c);
bind with per-beat `MusicCue` + `audio_mix.bed`/`sfx`; density gate; assemble (per-beat ducked mix →
join → master audio finish); accurate disclosure; submit for approval. Pass A DryRun (no upload); Pass B
private upload only on Banks's word once it stands next to the lion.

---

## MUSIC CREDIT ESTIMATE (before generating — ElevenLabs Music @ 15 credits/second)
| Cue | Length | Credits |
|---|---|---|
| `theme` (beats 1,3) | ~45s | ~675 |
| `cold` (beat 2) | ~35s | ~525 |
| `dusk_swell` (beat 4) | ~30s | ~450 |
| `bed` (continuous) | ~40s | ~600 |
| **Total music/ambience** | **~150s** | **~2,250 credits** |
Plus SFX via sound-generation (if scope allows): ~1 short howl ≈ ~75–150 credits (else Freesound = 0).
**≈ 2,250–2,400 credits estimate; HARD CEILING 4,000 Music credits incl. retakes (Amendment 4)** —
cumulative generated credits are tracked and generation HARD-STOPS + reports on reaching 4,000. Cue
lengths follow the MEASURED timeline (Amendment 2), not this table (the table is a budgeting ceiling).
Marginal £ is subscription-covered (prepaid). Generation happens ONLY in Stage 2 after Stage 1 is green
and Banks says go. Credits reconcile against the live balance afterward.

## Files
**New:** `ytagent/music/{__init__,base,elevenlabs}.py`; `ytagent/sourcing/vision.py`;
`ytagent/sfx/…` or reuse the music provider for sound-generation. **Edited:** `sourcing/query.py`
(setting terms), `sourcing/rank.py` (negative filter), `sourcing/orchestrator.py`
(`source_clips_for_brief` calls the vision gate), `assembly/audio.py` (`master_audio_finish`),
`assembly/binder.py` (attach `MusicCue` + bed/sfx), `assembly/assembler.py` (call the finish when
bed/sfx present), `repo/ledger.py` (`write_music_cost`), `metadata/llm_writer.py` +
`metadata/description.py` (contents-manifest disclosure), `produce.py` (audio-design stage in
`remake_from_narration` + fresh `produce_video`), `scripts/prove_e2e.py`, `scripts/verify_e2e.py`.

## Verification
- **Offline (`verify_e2e`, zero network/spend):** the vision gate REJECTS the saved fence (t6) +
  coyote (t140) fixtures and PASSES a wild snowy wolf fixture (a FakeVisionLLM returning canned
  verdicts proves the wiring; a small live-gated check confirms real Haiku calibration); the negative
  filter drops a `fence`-tagged candidate; `master_audio_finish` on a fake narration+cue+bed yields a
  master with audio, correct duration, **noise gate PASS (48kHz)**; disclosure reflects a
  no-music vs full-audio manifest correctly. All prior verifies (density, Slice 1/3/4/5, Layer1) green.
- **Live re-make (gated, TWO-STAGE per Amendment 3):** **Stage 1** — curation + vision gate only, ZERO
  music spend: `ffprobe` the measured per-beat durations, source through the curation gates, print per
  beat whether `n_min` content-verified clips were reached WITH the vision verdicts (species/wild/season
  + reason). STOP and show Banks. **Stage 2** (only on Banks's go) — generate cues + bed (tracking
  cumulative credits against the 4,000 hard ceiling; hard-stop + report if reached), build the full
  audio, print the cue list + credits + audio layers + master QC + noise numbers + accurate disclosure.

## Expensive-to-retrofit (lock now)
1. Vision gate INSIDE sourcing (content-verified clips), not a post-hoc check.
2. Music/SFX providers mirror the TTS seam (swappable, `reconciled=False` estimate, noise-gated).
3. `MusicCue`/bed/SFX flow through the EXISTING spec fields + Slice-3 ducking — no spec redesign.
4. Master audio finish is an ADD-ON pass (lion `join_prebaked` path untouched).
5. Disclosure driven by a contents manifest (never a hard-coded line).

## Deliberately NOT in this slice
Per-shot-brief authoring; declared motif reuse; music that adapts to narration emotion; 9:16;
thumbnails; the budget governor. Keep it: curate footage, design the audio, re-make the wolf to stand
next to the lion.

## Human preconditions / decisions (flag for Banks)
- **Music scope:** confirmed present. **Sound-generation scope:** UNKNOWN — I'll pre-flight it; if
  blocked it's a human scope add or we use Freesound CC0 (SFX degrades gracefully either way).
- **Approve the ~2,250-credit Music estimate** before I generate anything.

## Conventions / safety
Channel-general (wolf = data; the standard is niche-agnostic). Synthetic/own audio only; every
generated cue + the bed + the finish pass through the noise gates (no audible broadband hiss — the
lion bed's failure is the precedent). Build/prove on the Mac; never touch the VPS/ocean stream.
Publishing + spending Telegram-gated; sourcing/generation/assembly autonomous within budget. Commit
locally; push only on the ship-word. Tag shell blocks `[ON YOUR MAC]`; no `#` lines; end chains with
`&& echo "OK…" || echo "FAILED…"`. **No code until Banks approves this plan.**
