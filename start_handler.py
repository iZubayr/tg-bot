import logging
from telegram import Update
from telegram.ext import ContextTypes
from database import get_or_create_user

logger = logging.getLogger(__name__)

WELCOME_TEXT = (
    "Assalamu a'layk 👋\n\n"
    "Agar savolingiz yoki taklifingiz bo'lsa, shu yerga yozib qoldirishingiz mumkin 🙂\n\n"
    "Meni kuzatib borish uchun kanallarim:\n"
    '👉 <a href="https://t.me/+4-8lpgLcdvU5ZTcy">Dev with Zubayr</a>\n'
    "👉 <a href=\"https://t.me/+uKrIs6gQR4JjYjFi\">She'rlar bog'i 🍃</a>"
)


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user

    # DB xatosi bo'lsa ham welcome xabar yuboriladi
    try:
        get_or_create_user(user.id, user.first_name, user.username)
    except Exception as e:
        logger.error(f"start_command DB xatosi (user={user.id}): {e}")

    await update.message.reply_text(
        WELCOME_TEXT,
        parse_mode="HTML",
        disable_web_page_preview=True,
    )
