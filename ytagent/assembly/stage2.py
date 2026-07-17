"""Stage 2 — beats → master.

`join_prebaked` is the lion REPRODUCTION path: the seven per-beat clips already carry their finished
mix (narration + music, roar in beat 6), so the master is just those beats crossfaded (xfade video +
acrossfade audio) with per-boundary overlaps, then mastered to −14 LUFS. Crossfade offsets are
computed from the MEASURED beat durations + the spec's per-boundary transition durations (the
documented 0.8s), so the run is faithful without re-deriving anything by hand.
"""
from __future__ import annotations

from . import ffmpeg


def _overlaps(spec) -> list[float]:
    """The 6 per-boundary crossfade durations (out_transition of beats 0..5)."""
    return [(b.out_transition.duration if b.out_transition else 0.0) for b in spec.beats[:-1]]


def join_prebaked(spec, dst: str) -> str:
    """xfade+acrossfade the beats' prebaked clips into a single mastered file at `dst`."""
    beats = spec.beats
    paths = [spec.resolve(b.prebaked) for b in beats]
    durs = [ffmpeg.probe(p)["duration"] for p in paths]
    overs = _overlaps(spec)
    tgt = spec.target

    fc: list[str] = []
    # normalize each input so xfade never trips on timebase / pixfmt / sample-rate mismatch
    for i in range(len(paths)):
        fc.append(f"[{i}:v]fps={tgt.fps},format=yuv420p,setsar=1,settb=AVTB[v{i}]")
        fc.append(f"[{i}:a]aformat=sample_rates=48000:channel_layouts=stereo,asetpts=N/SR/TB[a{i}]")

    # chain video with xfade and audio with acrossfade; offset = running length − overlap
    vprev, aprev = "[v0]", "[a0]"
    acc = durs[0]
    for i in range(1, len(paths)):
        o = overs[i - 1]
        off = acc - o
        vlbl, albl = f"[vx{i}]", f"[ax{i}]"
        curve = beats[i - 1].out_transition.curve if beats[i - 1].out_transition else "fade"
        fc.append(f"{vprev}[v{i}]xfade=transition={curve}:duration={o}:offset={off:.3f}{vlbl}")
        fc.append(f"{aprev}[a{i}]acrossfade=d={o}:c1=tri:c2=tri{albl}")
        vprev, aprev = vlbl, albl
        acc = off + durs[i]
    # master the crossfaded audio to the target loudness, then RESAMPLE BACK to the target rate:
    # loudnorm internally upsamples (emits 96k), which injects broadband high-freq hiss — force 48k.
    fc.append(f"{aprev}loudnorm=I={tgt.lufs}:TP={tgt.tp_dbfs}:LRA=11,aresample={tgt.asr}[aout]")

    args: list[str] = []
    for p in paths:
        args += ["-i", p]
    args += [
        "-filter_complex", ";".join(fc),
        "-map", vprev, "-map", "[aout]",
        "-c:v", tgt.vcodec, "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p",
        "-r", str(tgt.fps),
        "-c:a", tgt.acodec, "-b:a", f"{tgt.abitrate_k}k", "-ar", str(tgt.asr),  # belt + braces vs 96k
        "-movflags", "+faststart",
    ]
    return ffmpeg.run(args, dst=dst)
