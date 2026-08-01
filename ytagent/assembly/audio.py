"""The general audio pipeline — narration + music (ducked) → mastered track, plus a master-level
finish that layers an ambience bed + SFX over the whole film.

Per-beat: the music is ducked UNDER the narration via `sidechaincompress` (never `aeval`). A STRUCTURAL
breather (extra picture+score time after the narration, no voice) is produced by padding the narration
with trailing silence: during that silence the sidechain key is quiet, so the music naturally UN-DUCKS
back to full level — a genuine breath where the score carries, not a gain-lift under speech.

Master finish (`master_audio_finish`): over the joined master's audio, `amix` a crossfade-looped
ambience bed (low, felt-not-heard) + any SFX (`adelay` to each timestamp), then `loudnorm` +
`aresample=48000` (the mandatory anti-96k-hiss step) and remux with the master video (`-c:v copy`).
"""
from __future__ import annotations

from . import ffmpeg


def beat_total(spec, beat) -> float:
    """A beat's full audio length: narration length (or declared duration) + its breather."""
    if beat.narration:
        body = float(ffmpeg.probe(spec.resolve(beat.narration))["duration"])
    else:
        body = float(beat.duration or 0.0)
    return body + max(float(beat.breather_s or 0.0), 0.0)


def build_beat_audio(spec, beat, dst: str) -> str:
    """One beat's audio. Narration+music → the ducked mix + un-ducked breather (`rebuild_beat_audio`).
    Narration-only → narration at 48 kHz stereo (+ a silent breather tail if declared). WORDLESS beat
    (a cold open): score/ambience only for its declared `duration`, or pure silence if there is no music
    either. The master loudnorm does the −14 LUFS + aresample=48k."""
    tgt = spec.target
    if beat.narration and beat.music:
        return rebuild_beat_audio(spec, beat, dst)
    if beat.narration:
        breather = max(float(beat.breather_s or 0.0), 0.0)
        total = float(ffmpeg.probe(spec.resolve(beat.narration))["duration"]) + breather
        af = f"aformat=sample_rates=48000:channel_layouts=stereo,apad,atrim=0:{total:.3f},asetpts=N/SR/TB"
        args = ["-i", spec.resolve(beat.narration), "-af", af,
                "-c:a", tgt.acodec, "-b:a", f"{tgt.abitrate_k}k", "-ar", str(tgt.asr)]
        return ffmpeg.run(args, dst=dst)

    # WORDLESS beat — no narration; use the declared duration
    dur = float(beat.duration or 0.0)
    if dur <= 0:
        raise ValueError(f"beat {beat.name!r}: wordless beat needs a declared duration")
    if beat.music:                                   # score/ambience only, no ducking
        music = spec.resolve(beat.music.file)
        fc = (f"[0:a]aformat=sample_rates=48000:channel_layouts=stereo,volume={beat.music.in_db}dB,"
              f"atrim=0:{dur:.3f},asetpts=N/SR/TB[aout]")
        args = ["-stream_loop", "-1", "-t", f"{dur:.3f}", "-i", music, "-filter_complex", fc,
                "-map", "[aout]", "-c:a", tgt.acodec, "-b:a", f"{tgt.abitrate_k}k", "-ar", str(tgt.asr)]
        return ffmpeg.run(args, dst=dst)
    # pure silence of the declared length (score can be layered by the master audio finish later)
    args = ["-f", "lavfi", "-t", f"{dur:.3f}", "-i", f"anullsrc=r={tgt.asr}:cl=stereo",
            "-c:a", tgt.acodec, "-b:a", f"{tgt.abitrate_k}k", "-ar", str(tgt.asr)]
    return ffmpeg.run(args, dst=dst)


def rebuild_beat_audio(spec, beat, dst: str) -> str:
    """narration + (ducked) music → one mastered audio file for a single beat, incl. a trailing breather
    where the music un-ducks (the narration is padded with silence, so nothing keys the sidechain)."""
    if not beat.narration or not beat.music:
        raise ValueError(f"beat {beat.name!r} needs narration + music to rebuild audio")
    tgt = spec.target
    narr = spec.resolve(beat.narration)
    music = spec.resolve(beat.music.file)
    ndur = float(ffmpeg.probe(narr)["duration"])
    breather = max(float(beat.breather_s or 0.0), 0.0)
    total = ndur + breather
    music_db = beat.music.in_db

    fc = (
        # pad narration with trailing silence to the full beat length → the breather keys no ducking
        f"[0:a]aformat=sample_rates=48000:channel_layouts=stereo,apad,atrim=0:{total:.3f},"
        "asetpts=N/SR/TB[narr];"
        f"[1:a]aformat=sample_rates=48000:channel_layouts=stereo,volume={music_db}dB[musraw];"
        # duck the music under the narration; narration is the sidechain key (un-ducks in the breather)
        "[musraw][narr]sidechaincompress=threshold=0.05:ratio=8:attack=5:release=300[mus];"
        # both inputs are deliberately `total`s (narration padded, music looped) → longest = total;
        # 'first' would treat the narration's trailing silence as EOF and drop the breather.
        "[narr][mus]amix=inputs=2:duration=longest:normalize=0[mix];"
        # resample back to the target rate after loudnorm (it upsamples to 96k → broadband hiss)
        f"[mix]loudnorm=I={tgt.lufs}:TP={tgt.tp_dbfs}:LRA=11,aresample={tgt.asr}[aout]"
    )
    args = [
        "-i", narr,
        "-stream_loop", "-1", "-t", f"{total:.3f}", "-i", music,   # loop music across narration+breather
        "-filter_complex", fc, "-map", "[aout]",
        "-c:a", tgt.acodec, "-b:a", f"{tgt.abitrate_k}k", "-ar", str(tgt.asr),
    ]
    return ffmpeg.run(args, dst=dst)


def _crossfade_loop_lines(idx0: int, n: int, xf: float, out_label: str) -> list[str]:
    """Filter lines that acrossfade `n` identical bed inputs (indices idx0..idx0+n-1) into one seamless
    stream `out_label` — no hard-cut loop seam. n==1 → a passthrough."""
    lines: list[str] = []
    prev = f"[{idx0}:a]aformat=sample_rates=48000:channel_layouts=stereo[bl0]"
    lines.append(prev)
    cur = "[bl0]"
    for i in range(1, n):
        nxt = f"[nb{i}]"
        lines.append(f"[{idx0 + i}:a]aformat=sample_rates=48000:channel_layouts=stereo{nxt}")
        lbl = out_label if i == n - 1 else f"[bx{i}]"
        lines.append(f"{cur}{nxt}acrossfade=d={xf}:c1=tri:c2=tri{lbl}")
        cur = lbl
    if n == 1:
        lines[-1] = f"[{idx0}:a]aformat=sample_rates=48000:channel_layouts=stereo{out_label}"
    return lines


def master_audio_finish(spec, master: str, dst: str, *, bed: str | None, bed_db: float = -30.0,
                        sfx: tuple = (), xf: float = 3.0) -> str:
    """Layer a crossfade-looped ambience `bed` (low) + `sfx` (each `adelay`ed to its `at_s`) over the
    joined master's audio, then loudnorm + aresample=48k, remuxing with the master video (`-c:v copy`).
    Runs only when a bed and/or SFX exist; otherwise the caller keeps the join_prebaked master as-is."""
    tgt = spec.target
    D = float(ffmpeg.probe(master)["duration"])

    args = ["-i", master]
    fc: list[str] = []
    mix_labels = ["[m0]"]
    fc.append(f"[0:a]aformat=sample_rates=48000:channel_layouts=stereo[m0]")

    next_idx = 1
    if bed:
        bed_len = float(ffmpeg.probe(bed)["duration"])
        step = max(bed_len - xf, 1.0)
        n = 1 if bed_len >= D else min(40, int((D - bed_len) / step) + 2)   # copies to span D (cap 40)
        for _ in range(n):
            args += ["-i", bed]
        fc += _crossfade_loop_lines(next_idx, n, xf, "[bedloop]")
        fc.append(f"[bedloop]atrim=0:{D:.3f},asetpts=N/SR/TB,volume={bed_db}dB[bedout]")
        mix_labels.append("[bedout]")
        next_idx += n

    for j, s in enumerate(sfx):
        args += ["-i", spec.resolve(s.file)]
        delay_ms = int(max(float(s.at_s), 0.0) * 1000)
        fc.append(f"[{next_idx}:a]aformat=sample_rates=48000:channel_layouts=stereo,"
                  f"volume={s.level_db}dB,adelay={delay_ms}|{delay_ms}[sfx{j}]")
        mix_labels.append(f"[sfx{j}]")
        next_idx += 1

    fc.append(f"{''.join(mix_labels)}amix=inputs={len(mix_labels)}:duration=first:normalize=0[premix];"
              f"[premix]loudnorm=I={tgt.lufs}:TP={tgt.tp_dbfs}:LRA=11,aresample={tgt.asr}[aout]")

    args += [
        "-filter_complex", ";".join(fc),
        "-map", "0:v", "-map", "[aout]",
        "-c:v", "copy", "-c:a", tgt.acodec, "-b:a", f"{tgt.abitrate_k}k", "-ar", str(tgt.asr),
        "-movflags", "+faststart",
    ]
    return ffmpeg.run(args, dst=dst)
