"""Offline (zero network/spend) verification for the end-to-end production slice + the VISUAL DENSITY
standard.

Proves without any API call: (A) the binder + assembler clips path turn a Script + MULTIPLE distinct
sourced clips + fake TTS narration into a real master WITH audio, 48 kHz clean, narration-driven, cut
between the clips; (B) the density gate — a beat too sparse (one clip held >15s) or reusing a clip
FAILS `assert_visual_density`; a multi-clip beat PASSES; (C) the produce conductor fails loudly
(`ProductionError`) on a shot-brief `NoMatch` BEFORE any TTS is called.

Run: POSTGRES_HOST=localhost POSTGRES_PORT=5433 ./.venv/bin/python -m scripts.verify_e2e
"""
from __future__ import annotations

import asyncio
import os
import subprocess
import sys
import tempfile

import psycopg
from psycopg.rows import dict_row

from ytagent import produce, repo
from ytagent.assembly import assemble_spec, bind_edit_spec
from ytagent.assembly.density import VisualDensityError, assert_visual_density
from ytagent.assembly.ffmpeg import FFMPEG, probe
from ytagent.assembly.spec import Target
from ytagent.authoring.script import Beat, Fact, Script
from ytagent.config import load_settings
from ytagent.notifier import StubNotifier
from ytagent.publish import DryRunPublisher
from ytagent.sourcing.base import Candidate, GateResult, SourcedAsset

PASS, FAIL = "✅", "❌"
_failures = 0
_COLORS = ["teal", "maroon", "olive", "navy", "purple", "green", "gray", "orange"]


def check(label, ok, detail=""):
    global _failures
    print(f"  {PASS if ok else FAIL} {label}{(' — ' + detail) if detail else ''}")
    if not ok:
        _failures += 1


def _clip(work, i, dur=10):
    p = os.path.join(work, f"clip{i}.mp4")
    subprocess.run([FFMPEG, "-y", "-f", "lavfi", "-i", f"color=c={_COLORS[i]}:s=1920x1080:d={dur}:r=24",
                    "-an", "-c:v", "libx264", "-pix_fmt", "yuv420p", p], capture_output=True, check=True)
    return p


def _mp3(work, name, dur):
    p = os.path.join(work, name)
    subprocess.run([FFMPEG, "-y", "-f", "lavfi", "-i", f"sine=frequency=180:duration={dur}",
                    "-c:a", "libmp3lame", p], capture_output=True, check=True)
    return p


def _asset(clip):
    c = Candidate(source="pixabay", asset_id=os.path.basename(clip), page_url=f"https://x/{clip}/",
                  download_url=clip, licence="L", width=1920, height=1080, duration=10.0)
    return SourcedAsset(source="pixabay", asset_id=c.asset_id, local_path=clip, candidate=c,
                        gate=GateResult(ok=True), provenance={}, score=1.0)


def _script(beats):   # beats: list of (index, label)
    return Script(title="Test Wolf", runtime_target_s=60, word_target=120, facts_used=(Fact("x", True),),
                  beats=tuple(Beat(i, lbl, "grey wolf", "The wolf moves.", 30) for i, lbl in beats))


TGT = Target(fmt="16:9", w=1920, h=1080, fps=24)


class _EmptyProvider:
    def name(self): return "empty"
    def rate_limit(self): return {}
    async def healthcheck(self): return True
    async def search(self, q, *, orientation, min_duration, per_page=15): return []


class _CountingTTS:
    def __init__(self): self.calls = 0
    def name(self): return "fake-tts"
    def synthesize(self, text, *, voice_id, dst, model):
        self.calls += 1
        raise AssertionError("TTS must not be called when a beat no-matched")


class _Sink:
    def __init__(self): self.records = []
    def record(self, rec): self.records.append(rec)
    def drain(self): out = self.records[:]; self.records.clear(); return out


async def run():
    settings = load_settings()
    conn = await psycopg.AsyncConnection.connect(settings.dsn(), row_factory=dict_row, autocommit=True)
    work = tempfile.mkdtemp(prefix="verify-e2e-")
    try:
        ch = await repo.channels.get_by_slug(conn, "wildlife")

        print("[A] multi-clip binder + clips-path assembly → master cut between distinct clips")
        clips = [_asset(_clip(work, i, 10)) for i in range(3)]      # 3 DISTINCT clips
        n1 = _mp3(work, "n1.mp3", 30)                                # 30s beat → ~3 shots @ ~10s
        spec = bind_edit_spec(_script([(1, "B1")]), {1: clips}, {1: n1}, target=TGT)
        check("binder made a 3-clip beat (distinct srcs)",
              len(spec.beats[0].clips) == 3 and len({c.src for c in spec.beats[0].clips}) == 3)
        rep = assert_visual_density(spec, {"beat1": 30.0})
        check("density gate PASSES a 3-clip 30s beat, shots ≤15s",
              rep["beat1"]["clips"] == 3 and rep["beat1"]["shot_s"] <= 15.0, f"shot {rep['beat1']['shot_s']}s")
        dst = os.path.join(work, "master.mp4")
        res = assemble_spec(spec, dst=dst, workdir=work)
        p = probe(dst)
        check("master HAS an audio stream", p["has_audio"] is True)
        check("master is 1920x1080 @ 24fps", (p["width"], p["height"], round(p["fps"])) == (1920, 1080, 24))
        check("duration is narration-driven (~30s)", abs(p["duration"] - 30.0) <= 1.5, f"{p['duration']:.2f}s")
        check("NOISE gate PASS (48kHz, clean)", res.noise_gate.ok,
              f"sr={res.noise['sample_rate']} >16k={res.noise['hi16k_db']}")

        print("[B] density gate rejects sparse / reused cuts")
        one = bind_edit_spec(_script([(1, "B1")]), {1: [clips[0]]}, {1: n1}, target=TGT)
        try:
            assert_visual_density(one, {"beat1": 30.0})
            check("a 1-clip 30s beat is REJECTED (no clip held >15s)", False, "did NOT raise")
        except VisualDensityError as e:
            check("a 1-clip 30s beat is REJECTED (no clip held >15s)", True, str(e)[:52])
        reused = bind_edit_spec(_script([(1, "B1"), (2, "B2")]),
                                {1: [clips[0], clips[1], clips[2]], 2: [clips[0], clips[1], clips[2]]},
                                {1: n1, 2: n1}, target=TGT)
        try:
            assert_visual_density(reused, {"beat1": 30.0, "beat2": 30.0})
            check("a clip reused across two beats is REJECTED", False, "did NOT raise")
        except VisualDensityError as e:
            check("a clip reused across two beats is REJECTED", True, str(e)[:52])

        print("[C] produce conductor: a NoMatch fails loudly BEFORE any TTS spend")
        tts = _CountingTTS()
        try:
            await produce.produce_video(
                conn, StubNotifier(), channel=ch, topic="wolf", providers=[_EmptyProvider()],
                tts=tts, script_writer=_FakeWriter(), llm_provider=None, usage_sink=_Sink(),
                description_exemplar=None, publisher=DryRunPublisher(), chat_id="0",
                dst=os.path.join(work, "produced.mp4"), workdir=work)
            check("produce raised ProductionError on NoMatch", False, "did NOT raise")
        except produce.ProductionError as e:
            check("produce raised ProductionError on NoMatch", True, str(e)[:52])
        check("TTS was NEVER called (no spend before a full source set)", tts.calls == 0)
    finally:
        await conn.close()

    print(f"\n{'ALL PASSED' if _failures == 0 else str(_failures) + ' CHECK(S) FAILED'}")
    sys.exit(1 if _failures else 0)


class _FakeWriter:
    def write(self, *, topic, channel, research, runtime_target_s, n_beats):
        return _script([(1, "B1"), (2, "B2")])


if __name__ == "__main__":
    asyncio.run(run())
