import asyncio
import logging
from datetime import datetime, timezone, timedelta
from html import escape
from telegram import Update
from telegram.ext import ContextTypes

from config import RATE_LIMIT, RATE_WINDOW, BROADCAST_DELAY
from database import (
    get_or_create_user, get_user, update_user,
    save_message, save_admin_reply,
    save_message_map, get_user_from_map,
    is_admin, get_all_admins, get_all_active_users,
    add_admin, mark_blocked,
)

logger = logging.getLogger(__name__)


# ─── Asosiy kirish nuqtalari ──────────────────────────────────────────────────

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if is_admin(user.id):
        await _handle_admin_text(update, context)
    else:
        await _handle_user_message(update, context)


async def handle_media(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if is_admin(user.id):
        # Admin user xabariga media javob yubormoqda
        if update.message.reply_to_message:
            await _forward_media_reply_to_user(update, context)
        return
    await _handle_user_media(update, context)


# ─── Admin text yo'naltiruvchi ────────────────────────────────────────────────

async def _handle_admin_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message.reply_to_message:
        await _forward_reply_to_user(update, context)
    elif context.user_data.get("waiting_broadcast"):
        await _do_broadcast(update, context)
    elif context.user_data.get("waiting_admin_id"):
        await _do_add_admin(update, context)


async def _forward_reply_to_user(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Admin reply qilgan matnni asl foydalanuvchiga yuboradi."""
    reply_msg_id = update.message.reply_to_message.message_id
    chat_id      = update.effective_chat.id

    user_id = get_user_from_map(reply_msg_id, chat_id)
    if not user_id:
        await update.message.reply_text("❌ Bu xabarning egasi topilmadi.")
        return

    try:
        await context.bot.send_message(user_id, f"📩 Javob:\n\n{update.message.text}")

        try:
            save_admin_reply(update.effective_user.id, user_id, update.message.text or "")
        except Exception as e:
            logger.error(f"save_admin_reply xatosi: {e}")

        await update.message.reply_text("✅ Javob yuborildi.")
    except Exception as e:
        if "Forbidden" in str(e):
            mark_blocked(user_id)
            await update.message.reply_text("🚫 Foydalanuvchi botni bloklagan.")
        else:
            await update.message.reply_text(f"❌ Xato: {e}")


async def _forward_media_reply_to_user(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Admin reply qilgan media ni asl foydalanuvchiga yuboradi."""
    reply_msg_id = update.message.reply_to_message.message_id
    chat_id      = update.effective_chat.id

    user_id = get_user_from_map(reply_msg_id, chat_id)
    if not user_id:
        await update.message.reply_text("❌ Bu xabarning egasi topilmadi.")
        return

    try:
        await context.bot.copy_message(
            chat_id=user_id,
            from_chat_id=chat_id,
            message_id=update.message.message_id,
        )

        try:
            save_admin_reply(update.effective_user.id, user_id, "[media]")
        except Exception as e:
            logger.error(f"save_admin_reply xatosi: {e}")

        await update.message.reply_text("✅ Javob yuborildi.")
    except Exception as e:
        if "Forbidden" in str(e):
            mark_blocked(user_id)
            await update.message.reply_text("🚫 Foydalanuvchi botni bloklagan.")
        else:
            await update.message.reply_text(f"❌ Xato: {e}")


async def _do_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Barcha aktiv foydalanuvchilarga xabar yuboradi."""
    context.user_data.pop("waiting_broadcast", None)
    text  = update.message.text
    users = get_all_active_users()

    if not users:
        await update.message.reply_text("📭 Aktiv foydalanuvchilar yo'q.")
        return

    sent = failed = 0
    total  = len(users)
    status = await update.message.reply_text(f"📢 Yuborilmoqda... 0 / {total}")

    for i, uid in enumerate(users):
        try:
            await context.bot.send_message(uid, text)
            sent += 1
        except Exception as e:
            failed += 1
            if "Forbidden" in str(e):
                mark_blocked(uid)

        await asyncio.sleep(BROADCAST_DELAY)

        if (i + 1) % 25 == 0:
            try:
                await status.edit_text(f"📢 Yuborilmoqda... {i + 1} / {total}")
            except Exception:
                pass

    await status.edit_text(
        f"✅ Broadcast yakunlandi!\n\n"
        f"📤 Yuborildi: {sent}\n"
        f"❌ Xato / Bloklagan: {failed}"
    )


async def _do_add_admin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Yangi admin qo'shadi."""
    context.user_data.pop("waiting_admin_id", None)
    try:
        new_id = int(update.message.text.strip())
        add_admin(new_id)
        await update.message.reply_text(
            f"✅ Admin muvaffaqiyatli qo'shildi!\n🆔 <code>{new_id}</code>",
            parse_mode="HTML",
        )
    except ValueError:
        await update.message.reply_text("❌ Noto'g'ri format. Faqat raqam kiriting.")


# ─── Foydalanuvchi matn xabari ────────────────────────────────────────────────

async def _handle_user_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    text = update.message.text

    try:
        get_or_create_user(user.id, user.first_name, user.username)
    except Exception as e:
        logger.error(f"get_or_create_user xatosi (user={user.id}): {e}")

    try:
        allowed = _check_and_update_rate_limit(user.id, context)
    except Exception as e:
        logger.error(f"rate_limit xatosi: {e}")
        allowed = True

    if not allowed:
        await update.message.reply_text(
            "⚠️ Siz vaqtinchalik xabar yuborish chekloviga yetdingiz.\n"
            "Iltimos, 1 soatdan so'ng qayta yuboring."
        )
        return

    try:
        save_message(user.id, text)
    except Exception as e:
        logger.error(f"save_message xatosi: {e}")

    safe_name = escape(user.first_name or "")
    uname     = f"@{user.username}" if user.username else "—"
    safe_uname = escape(uname)
    safe_text  = escape(text)

    # ✅ HTML parse_mode bilan to'g'ri format
    admin_text = (
        f"👤 <b>{safe_name}</b>\n"
        f"🆔 <code>{user.id}</code> · {safe_uname}\n"
        f"──────────────────\n"
        f"💬 {safe_text}"
    )

    for admin_id in get_all_admins():
        try:
            sent = await context.bot.send_message(
                admin_id,
                admin_text,
                parse_mode="HTML",
            )
            try:
                save_message_map(sent.message_id, admin_id, user.id)
            except Exception as e:
                logger.error(f"save_message_map xatosi: {e}")
        except Exception as e:
            logger.error(f"Admin {admin_id} ga yuborishda xato: {e}")

    await update.message.reply_text(
        "✅ Xabaringiz yetkazildi, tez orada javob beriladi 🙂"
    )


# ─── Foydalanuvchi media xabari ───────────────────────────────────────────────

async def _handle_user_media(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    msg  = update.message

    if msg.photo:
        media_type = "📷 Rasm"
    elif msg.video:
        media_type = "🎥 Video"
    elif msg.audio:
        media_type = "🎵 Audio"
    elif msg.voice:
        media_type = "🎙 Ovozli xabar"
    elif msg.sticker:
        media_type = "🎭 Stiker"
    elif msg.animation:
        media_type = "🎞 GIF"
    elif msg.video_note:
        media_type = "⭕ Video xabar"
    elif msg.document:
        media_type = "📎 Fayl"
    else:
        media_type = "📎 Media"

    try:
        get_or_create_user(user.id, user.first_name, user.username)
    except Exception as e:
        logger.error(f"get_or_create_user xatosi: {e}")

    safe_name  = escape(user.first_name or "")
    uname      = f"@{user.username}" if user.username else "—"
    safe_uname = escape(uname)

    # Header — kim yubordi + media turi
    header = (
        f"👤 <b>{safe_name}</b>\n"
        f"🆔 <code>{user.id}</code> · {safe_uname}\n"
        f"──────────────────\n"
        f"{media_type}"
    )

    for admin_id in get_all_admins():
        try:
            # 1. Kim yubordi — matn header
            await context.bot.send_message(admin_id, header, parse_mode="HTML")

            # 2. Medianing o'zi — copy_message qaytaradigan ID ni message_map ga saqlaymiz
            copied = await context.bot.copy_message(
                chat_id=admin_id,
                from_chat_id=msg.chat_id,
                message_id=msg.message_id,
            )
            try:
                save_message_map(copied.message_id, admin_id, user.id)
            except Exception as e:
                logger.error(f"save_message_map xatosi: {e}")

        except Exception as e:
            logger.error(f"Admin {admin_id} ga yuborishda xato: {e}")

    await update.message.reply_text(
        "✅ Xabaringiz yetkazildi, tez orada javob beriladi 🙂"
    )


# ─── Rate limit ───────────────────────────────────────────────────────────────

def _check_and_update_rate_limit(user_id: int, context) -> bool:
    """True = ruxsat. False = limit to'lgan."""
    db_user = get_user(user_id)
    if not db_user:
        return True

    msg_count = db_user.get("msg_count", 0)
    raw_reset = db_user.get("rate_reset_at")
    now       = datetime.now(timezone.utc)

    reset_time = None
    if raw_reset:
        reset_time = (
            datetime.fromisoformat(raw_reset.replace("Z", "+00:00"))
            if isinstance(raw_reset, str) else raw_reset
        )

    if reset_time and now > reset_time:
        update_user(user_id, msg_count=0, rate_reset_at=None)
        msg_count  = 0
        reset_time = None

    if reset_time and msg_count >= RATE_LIMIT:
        return False

    if msg_count == 0 and not reset_time:
        new_reset = now + timedelta(seconds=RATE_WINDOW)
        update_user(user_id, msg_count=1, rate_reset_at=new_reset.isoformat())
        _schedule_reset_notification(context, user_id, new_reset)
    else:
        update_user(user_id, msg_count=msg_count + 1)

    return True


def _schedule_reset_notification(context, user_id: int, reset_at: datetime) -> None:
    scheduler = context.bot_data.get("scheduler")
    if not scheduler:
        return

    job_id = f"rate_reset_{user_id}"
    try:
        scheduler.remove_job(job_id)
    except Exception:
        pass

    scheduler.add_job(
        _send_reset_notification,
        "date",
        run_date=reset_at,
        args=[context.bot, user_id],
        id=job_id,
    )


async def _send_reset_notification(bot, user_id: int) -> None:
    try:
        await bot.send_message(user_id, "✅ Endi yana yozishingiz mumkin!")
    except Exception:
        pass
