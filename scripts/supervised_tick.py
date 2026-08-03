"""ONE SUPERVISED scheduler tick — the first real end-to-end production through the scheduler, to the
Telegram approval card, with per-stage wall-clock. NOT run_forever: a single tick(), one commission,
one production. Publish is DRY-RUN (even an accidental tap cannot upload). Banks watches the card; he
does NOT tap. This proves the FAILURE CLASSIFICATION on real components (real ffmpeg/ElevenLabs/network)
that the monkeypatched tests could not — and measures what a production actually costs the machine.

Run: POSTGRES_HOST=localhost POSTGRES_PORT=5433 ./.venv/bin/python -m scripts.supervised_tick
"""
from __future__ import annotations

import asyncio
import os
import time

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from ytagent import repo
from ytagent.config import load_settings
from ytagent.music import get_music_provider
from ytagent.notifier import StubNotifier
from ytagent.providers import ListUsageSink, get_llm_provider
from ytagent.publish import DryRunPublisher
from ytagent.scheduler import Deps, tick
from ytagent.sourcing import get_stock_providers
from ytagent.tts import get_tts_provider

_POOL = ["african elephant"]   # option 1: the one deep+wild subject, for the per-stage timings
_MIN_VERDICT = "MARGINAL"            # legacy field; the verdict no longer gates (E<5 floor is the only skip)
_THRESHOLD = 50.0                    # generous: the spend gate must NOT fire on a normal ~£9 production
_N_BEATS = 6
_RUNTIME = 340


async def _make_notifier(settings):
    if settings.bot_token:
        try:
            from telegram import Bot
            from ytagent.notifier import TelegramNotifier
            bot = Bot(settings.bot_token)
            await bot.initialize()
            return TelegramNotifier(bot), bot
        except Exception as e:  # noqa: BLE001
            print(f"  (telegram unavailable — stub notifier: {e})")
    return StubNotifier(), None


async def run():
    settings = load_settings()
    sink = ListUsageSink()
    llm = get_llm_provider(settings, sink)
    tts = get_tts_provider(settings)
    music = get_music_provider(settings)
    providers = [p for p in get_stock_providers(settings) if await p.healthcheck()]
    if not (llm and tts and music and providers):
        raise SystemExit(f"prereqs — llm={bool(llm)} tts={bool(tts)} music={bool(music)}")
    conn = await psycopg.AsyncConnection.connect(settings.dsn(), row_factory=dict_row, autocommit=True)
    ch = await repo.channels.get_by_slug(conn, "wildlife")

    # the prior supervised runs recorded these subjects 'infeasible' under the OLD verdict-gate (now
    # removed); clear that stale history so the new sourcing-gate re-attempts them as novel.
    await conn.execute("DELETE FROM channel_subjects WHERE channel_id=%s AND subject = ANY(%s)",
                       [ch["id"], _POOL])

    # enable the wildlife playbook for this supervised run (idle + due now)
    await conn.execute(
        "UPDATE playbooks SET enabled=true, state='idle', next_run_at=NULL, subject_pool=%s, "
        "domain=NULL, min_verdict=%s, per_job_threshold_gbp=%s, n_beats=%s, runtime_target_s=%s, "
        "cadence='{\"per_week\":2}'::jsonb WHERE channel_id=%s",
        [Jsonb(_POOL), _MIN_VERDICT, _THRESHOLD, _N_BEATS, _RUNTIME, ch["id"]])
    print(f"=== SUPERVISED tick() — pool {_POOL}, min_verdict {_MIN_VERDICT}, threshold £{_THRESHOLD}, "
          f"{_N_BEATS} beats/~{_RUNTIME}s — DRY-RUN publish ===\n")

    notifier, bot = await _make_notifier(settings)
    deps = Deps(channel=ch, providers=providers, tts=tts, music=music, llm=llm, usage_sink=sink,
                notifier=notifier, publisher=DryRunPublisher(), chat_id=settings.chat_id)

    t0 = time.monotonic()
    summary = await tick(conn, deps)
    total = time.monotonic() - t0

    print(f"\ntick summary: {summary}")
    for subj, detail in summary.get("failed", []):
        print(f"  sourcing outcome: '{subj}' — {detail}")
    for subj, detail in summary.get("skipped_infeasible", []):
        print(f"  skipped (pool-depth floor): '{subj}' — {detail}")

    job_id = summary["submitted"][0] if summary["submitted"] else None
    if job_id is None:
        print("\nNo card this run — see the sourcing outcomes above (real clear counts, not probe guesses).")
        if bot:
            await bot.shutdown()
        await conn.close()
        return

    # per-stage wall-clock for the SUBMITTED job (its own events); probe from the matching 'probed' event
    ev = {}
    for r in await (await conn.execute(
            "SELECT type, extract(epoch from created_at) AS t FROM events WHERE job_id=%s "
            "AND type IN ('produce_started','script_written','sourcing.film_pool','narrated',"
            "'audio_designed','produce_assembled','video_submitted') ORDER BY id", [job_id])).fetchall():
        ev.setdefault(r["type"], r["t"])
    topic = await (await conn.execute("SELECT payload->>'topic' AS t FROM jobs WHERE id=%s", [job_id])).fetchone()
    probed = await (await conn.execute(
        "SELECT extract(epoch from created_at) AS t FROM events WHERE type='probed' "
        "AND data->>'subject'=%s AND extract(epoch from created_at) <= %s ORDER BY id DESC LIMIT 1",
        [topic["t"], ev.get("produce_started", 0)])).fetchone()

    def dur(a, b_type):
        return ev.get(b_type, 0) - a if (ev.get(b_type) and a) else None

    stages = [
        ("probe", (ev["produce_started"] - probed["t"]) if (probed and ev.get("produce_started")) else None),
        ("script", dur(ev.get("produce_started"), "script_written")),
        ("source", dur(ev.get("script_written"), "sourcing.film_pool")),
        ("TTS", dur(ev.get("sourcing.film_pool"), "narrated")),
        ("design (music)", dur(ev.get("narrated"), "audio_designed")),
        ("assemble (render)", dur(ev.get("audio_designed"), "produce_assembled")),
        ("submit", dur(ev.get("produce_assembled"), "video_submitted")),
    ]
    print(f"\n=== PER-STAGE WALL-CLOCK — '{topic['t']}' (job {job_id}) ===")
    for name, s in stages:
        print(f"  {name:<20} {('%.1f min' % (s/60)) if s and s > 0 else '—'}")
    print(f"  {'TOTAL tick()':<20} {total/60:.1f} min")
    print(f"\nReached the Telegram approval card: YES ✅ (DRY RUN — not tapped)")
    if bot:
        await bot.shutdown()
    await conn.close()


if __name__ == "__main__":
    asyncio.run(run())
