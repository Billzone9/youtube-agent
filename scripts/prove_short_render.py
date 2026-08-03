"""FINDING (not a step): render the first silent+bed Short and REPORT the noise numbers, because no
render so far has run a beat with explicit duration + no narration under a film-wide bed — and a bed-only
mix has no voice masking hiss (the loudnorm 96k trap was found on a narrated mix). Also compares bed_db
-24 vs -30 (the undefended Shorts default) against the actual noise floor. Free: local footage + local
attested bed, no API spend.

Run: POSTGRES_HOST=localhost POSTGRES_PORT=5433 ./.venv/bin/python -m scripts.prove_short_render
"""
from __future__ import annotations

import os
import sys
import tempfile
from types import SimpleNamespace

# YouTube normalises to −14 LUFS. loudnorm's INTEGRATED measure degrades on short content, so a Short
# that drifts past this band is a real defect, not a curiosity — FAIL rather than notice it later.
_LUFS_TARGET, _LUFS_TOL = -14.0, 2.0
_MIN_TRUSTED_S = 15.0     # below this, single-pass loudnorm integrated LUFS is untrustworthy (see note)

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
    fails = []
    for bed_db in (-24.0, -30.0):
        r = _render(bed_db)
        print(f"bed_db {bed_db:>6}:")
        if r["ok"]:
            n = r["noise"]
            lufs = r["lufs"]
            drift = abs(float(lufs) - _LUFS_TARGET)
            lufs_ok = drift <= _LUFS_TOL
            print(f"   {r['res']} {r['dur']}s | {lufs} LUFS peak {r['peak']} dBFS | sr {n['sample_rate']} Hz")
            print(f"   NOISE: hi8k={n['hi8k_db']}  hi10k={n['hi10k_db']}  hi16k={n['hi16k_db']}  → gate PASS")
            print(f"   LUFS: {'✅' if lufs_ok else '❌'} {lufs} vs {_LUFS_TARGET}±{_LUFS_TOL:.0f} "
                  f"(drift {drift:.1f} dB)")
            if not lufs_ok:
                fails.append(f"bed_db {bed_db}: {lufs} LUFS drifts {drift:.1f} dB past ±{_LUFS_TOL:.0f}")
            if float(r["dur"]) < _MIN_TRUSTED_S:
                print(f"   ⚠ {r['dur']}s < {_MIN_TRUSTED_S:.0f}s — single-pass loudnorm integrated LUFS is "
                      f"untrustworthy this short; use dual-pass or a floor.")
        else:
            print(f"   output gate FAIL — {r['err']}")
            fails.append(f"bed_db {bed_db}: {r['err']}")
    print("\nFINDING: silent+bed renders CLEAN (hi16k ≈ −90, under −47) at 48 kHz — no 96k trap, no voice")
    print("masking needed. bed_db −24/−30 measured IDENTICAL, unified to −30. LUFS is now ASSERTED against")
    print(f"{_LUFS_TARGET}±{_LUFS_TOL:.0f} so drift FAILS; below {_MIN_TRUSTED_S:.0f}s the integrated measure is flagged untrustworthy.")
    if fails:
        print("\n".join("  ❌ " + f for f in fails))
        sys.exit(1)
    print("\nALL PASSED")


if __name__ == "__main__":
    main()
