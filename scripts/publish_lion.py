"""Publish the lion — the agent does it itself, gated behind Banks's Telegram approve.

Submits a `publish_public` approval for the already-uploaded lion (yGdNuUB5f_I): on approve, the BOT
sets the CLEAN latest-authored description and flips the video to PUBLIC on @TheTalesofWildlifeandNature
(channel verified). It replaces the leaked legacy description in the same action, so the video is clean
the instant it goes public.

PRECONDITIONS (do these first — the live path fails without them):
  1. Re-auth with youtube.force-ssl:  ./.venv/bin/python -m ytagent.youtube_auth   (upload-only can't update)
  2. Rebuild the bot so it has the new code + token:  docker compose up -d --build telegram-bot
This runner only SENDS the approval card; the bot performs the update_public on your tap.

Run: POSTGRES_HOST=localhost POSTGRES_PORT=5433 ./.venv/bin/python -m scripts.publish_lion
"""
from __future__ import annotations

import asyncio

import psycopg
from psycopg.rows import dict_row

from ytagent import orchestrator, repo
from ytagent.config import load_settings
from ytagent.metadata.guard import scan
from ytagent.notifier import StubNotifier

_LION_YT_ID = "yGdNuUB5f_I"


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


def _live_available(settings) -> bool:
    return bool(settings.youtube_refresh_token and settings.youtube_client_id
               and settings.youtube_client_secret)


async def run():
    settings = load_settings()
    conn = await psycopg.AsyncConnection.connect(settings.dsn(), row_factory=dict_row, autocommit=True)
    ch = await repo.channels.get_by_slug(conn, "wildlife")

    video = await (await conn.execute(
        "SELECT * FROM videos WHERE youtube_video_id=%s", [_LION_YT_ID])).fetchone()
    if video is None:
        print(f"no lion video row for {_LION_YT_ID}"); await conn.close(); raise SystemExit(2)

    clean = await repo.metadata.get_latest_authored(conn, video["id"])
    if clean is None:
        print("no authored description version found"); await conn.close(); raise SystemExit(2)
    hits = scan(clean["title"], clean["description"], *[str(t) for t in (clean["tags"] or [])])
    if hits:
        print(f"REFUSING: latest authored description trips the guard: {hits}")
        await conn.close(); raise SystemExit(2)

    mode = "live" if _live_available(settings) else "dry_run"
    chan_id = (ch.get("config") or {}).get("youtube_channel_id")
    print(f"=== PUBLISH LION — '{clean['title']}' → PUBLIC ===")
    print(f"video: #{video['id']}  youtube_id={_LION_YT_ID}  current_privacy={video['privacy_status']}")
    print(f"target channel: {chan_id}  ({(ch.get('config') or {}).get('youtube_handle')})")
    print(f"clean description v{clean['version']} [{clean['source']}] — guard: clean ✅")
    print(f"publish_mode: {mode}" + ("" if mode == "live" else "  (no force-ssl token yet — DRY RUN)"))
    if mode == "live" and video["privacy_status"] == "public":
        print("already PUBLIC — nothing to do."); await conn.close(); return

    notifier, bot = await _make_notifier(settings)
    sub = await orchestrator.submit_publish_for_approval(
        conn, notifier, channel=ch, video=video, clean=clean, chat_id=settings.chat_id, publish_mode=mode)
    print(f"\nApproval card sent (job {sub['job']['id']}, approval {sub['approval']['id']}). "
          "Tap ✅ in Telegram to publish; the bot performs the update.")
    if bot:
        await bot.shutdown()
    await conn.close()


if __name__ == "__main__":
    asyncio.run(run())
