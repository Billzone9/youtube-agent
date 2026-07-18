"""LIVE proof — one complete NEW video made end to end (topic: grey wolf).

writer → sourcing → TTS → binder → assembly → Telegram approval (→ private upload on approve).
Needs: ANTHROPIC_API_KEY (script + description), PEXELS/PIXABAY (footage, free), ELEVENLABS_API_KEY
with TTS scope (narration — the human precondition), and (for Pass B) YOUTUBE_* + the running bot.

Default = Pass A (DryRunPublisher: full pipeline, real spend on script+TTS, NO upload). Set
PROVE_E2E_LIVE=1 for Pass B (YouTubePublisher: the Telegram card's Approve triggers the real PRIVATE
upload via the running bot). Run only on Banks's go:
  POSTGRES_HOST=localhost POSTGRES_PORT=5433 ./.venv/bin/python -m scripts.prove_e2e
"""
from __future__ import annotations

import asyncio
import os
import pathlib
import sys
import tempfile

import psycopg
from psycopg.rows import dict_row

from ytagent import produce, repo
from ytagent.authoring.script import ScriptWriter
from ytagent.budget import budget_status
from ytagent.config import load_settings
from ytagent.metadata.lion_reference import build_lion_reference
from ytagent.notifier import StubNotifier
from ytagent.providers import ListUsageSink, get_llm_provider
from ytagent.publish import DryRunPublisher
from ytagent.sourcing import get_stock_providers
from ytagent.tts import get_tts_provider

_TOPIC = ("the grey wolf through a northern winter — the pack, the hunt in the snow, the howl that "
          "carries across the forest at dusk")
_DST = "assets/produced/wolf.mp4"


async def _notifier(settings):
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
    providers = [p for p in get_stock_providers(settings) if await p.healthcheck()]
    if not (llm and tts and providers):
        print(f"Missing prerequisites — llm={bool(llm)} tts={bool(tts)} stock={[p.name() for p in providers]}"
              " (ELEVENLABS TTS scope is the likely blocker).")
        sys.exit(2)

    live = os.environ.get("PROVE_E2E_LIVE") == "1"
    if live:
        from ytagent.youtube import YouTubePublisher
        publisher = YouTubePublisher(settings)
        print("=== PASS B — LIVE: approve in Telegram → real PRIVATE upload (via the running bot) ===")
    else:
        publisher = DryRunPublisher()
        print("=== PASS A — DRY RUN: full pipeline, real script+TTS spend, NO upload ===")

    script_writer = ScriptWriter(llm, exemplar_text=pathlib.Path("lion-doc-01-script.md").read_text())
    # Pass A (dry run) uses the STUB notifier on purpose: a real Telegram approval card, if clicked,
    # would trigger the running bot's LIVE publisher = a real upload. Real Telegram only for Pass B.
    notifier, bot = (await _notifier(settings)) if live else (StubNotifier(), None)
    conn = await psycopg.AsyncConnection.connect(settings.dsn(), row_factory=dict_row, autocommit=True)
    try:
        channel = await repo.channels.get_by_slug(conn, "wildlife")
        os.makedirs(os.path.dirname(_DST), exist_ok=True)
        res = await produce.produce_video(
            conn, notifier, channel=channel, topic=_TOPIC, providers=providers, tts=tts,
            script_writer=script_writer, llm_provider=llm, usage_sink=sink,
            description_exemplar=build_lion_reference(), publisher=publisher,
            chat_id=settings.chat_id, dst=_DST, workdir=tempfile.mkdtemp(prefix="e2e-"),
            runtime_target_s=150, n_beats=4)

        s, r = res["script"], res["result"]
        print(f"\nSCRIPT: {s.title} — {len(s.beats)} beats, {s.word_count} words")
        for b in s.beats:
            a = res["sourced"][b.index]
            print(f"  beat{b.index} '{b.label}': {a.source}:{a.asset_id} ({a.candidate.page_url})")
        m = r.qc
        print(f"\nMASTER: {r.output_path}  {m['width']}x{m['height']}@{m['fps']}  {m['duration_s']}s  "
              f"{m['loudness_lufs']} LUFS  noise {'clean' if r.noise_gate.ok else 'FAIL'}")
        print(f"\nDESCRIPTION (authored):\n{res['description'].description}")
        print(f"\ntags: {', '.join(res['description'].tags)}")
        bud = await budget_status(conn)
        print(f"\nsubmitted for approval ({publisher.mode}) — job #{res['job_id']}, "
              f"video #{res['submit']['video']['id']}")
        print(f"month-to-date: £{bud['month_spend_gbp']:.2f} / £{bud['ceiling_gbp']:.0f} ({bud['tier']})")
        if not live:
            print("\n(Pass A dry-run: no upload. Re-run with PROVE_E2E_LIVE=1 for the real private upload.)")
    finally:
        if bot is not None:
            await bot.shutdown()
        await conn.close()


if __name__ == "__main__":
    asyncio.run(run())
