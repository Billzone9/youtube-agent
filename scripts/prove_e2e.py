"""LIVE proof — RE-MAKE the wolf to the visual-density standard, REUSING its narration (no TTS spend).

Reuses the four preserved narration mp3s (assets/produced/wolf/narration/), re-sources N DISTINCT
clips per beat (the density standard), binds → density gate → assembles → submits for approval.
writer/TTS are skipped; the treasured VO is untouched. Sourcing is free; the only spend is a few pence
of description LLM.

Default = Pass A (DryRunPublisher: full re-make, NO upload). Set PROVE_E2E_LIVE=1 for Pass B
(YouTubePublisher: the Telegram card's Approve triggers the real PRIVATE upload via the running bot).
  POSTGRES_HOST=localhost POSTGRES_PORT=5433 ./.venv/bin/python -m scripts.prove_e2e
"""
from __future__ import annotations

import asyncio
import os
import tempfile

import psycopg
from psycopg.rows import dict_row

from ytagent import produce, repo
from ytagent.authoring.script import Beat, Fact, Script
from ytagent.budget import budget_status
from ytagent.config import load_settings
from ytagent.metadata.lion_reference import build_lion_reference
from ytagent.notifier import StubNotifier
from ytagent.providers import ListUsageSink, get_llm_provider
from ytagent.publish import DryRunPublisher
from ytagent.sourcing import get_stock_providers

_TOPIC = ("the grey wolf through a northern winter — the pack, the hunt in the snow, the howl that "
          "carries across the forest at dusk")
_NARR = "assets/produced/wolf/narration"
_DST = "assets/produced/wolf.mp4"

# Reconstructed from job 29's beat LABELS (the shot-briefs weren't persisted; the VO mp3s are intact).
# These steer sourcing only — they never touch the narration.
_BEATS = [
    (1, "Before the pack wakes",
     "grey wolf pack resting in snowy boreal forest before dawn, wolves lying in snow, misty winter woods"),
    (2, "A life made for the cold",
     "grey wolf with thick winter coat walking and trotting through deep snow, wolf in falling snow"),
    (3, "Reading the snow",
     "grey wolf nose to the ground tracking a scent, wolf pack moving single file through deep snow"),
    (4, "The howl at the edge of dark",
     "grey wolf howling at dusk, lone wolf silhouette against twilight, wolf in the evening forest"),
]
_FACTS = [
    Fact("Wolves have a dense double-layered coat that insulates them against extreme cold", True),
    Fact("Wolves have broad paws that spread their weight across the snowpack", True),
    Fact("A wolf pack often travels single file so each wolf treads a path already broken, saving energy", True),
    Fact("A wolf's sense of smell is many times more acute than a human's", True),
    Fact("A wolf's howl can carry several kilometres across open country", True),
]


def _reconstructed_script():
    beats = tuple(Beat(index=i, label=lbl, shot_brief=brief, vo="", approx_seconds=40)
                  for i, lbl, brief in _BEATS)
    return Script(title="Wolf", runtime_target_s=160, word_target=340, beats=beats,
                  facts_used=tuple(_FACTS), provenance={"reused_narration": True})


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
    providers = [p for p in get_stock_providers(settings) if await p.healthcheck()]
    narration = {i: os.path.abspath(os.path.join(_NARR, f"narr_beat{i}.mp3")) for i, _, _ in _BEATS}
    missing = [p for p in narration.values() if not os.path.exists(p)]
    if not (llm and providers) or missing:
        print(f"Missing prerequisites — llm={bool(llm)} stock={[p.name() for p in providers]} "
              f"missing_narration={missing}")
        raise SystemExit(2)

    live = os.environ.get("PROVE_E2E_LIVE") == "1"
    if live:
        from ytagent.youtube import YouTubePublisher
        publisher = YouTubePublisher(settings)
        notifier, bot = await _notifier(settings)
        print("=== PASS B — LIVE: approve in Telegram → real PRIVATE upload (via the running bot) ===")
    else:
        publisher = DryRunPublisher()
        notifier, bot = StubNotifier(), None   # dry run must not send a card the live bot could act on
        print("=== PASS A — DRY RUN re-make (reuse narration), NO upload ===")

    conn = await psycopg.AsyncConnection.connect(settings.dsn(), row_factory=dict_row, autocommit=True)
    try:
        channel = await repo.channels.get_by_slug(conn, "wildlife")
        res = await produce.remake_from_narration(
            conn, notifier, channel=channel, topic=_TOPIC, script=_reconstructed_script(),
            narration_paths=narration, providers=providers, llm_provider=llm, usage_sink=sink,
            description_exemplar=build_lion_reference(), publisher=publisher,
            chat_id=settings.chat_id, dst=_DST, workdir=tempfile.mkdtemp(prefix="wolf-remake-"))

        r, dens = res["result"], res["density"]
        print(f"\nRE-MADE: {res['script'].title} — {len(res['sourced'])} beats")
        for b in res["script"].beats:
            assets = res["sourced"][b.index]
            d = dens[f"beat{b.index}"]
            print(f"  beat{b.index} '{b.label}': {len(assets)} distinct shots @ ~{d['shot_s']}s each "
                  f"(min {d['min']}, {d['length_s']}s narration)")
            for a in assets:
                print(f"      - {a.source}:{a.asset_id}  {a.candidate.page_url}")
        m = r.qc
        print(f"\nMASTER: {r.output_path}  {m['width']}x{m['height']}@{m['fps']}  {m['duration_s']}s  "
              f"{m['loudness_lufs']} LUFS  noise {'clean' if r.noise_gate.ok else 'FAIL'}")
        total_shots = sum(len(v) for v in res["sourced"].values())
        print(f"total distinct shots: {total_shots} across {len(res['sourced'])} beats "
              f"(lion reference: 17 across 7)")
        print(f"\nDESCRIPTION (authored):\n{res['description'].description}")
        bud = await budget_status(conn)
        print(f"\nsubmitted for approval ({publisher.mode}) — job #{res['job_id']}, "
              f"video #{res['submit']['video']['id']}")
        print(f"month-to-date: £{bud['month_spend_gbp']:.2f} / £{bud['ceiling_gbp']:.0f} ({bud['tier']})")
        if not live:
            print("\n(Pass A dry-run: no upload, no TTS spent. Re-run with PROVE_E2E_LIVE=1 for the "
                  "real private upload once the visuals are approved.)")
    finally:
        if bot is not None:
            await bot.shutdown()
        await conn.close()


if __name__ == "__main__":
    asyncio.run(run())
