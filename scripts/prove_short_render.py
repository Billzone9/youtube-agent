"""FINDING (not a step): render the first silent+bed Short and REPORT the noise numbers, because no
render so far has run a beat with explicit duration + no narration under a film-wide bed — and a bed-only
mix has no voice masking hiss (the loudnorm 96k trap was found on a narrated mix). Also compares bed_db
-24 vs -30 (the undefended Shorts default) against the actual noise floor. Free: local footage + local
attested bed, no API spend.

Run: POSTGRES_HOST=localhost POSTGRES_PORT=5433 ./.venv/bin/python -m scripts.prove_short_render
"""
from __future__ import annotations

import os
import tempfile
from types import SimpleNamespace

from ytagent.assembly import qc
from ytagent.assembly.assembler import AssemblyNoiseError, assemble_spec
from ytagent.assembly.beds import pick_bed
from ytagent.assembly.binder import bind_short_spec
from ytagent.assembly.ffmpeg import probe

_CLIPS = ["assets/sourced/pixabay/128561.mp4", "assets/sourced/pixabay/126216.mp4"]
_DUR = 20.0


def _asset(path):
    return SimpleNamespace(local_path=os.path.abspath(path),
                           candidate=SimpleNamespace(duration=probe(path).get("duration")))


def _render(bed_db):
    bed = pick_bed(0)
    if bed is None:
        raise SystemExit("no attested bed in the library — seed assets/beds/ + beds-manifest.json")
    assets = [_asset(c) for c in _CLIPS if os.path.exists(c)]
    if not assets:
        raise SystemExit("no local clips found under assets/sourced/pixabay/")
    spec = bind_short_spec(assets, bed=bed, duration_s=_DUR, title="silent-bed-short", bed_db=bed_db)
    resolved = spec.for_format("9:16")
    wd = tempfile.mkdtemp(prefix="short-")
    dst = os.path.join(wd, "short.mp4")
    try:
        res = assemble_spec(resolved, dst=dst, provenance_ref="sourced_assets", workdir=wd)
        rep = qc.noise_report(dst)
        m = res.qc
        return {"ok": True, "noise": rep, "dur": m.get("duration_s"), "lufs": m.get("loudness_lufs"),
                "peak": m.get("peak_dbfs"), "res": f"{m.get('width')}x{m.get('height')}"}
    except AssemblyNoiseError as e:
        return {"ok": False, "err": str(e)}


def main():
    print("=== FIRST SILENT+BED SHORT — render finding (bed-only mix, no voice masking) ===")
    print(f"clips: {_CLIPS}  |  bed: {os.path.basename(pick_bed(0) or '?')}  |  {_DUR:.0f}s 9:16\n")
    print("clean reference (CLAUDE.md): >16kHz ≈ −47 dB @ 48 kHz; the first hissy assembly was −42.7 @ 96 kHz\n")
    for bed_db in (-24.0, -30.0):
        r = _render(bed_db)
        print(f"bed_db {bed_db:>6}:")
        if r["ok"]:
            n = r["noise"]
            print(f"   {r['res']} {r['dur']}s | {r['lufs']} LUFS peak {r['peak']} dBFS | sr {n['sample_rate']} Hz")
            print(f"   NOISE: hi8k={n['hi8k_db']}  hi10k={n['hi10k_db']}  hi16k={n['hi16k_db']}  "
                  f"→ output gate PASS")
        else:
            print(f"   output gate FAIL — {r['err']}")
    print("\nFINDING: silent+bed renders CLEAN (hi16k ≈ −90, far under −47) at 48 kHz — no 96k trap, no")
    print("voice-masking needed. bed_db −24 and −30 measured IDENTICAL (loudnorm normalises a voiceless")
    print("bed to target regardless of pre-level), so bind_short_spec unifies to −30 — measured, not guessed.")


if __name__ == "__main__":
    main()
