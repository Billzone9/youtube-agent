"""Regression for D3 — the audio-design completeness guard (`assert_audio_complete`). The guard must
distinguish a DECLARED degradation (capability unavailable / scope-blocked / credit-ceiling — expected,
ships cleanly) from a PLANNED-THEN-MISSING element (a defect — fail loud before the render). Pure/offline
(no DB, no keys): builds AudioDesign fixtures against a real plan and real temp cue files.

Run: ./.venv/bin/python -m scripts.verify_d3
"""
from __future__ import annotations

import os
import sys
import tempfile

from ytagent.audio_design import AudioDesign, AudioDesignError, assert_audio_complete, plan_cues
from ytagent.authoring.script import Beat, Fact, Script
from ytagent.assembly.spec import MusicCue

_fail = 0


def check(label, ok, detail=""):
    global _fail
    print(f"  {'✅' if ok else '❌'} {label}{(' — ' + detail) if detail else ''}")
    if not ok:
        _fail += 1


def _raises(design, script, channel):
    try:
        assert_audio_complete(design, script, channel)
        return False
    except AudioDesignError:
        return True


def main():
    ch = {"id": 1, "config": {"tone": "reverent", "niche": "nature documentary"}}
    # a 3-beat script (beats 1..3 all spoken) so the plan assigns real cue beats
    script = Script(title="African Lion", runtime_target_s=90, word_target=90,
                    facts_used=(Fact("x", True),),
                    beats=(Beat(1, "B1", "wide", "The first beat speaks.", 20),
                           Beat(2, "B2", "mid", "The second beat speaks.", 20),
                           Beat(3, "B3", "close", "The third and final beat speaks.", 20)))
    cue_specs, _, _ = plan_cues(script, ch)
    planned_beats = sorted({b for spec in cue_specs for b in spec.beats})
    print(f"plan → cue beats {planned_beats}")

    work = tempfile.mkdtemp(prefix="d3-")

    def _cue(name):
        p = os.path.join(work, f"{name}.mp3")
        with open(p, "wb") as f:
            f.write(b"\x00" * 16)   # a real file on disk (existence is all the guard checks)
        return MusicCue(file=p, in_db=-16.0, fade_in=2.0, fade_out=3.0)

    # [1] COMPLETE — every planned beat present, files exist, nothing declared → PASS
    print("[1] a complete design (all planned cues present, files exist) passes")
    d_ok = AudioDesign()
    shared = _cue("theme")
    d_ok.cues = {b: shared for b in planned_beats}
    try:
        assert_audio_complete(d_ok, script, ch)
        check("complete design passes", True)
    except AudioDesignError as e:
        check("complete design passes", False, str(e)[:60])

    # [2] DECLARED unavailable — music declared, zero cues → PASS (clean degradation, NOT a defect)
    print("[2] a DECLARED degradation (music unavailable, 0 cues) passes")
    d_decl = AudioDesign()
    d_decl.declared = {"music": "no music provider configured"}
    check("music-declared, no cues → passes (narration-only is legitimate)",
          not _raises(d_decl, script, ch))

    # [3] PLANNED-THEN-MISSING — music NOT declared, a planned beat absent → DEFECT
    print("[3] planned-then-missing (music available, a planned beat absent) FAILS")
    d_gap = AudioDesign()
    d_gap.cues = {b: shared for b in planned_beats[:-1]}   # drop the last planned beat, nothing declared
    check("a silently-dropped planned cue is caught as a defect", _raises(d_gap, script, ch),
          f"missing beat {planned_beats[-1]}")

    # [4] REFERENTIAL INTEGRITY — a cue references a file that does not exist → DEFECT
    print("[4] a referenced cue file that does not exist FAILS (planned-then-vanished)")
    d_dangling = AudioDesign()
    d_dangling.cues = {b: MusicCue(file=os.path.join(work, "gone.mp3"), in_db=-16.0,
                                   fade_in=2.0, fade_out=3.0) for b in planned_beats}
    check("a dangling cue-file reference is caught", _raises(d_dangling, script, ch))

    # [5] the credit-ceiling case is DECLARED → a partial score passes (known-degraded, not a defect)
    print("[5] a credit-ceiling degradation (declared) with a partial score passes")
    d_budget = AudioDesign()
    d_budget.declared = {"music": "credit ceiling 4000 reached"}
    d_budget.cues = {planned_beats[0]: shared}            # only one cue made before the ceiling
    check("declared budget degradation with a partial score passes", not _raises(d_budget, script, ch))

    # [6] a set-but-missing BED is a defect even though a bed is optional (referential integrity)
    print("[6] a set-but-missing bed is a defect (referential integrity applies to what IS referenced)")
    d_bed = AudioDesign()
    d_bed.cues = {b: shared for b in planned_beats}
    d_bed.bed = os.path.join(work, "no-bed.mp3")          # referenced but never written
    check("a referenced-but-absent bed is caught", _raises(d_bed, script, ch))

    print(f"\n{'✅ ALL PASS' if _fail == 0 else f'❌ {_fail} FAILED'}")
    return 1 if _fail else 0


if __name__ == "__main__":
    sys.exit(main())
