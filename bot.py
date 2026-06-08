import os
import logging
import asyncio
from aiohttp import web
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
)
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from config import BOT_TOKEN
from start_handler import start_command
from admin_handler import admin_command, handle_callback
from message_handler import handle_text, handle_media

logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# ─── Scheduler ────────────────────────────────────────────────────────────────
async def post_init(app: Application) -> None:
    scheduler = AsyncIOScheduler(timezone="UTC")
    scheduler.start()
    app.bot_data["scheduler"] = scheduler
    logger.info("✅ APScheduler ishga tushdi.")

async def post_shutdown(app: Application) -> None:
    scheduler = app.bot_data.get("scheduler")
    if scheduler and scheduler.running:
        scheduler.shutdown()
        logger.info("⛔ APScheduler to'xtatildi.")

# ─── Media filter ─────────────────────────────────────────────────────────────
MEDIA_FILTER = (
    filters.PHOTO

    | filters.AUDIO
    | filters.VOICE
    | filters.VIDEO

    | filters.VIDEO_NOTE
    | filters.Sticker.ALL
    | filters.ANIMATION
    | filters.Document.ALL
)

# ─── Veb-Server (Render'ni uyg'oq tutish uchun eshik) ──────────────────────────
async def handle_home(request):
    """UptimeRobot kirganda shu funksiya javob beradi"""
    return web.Response(text="Bot muvaffaqiyatli ishlamoqda!", status=200)

async def start_web_server():
    """Render beradigan maxsus PORT orqali serverni yoqish"""
    app_web = web.Application()
    app_web.router.add_get('/', handle_home)
    
    # Render o'zi avtomatik PORT raqamini taqdim etadi (masalan, 10000)
    port = int(os.environ.get("PORT", 10000))
    
    runner = web.AppRunner(app_web)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', port)
    await site.start()
    logger.info(f"🌐 Veb-server {port}-portda ishga tushdi.")

# ─── Main ─────────────────────────────────────────────────────────────────────
async def main_async() -> None:
    # 1. Botni quramiz
    app = (
        Application.builder()
        .token(BOT_TOKEN)
        .post_init(post_init)
        .post_shutdown(post_shutdown)
        .build()
    )

    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("admin", admin_command))
    app.add_handler(CallbackQueryHandler(handle_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    app.add_handler(MessageHandler(MEDIA_FILTER & ~filters.COMMAND, handle_media))

    # 2. Veb-serverni parallel fonda ishga tushiramiz
    await start_web_server()

    # 3. Botni Polling rejimida start qilamiz
    logger.info("✅ Bot ishga tushdi (polling+web rejimi)!")
    await app.initialize()
    await app.start()
    await app.updater.start_polling(drop_pending_updates=True)
    
    # Bot fonda to'xtovsiz ishlashi uchun cheksiz sikl
    while True:
        await asyncio.sleep(3600)

def main() -> None:
    # Asosiy async funksiyani ishga tushirish
    asyncio.run(main_async())

if __name__ == "__main__":
    main()
import os
import logging
import asyncio
from aiohttp import web
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
)
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from config import BOT_TOKEN
from start_handler import start_command
from admin_handler import admin_command, handle_callback
from message_handler import handle_text, handle_media

logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# ─── Scheduler ────────────────────────────────────────────────────────────────
async def post_init(app: Application) -> None:
    scheduler = AsyncIOScheduler(timezone="UTC")
    scheduler.start()
    app.bot_data["scheduler"] = scheduler
    logger.info("✅ APScheduler ishga tushdi.")

async def post_shutdown(app: Application) -> None:
    scheduler = app.bot_data.get("scheduler")
    if scheduler and scheduler.running:
        scheduler.shutdown()
        logger.info("⛔ APScheduler to'xtatildi.")

# ─── Media filter ─────────────────────────────────────────────────────────────
MEDIA_FILTER = (
    filters.PHOTO

    | filters.AUDIO
    | filters.VOICE
    | filters.VIDEO

    | filters.VIDEO_NOTE
    | filters.Sticker.ALL
    | filters.ANIMATION
    | filters.Document.ALL
)

# ─── Veb-Server (Render'ni uyg'oq tutish uchun eshik) ──────────────────────────
async def handle_home(request):
    """UptimeRobot kirganda shu funksiya javob beradi"""
    return web.Response(text="Bot muvaffaqiyatli ishlamoqda!", status=200)

async def start_web_server():
    """Render beradigan maxsus PORT orqali serverni yoqish"""
    app_web = web.Application()
    app_web.router.add_get('/', handle_home)
    
    # Render o'zi avtomatik PORT raqamini taqdim etadi (masalan, 10000)
    port = int(os.environ.get("PORT", 10000))
    
    runner = web.AppRunner(app_web)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', port)
    await site.start()
    logger.info(f"🌐 Veb-server {port}-portda ishga tushdi.")

# ─── Main ─────────────────────────────────────────────────────────────────────
async def main_async() -> None:
    # 1. Botni quramiz
    app = (
        Application.builder()
        .token(BOT_TOKEN)
        .post_init(post_init)
        .post_shutdown(post_shutdown)
        .build()
    )

    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("admin", admin_command))
    app.add_handler(CallbackQueryHandler(handle_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    app.add_handler(MessageHandler(MEDIA_FILTER & ~filters.COMMAND, handle_media))

    # 2. Veb-serverni parallel fonda ishga tushiramiz
    await start_web_server()

    # 3. Botni Polling rejimida start qilamiz
    logger.info("✅ Bot ishga tushdi (polling+web rejimi)!")
    await app.initialize()
    await app.start()
    await app.updater.start_polling(drop_pending_updates=True)
    
    # Bot fonda to'xtovsiz ishlashi uchun cheksiz sikl
    while True:
        await asyncio.sleep(3600)

def main() -> None:
    # Asosiy async funksiyani ishga tushirish
    asyncio.run(main_async())

if __name__ == "__main__":
    main()
