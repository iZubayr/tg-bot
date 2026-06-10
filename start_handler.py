import logging
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import ContextTypes
from database import get_or_create_user, get_text, is_admin

logger = logging.getLogger(__name__)


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    try:
        get_or_create_user(user.id, user.first_name, user.username)
    except Exception as e:
        logger.error(f"start: {e}")

    kb = (
        ReplyKeyboardMarkup([["🛠 Admin panel"]], resize_keyboard=True, is_persistent=True)
        if is_admin(user.id)
        else ReplyKeyboardRemove()
    )

    await update.message.reply_text(
        get_text("welcome"),
        parse_mode="HTML",
        disable_web_page_preview=True,
        reply_markup=kb,
    )
