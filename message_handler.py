import asyncio
import logging
from datetime import datetime, timezone, timedelta
from html import escape
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.error import BadRequest
from telegram.ext import ContextTypes

from config import RATE_WINDOW, BROADCAST_DELAY
from database import (
    get_or_create_user, get_user, update_user,
    save_message, save_admin_reply,
    save_message_map, get_message_map_row,
    save_admin_reply_map, get_admin_reply_target,
    is_admin, get_all_admins, get_all_active_users,
    add_admin, mark_blocked, get_text, set_text,
    TEXT_LABELS, set_vip, get_setting,
    update_message_status,
    search_users, get_user_message_count, resolve_user_id,
    check_help_limit, increment_help_count,
)

logger = logging.getLogger(__name__)

# Obuna hisoblanadigan statuslar (PTB versiyasidan mustaqil)
_SUBSCRIBED = {"creator", "administrator", "member", "restricted"}


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
        return
    await _handle_user_media(update, context)


async def handle_edited(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Admin o'z javobini tahrirlasa — user tomonida ham yangilanadi."""
    try:
        if not update.edited_message:
            return
        if not is_admin(update.effective_user.id):
            return
        msg    = update.edited_message
        target = get_admin_reply_target(msg.message_id, msg.chat_id)
        if not target:
            return
        new_text = msg.text or msg.caption
        if not new_text:
            return
        try:
            await context.bot.edit_message_text(
                chat_id=target["user_id"],
                message_id=target["bot_msg_id"],
                text=f"\U0001f4e9 Javob (tahrirlangan):\n\n{new_text}",
            )
        except BadRequest as e:
            err = str(e).lower()
            if "not modified" not in err and "not found" not in err:
                logger.error(f"handle_edited: {e}")
        except Exception as e:
            logger.error(f"handle_edited: {e}")
    except Exception as e:
        logger.error(f"handle_edited outer: {e}")


# ─── Pinlangan xabar broadcast va unpin ──────────────────────────────────────

async def _broadcast_pinned_to_all(bot, text: str) -> tuple[int, int]:
    """Barcha active userlarga pin xabar yuboradi va pin qiladi."""
    sent = failed = 0
    for uid in get_all_active_users():
        try:
            msg = await bot.send_message(uid, text, parse_mode="HTML", disable_web_page_preview=True)
            try:
                await bot.pin_chat_message(chat_id=uid, message_id=msg.message_id, disable_notification=True)
            except Exception:
                pass
            sent += 1
        except Exception as e:
            failed += 1
            if "Forbidden" in str(e):
                mark_blocked(uid)
        await asyncio.sleep(BROADCAST_DELAY)
    return sent, failed


async def _unpin_for_all(bot) -> None:
    """Barcha active userlar chatidan pinni olib tashlaydi."""
    for uid in get_all_active_users():
        try:
            await bot.unpin_all_chat_messages(chat_id=uid)
        except Exception:
            pass
        await asyncio.sleep(BROADCAST_DELAY)


# ─── /help buyrug'i ───────────────────────────────────────────────────────────

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Blok va rate limit bo'lsa ham ishlaydi. Admin belgilagan kunlik limit."""
    user = update.effective_user
    try:
        get_or_create_user(user.id, user.first_name, user.username)
    except Exception:
        pass

    limit = int(get_setting("help_limit_count") or 2)

    if limit <= 0:
        await update.message.reply_text("\U0001f6ab /help buyrug'i hozircha cheklangan.")
        return

    if not check_help_limit(user.id):
        await update.message.reply_text(
            f"\u26a0\ufe0f Bugun /help uchun limitingiz tugadi ({limit} ta/kun).\n"
            "Ertaga kechasi 00:00 dan keyin qayta ishlating."
        )
        return

    increment_help_count(user.id)

    # Userga yordam matni
    await update.message.reply_text(
        get_text("help"), parse_mode="HTML", disable_web_page_preview=True
    )

    # Admin ga bildirim: kim yordam so'radi
    safe_name = escape(user.first_name or "")
    uname     = f"@{user.username}" if user.username else "\u2014"
    admin_text = (
        f"\U0001f464 <b>{safe_name}</b>\n"
        f"\U0001f194 <code>{user.id}</code> \u00b7 {escape(uname)}\n"
        f"\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\n"
        f"\U0001f4de Yordam so'rayapti"
    )
    action_kb = InlineKeyboardMarkup([[
        InlineKeyboardButton("\U0001f4e9 Javob", callback_data=f"reply_{user.id}"),
    ]])
    for admin_id in get_all_admins():
        try:
            sent = await context.bot.send_message(
                admin_id, admin_text, parse_mode="HTML", reply_markup=action_kb
            )
            save_message_map(sent.message_id, admin_id, user.id,
                             btn_msg_id=sent.message_id, preview="\U0001f4de Yordam so'radi")
        except Exception as e:
            logger.error(f"help admin {admin_id}: {e}")


# ─── /info buyrug'i ───────────────────────────────────────────────────────────

async def info_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    enabled = get_setting("pinned_enabled") == "true"
    text    = get_setting("pinned_text")
    if not enabled or not text:
        await update.message.reply_text("\U0001f4cc Hozircha e'lon yo'q.")
        return
    sent = await update.message.reply_text(text, parse_mode="HTML", disable_web_page_preview=True)
    try:
        await context.bot.pin_chat_message(
            chat_id=update.effective_chat.id,
            message_id=sent.message_id,
            disable_notification=True,
        )
    except Exception as e:
        logger.warning(f"Pin xatosi: {e}")


# ─── Admin text yo'naltiruvchi ────────────────────────────────────────────────

async def _handle_admin_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    ud  = context.user_data
    msg = update.message
    if msg.reply_to_message:
        context.user_data.pop("replying_to", None)
        await _forward_text_reply(update, context)
    elif ud.get("waiting_broadcast"):       await _do_broadcast(update, context)
    elif ud.get("waiting_admin_id"):        await _do_add_admin(update, context)
    elif ud.get("waiting_text_edit"):       await _do_edit_text(update, context)
    elif ud.get("replying_to"):             await _do_direct_reply(update, context)
    elif ud.get("waiting_user_search"):     await _do_user_search(update, context)
    elif ud.get("waiting_vip_add"):         await _do_vip_add(update, context)
    elif ud.get("waiting_channel_id"):      await _do_set_channel_id(update, context)
    elif ud.get("waiting_pinned_text"):     await _do_set_pinned_text(update, context)
    elif ud.get("waiting_remind_interval"): await _do_set_remind_interval(update, context)
    elif ud.get("waiting_rate_limit"):      await _do_set_rate_limit(update, context)
    elif ud.get("waiting_help_limit"):      await _do_set_help_limit(update, context)


# ─── Admin reply ──────────────────────────────────────────────────────────────

async def _forward_text_reply(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    reply_id = update.message.reply_to_message.message_id
    chat_id  = update.effective_chat.id
    row = get_message_map_row(reply_id, chat_id)
    if not row:
        await update.message.reply_text("\u274c Bu xabarning egasi topilmadi.")
        return
    user_id = row["user_id"]
    try:
        sent = await context.bot.send_message(user_id, f"\U0001f4e9 Javob:\n\n{update.message.text}")
        save_admin_reply(update.effective_user.id, user_id, update.message.text or "")
        save_admin_reply_map(update.message.message_id, chat_id, user_id, sent.message_id)
        await _mark_replied(context, row)
    except Exception as e:
        await _handle_send_error(update, context, user_id, e)


async def _forward_media_reply(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    reply_id = update.message.reply_to_message.message_id
    chat_id  = update.effective_chat.id
    row = get_message_map_row(reply_id, chat_id)
    if not row:
        await update.message.reply_text("\u274c Bu xabarning egasi topilmadi.")
        return
    user_id = row["user_id"]
    try:
        await context.bot.copy_message(
            chat_id=user_id, from_chat_id=chat_id, message_id=update.message.message_id,
        )
        save_admin_reply(update.effective_user.id, user_id, "[media]")
        await _mark_replied(context, row)
    except Exception as e:
        await _handle_send_error(update, context, user_id, e)


async def _do_direct_reply(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Tugma orqali javob (xabar o'chirilmaydi — tahrirlash imkoniyati saqlanadi)."""
    info    = context.user_data.pop("replying_to")
    user_id = info["user_id"]
    chat_id = update.effective_chat.id
    try:
        sent = await context.bot.send_message(user_id, f"\U0001f4e9 Javob:\n\n{update.message.text}")
        save_admin_reply(update.effective_user.id, user_id, update.message.text or "")
        # admin_reply_map — keyinchalik tahrirlash uchun
        save_admin_reply_map(update.message.message_id, chat_id, user_id, sent.message_id)
        await _mark_replied_by_info(context, info)
        # "Javob yozilyapti" xabarini — status ko'rinishiga o'tkazamiz
        orig_text = info.get("orig_text", "")
        try:
            await context.bot.edit_message_text(
                chat_id=info["chat_id"],
                message_id=info["msg_id"],
                text=orig_text + "\n\n\u2705 <i>Javob berildi</i>",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("\u2705 Javob berildi", callback_data="noop")
                ]]),
                parse_mode="HTML",
            )
        except Exception:
            pass
    except Exception as e:
        await _handle_send_error(update, context, user_id, e)


async def _do_direct_media_reply(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Tugma orqali media javob (xabar o'chirilmaydi)."""
    info    = context.user_data.pop("replying_to")
    user_id = info["user_id"]
    try:
        await context.bot.copy_message(
            chat_id=user_id, from_chat_id=update.effective_chat.id,
            message_id=update.message.message_id,
        )
        save_admin_reply(update.effective_user.id, user_id, "[media]")
        await _mark_replied_by_info(context, info)
        orig_text = info.get("orig_text", "")
        try:
            await context.bot.edit_message_text(
                chat_id=info["chat_id"],
                message_id=info["msg_id"],
                text=orig_text + "\n\n\u2705 <i>Javob berildi (media)</i>",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("\u2705 Javob berildi", callback_data="noop")
                ]]),
                parse_mode="HTML",
            )
        except Exception:
            pass
    except Exception as e:
        await _handle_send_error(update, context, user_id, e)


async def _mark_replied(context, row: dict) -> None:
    update_message_status(row["admin_msg_id"], row["admin_chat_id"], "replied")
    await _remove_action_buttons(
        context, row["admin_chat_id"], row.get("btn_msg_id", row["admin_msg_id"])
    )


async def _mark_replied_by_info(context, info: dict) -> None:
    if info.get("msg_id") and info.get("chat_id"):
        row = get_message_map_row(info["msg_id"], info["chat_id"])
        if row:
            await _mark_replied(context, row)


async def _remove_action_buttons(context, chat_id: int, msg_id: int) -> None:
    try:
        await context.bot.edit_message_reply_markup(
            chat_id=chat_id, message_id=msg_id,
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("\u2705 Javob berildi", callback_data="noop")
            ]]),
        )
    except Exception:
        pass


async def _handle_send_error(update, context, user_id: int, e: Exception) -> None:
    if "Forbidden" in str(e):
        mark_blocked(user_id)
        await update.message.reply_text("\U0001f6ab Foydalanuvchi botni bloklagan.")
    else:
        await update.message.reply_text(f"\u274c Xato: {e}")


# ─── Broadcast ────────────────────────────────────────────────────────────────

async def _do_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    context.user_data.pop("waiting_broadcast", None)
    from_chat_id = update.effective_chat.id
    msg_id       = update.message.message_id
    users = get_all_active_users()
    if not users:
        await update.message.reply_text("\U0001f4ad Aktiv foydalanuvchilar yo'q.")
        return
    sent = failed = 0
    total  = len(users)
    status = await update.message.reply_text(f"\U0001f4e2 Yuborilmoqda... 0 / {total}")
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
                await status.edit_text(f"\U0001f4e2 Yuborilmoqda... {i + 1} / {total}")
            except Exception:
                pass
    await status.edit_text(
        f"\u2705 Broadcast yakunlandi!\n\n\U0001f4e4 Yuborildi: {sent}\n\u274c Xato/Bloklagan: {failed}"
    )



# ─── Admin boshqaruv ──────────────────────────────────────────────────────────

async def _do_add_admin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    context.user_data.pop("waiting_admin_id", None)
    uid = resolve_user_id(update.message.text.strip())
    if uid is None:
        await update.message.reply_text("\u274c Foydalanuvchi topilmadi. ID yoki @username kiriting.")
        return
    add_admin(uid)
    await update.message.reply_text(f"\u2705 Admin qo'shildi! \U0001f194 <code>{uid}</code>", parse_mode="HTML")


async def _do_edit_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    key = context.user_data.pop("waiting_text_edit")
    value = update.message.text
    if not value:
        await update.message.reply_text("\u274c Faqat matn.")
        context.user_data["waiting_text_edit"] = key
        return
    set_text(key, value)
    label = TEXT_LABELS.get(key, key)
    await update.message.reply_text(f"\u2705 <b>{label}</b> yangilandi!", parse_mode="HTML")


async def _do_user_search(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    context.user_data.pop("waiting_user_search", None)
    query   = update.message.text.strip()
    results = search_users(query)
    if not results:
        await update.message.reply_text("\U0001f50d Hech narsa topilmadi.")
        return
    buttons = []
    for u in results[:8]:
        name   = escape(u.get("first_name", "\u2014"))
        uid    = u["user_id"]
        uname  = f" @{u['username']}" if u.get("username") else ""
        badges = ("\u2b50" if u.get("vip") else "") + ("\U0001f6ab" if u.get("is_blocked") else "")
        buttons.append([InlineKeyboardButton(
            f"\U0001f464 {name}{uname} {badges}".strip(), callback_data=f"usr_prof_{uid}"
        )])
    buttons.append([InlineKeyboardButton("\U0001f519 Orqaga", callback_data="users")])
    await update.message.reply_text(
        f"\U0001f50d <b>Natijalar</b> ({len(results)} ta):",
        reply_markup=InlineKeyboardMarkup(buttons), parse_mode="HTML",
    )


async def _do_vip_add(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    context.user_data.pop("waiting_vip_add", None)
    uid = resolve_user_id(update.message.text.strip())
    if uid is None:
        await update.message.reply_text("\u274c Foydalanuvchi topilmadi.")
        return
    set_vip(uid, True)
    await update.message.reply_text(f"\u2705 VIP qo'shildi! \U0001f194 <code>{uid}</code>", parse_mode="HTML")


async def _do_set_channel_id(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    context.user_data.pop("waiting_channel_id", None)
    val = update.message.text.strip()
    from database import set_setting
    set_setting("channel_id", val)
    await update.message.reply_text(
        f"\u2705 Kanal saqlandi: <code>{escape(val)}</code>\n\n"
        "<i>Private kanal uchun bot kanalga admin sifatida qo'shilgan bo'lishi kerak!</i>",
        parse_mode="HTML"
    )


async def _do_set_pinned_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    context.user_data.pop("waiting_pinned_text", None)
    val = update.message.text or ""
    from database import set_setting
    set_setting("pinned_text", val)
    if get_setting("pinned_enabled") == "true":
        status = await update.message.reply_text("\u2705 Saqlandi! Yuborilyapti...")
        sent, failed = await _broadcast_pinned_to_all(context.bot, val)
        try:
            await status.edit_text(
                f"\u2705 Pinlangan xabar saqlandi va yuborildi!\n"
                f"\U0001f4e4 {sent} ta | \u274c {failed} ta"
            )
        except Exception:
            pass
    else:
        await update.message.reply_text(
            "\u2705 Pinlangan xabar saqlandi!\n"
            "Yuborish uchun sozlamalardan '\U0001f7e2 Yoqish' ni bosing."
        )


async def _do_set_remind_interval(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    context.user_data.pop("waiting_remind_interval", None)
    try:
        hours = int(update.message.text.strip())
        if not (1 <= hours <= 24):
            raise ValueError
        from database import set_setting
        set_setting("reminder_interval", str(hours))
        _reschedule_reminder(context)
        await update.message.reply_text(f"\u2705 Eslatma har {hours} soatda yuboriladi.")
    except ValueError:
        await update.message.reply_text("\u274c 1 dan 24 gacha raqam kiriting.")


def _reschedule_reminder(context) -> None:
    scheduler = context.bot_data.get("scheduler")
    if not scheduler:
        return
    try:
        scheduler.remove_job("reminder_job")
    except Exception:
        pass
    if get_setting("reminder_enabled") == "true":
        interval = int(get_setting("reminder_interval") or 2)
        scheduler.add_job(
            _send_reminder, "interval", hours=interval,
            args=[context.bot], id="reminder_job",
        )


async def _do_set_rate_limit(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    context.user_data.pop("waiting_rate_limit", None)
    try:
        count = int(update.message.text.strip())
        if count < 0:
            raise ValueError
        from database import set_setting
        set_setting("rate_limit_count", str(count))
        await update.message.reply_text(
            f"\u2705 Rate limit yangilandi: soatiga <b>{count}</b> ta xabar.",
            parse_mode="HTML"
        )
    except ValueError:
        await update.message.reply_text("\u274c 0 yoki musbat raqam kiriting.")


async def _do_set_help_limit(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    context.user_data.pop("waiting_help_limit", None)
    try:
        count = int(update.message.text.strip())
        if count < 0:
            raise ValueError
        from database import set_setting
        set_setting("help_limit_count", str(count))
        if count == 0:
            await update.message.reply_text(
                "\u2705 /help limiti <b>0</b> ga o'rnatildi \u2014 endi butunlay cheklangan.",
                parse_mode="HTML"
            )
        else:
            await update.message.reply_text(
                f"\u2705 /help limiti yangilandi: kuniga <b>{count}</b> ta.",
                parse_mode="HTML"
            )
    except ValueError:
        await update.message.reply_text("\u274c 0 yoki musbat raqam kiriting.")


async def _send_reminder(bot) -> None:
    from database import get_all_admins, get_pending_messages, get_user
    for admin_id in get_all_admins():
        rows = get_pending_messages(admin_id)
        if not rows:
            continue
        lines = [f"\u23f0 <b>Javobsiz xabarlar: {len(rows)} ta</b>\n"]
        for row in rows[:5]:
            u    = get_user(row["user_id"])
            name = escape(u["first_name"]) if u else str(row["user_id"])
            prev = row.get("message_preview", "")[:40]
            lines.append(f"\u2022 {name}: <i>{escape(prev)}</i>")
        try:
            await bot.send_message(admin_id, "\n".join(lines), parse_mode="HTML")
        except Exception:
            pass


# ─── Foydalanuvchi text xabari ────────────────────────────────────────────────

async def _handle_user_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    text = update.message.text

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
    if not (db_user and db_user.get("vip")):
        try:
            if not _check_rate_limit(user.id, context):
                from database import get_user as _gu
                _u = _gu(user.id)
                _raw = _u.get("rate_reset_at") if _u else None
                if _raw:
                    from datetime import datetime, timezone
                    _reset = datetime.fromisoformat(_raw.replace("Z", "+00:00")) if isinstance(_raw, str) else _raw
                    _now = datetime.now(timezone.utc)
                    _diff = int((_reset - _now).total_seconds() / 60)
                    _h, _m = divmod(max(_diff, 0), 60)
                    if _h:
                        _time_str = f"{_h} soat {_m} daqiqa"
                    else:
                        _time_str = f"{_m} daqiqa"
                    await update.message.reply_text(
                        f"⚠️ Xabar limitiga yetdingiz.\n⏰ {_time_str}dan so'ng qayta yuboring."
                    )
                else:
                    await update.message.reply_text(get_text("rate_limit"))
                return
        except Exception as e:
            logger.error(f"rate_limit: {e}")

    try:
        save_message(user.id, text)
    except Exception as e:
        logger.error(f"save_message: {e}")

    safe_name = escape(user.first_name or "")
    uname     = f"@{user.username}" if user.username else "\u2014"
    vip_badge = " \u2b50" if db_user and db_user.get("vip") else ""

    admin_text = (
        f"\U0001f464 <b>{safe_name}</b>{vip_badge}\n"
        f"\U0001f194 <code>{user.id}</code> \u00b7 {escape(uname)}\n"
        f"\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\n"
        f"\U0001f4ac {escape(text)}"
    )
    action_kb = InlineKeyboardMarkup([[
        InlineKeyboardButton("\U0001f4e9 Javob",   callback_data=f"reply_{user.id}"),
        InlineKeyboardButton("\U0001f464 Profil",  callback_data=f"usr_prof_{user.id}"),
        InlineKeyboardButton("\U0001f6ab Blokla", callback_data=f"block_{user.id}"),
    ]])

    for admin_id in get_all_admins():
        try:
            sent = await context.bot.send_message(
                admin_id, admin_text, parse_mode="HTML", reply_markup=action_kb
            )
            save_message_map(sent.message_id, admin_id, user.id,
                             btn_msg_id=sent.message_id, preview=text[:80])
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

    if   msg.photo:        mt = "\U0001f4f7 Rasm"
    elif msg.video:        mt = "\U0001f3a5 Video"
    elif msg.audio:        mt = "\U0001f3b5 Audio"
    elif msg.voice:        mt = "\U0001f399 Ovozli"
    elif msg.sticker:      mt = "\U0001f3ad Stiker"
    elif msg.animation:    mt = "\U0001f39e GIF"
    elif msg.video_note:   mt = "\u2b55 Video xabar"
    elif msg.document:     mt = "\U0001f4ce Fayl"
    else:                  mt = "\U0001f4ce Media"

    safe_name = escape(user.first_name or "")
    uname     = f"@{user.username}" if user.username else "\u2014"
    vip_badge = " \u2b50" if db_user and db_user.get("vip") else ""

    header = (
        f"\U0001f464 <b>{safe_name}</b>{vip_badge}\n"
        f"\U0001f194 <code>{user.id}</code> \u00b7 {escape(uname)}\n"
        f"\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\n{mt}"
    )
    action_kb = InlineKeyboardMarkup([[
        InlineKeyboardButton("\U0001f4e9 Javob",   callback_data=f"reply_{user.id}"),
        InlineKeyboardButton("\U0001f464 Profil",  callback_data=f"usr_prof_{user.id}"),
        InlineKeyboardButton("\U0001f6ab Blokla", callback_data=f"block_{user.id}"),
    ]])

    for admin_id in get_all_admins():
        try:
            hdr    = await context.bot.send_message(admin_id, header, parse_mode="HTML", reply_markup=action_kb)
            copied = await context.bot.copy_message(chat_id=admin_id, from_chat_id=msg.chat_id, message_id=msg.message_id)
            save_message_map(copied.message_id, admin_id, user.id, btn_msg_id=hdr.message_id, preview=mt)
        except Exception as e:
            logger.error(f"Admin {admin_id}: {e}")

    await update.message.reply_text(get_text("message_sent"))


# ─── Kanal obuna tekshiruvi ───────────────────────────────────────────────────

async def _check_channel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    if get_setting("channel_check_enabled") != "true":
        return True
    channel_id = get_setting("channel_id").strip()
    if not channel_id:
        return True
    user_id = update.effective_user.id
    try:
        member = await context.bot.get_chat_member(channel_id, user_id)
        # Faqat haqiqiy a'zolikni tekshiramiz
        if member.status not in _SUBSCRIBED:
            await update.message.reply_text(
                f"\U0001f4e2 Botdan foydalanish uchun kanalga obuna bo'ling:\n{channel_id}"
            )
            return False
        return True
    except Exception as e:
        err = str(e).lower()
        if "forbidden" in err or "not a member" in err:
            logger.warning(f"Bot kanalda emas, obuna talab qilinadi: {channel_id}")
            await update.message.reply_text(
                f"\U0001f4e2 Botdan foydalanish uchun kanalga obuna bo'ling:\n{channel_id}"
            )
            return False
        if "chat not found" in err or "invalid" in err:
            logger.error(f"Kanal topilmadi: {channel_id} \u2014 {e}")
            return True
        logger.error(f"Kanal tekshirish: {e}")
        return True


# ─── Rate limit ───────────────────────────────────────────────────────────────

def _check_rate_limit(user_id: int, context) -> bool:
    db_user = get_user(user_id)
    if not db_user:
        return True
    limit     = int(get_setting("rate_limit_count") or 5)
    count     = db_user.get("msg_count", 0)
    raw_reset = db_user.get("rate_reset_at")
    now       = datetime.now(timezone.utc)
    reset     = None
    if raw_reset:
        reset = datetime.fromisoformat(raw_reset.replace("Z", "+00:00")) if isinstance(raw_reset, str) else raw_reset
    if reset and now > reset:
        update_user(user_id, msg_count=0, rate_reset_at=None)
        count, reset = 0, None
    if reset and count >= limit:
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
        _send_reset_notification, "date", run_date=reset_at,
        args=[context.bot, user_id], id=job_id
    )


async def _send_reset_notification(bot, user_id: int) -> None:
    pass
