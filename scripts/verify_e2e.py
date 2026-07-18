"""Offline (zero network/spend) verification for the end-to-end production slice.

Proves the two new links + the clips-path audio fix without any API call: (A) the binder + assembler
clips path turn a Script + a (short) sourced clip + fake TTS narration into a real master WITH audio,
48 kHz and clean, whose duration is driven by the narration; (B) the produce conductor fails loudly
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
from ytagent.assembly import assemble_spec, bind_edit_spec, qc
from ytagent.assembly.ffmpeg import FFMPEG, probe
from ytagent.assembly.spec import Target
from ytagent.authoring.script import Beat, Fact, Script
from ytagent.config import load_settings
from ytagent.notifier import StubNotifier
from ytagent.publish import DryRunPublisher
from ytagent.sourcing.base import Candidate, GateResult, NoMatch, SourcedAsset

PASS, FAIL = "✅", "❌"
_failures = 0


def check(label, ok, detail=""):
    global _failures
    print(f"  {PASS if ok else FAIL} {label}{(' — ' + detail) if detail else ''}")
    if not ok:
        _failures += 1


def _clip(work, dur=10):
    p = os.path.join(work, "clip.mp4")
    subprocess.run([FFMPEG, "-y", "-f", "lavfi", "-i", f"color=c=teal:s=1920x1080:d={dur}:r=24",
                    "-an", "-c:v", "libx264", "-pix_fmt", "yuv420p", p], capture_output=True, check=True)
    return p


def _mp3(work, name, dur):
    p = os.path.join(work, name)
    subprocess.run([FFMPEG, "-y", "-f", "lavfi", "-i", f"sine=frequency=180:duration={dur}",
                    "-c:a", "libmp3lame", p], capture_output=True, check=True)
    return p


def _asset(clip):
    c = Candidate(source="pixabay", asset_id="x", page_url="https://x/x/", download_url=clip,
                  licence="L", width=1920, height=1080, duration=10.0)
    return SourcedAsset(source="pixabay", asset_id="x", local_path=clip, candidate=c,
                        gate=GateResult(ok=True), provenance={}, score=1.0)


class _FakeScriptWriter:
    def write(self, *, topic, channel, research, runtime_target_s, n_beats):
        return Script(title="Test Wolf", runtime_target_s=40, word_target=80,
                      facts_used=(Fact("wolves howl", True),),
                      beats=(Beat(1, "Beat 1", "grey wolf forest", "The forest wakes.", 14),
                             Beat(2, "Beat 2", "grey wolf", "The wolf moves.", 18)))


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


async def run():
    settings = load_settings()
    conn = await psycopg.AsyncConnection.connect(settings.dsn(), row_factory=dict_row, autocommit=True)
    work = tempfile.mkdtemp(prefix="verify-e2e-")
    try:
        ch = await repo.channels.get_by_slug(conn, "wildlife")

        print("[A] binder + clips-path assembly → real master WITH audio, narration-driven")
        clip = _clip(work, 10)                        # 10s clip, SHORTER than the narration → loop/slow
        n1, n2 = _mp3(work, "n1.mp3", 14), _mp3(work, "n2.mp3", 18)
        script = Script(title="Test Wolf", runtime_target_s=40, word_target=80,
                        facts_used=(Fact("x", True),),
                        beats=(Beat(1, "B1", "forest", "The forest wakes.", 14),
                               Beat(2, "B2", "wolf", "The wolf moves.", 18)))
        spec = bind_edit_spec(script, {1: _asset(clip), 2: _asset(clip)}, {1: n1, 2: n2},
                              target=Target(fmt="16:9", w=1920, h=1080, fps=24))
        check("binder emits a source='clips' EditSpec", spec.source == "clips")
        check("binder set both beats' narration + clip", all(b.narration and b.clips for b in spec.beats))
        dst = os.path.join(work, "master.mp4")
        res = assemble_spec(spec, dst=dst, workdir=work)
        p = probe(dst)
        check("master HAS an audio stream (the clips-path gap is fixed)", p["has_audio"] is True)
        check("master is 1920x1080 @ 24fps", (p["width"], p["height"], round(p["fps"])) == (1920, 1080, 24))
        exp = 14 + 18 - 0.8
        check("duration is narration-driven (Σ narration − Σ overlaps)", abs(p["duration"] - exp) <= 1.5,
              f"{p['duration']:.2f}s vs ~{exp}s")
        check("master loudness measured (audio present, in band)",
              res.qc["loudness_lufs"] is not None and abs(res.qc["loudness_lufs"] + 14) <= 3.0,
              f"{res.qc['loudness_lufs']} LUFS")
        check("NOISE gate PASS (48kHz, clean — loudnorm→96k trap avoided)", res.noise_gate.ok,
              f"sr={res.noise['sample_rate']} >16k={res.noise['hi16k_db']}")

        print("[B] produce conductor: a NoMatch fails loudly BEFORE any TTS spend")
        tts = _CountingTTS()
        try:
            await produce.produce_video(
                conn, StubNotifier(), channel=ch, topic="wolf", providers=[_EmptyProvider()],
                tts=tts, script_writer=_FakeScriptWriter(), llm_provider=None, usage_sink=_Sink(),
                description_exemplar=None, publisher=DryRunPublisher(), chat_id="0",
                dst=os.path.join(work, "produced.mp4"), workdir=work)
            check("produce raised ProductionError on NoMatch", False, "did NOT raise")
        except produce.ProductionError as e:
            check("produce raised ProductionError on NoMatch", True, str(e)[:60])
        check("TTS was NEVER called (no spend before a full source set)", tts.calls == 0)
    finally:
        await conn.close()

    print(f"\n{'ALL PASSED' if _failures == 0 else str(_failures) + ' CHECK(S) FAILED'}")
    sys.exit(1 if _failures else 0)


class _Sink:
    def __init__(self): self.records = []
    def record(self, rec): self.records.append(rec)
    def drain(self): out = self.records[:]; self.records.clear(); return out


if __name__ == "__main__":
    asyncio.run(run())
