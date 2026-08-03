"""Resume a paused/failed production job through run_production — reloads its checkpointed artifacts
(TTS + music NEVER re-charged) and continues from the first incomplete stage to the Telegram card.

Run: POSTGRES_HOST=localhost POSTGRES_PORT=5433 JOB=155 ./.venv/bin/python -m scripts.resume_job
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
from ytagent.providers import ListUsageSink, get_llm_provider
from ytagent.publish import DryRunPublisher
from ytagent.tts import get_tts_provider
from scripts.produce_elephant import _make_notifier


async def run():
    jid = int(os.environ["JOB"])
    settings = load_settings()
    sink = ListUsageSink()
    llm = get_llm_provider(settings, sink)
    tts = get_tts_provider(settings)
    music = get_music_provider(settings)
    conn = await psycopg.AsyncConnection.connect(settings.dsn(), row_factory=dict_row, autocommit=True)
    ch = await repo.channels.get_by_slug(conn, "wildlife")
    job = await repo.jobs.get(conn, jid)
    st = (job.get("result") or {}).get("production_state") or {}
    print(f"=== RESUME job {jid} from stage '{st.get('stage')}' — TTS+music reload (no re-charge) ===")
    notifier, bot = await _make_notifier(settings)

    try:
        res = await produce.produce_video(
            conn, notifier, channel=ch, topic=st.get("topic", "african elephant"), providers=[], tts=tts,
            music=music, script_writer=None, llm_provider=llm, usage_sink=sink, description_exemplar=None,
            publisher=DryRunPublisher(), chat_id=settings.chat_id, job=job,
            key_credit_cap=settings.elevenlabs_key_credit_cap)
    except produce.SpendGatePause as e:
        if e.gate == "credits":
            print(f"\n⏸️  PAUSED BEFORE SPENDING — needs {e.estimate:.0f} ElevenLabs credits, key has "
                  f"{e.limit:.0f}. Raise the key's cap (dashboard + ELEVENLABS_KEY_CREDIT_CAP={settings.elevenlabs_key_credit_cap}) "
                  f"by ~{e.estimate - e.limit:.0f}, then re-run. Nothing was spent; beats 1–2 stay voiced.")
        else:
            print(f"\n⏸️  PAUSED at the spend gate ({e.gate}): {e}")
        if bot:
            await bot.shutdown()
        await conn.close()
        return

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
    bud = await budget_status(conn)
    print(f"\nSUBMITTED for approval (dry_run). month-to-date £{bud['month_spend_gbp']:.2f} / £{bud['ceiling_gbp']:.0f}")
    print(f"master: {res['result'].output_path}")
    if bot:
        await bot.shutdown()
    await conn.close()


if __name__ == "__main__":
    asyncio.run(run())
