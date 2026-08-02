"""6b ACCEPTANCE — one REAL production end to end through the refactored resumable path (produce_video
→ run_production → all six stages) to the Telegram approval card. Not a simulation: real script, real
film-wide sourcing, real TTS + music, real assembly, real submission. Publish stays a separate gate
(DryRunPublisher). Subject probed FEASIBLE/MARGINAL first (footage-feasibility doctrine).

Run: POSTGRES_HOST=localhost POSTGRES_PORT=5433 SUBJECT=giraffe BEATS=6 RUNTIME=340 \
     ./.venv/bin/python -m scripts.produce_next
"""
from __future__ import annotations

import asyncio
import os

import psycopg
from psycopg.rows import dict_row

from ytagent import produce, repo
from ytagent.authoring.script import ScriptWriter
from ytagent.budget import budget_status
from ytagent.config import load_settings
from ytagent.music import get_music_provider
from ytagent.notifier import StubNotifier
from ytagent.providers import ListUsageSink, get_llm_provider
from ytagent.publish import DryRunPublisher
from ytagent.sourcing import get_stock_providers
from ytagent.tts import get_tts_provider


async def _make_notifier(settings):
    if settings.bot_token:
        try:
            from telegram import Bot
            from ytagent.notifier import TelegramNotifier
            bot = Bot(settings.bot_token)
            await bot.initialize()
            return TelegramNotifier(bot), bot
        except Exception as e:  # noqa: BLE001
            print(f"  (telegram unavailable — using stub notifier: {e})")
    return StubNotifier(), None


async def run():
    subject = os.environ.get("SUBJECT", "giraffe")
    n_beats = int(os.environ.get("BEATS", "6"))
    runtime = int(os.environ.get("RUNTIME", "340"))
    settings = load_settings()
    sink = ListUsageSink()
    llm = get_llm_provider(settings, sink)
    tts = get_tts_provider(settings)
    music = get_music_provider(settings)
    providers = [p for p in get_stock_providers(settings) if await p.healthcheck()]
    if not (llm and tts and music and providers):
        print(f"prereqs — llm={bool(llm)} tts={bool(tts)} music={bool(music)} stock={[p.name() for p in providers]}")
        raise SystemExit(2)

    conn = await psycopg.AsyncConnection.connect(settings.dsn(), row_factory=dict_row, autocommit=True)
    ch = await repo.channels.get_by_slug(conn, "wildlife")
    notifier, bot = await _make_notifier(settings)
    root = f"assets/produced/next-{subject}"

    print(f"=== REAL PRODUCTION (refactored resumable path) — subject '{subject}', {n_beats} beats, ~{runtime}s ===")
    print("stages: script → source (film-wide) → TTS → design → assemble → submit; publish = DRY RUN gate\n")

    res = await produce.produce_video(
        conn, notifier, channel=ch, topic=subject, providers=providers, tts=tts, music=music,
        script_writer=ScriptWriter(llm), llm_provider=llm, usage_sink=sink, description_exemplar=None,
        publisher=DryRunPublisher(), chat_id=settings.chat_id,
        dst=os.path.join(root, "output", f"{subject}_scored.mp4"), workdir=os.path.join(root, "work"),
        runtime_target_s=runtime, n_beats=n_beats, budget_credits=4000)

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
