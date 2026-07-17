# Slice 3 — Assembly (reproduce the lion edit as an automated job; multi-format ready)

## Context
The lion film was hand-assembled from footage with FFmpeg; the executable build scripts were
ephemeral (scratchpad) and are gone. Slice 3 turns assembly into an **automated, channel-general
job**: consume a declarative timeline (an EditSpec, stored as DATA) + on-disk assets and render a
video whose QC matches the locked reference `assets/lion-doc-01/output/lion-doc-01_scored.mp4`
(1920×1080, 24fps, 394.783s, −13.8 LUFS, −0.5 dBFS, 368,842,754 bytes — recorded in
`ytagent/artifacts.py` `lion_video_meta()`). Design for **multiple formats/aspect ratios** (16:9
long-form now, 9:16 Shorts-ready — §14.4). Thinnest provable version first, assembling from the
assets already on disk (no TTS/sourcing — those are other slices). The lion film is the reference
OUTPUT to match; it is **never altered** — output goes to a NEW filename.

## Ground truth (verified by ffprobe — corrects the recon)
- **The 7 per-beat clips already carry a full mixed audio track** (AAC; narration + music, roar in
  beat 6), NOT silent. Durations: beat1_v3 52.04 / beat2 64.33 / beat3 64.50 / beat4_v2 61.50 /
  beat5 64.58 / beat6_v2 45.50 / beat7 46.75 s. So the reproduction needs **no audio rebuild**.
- **The master = the 7 beats crossfaded.** Σ beat durations 399.21s − master 394.78s = **4.43s** across
  6 transitions (accumulating overlap → stacked `xfade`/`acrossfade`). Per-boundary crossfades are
  recovered by **scene-detecting the real beat starts** in `_scored.mp4` (don't trust the rounded
  chapter marks 0/51/114/178/239/303/347) and solving for the 6 offsets.
- **This Mac is 8-core Apple Silicon (M1 Pro)** — the 2-core limit is the VPS, which assembly never
  touches. Big xfade filtergraphs are fine; stage them for clarity/generation-loss, not CPU.
- FFmpeg 8.1.2 has xfade, acrossfade, zoompan, crop, scale, loudnorm, sidechaincompress, overlay,
  **libvmaf** (objective similarity available). **No `drawtext`** → title cards are Pillow→PNG→
  `overlay` (Pillow 12.2.0 is in `.venv`). Reusable primitives: `asset_builder/build_master.sh`
  (cover-then-crop `scale=W:H:force_original_aspect_ratio=increase,crop=W:H` → concat → loudnorm),
  `asset_builder/build_audio.sh` (bed via anoisesrc + `volume` sine swell + loudnorm).
- Reference = `_scored.mp4` (the beats carry music, so joining them reproduces the SCORED master; the
  synthetic `savanna_bed.wav` "jet-engine hiss" is almost certainly NOT in it → bed default OFF).

## Architecture — `ytagent/assembly/` (channel-general; the lion is DATA)
- **`spec.py`** — the EditSpec model + JSON load/validate (frozen dataclasses `Target, Clip,
  Transition, MusicCue, Sfx, AudioMix, TitleCard, Beat, EditSpec`); `load_spec(path)`;
  `EditSpec.for_format(fmt) -> EditSpec` (the format seam — swaps `Target`, applies per-clip focus).
- **`ffmpeg.py`** — the ONLY place that shells out; enforces the CLAUDE rules structurally:
  `run(args, *, dst)` writes `dst.tmp` then `os.replace` + asserts size>0; `probe(path)` (ffprobe
  JSON→dict); pure, unit-testable filtergraph builders `crop_to_format(sw,sh,tw,th,focus)`,
  `zoompan_expr(effect,frames)`, `normalize_clip(clip,target)`. Never `aeval`; swells via `volume`
  sine, never `tremolo`.
- **`stage1.py`** — `build_beat(beat, target, workdir) -> path`: raw clips → one normalized beat
  (per-clip normalize + effect → intra-beat xfade). The general video path (future videos).
- **`stage2.py`** — beats → master, two separately-runnable entrypoints: **`join_prebaked(spec,
  beat_paths, dst)`** (xfade+acrossfade beats that already carry audio — the lion reproduction path)
  and `mux_master(spec, video_track, audio_track, dst)` (general path).
- **`audio.py`** — the general audio pipeline (built, proven on ONE beat, NOT on the lion critical
  path): `concat_narration`, `build_music_bed`, `duck(narr, music)` (sidechaincompress),
  `place_sfx`, `master_loudnorm(src, target=-14)`.
- **`qc.py`** — `measure(path) -> dict` (SHAPE-IDENTICAL to `lion_video_meta()` + real sha256
  `checksum` — the comment in artifacts.py says checksum is "deferred to the assembly slice"; this is
  it); `integrated_loudness` (ebur128 meter, honest), `noise_floor_db` (highpass 8k + volumedetect),
  `compare(measured, reference, tol) -> QCResult`, `vmaf(candidate, reference)`.
- **`titlecard.py`** — optional `render_card(text,target,style)` (Pillow transparent PNG) +
  `overlay_fragment`. Not required for the proof.
- **`provenance.py`** — `asset_id_from_filename`, `source_url(id, source)`, `build_provenance(spec)`
  → per-clip records (beat, filename, source, url, licence, contributor). INTERNAL record only.
- **`assembler.py`** — `assemble(spec_path, *, fmt="16:9", from_stage="beats"|"clips", dst) ->
  AssemblyResult{qc, provenance, output_path, comparison}`.

## The EditSpec schema (DATA, at `assets/lion-doc-01/edit_spec.json`)
Format-aware; the fields below are the ones expensive to retrofit for 9:16:
- **`targets` as a MAP** (`"16:9"`/`"9:16"` → w,h,fps,lufs,tp_dbfs,vcodec,acodec) — format is a
  first-class axis, not a hardcoded 1920×1080.
- **beats**: `prebaked` path (Stage-2 fast input), `narration`, `music` {file,in_db,fade_in,fade_out},
  ordered `clips`, and **`out_transition` per boundary** {type,curve,duration} — NOT a global xfade
  constant (needed to reproduce the accumulating overlap + hit chapter marks).
- **per-clip `focus` keyed by format** (`{"16:9":[fx,fy], "9:16":[fx,fy]}`, normalized focal point) —
  `crop_to_format` = `crop=ow:oh:(iw-ow)*fx:(ih-oh)*fy`. Center-crop throws the lion out of a 9:16
  frame; focal points can't be retrofitted without re-authoring every clip. **#1 retrofit risk.**
- **`audio_mix`** modeled independently of the baked beats (narration/music levels, `duck`
  threshold/ratio/attack/release, `include_bed` bool=false, bed path) — so future videos (no baked
  beats) can rebuild an equivalent mix.
- **`sfx`** (file, beat, at_s, level_db); **`title_card`** null (optional).

## Thinnest proof (what Banks judges)
- **GATE — reproduction (Stage-2 only):** `join_prebaked` → xfade+acrossfade the 7 existing beat
  clips with per-boundary crossfades (calibrated by scene-detecting the real beat starts in
  `_scored.mp4`) → `loudnorm` −14 → `assets/lion-doc-01/output/lion-doc-01_assembled.mp4` (NEW file;
  the locked `_scored.mp4` is untouched). Verify QC vs the reference within tolerance, incl. **VMAF ≥
  90** vs `_scored.mp4` (same source frames → expect near-perfect) and **beat-boundary timestamps
  aligned within ±1s** (a real structural check, not vibes). Banks A/Bs the two files.
- **Capability proofs (ONE beat each, cheap, NOT gating):** (a) **Stage-1** raw clips → `beat1` via
  `crop_to_format`+`zoompan`+intra-beat xfade, compared to `beat1_v3.mp4` by SSIM/VMAF + QC (proves
  the raw→beat path future videos need); (b) **general audio** rebuild of beat1's audio from
  `narration/beat1.mp3` + `music/main_theme.mp3` (duck), QC-compare loudness to the baked mix;
  (c) **9:16** render of that one demo beat at 1080×1920 via `focus["9:16"]` (proves the
  format-general path end-to-end, no Shorts pipeline).

## Multi-format crop math (§14.4)
Cover-then-crop with a focal offset (not hardcoded center): 16:9-from-vertical → scale to cover
width, crop at `y=(ih-oh)*fy` (fy<0.5 keeps head/sky); 9:16-from-landscape → scale to cover height,
crop at `x=(iw-ow)*fx` (fx mandatory for off-centre subjects); 9:16-from-native-vertical → direct
scale, no crop. Only `focus` + `targets` must exist now; Shorts scheduling/duration caps do not.

## QC + tolerances
Measure via ffprobe (duration/w/h/fps/audio-present), ebur128 (integrated LUFS + true peak),
highpass-8k+volumedetect (noise floor), sha256 (checksum), libvmaf (similarity). "Matches reference":
w×h exact (1920×1080) · fps exact (24) · duration ±1.0s (ref 394.783) · loudness within ±0.5 of −14 ·
peak < 0 (require ≤ −1.0 to match loudnorm TP) · audio present · noise floor (>8kHz) ≤ −30 dB ·
VMAF vs `_scored` ≥ 90 (prebaked join). Report the noise-floor number every render (mandatory).

## Honest reproduction framing
Byte-exact reproduction is impossible (ephemeral scripts gone; ffmpeg non-deterministic; exact
per-boundary crossfades + mix levels unknown). The bar is: **same structure (7 beats, 6 crossfades,
chapter marks within ±1s) + QC within tolerance + VMAF ≥ 90 + Banks's A/V review; the locked
`_scored.mp4` is never altered; output goes to a NEW filename.**

## Integration (minimal now; defer the rest)
No migration — `jobs.stage` already allows `'assemble'` and `videos` carries the full QC payload.
Minimal: `orchestrator.record_assembly(conn, *, channel, result)` — one txn creates
`jobs(type='assemble', stage='assemble')`, runs the assembler OUTSIDE a held txn (the Phase-2 pattern
from `handle_decision`, since ffmpeg is multi-minute), persists a `videos` row from `result.qc` +
`provenance_ref`, records `assembly_started`/`assembly_completed` events. This produces the GENERATED
internal payload that **replaces the hardcoded `lion_video_meta()`**, and it flows straight into the
existing `submit_video_for_approval(video_meta=...)` (same dict shape) → Slice-5 description → Slice-
1/2 approval/publish. **Defer:** a job worker/queue, auto-trigger from sourcing/TTS slices, the
multi-format render matrix, Shorts scheduling, and Telegram `assemble` wiring. The proof is a direct
CLI (`scripts/prove_slice3.py`), no bot, no queue.

## Files
**New:** `ytagent/assembly/{__init__,spec,ffmpeg,stage1,stage2,audio,qc,titlecard,provenance,
assembler}.py`; `assets/lion-doc-01/edit_spec.json` (the lion timeline as DATA);
`scripts/prove_slice3.py` (renders the assembled master + prints QC/VMAF vs reference);
`scripts/verify_slice3.py` (OFFLINE zero-render logic: spec load/validate, filtergraph string
builders, `crop_to_format` math for 16:9 AND 9:16, `for_format`, provenance filename→URL, QC
tolerance comparison against a fixture). **Edited (light):** `ytagent/orchestrator.py`
(`record_assembly` seam); `ytagent/artifacts.py` (kept as the reference payload the assembler's QC is
compared against — the hardcoded values become the comparison target, then future videos use the
generated payload).

## Verification
- **Offline (`scripts/verify_slice3.py`, zero render, fast):** spec loads + validates; `crop_to_format`
  produces correct crop expressions for both formats; `for_format` derives the 9:16 target + focus;
  provenance derives the right Pexels/Pixabay URLs from filenames; QC `compare` passes/fails against a
  fixture at the tolerances. ALL PASSED.
- **Live proof (`scripts/prove_slice3.py`, local FFmpeg, ZERO API spend):** the GATE (join_prebaked →
  `lion-doc-01_assembled.mp4`, QC + VMAF + boundary-alignment vs `_scored.mp4`), then the 3 one-beat
  capability proofs (Stage-1 vs beat1_v3 SSIM/VMAF; general-audio loudness compare; 9:16 beat). Prints
  a QC table and the VMAF number. Existing Slice 1 / Layer 1 / Slice 5 verifies stay green.

## Expensive-to-retrofit (locked)
1. **Per-clip `focus` focal point keyed by format** (else 9:16 = re-author every clip).
2. **`targets` as a map / format as a first-class axis** (beats, QC, outputs keyed by format).
3. **Audio graph modeled as DATA independent of the baked beats** (levels, duck, include_bed, sfx).
4. **Per-boundary transition model** (duration+curve+offset), not a global xfade constant.
5. **QC payload shape ≡ `lion_video_meta()`, measured + sha256, with a provenance list** (the DB seam
   retiring the hardcoded payload).
6. **Two separately-runnable stages with a stable normalized-beat intermediate** (`from_stage`).
7. **Title card as an optional overlay field** (Pillow PNG), never required.

## Deliberately NOT in this slice
Rebuilding the full audio mix on the lion critical path (the baked beats already carry it); a job
worker/queue; auto-triggering assembly; the multi-format render matrix + Shorts scheduling; Telegram
`assemble` wiring; a burned-in title card (optional, off by default); re-deriving all 7 beats' exact
hand-tuned Stage-1 params (lost; the on-disk beat clips are the trusted Stage-1 outputs).

## Conventions / safety
Channel-general (lion is data; nothing niche in code). Add only this slice's stack (FFmpeg via
subprocess; Pillow already present) — **zero API spend, local only**. Never alter the locked
`_scored.mp4`; build to temp → `os.replace`; verify by measurement + byte-count; obey the
aeval/tremolo/−14 LUFS/noise-check rules. Never touch the VPS or ocean stream. Commit locally only
(no push). Tag command blocks `[ON YOUR MAC]`; no `#` lines in shell blocks; end chains with
`&& echo "OK..." || echo "FAILED..."`.
