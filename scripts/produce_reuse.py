"""6b acceptance (reliable variant) — drive a REAL production to the Telegram card THROUGH the refactored
run_production, reusing the elephant's proven 26-clip curated allocation (so the sourcing lottery can't
block the proof). The state machine starts at the `sourced` checkpoint and runs the real money + render
stages: spend-gate → TTS → design → assemble → submit. A real film you can watch and compare to the
known-good public elephant, exercising exactly the code 6b refactored.

Run: POSTGRES_HOST=localhost POSTGRES_PORT=5433 ./.venv/bin/python -m scripts.produce_reuse
"""
from __future__ import annotations

import asyncio
import os

import psycopg
from psycopg.rows import dict_row

from ytagent import produce, repo
from ytagent.budget import budget_status
from ytagent.config import load_settings
from ytagent.music import get_music_provider
from ytagent.notifier import StubNotifier
from ytagent.providers import ListUsageSink, get_llm_provider
from ytagent.publish import DryRunPublisher
from ytagent.tts import get_tts_provider
from scripts.produce_elephant import _ALLOC, _load_script, _make_notifier


async def _allocation(conn):
    """Beat → [{source, asset_id}] for the 26 curated clips, resolving each id's source from the DB."""
    alloc = {}
    for beat, ids in _ALLOC.items():
        items = []
        for aid in ids:
            row = await (await conn.execute(
                "SELECT source FROM sourced_assets WHERE asset_id=%s ORDER BY id DESC LIMIT 1", [aid])).fetchone()
            if not row:
                raise SystemExit(f"curated clip {aid} not in sourced_assets — run Stage 1 first")
            items.append({"source": row["source"], "asset_id": aid})
        alloc[str(beat)] = items
    return alloc


async def run():
    settings = load_settings()
    sink = ListUsageSink()
    llm = get_llm_provider(settings, sink)
    tts = get_tts_provider(settings)
    music = get_music_provider(settings)
    if not (llm and tts and music):
        raise SystemExit(f"prereqs — llm={bool(llm)} tts={bool(tts)} music={bool(music)}")

    conn = await psycopg.AsyncConnection.connect(settings.dsn(), row_factory=dict_row, autocommit=True)
    ch = await repo.channels.get_by_slug(conn, "wildlife")
    script = _load_script()
    alloc = await _allocation(conn)
    notifier, bot = await _make_notifier(settings)

    root = "assets/produced/reuse-elephant"
    workdir = os.path.join(root, "work")
    os.makedirs(workdir, exist_ok=True)
    cfg = {"target_fmt": "16:9", "target_w": 1920, "target_h": 1080, "budget_credits": 4000,
           "voice_id": (ch["config"].get("voice_profile") or {}).get("voice_id"),
           "model": (ch["config"].get("voice_profile") or {}).get("model", "eleven_multilingual_v2"),
           "workdir": os.path.abspath(workdir),
           "dst": os.path.abspath(os.path.join(root, "output", "the-matriarch-v2_scored.mp4")),
           "cache_dir": "assets/sourced", "runtime_target_s": 394, "n_beats": 7}
    job = await repo.jobs.create(conn, channel_id=ch["id"], type="produce", status="assembling",
                                 payload={"topic": "african elephant", "cfg": cfg})
    spath = os.path.join(workdir, "script.json")
    produce._write_script_json(spath, script)
    state = {"job_id": job["id"], "channel_id": ch["id"], "topic": "african elephant", "cfg": cfg,
             "root": os.path.abspath(root), "workdir": cfg["workdir"], "dst": cfg["dst"],
             "stage": "sourced", "script_path": os.path.abspath(spath), "title": script.title,
             "allocation": alloc}
    await repo.jobs.set_status(conn, job["id"], "assembling", result={"production_state": state})
    await conn.execute("UPDATE jobs SET stage='sourced' WHERE id=%s", [job["id"]])

    print(f"=== REAL PRODUCTION via run_production (reuse 26 curated clips) — '{script.title}', job {job['id']} ===")
    print("stages from checkpoint: [sourced] → spend-gate → TTS → design → assemble → submit (DRY RUN)\n")

    job = await repo.jobs.get(conn, job["id"])
    res = await produce.produce_video(
        conn, notifier, channel=ch, topic="african elephant", providers=[], tts=tts, music=music,
        script_writer=None, llm_provider=llm, usage_sink=sink, description_exemplar=None,
        publisher=DryRunPublisher(), chat_id=settings.chat_id, job=job)

    qc = res["result"].qc
    noise = res["result"].noise
    d = res["design"]
    print("\n=== MASTER QC (vs lion: 1080p/24fps, ~-14 LUFS, 48kHz, no clip, no hiss) ===")
    print(f"  resolution : {qc.get('width')}x{qc.get('height')} @ {qc.get('fps')}fps")
    print(f"  duration   : {qc.get('duration_s')}s ({qc.get('duration_s',0)/60:.1f} min)")
    print(f"  loudness   : {qc.get('loudness_lufs')} LUFS   peak {qc.get('peak_dbfs')} dBFS")
    print(f"  audio      : {noise.get('sample_rate')} Hz   >16k={noise.get('hi16k_db')} dB   "
          f"gate={'PASS' if res['result'].noise_gate.ok else 'FAIL'}")
    print(f"  audio design: {'; '.join(d.layers) if d and d.layers else 'narration only'}")
    print(f"  estimate £{res.get('estimate_gbp')}  |  music credits {d.credits_spent if d else 0:.0f}/4000")
    bud = await budget_status(conn)
    print(f"\nSUBMITTED for approval (dry_run). month-to-date £{bud['month_spend_gbp']:.2f} / £{bud['ceiling_gbp']:.0f}")
    print(f"master: {res['result'].output_path}")
    if bot:
        await bot.shutdown()
    await conn.close()


if __name__ == "__main__":
    asyncio.run(run())
