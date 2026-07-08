"""Thin Telegram shell. Knows Telegram I/O only; all business logic lives in the orchestrator.
Startup: wait_for_db -> migrate -> seed -> open pool -> poll.  CLI: python -m ytagent.bot
"""
from __future__ import annotations

from telegram import Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
)

from . import orchestrator, repo
from .artifacts import lion_video_meta
from .config import Settings, load_settings
from .db import make_pool, wait_for_db
from .migrations.runner import run_migrations
from .notifier import TelegramNotifier, parse_approval_callback
from .publish import DryRunPublisher
from .seed import run_seed


def _build_publisher(settings: Settings):
    """YouTubePublisher when a refresh token is configured; else the dry-run publisher."""
    if settings.youtube_refresh_token:
        from .youtube import YouTubePublisher  # imported lazily (needs the google libs)

        return YouTubePublisher(settings)
    return DryRunPublisher()


def _is_operator(update: Update, settings: Settings) -> bool:
    chat = update.effective_chat
    return chat is not None and str(chat.id) == str(settings.chat_id)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        f"YouTube Agent online. Your chat ID is {update.effective_chat.id}. Try /ping or /submit_lion."
    )


async def ping(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text("pong — the agent is alive and listening.")


async def submit_lion(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    settings = context.application.bot_data["settings"]
    if not _is_operator(update, settings):
        return
    pool = context.application.bot_data["pool"]
    notifier = context.application.bot_data["notifier"]
    publisher = context.application.bot_data["publisher"]
    async with pool.connection() as conn:
        channel = await repo.channels.get_by_slug(conn, "wildlife")
        if channel is None:
            await update.message.reply_text("No 'wildlife' channel found — seed has not run.")
            return
        res = await orchestrator.submit_video_for_approval(
            conn, notifier, channel=channel, video_meta=lion_video_meta(),
            chat_id=settings.chat_id, publish_mode=publisher.mode,
        )
    await update.message.reply_text(
        f"Submitted job #{res['job']['id']} (video #{res['video']['id']}). "
        f"Approval request sent ({publisher.mode})."
    )


async def on_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    await q.answer()
    settings = context.application.bot_data["settings"]
    if q.message is None or str(q.message.chat_id) != str(settings.chat_id):
        return
    parsed = parse_approval_callback(q.data or "")
    if parsed is None:
        return
    approval_id, decision = parsed
    pool = context.application.bot_data["pool"]
    notifier = context.application.bot_data["notifier"]
    publisher = context.application.bot_data["publisher"]
    async with pool.connection() as conn:
        await orchestrator.handle_decision(
            conn, notifier, publisher, approval_id=approval_id, decision=decision, decided_by="banks"
        )


async def _post_init(app: Application) -> None:
    await app.bot_data["pool"].open()
    await app.bot_data["pool"].wait()
    print("[bot] db pool open; polling for updates")


async def _post_shutdown(app: Application) -> None:
    await app.bot_data["pool"].close()


def main() -> None:
    settings = load_settings()
    print(f"[bot] starting; {settings.safe_summary()}")
    wait_for_db(settings)
    run_migrations(settings)
    run_seed()

    pool = make_pool(settings)
    app = (
        Application.builder()
        .token(settings.bot_token)
        .post_init(_post_init)
        .post_shutdown(_post_shutdown)
        .build()
    )
    app.bot_data.update(
        pool=pool, settings=settings, notifier=TelegramNotifier(app.bot),
        publisher=_build_publisher(settings),
    )
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("ping", ping))
    app.add_handler(CommandHandler("submit_lion", submit_lion))
    app.add_handler(CallbackQueryHandler(on_callback))
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
