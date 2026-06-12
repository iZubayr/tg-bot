import os
import asyncio
import logging
from aiohttp import web
from telegram import Update
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    CallbackQueryHandler, filters,
)
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from config import BOT_TOKEN
from start_handler import start_command
from admin_handler import admin_command, handle_callback
from message_handler import handle_text, handle_media, handle_edited, info_command

logging.basicConfig(format="%(asctime)s | %(levelname)s | %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

MEDIA_FILTER = (
    filters.PHOTO | filters.AUDIO | filters.VOICE | filters.VIDEO
    | filters.VIDEO_NOTE | filters.Sticker.ALL | filters.ANIMATION
    | filters.Document.ALL
)


async def global_error_handler(update: object, context) -> None:
    logger.error(f"Xato: {context.error}", exc_info=context.error)
    if isinstance(update, Update) and update.effective_message:
        try:
            await update.effective_message.reply_text("⚠️ Ichki xato yuz berdi. Iltimos qayta urinib ko'ring.")
        except Exception:
            pass


async def post_init(app: Application) -> None:
    scheduler = AsyncIOScheduler(timezone="UTC")
    scheduler.start()
    app.bot_data["scheduler"] = scheduler
    logger.info("✅ APScheduler ishga tushdi.")
    await _restore_broadcasts(app, scheduler)
    _restore_reminder(app.bot, scheduler)


async def post_shutdown(app: Application) -> None:
    s = app.bot_data.get("scheduler")
    if s and s.running:
        s.shutdown()
        logger.info("⛔ APScheduler to'xtatildi.")


async def _restore_broadcasts(app: Application, scheduler) -> None:
    from database import get_pending_broadcasts, delete_scheduled_broadcast
    from message_handler import _run_broadcast_job
    from datetime import datetime, timezone
    for bc in get_pending_broadcasts():
        try:
            dt = datetime.fromisoformat(bc["scheduled_at"])
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            if dt <= datetime.now(timezone.utc):
                asyncio.create_task(_run_broadcast_job(
                    app.bot, bc["id"], bc["from_chat_id"], bc["message_id"]
                ))
            else:
                scheduler.add_job(
                    _run_broadcast_job, "date", run_date=dt,
                    args=[app.bot, bc["id"], bc["from_chat_id"], bc["message_id"]],
                    id=f"bc_{bc['id']}", replace_existing=True,
                )
        except Exception as e:
            logger.error(f"Broadcast restore: {e}")


def _restore_reminder(bot, scheduler) -> None:
    from database import get_setting
    from message_handler import _send_reminder
    if get_setting("reminder_enabled") == "true":
        interval = int(get_setting("reminder_interval") or 2)
        scheduler.add_job(
            _send_reminder, "interval", hours=interval,
            args=[bot], id="reminder_job", replace_existing=True,
        )


async def _health(request):
    return web.Response(text="OK", status=200)


async def main_async() -> None:
    app = (
        Application.builder()
        .token(BOT_TOKEN)
        .post_init(post_init)
        .post_shutdown(post_shutdown)
        .build()
    )

    app.add_error_handler(global_error_handler)

    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("admin", admin_command))
    app.add_handler(CommandHandler("info",  info_command))
    app.add_handler(CallbackQueryHandler(handle_callback))

    # "🛠 Admin panel" tugmasi
    app.add_handler(MessageHandler(
        filters.Text(["🛠 Admin panel"]) & ~filters.COMMAND, admin_command
    ))

    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    app.add_handler(MessageHandler(MEDIA_FILTER & ~filters.COMMAND, handle_media))

    # Admin o'z javobini tahrirlasa — user tomonida ham yangilanadi
    app.add_handler(MessageHandler(filters.UpdateType.EDITED_MESSAGE, handle_edited))

    # Render uchun web server (port binding)
    web_app = web.Application()
    web_app.router.add_get("/", _health)
    port = int(os.environ.get("PORT", 10000))
    runner = web.AppRunner(web_app)
    await runner.setup()
    await web.TCPSite(runner, "0.0.0.0", port).start()
    logger.info(f"🌐 Web server :{port}")

    await app.initialize()
    await app.start()
    await app.updater.start_polling(drop_pending_updates=True)
    logger.info("✅ Bot ishga tushdi!")

    while True:
        await asyncio.sleep(3600)


def main():
    asyncio.run(main_async())


if __name__ == "__main__":
    main()
