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
        logger.error(f"start_command DB xatosi (user={user.id}): {e}")

    welcome_text = get_text("welcome")

    # Adminlar uchun tezkor panel tugmasi
    if is_admin(user.id):
        keyboard = ReplyKeyboardMarkup(
            [["🛠 Admin panel"]],
            resize_keyboard=True,
            is_persistent=True,
        )
    else:
        keyboard = ReplyKeyboardRemove()

    await update.message.reply_text(
        welcome_text,
        parse_mode="HTML",
        disable_web_page_preview=True,
        reply_markup=keyboard,
    )
