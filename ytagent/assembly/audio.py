"""The general audio pipeline — narration + music (ducked) → mastered track.

Future videos won't have a pre-baked beat mix, so this rebuilds one: the music is ducked UNDER the
narration via `sidechaincompress` (never `aeval`), then mastered to the target loudness. Proven on
ONE beat (loudness compared to the baked beat's own audio); the lion reproduction never needs it.
"""
from __future__ import annotations

from . import ffmpeg


def build_beat_audio(spec, beat, dst: str) -> str:
    """One beat's audio. Narration+music → the ducked mix (`rebuild_beat_audio`). Narration-only → the
    narration at 48 kHz stereo. WORDLESS beat (a cold open, no narration): score/ambience only with NO
    ducking (nothing to duck under), or pure silence if there is no music either — its length is the
    beat's declared `duration`. The master `join_prebaked` loudnorm does the −14 LUFS + aresample=48k."""
    tgt = spec.target
    if beat.narration and beat.music:
        return rebuild_beat_audio(spec, beat, dst)
    if beat.narration:
        args = ["-i", spec.resolve(beat.narration),
                "-af", "aformat=sample_rates=48000:channel_layouts=stereo",
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
    """narration + (ducked) music → one mastered audio file for a single beat."""
    if not beat.narration or not beat.music:
        raise ValueError(f"beat {beat.name!r} needs narration + music to rebuild audio")
    tgt = spec.target
    narr = spec.resolve(beat.narration)
    music = spec.resolve(beat.music.file)
    ndur = ffmpeg.probe(narr)["duration"]
    music_db = beat.music.in_db

    fc = (
        "[0:a]aformat=sample_rates=48000:channel_layouts=stereo[narr];"
        f"[1:a]aformat=sample_rates=48000:channel_layouts=stereo,volume={music_db}dB[musraw];"
        # duck the music under the narration; narration is the sidechain key
        "[musraw][narr]sidechaincompress=threshold=0.05:ratio=8:attack=5:release=300[mus];"
        "[narr][mus]amix=inputs=2:duration=first:normalize=0[mix];"
        # resample back to the target rate after loudnorm (it upsamples to 96k → broadband hiss)
        f"[mix]loudnorm=I={tgt.lufs}:TP={tgt.tp_dbfs}:LRA=11,aresample={tgt.asr}[aout]"
    )
    args = [
        "-i", narr,
        "-stream_loop", "-1", "-t", f"{ndur}", "-i", music,   # loop music to cover the narration
        "-filter_complex", fc, "-map", "[aout]",
        "-c:a", tgt.acodec, "-b:a", f"{tgt.abitrate_k}k", "-ar", str(tgt.asr),
    ]
    return ffmpeg.run(args, dst=dst)
