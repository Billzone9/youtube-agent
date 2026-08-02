"""6b — the crash/resume assertion that is the whole point of the sub-slice.

A production is crashed mid-`designed` (after TTS + music have run, before the checkpoint) and then
RESUMED. The fake TTS and fake music providers COUNT their calls; across the crash AND the resume each
must be called EXACTLY ONCE — proving the money stages reload their artifacts on resume and NEVER
re-charge. Also checks the spend gate (per-job + rolling ceiling) pauses/proceeds correctly. Zero real
spend; the run reaches a DRY-RUN Telegram submission.

Run: POSTGRES_HOST=localhost POSTGRES_PORT=5433 ./.venv/bin/python -m scripts.verify_produce_resume
"""
from __future__ import annotations

import asyncio
import os
import subprocess
import sys
import tempfile

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from ytagent import produce, repo
from ytagent.assembly.ffmpeg import FFMPEG
from ytagent.authoring.script import Beat, Fact, Script
from ytagent.config import load_settings
from ytagent.music.base import MusicResult
from ytagent.notifier import StubNotifier
from ytagent.publish import DryRunPublisher
from ytagent.tts.base import TTSResult

PASS, FAIL = "✅", "❌"
_failures = 0


def check(label, ok, detail=""):
    global _failures
    print(f"  {PASS if ok else FAIL} {label}{(' — ' + detail) if detail else ''}")
    if not ok:
        _failures += 1


def _mp4(path, dur=10, color="teal"):
    subprocess.run([FFMPEG, "-y", "-f", "lavfi", "-i", f"color=c={color}:s=1920x1080:d={dur}:r=24",
                    "-an", "-c:v", "libx264", "-pix_fmt", "yuv420p", path], capture_output=True, check=True)


def _mp3(path, dur):
    subprocess.run([FFMPEG, "-y", "-f", "lavfi", "-i", f"sine=frequency=180:duration={dur}",
                    "-c:a", "libmp3lame", path], capture_output=True, check=True)


class _FakeTTS:
    def __init__(self): self.calls = 0
    def name(self): return "fake-tts"
    def synthesize(self, text, *, voice_id, dst, model):
        self.calls += 1
        _mp3(dst, 8)
        return TTSResult(path=dst, characters=len(text), model=model, voice_id=voice_id, request_id="tts")


class _FakeMusic:
    def __init__(self): self.calls = 0
    def name(self): return "fake-music"
    def generate(self, prompt, *, seconds, dst, model="music_v1"):
        self.calls += 1
        _mp3(dst, min(seconds, 6))
        return MusicResult(path=dst, seconds=seconds, credits_est=round(seconds * 15), model=model,
                           kind="music", request_id="mus")
    def sound_effect(self, prompt, *, seconds, dst):
        raise AssertionError("sound_effect must not be called (sfx_specs=None)")


class _FakeWriter:
    def write(self, *, topic, channel, research, runtime_target_s, n_beats):
        return Script(title="Resume Test Film", runtime_target_s=40, word_target=40,
                      facts_used=(Fact("x", True),),
                      beats=(Beat(1, "B1", "wide savanna", "The first beat speaks briefly here now.", 8),
                             Beat(2, "B2", "close animal", "The second and final beat speaks here too.", 8)))


class _EmptyProvider:
    def name(self): return "empty"
    def rate_limit(self): return {}
    async def healthcheck(self): return True
    async def search(self, q, *, orientation, min_duration, per_page=15, page=1): return []


class _Sink:
    def __init__(self): self.records = []
    def record(self, rec): self.records.append(rec)
    def drain(self): out = self.records[:]; self.records.clear(); return out


async def _seed_sourced(conn, ch, work):
    """Four fake clips on disk + sourced_assets rows, so _st_source reconstructs (no real sourcing)."""
    alloc = {}
    for beat, colors in ((1, ["teal", "maroon"]), (2, ["olive", "navy"])):
        items = []
        for i, c in enumerate(colors):
            aid = f"rt_{beat}_{i}"
            p = os.path.join(work, f"clip_{aid}.mp4")
            _mp4(p, 10, c)
            await conn.execute("DELETE FROM sourced_assets WHERE source='pixabay' AND asset_id=%s", [aid])
            await conn.execute(
                "INSERT INTO sourced_assets (channel_id, source, asset_id, url, licence, local_path, "
                " width, height, duration_s, orientation, title, tags, gate_pass, shot_brief_ref) "
                "VALUES (%s,'pixabay',%s,%s,'L',%s,1920,1080,10,'landscape','t',%s,true,'rt')",
                [ch["id"], aid, f"https://x/{aid}", p, Jsonb(["a"])])
            items.append({"source": "pixabay", "asset_id": aid})
        alloc[str(beat)] = items
    return alloc


async def run():
    settings = load_settings()
    conn = await psycopg.AsyncConnection.connect(settings.dsn(), row_factory=dict_row, autocommit=True)
    ch = await repo.channels.get_by_slug(conn, "wildlife")
    work = tempfile.mkdtemp(prefix="resume-")
    tts, music = _FakeTTS(), _FakeMusic()
    created_jobs = []

    try:
        script = _FakeWriter().write(topic="t", channel=ch, research=None, runtime_target_s=40, n_beats=2)
        alloc = await _seed_sourced(conn, ch, work)

        # a job pre-seeded at stage 'sourced' (script + allocation done) so the run starts at the money
        # stages. script.json is written to the job root; production_state carries the allocation.
        cfg = {"target_fmt": "16:9", "target_w": 1920, "target_h": 1080, "budget_credits": 4000,
               "voice_id": "v", "model": "eleven_multilingual_v2", "workdir": work,
               "dst": os.path.join(work, "master.mp4"), "cache_dir": "assets/sourced"}
        job = await repo.jobs.create(conn, channel_id=ch["id"], type="produce", status="assembling",
                                     payload={"topic": "resume test", "cfg": cfg})
        created_jobs.append(job["id"])
        spath = os.path.join(work, "script.json")
        produce._write_script_json(spath, script)
        state = {"job_id": job["id"], "channel_id": ch["id"], "topic": "resume test", "cfg": cfg,
                 "root": work, "workdir": work, "dst": cfg["dst"], "stage": "sourced",
                 "script_path": spath, "title": script.title, "allocation": alloc}
        await repo.jobs.set_status(conn, job["id"], "assembling", result={"production_state": state})
        await conn.execute("UPDATE jobs SET stage='sourced' WHERE id=%s", [job["id"]])

        print("[1] fresh run CRASHES mid-designed (after TTS+music, before the designed checkpoint)")
        job = await repo.jobs.get(conn, job["id"])
        try:
            await produce.produce_video(
                conn, StubNotifier(), channel=ch, topic="resume test", providers=[_EmptyProvider()],
                tts=tts, music=music, script_writer=_FakeWriter(), llm_provider=None, usage_sink=_Sink(),
                description_exemplar=None, publisher=DryRunPublisher(), chat_id="0", job=job,
                crash_after={"designed"})
            check("crash injected mid-designed", False, "did NOT raise")
        except produce._CrashInjected:
            check("crash injected mid-designed (raised _CrashInjected)", True)
        tts_after_crash, music_after_crash = tts.calls, music.calls
        check("TTS ran on the fresh pass (2 spoken beats)", tts_after_crash == 2, str(tts_after_crash))
        check("music ran on the fresh pass (cues+bed)", music_after_crash >= 2, str(music_after_crash))

        print("[2] RESUME the SAME job — the money stages must NOT re-charge")
        job = await repo.jobs.get(conn, job["id"])
        check("checkpoint recorded stage 'narrated' (design was NOT checkpointed)", job["stage"] == "narrated", job["stage"])
        res = await produce.produce_video(
            conn, StubNotifier(), channel=ch, topic="resume test", providers=[_EmptyProvider()],
            tts=tts, music=music, script_writer=_FakeWriter(), llm_provider=_FakeLLM(), usage_sink=_Sink(),
            description_exemplar=None, publisher=DryRunPublisher(), chat_id="0", job=job)

        check("★ TTS called EXACTLY ONCE across crash+resume (no re-charge)", tts.calls == tts_after_crash,
              f"{tts.calls} vs {tts_after_crash}")
        check("★ MUSIC called EXACTLY ONCE across crash+resume (no re-charge)", music.calls == music_after_crash,
              f"{music.calls} vs {music_after_crash}")
        check("resume reached the DRY-RUN submission", res.get("ok") and res.get("submit") is not None)
        check("resume produced a real master with audio", os.path.exists(res["result"].output_path))

        print("[3] spend gate — per-job threshold pauses; a generous threshold proceeds")
        from ytagent.produce import _spend_gate, SpendGatePause
        st = {"job_id": job["id"], "channel_id": ch["id"], "topic": "t"}
        try:
            await _spend_gate(conn, st, script, per_job_threshold_gbp=0.01, enforce_ceiling=False, channel=ch)
            check("tiny per-job threshold PAUSES", False, "did NOT raise")
        except SpendGatePause as e:
            check("tiny per-job threshold PAUSES (SpendGatePause per_job)", e.gate == "per_job")
        await _spend_gate(conn, st, script, per_job_threshold_gbp=999, enforce_ceiling=False, channel=ch)
        check("generous per-job threshold PROCEEDS", True)

        print("[4] spend gate — rolling ceiling pauses when month-to-date + estimate would breach")
        try:
            # force the ceiling to 0 for the check via a fake budget: month-to-date + est > 0 always
            import ytagent.produce as pmod
            orig = pmod.budget_status
            async def _fake_budget(c): return {"month_spend_gbp": 100.0, "ceiling_gbp": 100.0, "tier": "m1"}
            pmod.budget_status = _fake_budget
            try:
                await _spend_gate(conn, st, script, per_job_threshold_gbp=None, enforce_ceiling=True, channel=ch)
                check("ceiling breach PAUSES", False, "did NOT raise")
            except SpendGatePause as e:
                check("ceiling breach PAUSES (SpendGatePause ceiling)", e.gate == "ceiling")
            finally:
                pmod.budget_status = orig
        except Exception as e:  # noqa: BLE001
            check("ceiling check ran", False, str(e)[:60])

    finally:
        for jid in created_jobs:
            await conn.execute("DELETE FROM events WHERE job_id=%s", [jid])
            await conn.execute("DELETE FROM approvals WHERE job_id=%s", [jid])
            await conn.execute("DELETE FROM videos WHERE job_id=%s", [jid])
        await conn.execute("DELETE FROM sourced_assets WHERE source='pixabay' AND asset_id LIKE 'rt_%'")
        # the submit created a publish job/video/approval — clean by the produced title
        await conn.execute("DELETE FROM jobs WHERE id = ANY(%s)", [created_jobs])
        await conn.close()

    print(f"\n{'ALL PASSED' if _failures == 0 else str(_failures) + ' CHECK(S) FAILED'}")
    sys.exit(1 if _failures else 0)


class _FakeLLM:
    """The resume's describe step calls the LLM writer; return canned JSON so it never hits the network."""
    def complete(self, req):
        from ytagent.providers.base import LLMResponse, TokenUsage
        return LLMResponse(
            text='{"title":"Resume Test Film","opening":"A short film.","disclosure":"Narration and '
                 'music are AI-generated; footage is licensed stock.","tags":["wildlife"]}',
            model="fake", usage=TokenUsage(), request_id="r")


if __name__ == "__main__":
    asyncio.run(run())
