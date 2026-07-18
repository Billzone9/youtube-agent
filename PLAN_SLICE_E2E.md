# End-to-end production — the two missing links (TTS + binder), one video made whole

## Context
Five slices exist (spine+gate, publishing, assembly, LLM writer, sourcing) but the production LINE has
two gaps: nothing turns a script's words into narration audio (TTS), and nothing turns a written
script + its sourced clips into the assembler's EditSpec (the binder). Also — verified while planning
— the assembler's **clips path currently HARD-FAILS** (`stage1.build_beat` renders `-an`;
`stage2.join_prebaked` demands an audio stream per input → "Stream specifier ':a' matches no
streams"): it has never produced a master. This slice builds TTS + the binder + wires the clips path
to carry real audio, then runs the whole chain — **writer → sourcing → TTS → binder → assembly →
Telegram approval → private upload** — to make ONE complete NEW video. Topic chosen for real library
coverage (the penguin/BACKLOG lesson).

## Topic — coverage-probed (I ran live searches; pick at approval)
Landscape ≥1080p, subject-in-metadata: **grey wolf** 30 (forest 25, snow 16) · **red fox** 27
(fox-snow 30, fox-forest 26) · **elephant** 35–37 (herd 21, savanna 8). All far above penguin's ~1.
**Recommended: grey wolf** — strong subject + scene coverage, suits the reverent house voice (like the
lion); fox/elephant are fine alternates.

## Human precondition (flag for Banks) — the Music→TTS key scope
Banks's ElevenLabs key is **Music-scoped** by design (structural spend control). TTS needs a
**deliberate manual scope addition** (or, better, a new least-privilege TTS-scoped key with its own
cap) in the ElevenLabs dashboard — a spend-capability change, which is human-only. Until then
`synthesize` returns 401/403 → `TTSScopeError` and the live proof can't run (the offline verify still
runs). Also needed: **David's `voice_id`** (a config value Banks supplies).

## TTS — new package `ytagent/tts/` (NOT bolted onto providers/, which is LLM-token-shaped)
- `base.py` — `TTSResult{path, characters, model, voice_id, request_id}`; `TTSUnavailable` (no key),
  `TTSScopeError` (401/403 — the Music-scope case); `TTSProvider` Protocol
  `synthesize(text, *, voice_id, dst, model) -> TTSResult`.
- `elevenlabs.py` — httpx `POST https://api.elevenlabs.io/v1/text-to-speech/{voice_id}?output_format=
  mp3_44100_128`, header `xi-api-key`, body `{text, model_id, voice_settings}`; atomic temp→`os.replace`
  (mirror `ffmpeg.run`). 401/403 → `TTSScopeError`.
- `__init__.py` — `get_tts_provider(settings) -> TTSProvider | None` (None w/o key → honest degradation).
- **config** (`ytagent/config.py`): optional `elevenlabs_api_key` + `elevenlabs_configured` in
  `safe_summary` (`ELEVENLABS_API_KEY` already in `.env`, unwired). **seed** (`ytagent/seed.py`
  WILDLIFE_CONFIG): add `voice_id` + `model` to `voice_profile` (default model the STABLE
  `eleven_multilingual_v2`; `eleven_v3` is alpha and may 422 — configurable, not hard-coded).
- **cost** (`ytagent/repo/ledger.py`): `write_tts_cost(conn, *, channel_id, job_id, characters,
  credits_est, amount_gbp_est, request_id, model, voice_id)` → `cost_ledger` category
  `ai_generation`, provider `"ElevenLabs TTS"`, **`reconciled=False`**, `metadata={estimate:true,
  characters, credits}`, idempotency `tts:{job_id}:{beat_name}`. ElevenLabs bills **asynchronously**
  (CLAUDE.md) — the per-call row is an unreconciled ESTIMATE a later balance pass settles. Do NOT
  reuse `write_llm_cost` (Anthropic/token-specific).
- **noise:** `qc.check_source_clean` each narration mp3 in the conductor before the render (cheap;
  the master output gate is the backstop).

## The clips-path audio fix (core assembly work; reuse `join_prebaked` unchanged)
- **`stage1.build_beat_fitted(spec, beat, dst, *, duration)`** — fill exactly `duration`s: clip ≥
  duration → trim (today's behaviour); `duration/clip ≤ ~1.4` → slow via `setpts=PTS*f` (imperceptible
  on slow wildlife); else **xfade-loop** N=⌈duration/clip⌉ times through the EXISTING intra-beat xfade
  chain (crossfaded seams, not hard cuts) then trim the tail. (Single-clip-per-beat looping is the
  main visual weakness → keep beats SHORT ~15–25s; multi-clip-per-beat is the #1 deferrable.)
- **`audio.build_beat_audio(spec, beat, dst)`** — NEW narration-only builder (`rebuild_beat_audio`
  can't: it mandates music): `[0:a]aformat=sample_rates=48000:channel_layouts=stereo` → AAC 48k, no
  per-beat loudnorm (the master `join_prebaked` loudnorm does −14 LUFS + `aresample=48000`, the
  no-broadband-noise fix). Duration = narration length (authoritative).
- **`assembler`**: split `assemble` into a thin loader + core **`assemble_spec(spec: EditSpec, *, dst,
  fmt, reference, provenance_ref, workdir) -> AssemblyResult`** (in-memory, no JSON round-trip).
  Rewrite `_build_from_clips`: per beat `ndur = ffmpeg.probe(narration)["duration"]`;
  `build_beat_fitted(duration=ndur)` → video; `build_beat_audio` → audio; **mux** (`-c:v copy -c:a
  copy -shortest`) → beat-with-audio; `replace(beat, prebaked=that)`; `stage2.join_prebaked` (offsets
  from MEASURED durations → narration is the single source of beat duration; master runtime = Σ
  narration − Σ overlaps). All existing gates (input + output noise, 48k) apply.
- **Music: narration-only FIRST** (avoids a second ElevenLabs scope/spend; the music seam —
  `MusicCue`/`AudioMix`/`rebuild_beat_audio` — is a follow-up flip, not a rebuild).

## The binder — `ytagent/assembly/binder.py`
`bind_edit_spec(script, sourced: dict[int, SourcedAsset], narration: dict[int, str], *, target) ->
EditSpec`: per beat `Beat(name=f"beat{b.index}", clips=(to_clip(asset, approx_seconds=b.approx_seconds),),
narration=<mp3>, music=None, out_transition=Transition("xfade","fade",0.8))`; `source="clips"`,
`targets={"16:9": Target(1920,1080,fps=24,...)}`, `fade_in=1.5`, `fade_out=2.0`. **In-memory** EditSpec
with ABSOLUTE asset paths (`EditSpec.resolve` returns them unchanged); may also serialize to
`workdir/edit_spec.json` as a debug/provenance artifact. `to_clip`'s `trim_out=min(dur, approx_seconds)`
is a source cap only — the FITTER owns the measured duration.

## The produce conductor — `ytagent/produce.py`
`async produce_video(conn, notifier, *, channel, topic, providers, tts, llm_provider, script_writer,
publisher, chat_id, runtime_target_s=150, n_beats=4, workdir, publish_mode) -> dict`:
1. `jobs.create(type="produce", stage="produce")` + `produce_started` event.
2. **Script** (autonomous): `script_writer.write(topic, channel, research=UnavailableResearch(),
   runtime_target_s, n_beats)`; drain LLM usage → `write_llm_cost`.
3. **Source ALL beats** (autonomous, free): `source_for_brief` per `b.shot_brief`; **any `NoMatch` →
   raise `ProductionError` listing unmatched briefs — BEFORE any TTS spend** (source-all-then-spend;
   never drop a beat).
4. **TTS ALL beats** (autonomous, within budget): `script.to_narration()` (`beat{index}`→clean prose)
   → `tts.synthesize(...)`; `check_source_clean` each mp3; `write_tts_cost`.
5. **Bind** → in-memory `EditSpec`.
6. **Assemble** OUTSIDE any held txn (`asyncio.to_thread(assemble_spec, ...)`, multi-minute; gates
   apply) → `AssemblyResult`; `video_meta = result.qc`. (Three-phase pattern from `record_assembly`.)
7. **Description** (autonomous): `LLMWriter(llm_provider).write(video={topic, facts})` →
   `generate_description` → `Description` (no chapters for a fresh cut); drain LLM cost.
8. **Submit**: `submit_video_for_approval(conn, notifier, channel=…, video_meta=…, description=…,
   chat_id=…, publish_mode=publisher.mode, metadata_source="produce")` — the **Telegram gate**;
   completion ping. Steps 2–7 autonomous within budget; **8 opens the human gate**; the private upload
   happens only later in `handle_decision` on approve.

## The upload (reuses Slice 2, no change)
Pass a live `YouTubePublisher` + `publish_mode="live"`. `qc.measure` is shape-identical to
`lion_video_meta()` → slots into `submit_video_for_approval` unchanged; privacy is `PRIVATE` structural;
`containsSyntheticMedia=True` set; description has no chapters (fresh cut — `assemble_description`
omits the block; `LLMWriter._author_chapters` returns None without `video["beats"]`). Follow-up: pass
measured per-beat offsets so the LLM authors real chapter labels.

## Files
**New:** `ytagent/tts/{__init__,base,elevenlabs}.py`; `ytagent/assembly/binder.py`; `ytagent/produce.py`;
`scripts/verify_e2e.py` (offline); `scripts/prove_e2e.py` (live, gated). **Edited:**
`ytagent/assembly/assembler.py` (split `assemble_spec` + rewrite `_build_from_clips` to beats-with-
audio); `ytagent/assembly/stage1.py` (`build_beat_fitted`); `ytagent/assembly/audio.py`
(`build_beat_audio`); `ytagent/config.py` (`elevenlabs_api_key` + `_configured`); `ytagent/seed.py`
(`voice_id`/`model` in voice_profile); `ytagent/repo/ledger.py` (`write_tts_cost`); `.env.example`
(ELEVENLABS_API_KEY); `telegram_bot/requirements.txt` (httpx already pinned).

## Verification
- **Offline (`scripts/verify_e2e.py`, zero network/spend):** a FAKE TTS writes a clean lavfi mp3 of
  known duration per beat; a FAKE sourced clip is a lavfi mp4 deliberately SHORTER than the narration
  (exercises the loop/fit). Run `bind_edit_spec` → `assemble_spec` (clips path). Assert: valid
  `source="clips"` EditSpec; **each built beat has an audio stream** (`probe["has_audio"] is True` —
  proves the master isn't silent/failing); master loudness in band + `noise_gate` **PASS** (48kHz,
  clean — the loudnorm→96k trap avoided); master `duration_s ≈ Σ narration − Σ overlaps`
  (within `QCTolerance`); a `NoMatch` injected for one beat raises `ProductionError` BEFORE any TTS
  call. All existing verifies (Slice 1/Layer1/3/4/5) stay green.
- **Live (`scripts/prove_e2e.py`, gated behind the keys + TTS scope):** Pass A — `produce_video(…,
  publisher=DryRunPublisher())` on WOLF: full pipeline (real script LLM + real sourcing (downloads
  free) + real TTS + real assemble), print master path + QC + authored Description + month-to-date;
  NO upload. Pass B (gated) — `publisher=YouTubePublisher(…)`, `publish_mode="live"` → Telegram
  approval card → on Banks's YES, `handle_decision` performs the real **PRIVATE** upload. The one live
  spend/publish gate.

## Expensive-to-retrofit (locked)
1. **In-memory `assemble_spec(spec_obj)`** (split `assemble`); binder emits an in-memory EditSpec with
   absolute paths — avoids a JSON round-trip in every caller.
2. **Narration is the single authoritative beat duration** threaded measured-TTS → `build_beat_fitted`
   → `join_prebaked` offsets.
3. **Clip-fit primitive** (trim / slow / xfade-loop) — the loop-seam reuse is hard to change once beats bake.
4. **Narration-only audio is a NEW builder**, not `rebuild_beat_audio` (which mandates music).
5. **TTS cost = `ai_generation` / "ElevenLabs TTS" / `reconciled=False` estimate** (async billing).
6. **NoMatch fails the whole production BEFORE TTS spend** (source-all-then-spend ordering).
7. **`voice_id` in voice_profile + `elevenlabs_api_key` + the Music→TTS scope as a human precondition.**

## Deliberately NOT in this slice
Music score generation (a 2nd ElevenLabs scope/spend; seam exists); multi-clip-per-beat (the real fix
for looping — later); 9:16 Shorts (the axis exists); MLA/localization; thumbnails; chapters on the
fresh cut (follow-up via measured beat offsets); budget-governor enforcement (§4.10). Keep the first
proof a 4-beat ~2–2.5 min narration-only 16:9 WOLF video, real private upload on approval.

## Conventions / safety
Channel-general (topic is data; nothing niche in code). Reuse the prior seams; add only TTS + binder +
clips-audio wiring + the thin conductor. Secrets via `.env`, never printed. No audible broadband noise
(gates apply). Build/prove on the Mac; never touch the VPS/ocean stream. Publishing + spending are
Telegram-gated; scripting/sourcing/TTS/assembly are autonomous within budget. Commit locally; push
only on the ship-word. Tag command blocks `[ON YOUR MAC]`; no `#` lines in shell blocks; end chains
with `&& echo "OK..." || echo "FAILED..."`.
