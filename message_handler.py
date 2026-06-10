import asyncio
import logging
from datetime import datetime, timezone, timedelta
from html import escape
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from config import RATE_LIMIT, RATE_WINDOW, BROADCAST_DELAY
from database import (
    get_or_create_user, get_user, update_user,
    save_message, save_admin_reply,
    save_message_map, get_message_map_row,
    is_admin, get_all_admins, get_all_active_users,
    add_admin, mark_blocked, get_text, set_text,
    TEXT_LABELS, set_vip, get_setting,
    update_message_status, save_scheduled_broadcast,
    search_users, get_user_message_count,
)

logger = logging.getLogger(__name__)


# ─── Kirish nuqtalari ─────────────────────────────────────────────────────────

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if is_admin(update.effective_user.id):
        await _handle_admin_text(update, context)
    else:
        await _handle_user_message(update, context)


async def handle_media(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if is_admin(user.id):
        msg = update.message
        if msg.reply_to_message:
            context.user_data.pop("replying_to", None)
            await _forward_media_reply(update, context)
        elif context.user_data.get("waiting_broadcast"):
            await _do_broadcast(update, context)
        elif context.user_data.get("replying_to"):
            await _do_direct_media_reply(update, context)
        elif context.user_data.get("waiting_bc_message"):
            await _do_save_bc_message(update, context)
        return
    await _handle_user_media(update, context)


# ─── Admin text yo'naltiruvchi ────────────────────────────────────────────────

async def _handle_admin_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    ud = context.user_data
    msg = update.message

    if msg.reply_to_message:
        context.user_data.pop("replying_to", None)
        await _forward_text_reply(update, context)
    elif ud.get("waiting_broadcast"):
        await _do_broadcast(update, context)
    elif ud.get("waiting_admin_id"):
        await _do_add_admin(update, context)
    elif ud.get("waiting_text_edit"):
        await _do_edit_text(update, context)
    elif ud.get("replying_to"):
        await _do_direct_reply(update, context)
    elif ud.get("waiting_user_search"):
        await _do_user_search(update, context)
    elif ud.get("waiting_vip_add"):
        await _do_vip_add(update, context)
    elif ud.get("waiting_channel_id"):
        await _do_set_channel_id(update, context)
    elif ud.get("waiting_pinned_text"):
        await _do_set_pinned_text(update, context)
    elif ud.get("waiting_bc_message"):
        await _do_save_bc_message(update, context)
    elif ud.get("waiting_bc_time"):
        await _do_schedule_broadcast(update, context)
    elif ud.get("waiting_remind_interval"):
        await _do_set_remind_interval(update, context)


# ─── Admin reply (xabar orqali) ───────────────────────────────────────────────

async def _forward_text_reply(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    reply_id = update.message.reply_to_message.message_id
    chat_id  = update.effective_chat.id
    row = get_message_map_row(reply_id, chat_id)
    if not row:
        await update.message.reply_text("❌ Bu xabarning egasi topilmadi.")
        return
    user_id = row["user_id"]
    try:
        await context.bot.send_message(user_id, f"📩 Javob:\n\n{update.message.text}")
        save_admin_reply(update.effective_user.id, user_id, update.message.text or "")
        await _mark_replied(context, row)
        await update.message.reply_text("✅ Javob yuborildi.")
    except Exception as e:
        await _handle_send_error(update, context, user_id, e)


async def _forward_media_reply(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    reply_id = update.message.reply_to_message.message_id
    chat_id  = update.effective_chat.id
    row = get_message_map_row(reply_id, chat_id)
    if not row:
        await update.message.reply_text("❌ Bu xabarning egasi topilmadi.")
        return
    user_id = row["user_id"]
    try:
        await context.bot.copy_message(
            chat_id=user_id,
            from_chat_id=chat_id,
            message_id=update.message.message_id,
        )
        save_admin_reply(update.effective_user.id, user_id, "[media]")
        await _mark_replied(context, row)
        await update.message.reply_text("✅ Javob yuborildi.")
    except Exception as e:
        await _handle_send_error(update, context, user_id, e)


# ─── Admin reply (tugma orqali) ───────────────────────────────────────────────

async def _do_direct_reply(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    info    = context.user_data.pop("replying_to")
    user_id = info["user_id"]
    try:
        await context.bot.send_message(user_id, f"📩 Javob:\n\n{update.message.text}")
        save_admin_reply(update.effective_user.id, user_id, update.message.text or "")
        await _mark_replied_by_info(context, info)
        await update.message.reply_text("✅ Javob yuborildi.")
    except Exception as e:
        await _handle_send_error(update, context, user_id, e)


async def _do_direct_media_reply(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    info    = context.user_data.pop("replying_to")
    user_id = info["user_id"]
    try:
        await context.bot.copy_message(
            chat_id=user_id,
            from_chat_id=update.effective_chat.id,
            message_id=update.message.message_id,
        )
        save_admin_reply(update.effective_user.id, user_id, "[media]")
        await _mark_replied_by_info(context, info)
        await update.message.reply_text("✅ Javob yuborildi.")
    except Exception as e:
        await _handle_send_error(update, context, user_id, e)


async def _mark_replied(context, row: dict) -> None:
    update_message_status(row["admin_msg_id"], row["admin_chat_id"], "replied")
    await _remove_action_buttons(context, row["admin_chat_id"], row.get("btn_msg_id", row["admin_msg_id"]))


async def _mark_replied_by_info(context, info: dict) -> None:
    if info.get("msg_id") and info.get("chat_id"):
        row = get_message_map_row(info["msg_id"], info["chat_id"])
        if row:
            await _mark_replied(context, row)


async def _remove_action_buttons(context, chat_id: int, msg_id: int) -> None:
    try:
        await context.bot.edit_message_reply_markup(
            chat_id=chat_id,
            message_id=msg_id,
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("✅ Javob berildi", callback_data="noop")
            ]]),
        )
    except Exception:
        pass


async def _handle_send_error(update, context, user_id: int, e: Exception) -> None:
    if "Forbidden" in str(e):
        mark_blocked(user_id)
        await update.message.reply_text("🚫 Foydalanuvchi botni bloklagan.")
    else:
        await update.message.reply_text(f"❌ Xato: {e}")


# ─── Broadcast ────────────────────────────────────────────────────────────────

async def _do_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    context.user_data.pop("waiting_broadcast", None)
    from_chat_id = update.effective_chat.id
    msg_id       = update.message.message_id
    users  = get_all_active_users()
    if not users:
        await update.message.reply_text("📭 Aktiv foydalanuvchilar yo'q.")
        return
    sent = failed = 0
    total  = len(users)
    status = await update.message.reply_text(f"📢 Yuborilmoqda... 0 / {total}")
    for i, uid in enumerate(users):
        try:
            await context.bot.copy_message(chat_id=uid, from_chat_id=from_chat_id, message_id=msg_id)
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
        f"✅ Broadcast yakunlandi!\n\n📤 Yuborildi: {sent}\n❌ Xato/Bloklagan: {failed}"
    )


async def _do_save_bc_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Jadval broadcast uchun xabarni saqlaydi, vaqt so'raydi."""
    context.user_data.pop("waiting_bc_message", None)
    context.user_data["bc_message_data"] = {
        "from_chat_id": update.effective_chat.id,
        "message_id":   update.message.message_id,
    }
    context.user_data["waiting_bc_time"] = True
    await update.message.reply_text(
        "⏰ <b>Qachon yuborilsin?</b>\n\n"
        "Format: <code>KK.OO.YYYY SS:DD</code>\n"
        "Misol: <code>20.06.2026 14:30</code>\n\n"
        "<i>Toshkent vaqti (UTC+5)</i>",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("🔙 Bekor qilish", callback_data="bc_menu")
        ]]),
    )


async def _do_schedule_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    context.user_data.pop("waiting_bc_time", None)
    bc_data = context.user_data.pop("bc_message_data", None)
    if not bc_data:
        await update.message.reply_text("❌ Xabar ma'lumotlari topilmadi. Qaytadan boshlang.")
        return
    try:
        import pytz
        tz  = pytz.timezone("Asia/Tashkent")
        dt  = datetime.strptime(update.message.text.strip(), "%d.%m.%Y %H:%M")
        dt  = tz.localize(dt)
        now = datetime.now(tz)
        if dt <= now:
            await update.message.reply_text("❌ Vaqt o'tib ketgan! Kelajak vaqt kiriting.")
            context.user_data["bc_message_data"] = bc_data
            context.user_data["waiting_bc_time"]  = True
            return
        bc_id = save_scheduled_broadcast(
            admin_id=update.effective_user.id,
            from_chat_id=bc_data["from_chat_id"],
            message_id=bc_data["message_id"],
            scheduled_at=dt.isoformat(),
        )
        if bc_id:
            _add_broadcast_job(context, bc_id, dt.astimezone(timezone.utc), bc_data)
        await update.message.reply_text(
            f"✅ Jadvalga qo'shildi!\n📅 <code>{dt.strftime('%d.%m.%Y %H:%M')}</code> (Toshkent)",
            parse_mode="HTML",
        )
    except ValueError:
        await update.message.reply_text("❌ Format noto'g'ri. Misol: 20.06.2026 14:30")
        context.user_data["bc_message_data"] = bc_data
        context.user_data["waiting_bc_time"]  = True


def _add_broadcast_job(context, bc_id: int, run_at: datetime, bc_data: dict) -> None:
    scheduler = context.bot_data.get("scheduler")
    if not scheduler:
        return
    scheduler.add_job(
        _run_broadcast_job,
        "date",
        run_date=run_at,
        args=[context.bot, bc_id, bc_data["from_chat_id"], bc_data["message_id"]],
        id=f"bc_{bc_id}",
        replace_existing=True,
    )


async def _run_broadcast_job(bot, bc_id: int, from_chat_id: int, message_id: int) -> None:
    from database import get_all_active_users, delete_scheduled_broadcast
    users = get_all_active_users()
    for uid in users:
        try:
            await bot.copy_message(chat_id=uid, from_chat_id=from_chat_id, message_id=message_id)
        except Exception:
            pass
        await asyncio.sleep(BROADCAST_DELAY)
    delete_scheduled_broadcast(bc_id)
    logger.info(f"Jadval broadcast #{bc_id} yakunlandi.")


# ─── Admin boshqaruv ──────────────────────────────────────────────────────────

async def _do_add_admin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    context.user_data.pop("waiting_admin_id", None)
    try:
        new_id = int(update.message.text.strip())
        add_admin(new_id)
        await update.message.reply_text(
            f"✅ Admin qo'shildi! 🆔 <code>{new_id}</code>", parse_mode="HTML"
        )
    except ValueError:
        await update.message.reply_text("❌ Faqat raqam kiriting.")


async def _do_edit_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    key   = context.user_data.pop("waiting_text_edit")
    value = update.message.text
    if not value:
        await update.message.reply_text("❌ Faqat matn.")
        context.user_data["waiting_text_edit"] = key
        return
    set_text(key, value)
    label = TEXT_LABELS.get(key, key)
    await update.message.reply_text(f"✅ <b>{label}</b> yangilandi!", parse_mode="HTML")


async def _do_user_search(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    context.user_data.pop("waiting_user_search", None)
    query = update.message.text.strip()
    results = search_users(query)
    if not results:
        await update.message.reply_text("🔍 Hech narsa topilmadi.")
        return
    buttons = []
    for u in results[:8]:
        name = escape(u.get("first_name", "—"))
        uid  = u["user_id"]
        badges = ""
        if u.get("vip"):        badges += "⭐"
        if u.get("is_blocked"): badges += "🚫"
        buttons.append([InlineKeyboardButton(
            f"👤 {name} ({uid}) {badges}",
            callback_data=f"usr_prof_{uid}"
        )])
    buttons.append([InlineKeyboardButton("🔙 Orqaga", callback_data="users")])
    await update.message.reply_text(
        f"🔍 <b>Natijalar</b> ({len(results)} ta):",
        reply_markup=InlineKeyboardMarkup(buttons),
        parse_mode="HTML",
    )


async def _do_vip_add(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    context.user_data.pop("waiting_vip_add", None)
    try:
        uid = int(update.message.text.strip())
        set_vip(uid, True)
        await update.message.reply_text(
            f"✅ VIP qo'shildi! 🆔 <code>{uid}</code>", parse_mode="HTML"
        )
    except ValueError:
        await update.message.reply_text("❌ Faqat raqam kiriting.")


async def _do_set_channel_id(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    context.user_data.pop("waiting_channel_id", None)
    val = update.message.text.strip()
    from database import set_setting
    set_setting("channel_id", val)
    await update.message.reply_text(
        f"✅ Kanal saqlandi: <code>{escape(val)}</code>", parse_mode="HTML"
    )


async def _do_set_pinned_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    context.user_data.pop("waiting_pinned_text", None)
    val = update.message.text or ""
    from database import set_setting
    set_setting("pinned_text", val)
    await update.message.reply_text("✅ Pinlangan xabar saqlandi!")


async def _do_set_remind_interval(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    context.user_data.pop("waiting_remind_interval", None)
    try:
        hours = int(update.message.text.strip())
        if not (1 <= hours <= 24):
            raise ValueError
        from database import set_setting
        set_setting("reminder_interval", str(hours))
        _reschedule_reminder(context)
        await update.message.reply_text(f"✅ Eslatma har {hours} soatda yuboriladi.")
    except ValueError:
        await update.message.reply_text("❌ 1 dan 24 gacha raqam kiriting.")


def _reschedule_reminder(context) -> None:
    scheduler = context.bot_data.get("scheduler")
    if not scheduler:
        return
    try:
        scheduler.remove_job("reminder_job")
    except Exception:
        pass
    enabled  = get_setting("reminder_enabled") == "true"
    interval = int(get_setting("reminder_interval") or 2)
    if enabled:
        scheduler.add_job(
            _send_reminder,
            "interval",
            hours=interval,
            args=[context.bot],
            id="reminder_job",
        )


async def _send_reminder(bot) -> None:
    from database import get_all_admins, get_pending_messages, get_user
    for admin_id in get_all_admins():
        rows = get_pending_messages(admin_id)
        if not rows:
            continue
        lines = [f"⏰ <b>Javobsiz xabarlar: {len(rows)} ta</b>\n"]
        for row in rows[:5]:
            u    = get_user(row["user_id"])
            name = escape(u["first_name"]) if u else str(row["user_id"])
            prev = row.get("message_preview", "")[:40]
            lines.append(f"• {name}: <i>{escape(prev)}</i>")
        try:
            await bot.send_message(admin_id, "\n".join(lines), parse_mode="HTML")
        except Exception:
            pass


# ─── /info – pinlangan xabar ─────────────────────────────────────────────────

async def info_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    enabled = get_setting("pinned_enabled") == "true"
    text    = get_setting("pinned_text")
    if not enabled or not text:
        await update.message.reply_text("📌 Hozircha e'lon yo'q.")
        return
    await update.message.reply_text(text, parse_mode="HTML", disable_web_page_preview=True)


# ─── Foydalanuvchi text xabari ────────────────────────────────────────────────

async def _handle_user_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    text = update.message.text

    try:
        db_user = get_or_create_user(user.id, user.first_name, user.username)
    except Exception as e:
        logger.error(f"get_or_create_user: {e}")
        db_user = None

    # Kanal obuna tekshiruvi
    if not await _check_channel(update, context):
        return

    # Blok tekshiruvi
    if db_user and db_user.get("is_blocked"):
        await update.message.reply_text(get_text("blocked"))
        return

    # Rate limit (VIP o'tkazib yuboradi)
    if not db_user or not db_user.get("vip"):
        try:
            if not _check_rate_limit(user.id, context):
                await update.message.reply_text(get_text("rate_limit"))
                return
        except Exception as e:
            logger.error(f"rate_limit: {e}")

    try:
        save_message(user.id, text)
    except Exception as e:
        logger.error(f"save_message: {e}")

    safe_name  = escape(user.first_name or "")
    uname      = f"@{user.username}" if user.username else "—"
    safe_uname = escape(uname)
    safe_text  = escape(text)
    vip_badge  = " ⭐" if db_user and db_user.get("vip") else ""

    admin_text = (
        f"👤 <b>{safe_name}</b>{vip_badge}\n"
        f"🆔 <code>{user.id}</code> · {safe_uname}\n"
        f"──────────────────\n"
        f"💬 {safe_text}"
    )
    preview = text[:80]

    action_kb = InlineKeyboardMarkup([[
        InlineKeyboardButton("📩 Javob",   callback_data=f"reply_{user.id}"),
        InlineKeyboardButton("👤 Profil",  callback_data=f"usr_prof_{user.id}"),
        InlineKeyboardButton("🚫 Blokla", callback_data=f"block_{user.id}"),
    ]])

    for admin_id in get_all_admins():
        try:
            sent = await context.bot.send_message(
                admin_id, admin_text, parse_mode="HTML", reply_markup=action_kb
            )
            save_message_map(sent.message_id, admin_id, user.id,
                             btn_msg_id=sent.message_id, preview=preview)
        except Exception as e:
            logger.error(f"Admin {admin_id}: {e}")

    await update.message.reply_text(get_text("message_sent"))


# ─── Foydalanuvchi media xabari ───────────────────────────────────────────────

async def _handle_user_media(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    msg  = update.message

    try:
        db_user = get_or_create_user(user.id, user.first_name, user.username)
    except Exception as e:
        logger.error(f"get_or_create_user: {e}")
        db_user = None

    if not await _check_channel(update, context):
        return

    if db_user and db_user.get("is_blocked"):
        await update.message.reply_text(get_text("blocked"))
        return

    if   msg.photo:        mt = "📷 Rasm"
    elif msg.video:        mt = "🎥 Video"
    elif msg.audio:        mt = "🎵 Audio"
    elif msg.voice:        mt = "🎙 Ovozli"
    elif msg.sticker:      mt = "🎭 Stiker"
    elif msg.animation:    mt = "🎞 GIF"
    elif msg.video_note:   mt = "⭕ Video xabar"
    elif msg.document:     mt = "📎 Fayl"
    else:                  mt = "📎 Media"

    safe_name  = escape(user.first_name or "")
    uname      = f"@{user.username}" if user.username else "—"
    vip_badge  = " ⭐" if db_user and db_user.get("vip") else ""

    header = (
        f"👤 <b>{safe_name}</b>{vip_badge}\n"
        f"🆔 <code>{user.id}</code> · {escape(uname)}\n"
        f"──────────────────\n"
        f"{mt}"
    )
    action_kb = InlineKeyboardMarkup([[
        InlineKeyboardButton("📩 Javob",   callback_data=f"reply_{user.id}"),
        InlineKeyboardButton("👤 Profil",  callback_data=f"usr_prof_{user.id}"),
        InlineKeyboardButton("🚫 Blokla", callback_data=f"block_{user.id}"),
    ]])

    for admin_id in get_all_admins():
        try:
            hdr = await context.bot.send_message(
                admin_id, header, parse_mode="HTML", reply_markup=action_kb
            )
            copied = await context.bot.copy_message(
                chat_id=admin_id, from_chat_id=msg.chat_id, message_id=msg.message_id
            )
            save_message_map(copied.message_id, admin_id, user.id,
                             btn_msg_id=hdr.message_id, preview=mt)
        except Exception as e:
            logger.error(f"Admin {admin_id}: {e}")

    await update.message.reply_text(get_text("message_sent"))


# ─── Kanal obuna tekshiruvi ───────────────────────────────────────────────────

async def _check_channel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """True = o'tdi. False = obuna emas (javob yuborildi)."""
    if get_setting("channel_check_enabled") != "true":
        return True
    channel_id = get_setting("channel_id")
    if not channel_id:
        return True
    try:
        member = await context.bot.get_chat_member(channel_id, update.effective_user.id)
        if member.status in ("left", "kicked"):
            await update.message.reply_text(
                f"📢 Botdan foydalanish uchun avval kanalga obuna bo'ling:\n{channel_id}"
            )
            return False
    except Exception as e:
        logger.error(f"Kanal tekshirish xatosi: {e}")
    return True


# ─── Rate limit ───────────────────────────────────────────────────────────────

def _check_rate_limit(user_id: int, context) -> bool:
    db_user = get_user(user_id)
    if not db_user:
        return True
    count     = db_user.get("msg_count", 0)
    raw_reset = db_user.get("rate_reset_at")
    now       = datetime.now(timezone.utc)
    reset     = None
    if raw_reset:
        reset = datetime.fromisoformat(raw_reset.replace("Z", "+00:00")) if isinstance(raw_reset, str) else raw_reset
    if reset and now > reset:
        update_user(user_id, msg_count=0, rate_reset_at=None)
        count = 0
        reset = None
    if reset and count >= RATE_LIMIT:
        return False
    if count == 0 and not reset:
        new_reset = now + timedelta(seconds=RATE_WINDOW)
        update_user(user_id, msg_count=1, rate_reset_at=new_reset.isoformat())
        _schedule_reset(context, user_id, new_reset)
    else:
        update_user(user_id, msg_count=count + 1)
    return True


def _schedule_reset(context, user_id: int, reset_at: datetime) -> None:
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
        await bot.send_message(user_id, get_text("rate_reset"))
    except Exception:
        pass
