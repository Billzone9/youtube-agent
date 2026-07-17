"""Offline (zero-render) verification for Slice 3 — pure logic, no ffmpeg, no spend.

Proves the parts that must be right BEFORE any long render: the EditSpec loads + validates, the
crop-to-format math is correct for BOTH 16:9 and 9:16, `for_format` derives the vertical target +
focus, provenance derives the right source URLs from filenames, and the QC comparator passes/fails
at the intended tolerances.

Run: ./.venv/bin/python -m scripts.verify_slice3
"""
from __future__ import annotations

import sys

from ytagent.assembly import provenance, qc
from ytagent.assembly.ffmpeg import crop_to_format, normalize_clip, volume_sine, zoompan_expr
from ytagent.assembly.spec import load_spec

PASS, FAIL = "✅", "❌"
_failures = 0
_SPEC = "lion-doc-01-edit-spec.json"


def check(label: str, ok: bool, detail: str = "") -> None:
    global _failures
    print(f"  {PASS if ok else FAIL} {label}{(' — ' + detail) if detail else ''}")
    if not ok:
        _failures += 1


def main() -> None:
    print("[1] EditSpec loads + validates")
    spec = load_spec(_SPEC)
    check("7 beats", len(spec.beats) == 7, f"{len(spec.beats)}")
    check("source=beats and every beat has a prebaked path",
          spec.source == "beats" and all(b.prebaked for b in spec.beats))
    check("targets carry 16:9 and 9:16", set(spec.targets) == {"16:9", "9:16"})
    check("default active format is 16:9", spec.active_format == "16:9")
    check("beat1 has 5 clips (for the Stage-1 path)", len(spec.beats[0].clips) == 5)
    check("6 of 7 beats declare an out_transition (last has none)",
          sum(1 for b in spec.beats if b.out_transition) == 6)
    check("bed is OFF by default (the 'jet-engine hiss')", spec.audio_mix.include_bed is False)
    check("roar sfx targets beat6", spec.sfx and spec.sfx[0].beat == "beat6")
    check("assets resolve under the spec dir",
          spec.resolve(spec.beats[0].prebaked).endswith("assets/lion-doc-01/output/beat1_v3.mp4"))

    print("[2] for_format derives the 9:16 view")
    v = spec.for_format("9:16")
    check("9:16 target is 1080x1920", (v.target.w, v.target.h) == (1080, 1920))
    check("16:9 target is 1920x1080", (spec.target.w, spec.target.h) == (1920, 1080))
    lion = spec.beats[0].clips[4]   # the vertical lion-walk clip (13309521)
    check("vertical clip focus differs by format (keeps the head in 16:9)",
          lion.focus_for("16:9") == (0.5, 0.40) and lion.focus_for("9:16") == (0.5, 0.5))

    print("[3] crop-to-format math (16:9 AND 9:16)")
    # landscape 3840x2160 into 16:9 → same aspect → pure scale, no crop
    s = crop_to_format(3840, 2160, 1920, 1080, (0.5, 0.5))
    check("landscape→16:9 is a plain scale (no crop)", "crop" not in s, s)
    # landscape 1920x1080 into 9:16 → cover height, crop width at focal x
    s2 = crop_to_format(1920, 1080, 1080, 1920, (0.5, 0.5))
    check("landscape→9:16 covers + crops", "force_original_aspect_ratio=increase" in s2 and "crop=1080:1920" in s2, s2)
    # off-centre focus shifts the crop origin (not center)
    s3 = crop_to_format(1920, 1080, 1080, 1920, (0.20, 0.5))
    check("off-centre focus shifts crop x (0.20, not center)", "(iw-1080)*0.2000" in s3, s3)
    # vertical source into 9:16 → same aspect → plain scale
    s4 = crop_to_format(1080, 1920, 1080, 1920, (0.5, 0.5))
    check("vertical→9:16 is a plain scale (native)", "crop" not in s4, s4)
    # vertical into 16:9 → cover width, crop height at focal y
    s5 = crop_to_format(1080, 1920, 1920, 1080, (0.5, 0.40))
    check("vertical→16:9 crops height at focal y=0.40", "(ih-1080)*0.4000" in s5, s5)

    print("[4] builders: zoompan + normalize + audio swell")
    zp = zoompan_expr({"type": "zoompan", "z_from": 1.0, "z_to": 1.08}, 240, 1920, 1080, 24)
    check("zoompan builds a bounded push", zp and "min(zoom+" in zp and "1.0800" in zp, zp or "")
    check("no-effect → no zoompan", zoompan_expr(None, 240, 1920, 1080, 24) is None)
    nc = normalize_clip(3840, 2160, spec.target, (0.5, 0.5), None, 240)
    check("normalize_clip sets fps + yuv420p", "fps=24" in nc and "format=yuv420p" in nc, nc)
    check("audio swell uses volume-sine, never tremolo/aeval",
          "sin(2*PI*t" in volume_sine(0.55, 0.45, 14) and "tremolo" not in volume_sine(0.55, 0.45, 14))

    print("[5] provenance: filename → asset id → source URL")
    check("Pexels _WxH_fps filename", provenance.source_of("14301979_3840_2160_24fps.mp4") == "pexels")
    check("bare-id filename is Pixabay", provenance.source_of("300312.mp4") == "pixabay")
    check("Pexels URL derived", provenance.source_url("14301979", "pexels")
          == "https://www.pexels.com/video/14301979/")
    check("asset id parsed from -uhd suffix name",
          provenance.asset_id_from_filename("20316284-uhd_3840_2160_25fps.mp4") == "20316284")
    recs = provenance.build_provenance(spec)
    check("provenance built for beat1's clips", len(recs) == 5 and all(r["url"] for r in recs))

    print("[6] QC comparator: tolerances pass/fail correctly")
    ref = {"width": 1920, "height": 1080, "fps": 24, "duration_s": 394.783,
           "loudness_lufs": -13.8, "peak_dbfs": -0.5, "noise_floor_db": -33.8}
    good = dict(ref, duration_s=394.40, loudness_lufs=-14.1, peak_dbfs=-1.0, noise_floor_db=-33.0)
    check("in-tolerance measurement passes", qc.compare(good, ref).ok)
    bad_dur = qc.compare(dict(good, duration_s=390.0), ref)
    check("out-of-tolerance duration fails", not bad_dur.ok,
          next(c[2] for c in bad_dur.checks if c[0] == "duration"))
    bad_res = qc.compare(dict(good, width=1080, height=1920), ref)
    check("wrong resolution fails", not bad_res.ok)
    hot_peak = qc.compare(dict(good, peak_dbfs=0.3), ref)
    check("positive peak (clipping) fails", not hot_peak.ok)
    hiss = qc.compare(dict(good, noise_floor_db=-12.0), ref)
    check("broadband hiss (high noise floor) fails", not hiss.ok)

    print(f"\n{'ALL PASSED' if _failures == 0 else str(_failures) + ' CHECK(S) FAILED'}")
    sys.exit(1 if _failures else 0)


if __name__ == "__main__":
    main()
