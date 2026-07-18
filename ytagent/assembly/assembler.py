"""Assembly orchestration — the channel-general entrypoint.

`assemble()` renders a master from an EditSpec (in a chosen format, from beats or from clips),
measures it (a QC dict shaped like `artifacts.lion_video_meta()` + provenance), and — when given a
reference — compares within tolerance. The caller decides `dst` (never the locked reference file).
"""
from __future__ import annotations

import os
import time
from dataclasses import dataclass, field

from . import audio, ffmpeg, provenance, qc, stage1, stage2
from .spec import load_spec


class AssemblyNoiseError(RuntimeError):
    """A source (input gate) or the render (output gate) carried audible broadband noise. HARD fail:
    no dirty output is ever kept (house rule — CLAUDE.md 'no audible broadband noise, ever')."""


@dataclass
class AssemblyResult:
    output_path: str
    qc: dict
    provenance: list = field(default_factory=list)
    comparison: qc.QCResult | None = None
    noise: dict = field(default_factory=dict)          # multi-band report, logged every render
    noise_gate: qc.QCResult | None = None
    duration_render_s: float = 0.0
    ok: bool = True


def _build_from_clips(spec, dst: str, workdir: str) -> str:
    """Build each beat as a real A/V clip — video FITTED to its narration length + narration audio,
    muxed — then join via the proven stage-2 path (xfade + acrossfade + loudnorm + 48k). Narration is
    the single source of beat duration; the master runtime = Σ narration − Σ crossfade overlaps."""
    from dataclasses import replace as dc_replace

    tag = spec.active_format.replace(":", "x")
    beat_paths = []
    for b in spec.beats:
        if not b.narration:
            raise ValueError(f"beat {b.name!r}: clips path needs narration (its duration drives the beat)")
        ndur = ffmpeg.probe(spec.resolve(b.narration))["duration"]
        vid = os.path.join(workdir, f"{tag}_{b.name}_v.mp4")
        aud = os.path.join(workdir, f"{tag}_{b.name}_a.m4a")
        av = os.path.join(workdir, f"{tag}_{b.name}.mp4")
        stage1.build_beat_fitted(spec, b, vid, duration=ndur)
        audio.build_beat_audio(spec, b, aud)
        ffmpeg.run(["-i", vid, "-i", aud, "-map", "0:v", "-map", "1:a",
                    "-c:v", "copy", "-c:a", "copy", "-shortest", "-movflags", "+faststart"], dst=av)
        beat_paths.append(av)
    rebuilt = dc_replace(spec, beats=tuple(dc_replace(b, prebaked=p)
                                           for b, p in zip(spec.beats, beat_paths)))
    return stage2.join_prebaked(rebuilt, dst)


def _input_gate(spec) -> None:
    """QC every AUDIO-bearing source for gross broadband noise BEFORE assembling. Fail loudly so a
    dirty input never silently degrades a production."""
    dirty = []
    for b in spec.beats:
        if not b.prebaked:
            continue
        p = spec.resolve(b.prebaked)
        res = qc.check_source_clean(p)
        if not res.ok:
            bad = "; ".join(f"{n}: {d}" for n, ok, d in res.checks if not ok)
            dirty.append(f"{b.name} ({os.path.basename(p)}) — {bad}")
    if dirty:
        raise AssemblyNoiseError("dirty source(s) failed the input noise gate: " + " | ".join(dirty))


def assemble(spec_path: str, *, fmt: str = "16:9", from_stage: str | None = None, dst: str,
             reference: dict | None = None, provenance_ref: str | None = None,
             workdir: str | None = None) -> AssemblyResult:
    """Load an EditSpec JSON and assemble it (thin wrapper over the in-memory core)."""
    return assemble_spec(load_spec(spec_path).for_format(fmt), dst=dst, from_stage=from_stage,
                         reference=reference, provenance_ref=provenance_ref, workdir=workdir)


def assemble_spec(spec, *, dst: str, from_stage: str | None = None, reference: dict | None = None,
                  provenance_ref: str | None = None, workdir: str | None = None) -> AssemblyResult:
    """Assemble an in-memory EditSpec (already format-resolved) → a mastered file at `dst`. The binder
    produces such a spec directly, so there's no JSON round-trip. All gates apply."""
    stage = from_stage or spec.source

    if stage == "beats":
        _input_gate(spec)   # INPUT gate — before spending minutes rendering

    t0 = time.monotonic()
    if stage == "beats":
        out = stage2.join_prebaked(spec, dst)
    elif stage == "clips":
        import tempfile
        out = _build_from_clips(spec, dst, workdir or tempfile.mkdtemp(prefix="assemble-"))
    else:
        raise ValueError(f"unknown from_stage {stage!r}")
    render_s = time.monotonic() - t0

    measured = qc.measure(out, provenance_ref=provenance_ref)
    prov = provenance.build_provenance(spec)
    comparison = qc.compare(measured, reference) if reference else None

    # OUTPUT gate — a render with audible broadband noise is NEVER kept.
    report = qc.noise_report(out)
    ngate = qc.noise_gate(report)
    if not ngate.ok:
        if os.path.exists(out):
            os.remove(out)
        bad = "; ".join(f"{n}: {d}" for n, ok, d in ngate.checks if not ok)
        raise AssemblyNoiseError(f"output failed the noise gate ({bad}) — deleted {os.path.basename(dst)}")

    return AssemblyResult(
        output_path=out, qc=measured, provenance=prov, comparison=comparison,
        noise=report, noise_gate=ngate, duration_render_s=round(render_s, 1),
        ok=(ngate.ok and (comparison.ok if comparison is not None else True)),
    )
