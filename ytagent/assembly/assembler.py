"""Assembly orchestration — the channel-general entrypoint.

`assemble()` renders a master from an EditSpec (in a chosen format, from beats or from clips),
measures it (a QC dict shaped like `artifacts.lion_video_meta()` + provenance), and — when given a
reference — compares within tolerance. The caller decides `dst` (never the locked reference file).
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field

from . import provenance, qc, stage1, stage2
from .spec import load_spec


@dataclass
class AssemblyResult:
    output_path: str
    qc: dict
    provenance: list = field(default_factory=list)
    comparison: qc.QCResult | None = None
    duration_render_s: float = 0.0
    ok: bool = True


def _build_from_clips(spec, dst: str, workdir: str) -> str:
    import os

    beat_paths = []
    for b in spec.beats:
        bp = os.path.join(workdir, f"{spec.active_format.replace(':','x')}_{b.name}.mp4")
        beat_paths.append(stage1.build_beat(spec, b, bp))
    # replace prebaked with freshly-built beats, then join via the same stage-2 path
    from dataclasses import replace as dc_replace
    rebuilt = dc_replace(spec, beats=tuple(dc_replace(b, prebaked=p)
                                           for b, p in zip(spec.beats, beat_paths)))
    return stage2.join_prebaked(rebuilt, dst)


def assemble(spec_path: str, *, fmt: str = "16:9", from_stage: str | None = None, dst: str,
             reference: dict | None = None, provenance_ref: str | None = None,
             workdir: str | None = None) -> AssemblyResult:
    spec = load_spec(spec_path).for_format(fmt)
    stage = from_stage or spec.source
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
    return AssemblyResult(
        output_path=out, qc=measured, provenance=prov, comparison=comparison,
        duration_render_s=round(render_s, 1),
        ok=(comparison.ok if comparison is not None else True),
    )
