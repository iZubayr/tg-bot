import asyncio
import logging
from datetime import datetime
from html import escape
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.error import BadRequest
from telegram.ext import ContextTypes

from config import MAIN_ADMIN_ID
from database import (
    get_stats, is_admin, get_all_admins, get_admin_added_at,
    remove_admin, add_admin, get_user, mark_blocked, unblock_user,
    unblock_all, get_blocked_users, set_vip, get_vip_users,
    get_text, set_text, TEXT_LABELS, get_setting, set_setting,
    get_pending_messages,
    get_user_message_count, update_message_status,
    resolve_user_id,
)

logger = logging.getLogger(__name__)


def _clear(context) -> None:
    for k in [
        "waiting_broadcast", "waiting_admin_id", "waiting_text_edit",
        "replying_to", "waiting_user_search", "waiting_vip_add",
        "waiting_channel_id", "waiting_pinned_text", "waiting_remind_interval",
        "waiting_rate_limit", "waiting_help_limit",
    ]:
        context.user_data.pop(k, None)


def _main_kb(caller_id: int) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton("\U0001f4ca Statistika", callback_data="stats"),
            InlineKeyboardButton("\U0001f4e2 Broadcast",  callback_data="bc_menu"),
        ],
        [
            InlineKeyboardButton("\U0001f4ec Xabarlar",         callback_data="msgs"),
            InlineKeyboardButton("\U0001f465 Foydalanuvchilar", callback_data="users"),
        ],
        [InlineKeyboardButton("\u2699\ufe0f Sozlamalar", callback_data="settings")],
    ]
    if caller_id == MAIN_ADMIN_ID:
        rows.append([InlineKeyboardButton("\U0001f451 Adminlar", callback_data="admins")])
    return InlineKeyboardMarkup(rows)


def _back(to: str = "back") -> list:
    return [InlineKeyboardButton("\U0001f519 Orqaga", callback_data=to)]


async def admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_admin(update.effective_user.id):
        return
    _clear(context)
    await update.message.reply_text(
        "\U0001f6e0 <b>Admin panel</b>",
        reply_markup=_main_kb(update.effective_user.id),
        parse_mode="HTML",
    )


async def _handle_callback_inner(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if not is_admin(query.from_user.id):
        await query.answer("\u274c Ruxsat yo'q!", show_alert=True)
        return
    await query.answer()
    data = query.data
    uid  = query.from_user.id

    if data == "noop":
        return

    elif data == "back":
        _clear(context)
        await _edit(query, "\U0001f6e0 <b>Admin panel</b>", _main_kb(uid))

    # ── Statistika ────────────────────────────────────────────────────────────
    elif data == "stats":
        s  = get_stats()
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("\U0001f504 Yangilash", callback_data="stats")],
            _back(),
        ])
        text = (
            "\U0001f4ca <b>Statistika</b>\n\n"
            f"\U0001f465 Jami:       <b>{s['total']}</b>\n"
            f"\U0001f195 Bugun:      <b>{s['today']}</b>\n"
            f"\u2b50 VIP:        <b>{s['vip']}</b>\n"
            f"\U0001f6ab Bloklangan: <b>{s['blocked']}</b>"
        )
        try:
            await query.edit_message_text(text, reply_markup=kb, parse_mode="HTML")
        except BadRequest as e:
            if "not modified" in str(e).lower():
                await query.answer("\u2705 Allaqachon yangi!", show_alert=False)
            else:
                raise

    # ── Broadcast (faqat hozir, jadval olib tashlandi) ───────────────────────
    elif data == "bc_menu":
        _clear(context)
        context.user_data["waiting_broadcast"] = True
        await _edit(query,
                    "\U0001f4e2 <b>Broadcast</b>\n\n"
                    "Barcha userlarga yuboriladigan xabarni yuboring.\n"
                    "<i>Matn, rasm, video, stiker, GIF \u2014 barchasi qabul qilinadi.</i>",
                    InlineKeyboardMarkup([_back()]))

    # ── Xabarlar ──────────────────────────────────────────────────────────────
    elif data == "msgs":
        _clear(context)
        pending = get_pending_messages(uid)
        rem_on  = get_setting("reminder_enabled") == "true"
        rem_h   = get_setting("reminder_interval") or "2"
        await _edit(query, "\U0001f4ec <b>Xabarlar</b>",
                    InlineKeyboardMarkup([
                        [InlineKeyboardButton(f"\U0001f4e8 Javobsizlar ({len(pending)} ta)", callback_data="msgs_pending")],
                        [InlineKeyboardButton(f"{'🟢' if rem_on else '🔴'} Eslatma (har {rem_h}h)", callback_data="msgs_remind")],
                        _back(),
                    ]))

    elif data == "msgs_pending":
        rows = get_pending_messages(uid)
        if not rows:
            await _edit(query, "\U0001f4e8 <b>Javobsiz xabarlar</b>\n\nBarcha xabarlarga javob berilgan \u2705",
                        InlineKeyboardMarkup([_back("msgs")]))
            return
        buttons = []
        for row in rows[:10]:
            u    = get_user(row["user_id"])
            name = escape(u["first_name"]) if u else str(row["user_id"])
            prev = (row.get("message_preview") or "")[:30]
            buttons.append([InlineKeyboardButton(
                f"\U0001f464 {name}: {prev}" if prev else f"\U0001f464 {name}",
                callback_data=f"usr_prof_{row['user_id']}"
            )])
        buttons.append(_back("msgs"))
        await _edit(query, f"\U0001f4e8 <b>Javobsiz xabarlar</b> ({len(rows)} ta):", InlineKeyboardMarkup(buttons))

    elif data == "msgs_remind":
        rem_on = get_setting("reminder_enabled") == "true"
        rem_h  = get_setting("reminder_interval") or "2"
        state  = "🟢 Yoqiq" if rem_on else "🔴 O'chiq"
        await _edit(query, f"\u23f0 <b>Eslatma</b>\n\nHolat: {state}\nInterval: har {rem_h}h",
                    InlineKeyboardMarkup([
                        [InlineKeyboardButton("🔴 O'chirish" if rem_on else "🟢 Yoqish", callback_data="remind_tog")],
                        [InlineKeyboardButton("\u270f\ufe0f Intervalni o'zgartirish", callback_data="remind_set")],
                        _back("msgs"),
                    ]))

    elif data == "remind_tog":
        cur = get_setting("reminder_enabled") == "true"
        set_setting("reminder_enabled", "false" if cur else "true")
        from message_handler import _reschedule_reminder
        _reschedule_reminder(context)
        await query.answer("\u2705 O'zgartirildi!")
        rem_on = get_setting("reminder_enabled") == "true"
        rem_h  = get_setting("reminder_interval") or "2"
        state  = "🟢 Yoqiq" if rem_on else "🔴 O'chiq"
        await _edit(query, f"\u23f0 <b>Eslatma</b>\n\nHolat: {state}\nInterval: har {rem_h}h",
                    InlineKeyboardMarkup([
                        [InlineKeyboardButton("🔴 O'chirish" if rem_on else "🟢 Yoqish", callback_data="remind_tog")],
                        [InlineKeyboardButton("\u270f\ufe0f Intervalni o'zgartirish", callback_data="remind_set")],
                        _back("msgs"),
                    ]))

    elif data == "remind_set":
        context.user_data["waiting_remind_interval"] = True
        await _edit(query, "\u270f\ufe0f <b>Eslatma intervali</b>\n\nNecha soatda bir? (1-24):",
                    InlineKeyboardMarkup([_back("msgs_remind")]))

    # ── Foydalanuvchilar ──────────────────────────────────────────────────────
    elif data == "users":
        _clear(context)
        blk = len(get_blocked_users())
        vip = len(get_vip_users())
        await _edit(query, "\U0001f465 <b>Foydalanuvchilar</b>",
                    InlineKeyboardMarkup([
                        [InlineKeyboardButton("\U0001f50d Qidiruv (ID, ism, @username)", callback_data="users_search")],
                        [InlineKeyboardButton(f"\u2b50 VIP ({vip} ta)",        callback_data="users_vip"),
                         InlineKeyboardButton(f"\U0001f6ab Bloklangan ({blk} ta)", callback_data="blk_list")],
                        _back(),
                    ]))

    elif data == "users_search":
        _clear(context)
        context.user_data["waiting_user_search"] = True
        await _edit(query, "\U0001f50d <b>Qidiruv</b>\n\nID, ism yoki <code>@username</code> yuboring:",
                    InlineKeyboardMarkup([_back("users")]))

    elif data == "users_vip":
        vips = get_vip_users()
        if not vips:
            await _edit(query, "\u2b50 <b>VIP</b>\n\nRo'yxat bo'sh.",
                        InlineKeyboardMarkup([
                            [InlineKeyboardButton("\u2795 VIP qo'shish", callback_data="vip_add")],
                            _back("users"),
                        ]))
            return
        buttons = []
        for u in vips[:15]:
            name  = escape(u.get("first_name", "-"))
            uname = f" @{u['username']}" if u.get("username") else ""
            buttons.append([InlineKeyboardButton(f"\u2b50 {name}{uname}", callback_data=f"usr_prof_{u['user_id']}")])
        buttons.append([InlineKeyboardButton("\u2795 VIP qo'shish", callback_data="vip_add")])
        buttons.append(_back("users"))
        await _edit(query, f"\u2b50 <b>VIP foydalanuvchilar</b> ({len(vips)} ta):", InlineKeyboardMarkup(buttons))

    elif data == "vip_add":
        _clear(context)
        context.user_data["waiting_vip_add"] = True
        await _edit(query, "\u2b50 <b>VIP qo'shish</b>\n\nID yoki <code>@username</code> yuboring:",
                    InlineKeyboardMarkup([_back("users_vip")]))

    elif data == "blk_list":
        blk_users = get_blocked_users()
        if not blk_users:
            await _edit(query, "\U0001f6ab <b>Bloklangan</b>\n\nHech kim yo'q.",
                        InlineKeyboardMarkup([_back("users")]))
            return
        buttons = []
        for u in blk_users[:15]:
            name  = escape(u.get("first_name", "-"))
            uname = f" @{u['username']}" if u.get("username") else ""
            buttons.append([InlineKeyboardButton(f"\U0001f464 {name}{uname}", callback_data=f"usr_prof_{u['user_id']}")])
        buttons.append([InlineKeyboardButton("\U0001f513 Ommaviy blok ochish", callback_data="blk_all")])
        buttons.append(_back("users"))
        await _edit(query, f"\U0001f6ab <b>Bloklangan</b> ({len(blk_users)} ta):", InlineKeyboardMarkup(buttons))

    elif data == "blk_all":
        await _edit(query, "Barcha bloklangan foydalanuvchilardan blok olib tashlanadi. Tasdiqlaysizmi?",
                    InlineKeyboardMarkup([
                        [InlineKeyboardButton("\u2705 Ha, hammani ochish", callback_data="blk_all_ok")],
                        [InlineKeyboardButton("\U0001f519 Bekor qilish",   callback_data="blk_list")],
                    ]))

    elif data == "blk_all_ok":
        count = unblock_all()
        await query.answer(f"\u2705 {count} ta blokdan chiqarildi!", show_alert=True)
        await _edit(query, "\U0001f6ab <b>Bloklangan</b>\n\nHech kim yo'q.",
                    InlineKeyboardMarkup([_back("users")]))

    elif data.startswith("unblk_"):
        user_id = int(data.split("_", 1)[1])
        unblock_user(user_id)
        await query.answer("\u2705 Blok olib tashlandi!", show_alert=True)
        await _show_user_profile(query, context, user_id)

    elif data.startswith("prof_back_"):
        user_id = int(data.split("_", 2)[2])
        ctx = context.user_data.pop(f"prof_ctx_{user_id}", None)
        if ctx and ctx.get("orig_text"):
            orig_kb = InlineKeyboardMarkup([[
                InlineKeyboardButton("\U0001f4e9 Javob",   callback_data=f"reply_{user_id}"),
                InlineKeyboardButton("\U0001f464 Profil",  callback_data=f"usr_prof_{user_id}"),
                InlineKeyboardButton("\U0001f6ab Blokla", callback_data=f"block_{user_id}"),
            ]])
            try:
                await context.bot.edit_message_text(
                    chat_id=ctx["chat_id"],
                    message_id=ctx["msg_id"],
                    text=ctx["orig_text"],
                    reply_markup=orig_kb,
                    parse_mode="HTML",
                )
                return
            except Exception:
                pass
        blk = len(get_blocked_users())
        vip = len(get_vip_users())
        await _edit(query, "\U0001f465 <b>Foydalanuvchilar</b>",
                    InlineKeyboardMarkup([
                        [InlineKeyboardButton("\U0001f50d Qidiruv", callback_data="users_search")],
                        [InlineKeyboardButton(f"\u2b50 VIP ({vip} ta)", callback_data="users_vip"),
                         InlineKeyboardButton(f"\U0001f6ab Bloklangan ({blk} ta)", callback_data="blk_list")],
                        _back(),
                    ]))

    elif data.startswith("vip_del_"):
        user_id = int(data.split("_", 2)[2])
        set_vip(user_id, False)
        await query.answer("\u2705 VIP olib tashlandi!", show_alert=True)
        await _show_user_profile(query, context, user_id)

    elif data.startswith("vip_add_id_"):
        user_id = int(data.split("_", 3)[3])
        set_vip(user_id, True)
        await query.answer("\u2705 VIP qo'shildi!", show_alert=True)
        await _show_user_profile(query, context, user_id)

    elif data.startswith("usr_prof_"):
        await _show_user_profile(query, context, int(data.split("_", 2)[2]))

    # ── Sozlamalar ────────────────────────────────────────────────────────────
    elif data == "settings":
        _clear(context)
        chan_on = get_setting("channel_check_enabled") == "true"
        await _edit(query, "\u2699\ufe0f <b>Sozlamalar</b>",
                    InlineKeyboardMarkup([
                        [InlineKeyboardButton("\U0001f4dd Matnlar", callback_data="texts")],
                        [InlineKeyboardButton("\U0001f4cc Pinlangan xabar", callback_data="set_pin")],
                        [InlineKeyboardButton(f"{'🟢' if chan_on else '🔴'} Kanal obuna", callback_data="set_chan")],
                        [InlineKeyboardButton("\U0001f6a6 Rate limit", callback_data="set_ratelimit")],
                        [InlineKeyboardButton("\u2753 /help limiti", callback_data="set_helplimit")],
                        _back(),
                    ]))

    elif data == "texts":
        _clear(context)
        buttons = [[InlineKeyboardButton(lbl, callback_data=f"txt_{key}")]
                   for key, lbl in TEXT_LABELS.items()]
        buttons.append(_back("settings"))
        await _edit(query, "\U0001f4dd <b>Bot matnlari</b>:", InlineKeyboardMarkup(buttons))

    elif data.startswith("txt_edit_"):
        key = data.split("_", 2)[2]
        context.user_data["waiting_text_edit"] = key
        await _edit(query,
                    f"\U0001f4dd <b>{TEXT_LABELS.get(key, key)}</b>\n\nYangi matnni yuboring:\n"
                    "<i>HTML teglari: &lt;b&gt;, &lt;i&gt;, &lt;a href='...'&gt;</i>",
                    InlineKeyboardMarkup([[InlineKeyboardButton("\U0001f519 Bekor qilish", callback_data=f"txt_{key}")]]))

    elif data.startswith("txt_"):
        key = data.split("_", 1)[1]
        context.user_data.pop("waiting_text_edit", None)
        label   = TEXT_LABELS.get(key, key)
        current = get_text(key)
        display = escape(current[:300] + ("..." if len(current) > 300 else ""))
        await _edit(query,
                    f"\U0001f4dd <b>{label}</b>\n\n\U0001f4cc Hozirgi:\n<i>{display}</i>",
                    InlineKeyboardMarkup([
                        [InlineKeyboardButton("\u270f\ufe0f O'zgartirish", callback_data=f"txt_edit_{key}")],
                        _back("texts"),
                    ]))

    elif data == "set_pin":
        _clear(context)
        pin_on  = get_setting("pinned_enabled") == "true"
        pin_txt = get_setting("pinned_text")
        display = escape(pin_txt[:200]) if pin_txt else "<i>O'rnatilmagan</i>"
        state   = "🟢 Yoqiq" if pin_on else "🔴 O'chiq"
        await _edit(query,
                    f"\U0001f4cc <b>Pinlangan xabar</b>\n\nHolat: {state}\n\n{display}\n\n"
                    "<i>Yoqilganda barcha userlarga yuboriladi va chatda pin qilinadi.\n"
                    "O'chirilganda esa barcha userlardan pin belgisi olib tashlanadi (xabar o'chirmaydi).</i>",
                    InlineKeyboardMarkup([
                        [InlineKeyboardButton("🔴 O'chirish" if pin_on else "🟢 Yoqish", callback_data="set_pin_tog")],
                        [InlineKeyboardButton("\u270f\ufe0f Matnni o'zgartirish", callback_data="set_pin_edit")],
                        _back("settings"),
                    ]))

    elif data == "set_pin_tog":
        cur     = get_setting("pinned_enabled") == "true"
        new_val = "false" if cur else "true"
        set_setting("pinned_enabled", new_val)
        await query.answer("\u2705 O'zgartirildi!")
        pin_on  = new_val == "true"
        pin_txt = get_setting("pinned_text")
        display = escape(pin_txt[:200]) if pin_txt else "<i>O'rnatilmagan</i>"
        state   = "🟢 Yoqiq" if pin_on else "🔴 O'chiq"
        await _edit(query,
                    f"\U0001f4cc <b>Pinlangan xabar</b>\n\nHolat: {state}\n\n{display}",
                    InlineKeyboardMarkup([
                        [InlineKeyboardButton("🔴 O'chirish" if pin_on else "🟢 Yoqish", callback_data="set_pin_tog")],
                        [InlineKeyboardButton("\u270f\ufe0f Matnni o'zgartirish", callback_data="set_pin_edit")],
                        _back("settings"),
                    ]))
        if pin_on and pin_txt:
            from message_handler import _broadcast_pinned_to_all
            asyncio.create_task(_broadcast_pinned_to_all(context.bot, pin_txt))
            await query.message.reply_text("\U0001f4cc Pinlangan xabar barcha userlarga yuborilmoqda...")
        elif not pin_on:
            from message_handler import _unpin_for_all
            asyncio.create_task(_unpin_for_all(context.bot))
            await query.message.reply_text("\U0001f4cc Pin belgisi barcha userlardan olib tashlanmoqda (xabar o'chirmaydi)...")

    elif data == "set_pin_edit":
        context.user_data["waiting_pinned_text"] = True
        await _edit(query, "\U0001f4cc Yangi pinlangan xabarni yuboring (HTML ishlaydi):",
                    InlineKeyboardMarkup([[InlineKeyboardButton("\U0001f519 Bekor qilish", callback_data="set_pin")]]))

    elif data == "set_chan":
        _clear(context)
        chan_on  = get_setting("channel_check_enabled") == "true"
        chan_id  = get_setting("channel_id") or ""
        state    = "🟢 Yoqiq" if chan_on else "🔴 O'chiq"
        chan_disp = f"<code>{chan_id}</code>" if chan_id else "<i>O'rnatilmagan</i>"
        await _edit(query,
                    f"\U0001f514 <b>Kanal obuna tekshiruvi</b>\n\n"
                    f"Holat: {state}\n"
                    f"Kanal: {chan_disp}\n\n"
                    f"<b>Muhim:</b>\n"
                    f"1. Bot kanalga <b>admin</b> sifatida qo'shilgan bo'lishi shart\n"
                    f"2. Public kanal: <code>@username</code>\n"
                    f"3. Private kanal: raqamli ID (<code>-1001234567890</code>)\n"
                    f"4. Supabase service_role kaliti to'g'ri bo'lishi shart",
                    InlineKeyboardMarkup([
                        [InlineKeyboardButton("🔴 O'chirish" if chan_on else "🟢 Yoqish", callback_data="set_chan_tog")],
                        [InlineKeyboardButton("\u270f\ufe0f Kanal ID o'rnatish", callback_data="set_chan_id")],
                        [InlineKeyboardButton("\U0001f9ea Tekshiruv sinovlash", callback_data="set_chan_test")],
                        _back("settings"),
                    ]))

    elif data == "set_chan_tog":
        cur = get_setting("channel_check_enabled") == "true"
        new_val = "false" if cur else "true"
        set_setting("channel_check_enabled", new_val)
        await query.answer("\u2705 O'zgartirildi!")
        logger.info(f"Kanal obuna {'yoqildi' if new_val == 'true' else 'o\'chirildi'}")
        chan_on = new_val == "true"
        chan_id = get_setting("channel_id") or ""
        state   = "🟢 Yoqiq" if chan_on else "🔴 O'chiq"
        chan_disp = f"<code>{chan_id}</code>" if chan_id else "<i>O'rnatilmagan</i>"
        await _edit(query,
                    f"\U0001f514 <b>Kanal obuna</b>\n\nHolat: {state}\nKanal: {chan_disp}",
                    InlineKeyboardMarkup([
                        [InlineKeyboardButton("🔴 O'chirish" if chan_on else "🟢 Yoqish", callback_data="set_chan_tog")],
                        [InlineKeyboardButton("\u270f\ufe0f Kanal ID o'rnatish", callback_data="set_chan_id")],
                        [InlineKeyboardButton("\U0001f9ea Tekshiruv sinovlash", callback_data="set_chan_test")],
                        _back("settings"),
                    ]))

    elif data == "set_chan_id":
        context.user_data["waiting_channel_id"] = True
        await _edit(query,
                    "\u270f\ufe0f <b>Kanal ID</b>\n\n"
                    "Public: <code>@channelname</code>\n"
                    "Private: <code>-1001234567890</code>\n\n"
                    "<b>Botni kanalga admin qilish:</b>\n"
                    "Kanal > Boshqarish > Adminlar > Bot qo'shish",
                    InlineKeyboardMarkup([[InlineKeyboardButton("\U0001f519 Bekor qilish", callback_data="set_chan")]]))

    elif data == "set_chan_test":
        # Kanal tekshiruvini o'zingizda sinab ko'ring
        chan_id = get_setting("channel_id").strip()
        if not chan_id:
            await query.answer("\u274c Avval kanal ID o'rnating!", show_alert=True)
            return
        try:
            member = await context.bot.get_chat_member(chan_id, uid)
            await query.message.reply_text(
                f"\u2705 <b>Kanal ulanishi ishlayapti!</b>\n\n"
                f"Kanal: <code>{chan_id}</code>\n"
                f"Sizning statusingiz: <code>{member.status}</code>",
                parse_mode="HTML"
            )
        except Exception as e:
            await query.message.reply_text(
                f"\u274c <b>Kanal tekshirish xatosi:</b>\n\n"
                f"<code>{escape(str(e))}</code>\n\n"
                f"<b>Mumkin bo'lgan sabablar:</b>\n"
                f"1. Bot kanalga admin sifatida qo'shilmagan\n"
                f"2. Kanal ID noto'g'ri\n"
                f"3. Supabase ulanishi ishlamayapti",
                parse_mode="HTML"
            )

    # ── Rate limit ───────────────────────────────────────────────────
    elif data == "set_ratelimit":
        _clear(context)
        cur = get_setting("rate_limit_count") or "5"
        await _edit(query,
                    f"\U0001f6a6 <b>Rate limit</b>\n\n"
                    f"Hozirgi: soatiga <b>{cur}</b> ta xabar\n\n"
                    f"<i>0 qilib qo'ysangiz \u2014 oddiy userlar xabar yubora olmaydi.\n"
                    f"VIP userlar bu limitdan mustasno.</i>",
                    InlineKeyboardMarkup([
                        [InlineKeyboardButton("\u270f\ufe0f O'zgartirish", callback_data="set_ratelimit_edit")],
                        _back("settings"),
                    ]))

    elif data == "set_ratelimit_edit":
        context.user_data["waiting_rate_limit"] = True
        await _edit(query,
                    "\u270f\ufe0f <b>Rate limit</b>\n\n"
                    "Soatiga nechta xabar ruxsat etilsin? (0 \u2014 butunlay taqiq)",
                    InlineKeyboardMarkup([[InlineKeyboardButton("\U0001f519 Bekor qilish", callback_data="set_ratelimit")]]))

    # ── /help limiti ────────────────────────────────────────────────
    elif data == "set_helplimit":
        _clear(context)
        cur = get_setting("help_limit_count") or "2"
        await _edit(query,
                    f"\u2753 <b>/help limiti</b>\n\n"
                    f"Hozirgi: kuniga <b>{cur}</b> ta\n\n"
                    f"<i>0 qilib qo'ysangiz \u2014 /help buyrug'i butunlay cheklanadi.</i>",
                    InlineKeyboardMarkup([
                        [InlineKeyboardButton("\u270f\ufe0f O'zgartirish", callback_data="set_helplimit_edit")],
                        _back("settings"),
                    ]))

    elif data == "set_helplimit_edit":
        context.user_data["waiting_help_limit"] = True
        await _edit(query,
                    "\u270f\ufe0f <b>/help limiti</b>\n\n"
                    "Kuniga nechta /help ruxsat etilsin? (0 \u2014 butunlay taqiq)",
                    InlineKeyboardMarkup([[InlineKeyboardButton("\U0001f519 Bekor qilish", callback_data="set_helplimit")]]))

    # ── Adminlar (faqat ega) ──────────────────────────────────────────────────
    elif data == "admins":
        if uid != MAIN_ADMIN_ID:
            await query.answer("\u274c Faqat bot egasi uchun!", show_alert=True)
            return
        _clear(context)
        await _edit(query, "\U0001f451 <b>Adminlar ro'yxati</b>", _admins_kb())

    elif data == "adm_add":
        if uid != MAIN_ADMIN_ID:
            await query.answer("\u274c Faqat bot egasi uchun!", show_alert=True)
            return
        context.user_data["waiting_admin_id"] = True
        await _edit(query, "\U0001f464 <b>Admin qo'shish</b>\n\nID yoki <code>@username</code> yuboring:",
                    InlineKeyboardMarkup([_back("admins")]))

    elif data.startswith("adm_info_"):
        admin_id = int(data.split("_", 2)[2])
        is_main  = (admin_id == MAIN_ADMIN_ID)
        u        = get_user(admin_id)
        name     = escape(u["first_name"]) if u else "-"
        added    = "-"
        if not is_main:
            raw = get_admin_added_at(admin_id)
            if raw:
                try:
                    added = datetime.fromisoformat(raw.replace("Z", "+00:00")).strftime("%d.%m.%Y")
                except Exception:
                    added = raw[:10]
        text  = f"\U0001f464 <b>{name}</b>\n\n\U0001f194 <code>{admin_id}</code>\n"
        text += "\U0001f451 Asosiy admin\n" if is_main else f"\U0001f4c5 Qo'shilgan: {added}\n"
        buttons = []
        if not is_main:
            buttons.append([InlineKeyboardButton("\U0001f5d1 O'chirish", callback_data=f"adm_del_{admin_id}")])
        buttons.append(_back("admins"))
        await _edit(query, text, InlineKeyboardMarkup(buttons))

    elif data.startswith("adm_del_"):
        if uid != MAIN_ADMIN_ID:
            await query.answer("\u274c Faqat bot egasi uchun!", show_alert=True)
            return
        admin_id = int(data.split("_", 2)[2])
        if admin_id == MAIN_ADMIN_ID:
            await query.answer("\u274c Asosiy adminni o'chirib bo'lmaydi!", show_alert=True)
            return
        remove_admin(admin_id)
        await query.answer("\u2705 Admin o'chirildi!", show_alert=True)
        await _edit(query, "\U0001f451 <b>Adminlar ro'yxati</b>", _admins_kb())

    # ── Xabar tugmalari ───────────────────────────────────────────────────────
    elif data.startswith("block_"):
        user_id = int(data.split("_", 1)[1])
        if is_admin(user_id):
            await query.answer("\u274c Adminni bloklash mumkin emas!", show_alert=True)
            return
        mark_blocked(user_id)
        await query.answer("\u2705 Bloklandi!", show_alert=True)
        try:
            await query.edit_message_reply_markup(reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("\U0001f6ab Bloklangan", callback_data="noop")
            ]]))
        except BadRequest:
            pass

    elif data.startswith("reply_"):
        user_id = int(data.split("_", 1)[1])
        u       = get_user(user_id)
        name    = escape(u["first_name"]) if u else str(user_id)
        uname   = f"@{u['username']}" if u and u.get("username") else "-"
        count   = get_user_message_count(user_id)
        is_vip  = u.get("vip", False) if u else False
        vip_str = " \u2b50" if is_vip else ""
        context.user_data["replying_to"] = {
            "user_id":   user_id,
            "msg_id":    query.message.message_id,
            "chat_id":   query.message.chat_id,
            "orig_text": query.message.text or query.message.caption or "",
        }
        await query.edit_message_text(
            f"\u270f\ufe0f <b>Javob yozilyapti</b>{vip_str}\n\n"
            f"\U0001f464 <b>{name}</b>  \u00b7  {escape(uname)}\n"
            f"\U0001f194 <code>{user_id}</code>  \U0001f4ac {count} ta\n\n"
            "Xabaringizni yuboring:",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("\u274c Bekor qilish", callback_data="rpl_cancel")
            ]]),
        )

    elif data == "rpl_cancel":
        info = context.user_data.pop("replying_to", None)
        if info:
            uid     = info["user_id"]
            orig_kb = InlineKeyboardMarkup([[
                InlineKeyboardButton("\U0001f4e9 Javob",   callback_data=f"reply_{uid}"),
                InlineKeyboardButton("\U0001f464 Profil",  callback_data=f"usr_prof_{uid}"),
                InlineKeyboardButton("\U0001f6ab Blokla", callback_data=f"block_{uid}"),
            ]])
            try:
                await context.bot.edit_message_text(
                    chat_id=info["chat_id"],
                    message_id=info["msg_id"],
                    text=info["orig_text"],
                    reply_markup=orig_kb,
                    parse_mode="HTML",
                )
                return
            except Exception:
                pass
        await query.edit_message_text("\u274c Javob bekor qilindi.")


# ─── Yordamchi funksiyalar ────────────────────────────────────────────────────

async def _show_user_profile(query, context, user_id: int) -> None:
    u = get_user(user_id)
    if not u:
        await query.message.reply_text("\u274c Foydalanuvchi topilmadi!")
        return
    name      = escape(u.get("first_name", "-"))
    uname     = f"@{escape(u['username'])}" if u.get("username") else "-"
    is_blk    = u.get("is_blocked", False)
    is_vip    = u.get("vip", False)
    joined    = (u.get("joined_at") or "")[:10]
    msg_count = get_user_message_count(user_id)
    vip_str   = "Ha \u2b50" if is_vip else "Yo'q"

    text = (
        f"\U0001f464 <b>{name}</b>\n\n"
        f"\U0001f194 <code>{user_id}</code>  \u00b7  {uname}\n"
        f"\U0001f4c5 Qo'shilgan: {joined}\n"
        f"\U0001f4ac Xabarlar: {msg_count}\n"
        f"\u2b50 VIP: {vip_str}\n"
        f"\U0001f6ab Holat: {'Bloklangan' if is_blk else 'Faol'}"
    )

    from_user_msg = False
    if query.message.reply_markup:
        for row in query.message.reply_markup.inline_keyboard:
            for btn in row:
                if f"reply_{user_id}" in (btn.callback_data or ""):
                    from_user_msg = True
                    break

    if from_user_msg:
        context.user_data[f"prof_ctx_{user_id}"] = {
            "orig_text": query.message.text or "",
            "msg_id":    query.message.message_id,
            "chat_id":   query.message.chat_id,
        }
        back_btn = [InlineKeyboardButton("\U0001f519 Orqaga", callback_data=f"prof_back_{user_id}")]
    else:
        back_btn = _back("users")

    buttons = [
        [
            InlineKeyboardButton("\U0001f4e9 Javob", callback_data=f"reply_{user_id}"),
            InlineKeyboardButton("\U0001f513 Blokdan chiq" if is_blk else "\U0001f6ab Blokla",
                                 callback_data=f"unblk_{user_id}" if is_blk else f"block_{user_id}"),
        ],
        [InlineKeyboardButton(
            "\u2b50 VIP olib tashlash" if is_vip else "\u2b50 VIP qo'shish",
            callback_data=f"vip_del_{user_id}" if is_vip else f"vip_add_id_{user_id}",
        )],
        back_btn,
    ]
    await _edit(query, text, InlineKeyboardMarkup(buttons))


def _admins_kb() -> InlineKeyboardMarkup:
    buttons = []
    for aid in get_all_admins():
        u    = get_user(aid)
        name = escape(u["first_name"]) if u else str(aid)
        lbl  = f"\U0001f451 {name}" if aid == MAIN_ADMIN_ID else f"\U0001f464 {name}"
        buttons.append([InlineKeyboardButton(lbl, callback_data=f"adm_info_{aid}")])
    buttons.append([InlineKeyboardButton("\u2795 Admin qo'shish", callback_data="adm_add")])
    buttons.append(_back())
    return InlineKeyboardMarkup(buttons)


async def _edit(query, text: str, kb: InlineKeyboardMarkup) -> None:
    try:
        await query.edit_message_text(text, reply_markup=kb, parse_mode="HTML")
    except BadRequest as e:
        if "not modified" not in str(e).lower():
            raise


async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _handle_callback_inner(update, context)
