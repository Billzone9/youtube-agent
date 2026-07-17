"""The general audio pipeline — narration + music (ducked) → mastered track.

Future videos won't have a pre-baked beat mix, so this rebuilds one: the music is ducked UNDER the
narration via `sidechaincompress` (never `aeval`), then mastered to the target loudness. Proven on
ONE beat (loudness compared to the baked beat's own audio); the lion reproduction never needs it.
"""
from __future__ import annotations

from . import ffmpeg


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
        f"[mix]loudnorm=I={tgt.lufs}:TP={tgt.tp_dbfs}:LRA=11[aout]"
    )
    args = [
        "-i", narr,
        "-stream_loop", "-1", "-t", f"{ndur}", "-i", music,   # loop music to cover the narration
        "-filter_complex", fc, "-map", "[aout]",
        "-c:a", tgt.acodec, "-b:a", f"{tgt.abitrate_k}k",
    ]
    return ffmpeg.run(args, dst=dst)
