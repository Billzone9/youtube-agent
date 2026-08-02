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
    subprocess.run([FFMPEG, "-y", "-f", "lavfi", "-i", f"color=c={_COLORS[i % len(_COLORS)]}:s=1920x1080:d={dur}:r=24",
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
    async def search(self, q, *, orientation, min_duration, per_page=15, page=1): return []


class _FakeLLM:
    """Satisfies the vision gate's fail-loud (llm present) + query planning (falls back on junk). Never
    reaches a vision call here — the empty provider yields no candidates to check."""
    def complete(self, req):
        from ytagent.providers.base import LLMResponse, TokenUsage
        return LLMResponse(text="{}", model="fake", usage=TokenUsage(), request_id="r")


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
        check("density gate PASSES a 3-clip 30s beat (~10s shots, no long-hold flag)",
              rep["beat1"]["clips"] == 3 and not rep["beat1"]["long_hold"], f"shot {rep['beat1']['shot_s']}s")
        dst = os.path.join(work, "master.mp4")
        res = assemble_spec(spec, dst=dst, workdir=work)
        p = probe(dst)
        check("master HAS an audio stream", p["has_audio"] is True)
        check("master is 1920x1080 @ 24fps", (p["width"], p["height"], round(p["fps"])) == (1920, 1080, 24))
        check("duration is narration-driven (~30s)", abs(p["duration"] - 30.0) <= 1.5, f"{p['duration']:.2f}s")
        check("NOISE gate PASS (48kHz, clean)", res.noise_gate.ok,
              f"sr={res.noise['sample_rate']} >16k={res.noise['hi16k_db']}")

        print("[B] density gate: HARD FLOOR (no 1-clip beat) + long-hold FLAG (reconciled to the lion)")
        one = bind_edit_spec(_script([(1, "B1")]), {1: [clips[0]]}, {1: n1}, target=TGT)
        try:
            assert_visual_density(one, {"beat1": 30.0})
            check("a 1-clip 30s beat is REJECTED (hard floor: no clip carries a beat)", False, "did NOT raise")
        except VisualDensityError as e:
            check("a 1-clip 30s beat is REJECTED (hard floor: no clip carries a beat)", True, str(e)[:52])
        # reconciled lion density: a 2-clip 40s beat (≈20s shots) PASSES but is FLAGGED for review
        n40 = _mp3(work, "n40.mp3", 40)
        two = bind_edit_spec(_script([(1, "B1")]), {1: [clips[0], clips[1]]}, {1: n40}, target=TGT)
        rep2 = assert_visual_density(two, {"beat1": 40.0})
        check("a 2-clip 40s beat PASSES at lion density (≥2 clips), FLAGGED as a long hold",
              rep2["beat1"]["clips"] == 2 and rep2["beat1"]["long_hold"] and "_long_holds" in rep2,
              f"shot {rep2['beat1']['shot_s']}s")
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
                tts=tts, script_writer=_FakeWriter(), llm_provider=_FakeLLM(), usage_sink=_Sink(),
                description_exemplar=None, publisher=DryRunPublisher(), chat_id="0",
                dst=os.path.join(work, "produced.mp4"), workdir=work)
            check("produce raised ProductionError on NoMatch", False, "did NOT raise")
        except produce.ProductionError as e:
            check("produce raised ProductionError on NoMatch", True, str(e)[:52])
        check("TTS was NEVER called (no spend before a full source set)", tts.calls == 0)

        print("[D] WORDLESS beat (cold open) end-to-end — declared duration, silence audio, no narration")
        wl = Script(title="Cold Open", runtime_target_s=30, word_target=60, facts_used=(Fact("x", True),),
                    beats=(Beat(1, "Before the first word", "wide establishing dawn", "", 8),   # vo="" → wordless
                           Beat(2, "B2", "grey wolf", "The wolf moves through the snow.", 20)))
        clips2 = [_asset(_clip(work, i, 10)) for i in range(3, 6)]      # 3 more DISTINCT clips
        wn2 = _mp3(work, "wn2.mp3", 20)
        wspec = bind_edit_spec(wl, {1: clips, 2: clips2}, {2: wn2}, target=TGT)   # beat1 absent → wordless
        check("binder made beat1 WORDLESS (no narration, declared 8s)",
              wspec.beats[0].narration is None and wspec.beats[0].duration == 8.0)
        rep = assert_visual_density(wspec)                             # uses the declared 8s length
        check("density gate handles the wordless beat on its declared length", "beat1" in rep)
        wdst = os.path.join(work, "wmaster.mp4")
        wres = assemble_spec(wspec, dst=wdst, workdir=work)
        wp = probe(wdst)
        check("wordless-beat master assembles WITH audio (no crash on empty narration)", wp["has_audio"] is True)
        check("master duration = declared cold-open + narration − overlap (~27s)",
              abs(wp["duration"] - 27.2) <= 1.6, f"{wp['duration']:.1f}s")
        check("wordless-beat noise gate PASS (silence is clean)", wres.noise_gate.ok)

        print("[E] AUDIO DESIGN: per-beat cue + structural breather + ambience bed → clean master")
        from ytagent.assembly.spec import MusicCue
        cue = _mp3(work, "cue.mp3", 20)                 # a clean 'score' cue (looped under narration)
        bed = _mp3(work, "bed.mp3", 12)                 # a clean ambience 'bed' (crossfade-looped)
        narrX = _mp3(work, "nx.mp3", 20)
        clipsE = [_asset(_clip(work, i, 10)) for i in range(6, 9)]
        specE = bind_edit_spec(_script([(1, "B1")]), {1: clipsE}, {1: narrX}, target=TGT,
                               cues={1: MusicCue(file=cue, in_db=-16.0)}, breathers={1: 4.0},
                               bed=bed, bed_db=-30.0)
        check("beat carries the cue + a 4s breather",
              specE.beats[0].music is not None and specE.beats[0].breather_s == 4.0)
        check("audio_mix carries the ambience bed", specE.audio_mix.include_bed and bool(specE.audio_mix.bed))
        edst = os.path.join(work, "emaster.mp4")
        eres = assemble_spec(specE, dst=edst, workdir=work)
        ep = probe(edst)
        check("audio-designed master HAS audio", ep["has_audio"] is True)
        check("duration = narration + breather (~24s)", abs(ep["duration"] - 24.0) <= 1.6, f"{ep['duration']:.1f}s")
        check("audio-designed master NOISE gate PASS (48kHz — bed+cue+finish clean)", eres.noise_gate.ok,
              f"sr={eres.noise['sample_rate']} >16k={eres.noise['hi16k_db']}")

        print("[F] contents MANIFEST drives the disclosure line (not a hard-coded string)")
        from ytagent.metadata.llm_writer import LLMWriter

        class _CapProvider:
            def __init__(self): self.seen = ""
            def complete(self, req):
                from ytagent.providers.base import LLMResponse, TokenUsage
                self.seen += " ".join(m["content"] for m in req.messages if isinstance(m["content"], str))
                return LLMResponse(
                    text='{"title":"T","opening":"o","disclosure":"Narration, music and ambience are '
                         'AI-generated; footage is licensed stock.","tags":[]}',
                    model="f", usage=TokenUsage(), request_id="r")

        cap = _CapProvider()
        out = LLMWriter(cap).write(
            video={"topic": "elephant", "title": "The Old Paths",
                   "contents": {"narration": "AI TTS", "music": "AI-generated", "ambience": "AI-generated",
                                "footage": "licensed stock"}},
            channel=ch, research=type("R", (), {"available": False, "notes": ""})())
        check("the manifest reached the writer prompt", "actual contents" in cap.seen and "ambience" in cap.seen)
        check("the writer returns a disclosure line", bool(out.get("disclosure")))

        print("[G] generate_audio degrades to NARRATION-ONLY without a music provider (no spend)")
        from ytagent.audio_design import generate_audio
        dz = await generate_audio(conn, None, _script([(1, "B1")]), channel=ch, job_id=None,
                                  workdir=work, budget_credits=4000)
        check("no music provider → no cues, no breathers, manifest = narration+footage only",
              not dz.cues and not dz.breathers and "music" not in dz.manifest and bool(dz.manifest.get("narration")))
    finally:
        await conn.close()

    print(f"\n{'ALL PASSED' if _failures == 0 else str(_failures) + ' CHECK(S) FAILED'}")
    sys.exit(1 if _failures else 0)


class _FakeWriter:
    def write(self, *, topic, channel, research, runtime_target_s, n_beats, footage_distribution=None):
        return _script([(1, "B1"), (2, "B2")])


if __name__ == "__main__":
    asyncio.run(run())
