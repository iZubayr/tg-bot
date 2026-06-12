import io
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
    get_pending_messages, get_pending_broadcasts, delete_scheduled_broadcast,
    get_user_message_count, get_user_growth, update_message_status,
    resolve_user_id,
)

logger = logging.getLogger(__name__)


def _clear(context) -> None:
    for k in [
        "waiting_broadcast", "waiting_admin_id", "waiting_text_edit",
        "replying_to", "waiting_user_search", "waiting_vip_add",
        "waiting_channel_id", "waiting_pinned_text", "waiting_bc_message",
        "waiting_bc_time", "bc_message_data", "waiting_remind_interval",
    ]:
        context.user_data.pop(k, None)


def _main_kb(caller_id: int) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton("📊 Statistika", callback_data="stats"),
            InlineKeyboardButton("📢 Broadcast",  callback_data="bc_menu"),
        ],
        [
            InlineKeyboardButton("📬 Xabarlar",        callback_data="msgs"),
            InlineKeyboardButton("👥 Foydalanuvchilar", callback_data="users"),
        ],
        [InlineKeyboardButton("⚙️ Sozlamalar", callback_data="settings")],
    ]
    if caller_id == MAIN_ADMIN_ID:
        rows.append([InlineKeyboardButton("👑 Adminlar", callback_data="admins")])
    return InlineKeyboardMarkup(rows)


def _back(to: str = "back") -> list:
    return [InlineKeyboardButton("🔙 Orqaga", callback_data=to)]


async def admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_admin(update.effective_user.id):
        return
    _clear(context)
    await update.message.reply_text(
        "🛠 <b>Admin panel</b>",
        reply_markup=_main_kb(update.effective_user.id),
        parse_mode="HTML",
    )


async def _handle_callback_inner(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if not is_admin(query.from_user.id):
        await query.answer("❌ Ruxsat yo'q!", show_alert=True)
        return
    await query.answer()
    data = query.data
    uid  = query.from_user.id

    if data == "noop":
        return

    elif data == "back":
        _clear(context)
        await _edit(query, "🛠 <b>Admin panel</b>", _main_kb(uid))

    # ── Statistika ────────────────────────────────────────────────────────────
    elif data == "stats":
        s  = get_stats()
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔄 Yangilash", callback_data="stats"),
             InlineKeyboardButton("📈 Grafik",    callback_data="stat_graph")],
            _back(),
        ])
        text = (
            f"📊 <b>Statistika</b>\n\n"
            f"👥 Jami:       <b>{s['total']}</b>\n"
            f"🆕 Bugun:      <b>{s['today']}</b>\n"
            f"⭐ VIP:        <b>{s['vip']}</b>\n"
            f"🚫 Bloklangan: <b>{s['blocked']}</b>"
        )
        try:
            await query.edit_message_text(text, reply_markup=kb, parse_mode="HTML")
        except BadRequest as e:
            if "not modified" in str(e).lower():
                await query.answer("✅ Allaqachon yangi!", show_alert=False)
            else:
                raise

    elif data == "stat_graph":
        await _send_graph(query, context)

    # ── Broadcast ─────────────────────────────────────────────────────────────
    elif data == "bc_menu":
        _clear(context)
        bcs  = get_pending_broadcasts()
        bc_n = f" ({len(bcs)} ta)" if bcs else ""
        await _edit(query, "📢 <b>Broadcast</b>\n\nQanday yubormoqchisiz?",
                    InlineKeyboardMarkup([
                        [InlineKeyboardButton("📤 Hozir",   callback_data="bc_now"),
                         InlineKeyboardButton("⏰ Jadval",  callback_data="bc_sched")],
                        [InlineKeyboardButton(f"📋 Jadval ro'yxati{bc_n}", callback_data="bc_list")],
                        _back(),
                    ]))

    elif data == "bc_now":
        _clear(context)
        context.user_data["waiting_broadcast"] = True
        await _edit(query, "📤 <b>Broadcast — Hozir</b>\n\nXabarni yuboring (matn, rasm, video, stiker...):",
                    InlineKeyboardMarkup([_back("bc_menu")]))

    elif data == "bc_sched":
        _clear(context)
        context.user_data["waiting_bc_message"] = True
        await _edit(query, "⏰ <b>Jadval broadcast</b>\n\nAvval broadcast xabarini yuboring:",
                    InlineKeyboardMarkup([_back("bc_menu")]))

    elif data == "bc_list":
        bcs = get_pending_broadcasts()
        if not bcs:
            await _edit(query, "📋 <b>Jadval ro'yxati</b>\n\nJadvalda xabar yo'q.",
                        InlineKeyboardMarkup([_back("bc_menu")]))
            return
        import pytz; tz = pytz.timezone("Asia/Tashkent")
        buttons = []
        for bc in bcs[:10]:
            try:
                lbl = datetime.fromisoformat(bc["scheduled_at"]).astimezone(tz).strftime("%d.%m %H:%M")
            except Exception:
                lbl = bc["scheduled_at"][:16]
            buttons.append([InlineKeyboardButton(f"🗓 {lbl} — ❌", callback_data=f"bc_del_{bc['id']}")])
        buttons.append(_back("bc_menu"))
        await _edit(query, f"📋 <b>Jadval ro'yxati</b> ({len(bcs)} ta):", InlineKeyboardMarkup(buttons))

    elif data.startswith("bc_del_"):
        bc_id = int(data.split("_", 2)[2])
        delete_scheduled_broadcast(bc_id)
        sched = context.bot_data.get("scheduler")
        if sched:
            try: sched.remove_job(f"bc_{bc_id}")
            except: pass
        await query.answer("✅ O'chirildi!", show_alert=True)
        bcs = get_pending_broadcasts()
        if not bcs:
            await _edit(query, "📋 <b>Jadval ro'yxati</b>\n\nJadvalda xabar yo'q.",
                        InlineKeyboardMarkup([_back("bc_menu")]))
        else:
            import pytz; tz = pytz.timezone("Asia/Tashkent")
            buttons = []
            for bc in bcs[:10]:
                try:
                    lbl = datetime.fromisoformat(bc["scheduled_at"]).astimezone(tz).strftime("%d.%m %H:%M")
                except: lbl = bc["scheduled_at"][:16]
                buttons.append([InlineKeyboardButton(f"🗓 {lbl} — ❌", callback_data=f"bc_del_{bc['id']}")])
            buttons.append(_back("bc_menu"))
            await _edit(query, f"📋 <b>Jadval ro'yxati</b> ({len(bcs)} ta):", InlineKeyboardMarkup(buttons))

    # ── Xabarlar ──────────────────────────────────────────────────────────────
    elif data == "msgs":
        _clear(context)
        pending = get_pending_messages(uid)
        rem_on  = get_setting("reminder_enabled") == "true"
        rem_h   = get_setting("reminder_interval") or "2"
        await _edit(query, "📬 <b>Xabarlar</b>",
                    InlineKeyboardMarkup([
                        [InlineKeyboardButton(f"📨 Javobsizlar ({len(pending)} ta)", callback_data="msgs_pending")],
                        [InlineKeyboardButton(f"{'🟢' if rem_on else '🔴'} Eslatma (har {rem_h}h)", callback_data="msgs_remind")],
                        _back(),
                    ]))

    elif data == "msgs_pending":
        rows = get_pending_messages(uid)
        if not rows:
            await _edit(query, "📨 <b>Javobsiz xabarlar</b>\n\nBarcha xabarlarga javob berilgan ✅",
                        InlineKeyboardMarkup([_back("msgs")]))
            return
        buttons = []
        for row in rows[:10]:
            u    = get_user(row["user_id"])
            name = escape(u["first_name"]) if u else str(row["user_id"])
            prev = (row.get("message_preview") or "")[:30]
            buttons.append([InlineKeyboardButton(
                f"👤 {name}: {prev}" if prev else f"👤 {name}",
                callback_data=f"usr_prof_{row['user_id']}"
            )])
        buttons.append(_back("msgs"))
        await _edit(query, f"📨 <b>Javobsiz xabarlar</b> ({len(rows)} ta):", InlineKeyboardMarkup(buttons))

    elif data == "msgs_remind":
        rem_on = get_setting("reminder_enabled") == "true"
        rem_h  = get_setting("reminder_interval") or "2"
        await _edit(query,
                    f"⏰ <b>Eslatma</b>\n\nHolat: {'🟢 Yoqiq' if rem_on else '🔴 O\'chiq'}\nInterval: har {rem_h}h",
                    InlineKeyboardMarkup([
                        [InlineKeyboardButton("🔴 O'chirish" if rem_on else "🟢 Yoqish", callback_data="remind_tog")],
                        [InlineKeyboardButton("✏️ Intervalni o'zgartirish", callback_data="remind_set")],
                        _back("msgs"),
                    ]))

    elif data == "remind_tog":
        cur = get_setting("reminder_enabled") == "true"
        set_setting("reminder_enabled", "false" if cur else "true")
        from message_handler import _reschedule_reminder
        _reschedule_reminder(context)
        await query.answer("✅ O'zgartirildi!")
        rem_on = get_setting("reminder_enabled") == "true"
        rem_h  = get_setting("reminder_interval") or "2"
        await _edit(query,
                    f"⏰ <b>Eslatma</b>\n\nHolat: {'🟢 Yoqiq' if rem_on else '🔴 O\'chiq'}\nInterval: har {rem_h}h",
                    InlineKeyboardMarkup([
                        [InlineKeyboardButton("🔴 O'chirish" if rem_on else "🟢 Yoqish", callback_data="remind_tog")],
                        [InlineKeyboardButton("✏️ Intervalni o'zgartirish", callback_data="remind_set")],
                        _back("msgs"),
                    ]))

    elif data == "remind_set":
        context.user_data["waiting_remind_interval"] = True
        await _edit(query, "✏️ <b>Eslatma intervali</b>\n\nNecha soatda bir? (1–24):",
                    InlineKeyboardMarkup([_back("msgs_remind")]))

    # ── Foydalanuvchilar ──────────────────────────────────────────────────────
    elif data == "users":
        _clear(context)
        blk = len(get_blocked_users())
        vip = len(get_vip_users())
        await _edit(query, "👥 <b>Foydalanuvchilar</b>",
                    InlineKeyboardMarkup([
                        [InlineKeyboardButton("🔍 Qidiruv (ID, ism, @username)", callback_data="users_search")],
                        [InlineKeyboardButton(f"⭐ VIP ({vip} ta)",        callback_data="users_vip"),
                         InlineKeyboardButton(f"🚫 Bloklangan ({blk} ta)", callback_data="blk_list")],
                        _back(),
                    ]))

    elif data == "users_search":
        _clear(context)
        context.user_data["waiting_user_search"] = True
        await _edit(query,
                    "🔍 <b>Qidiruv</b>\n\nID, ism yoki <code>@username</code> yuboring:",
                    InlineKeyboardMarkup([_back("users")]))

    elif data == "users_vip":
        vips = get_vip_users()
        if not vips:
            await _edit(query, "⭐ <b>VIP</b>\n\nRo'yxat bo'sh.",
                        InlineKeyboardMarkup([
                            [InlineKeyboardButton("➕ VIP qo'shish", callback_data="vip_add")],
                            _back("users"),
                        ]))
            return
        buttons = []
        for u in vips[:15]:
            name = escape(u.get("first_name", "—"))
            uname = f" @{u['username']}" if u.get("username") else ""
            buttons.append([InlineKeyboardButton(f"⭐ {name}{uname}", callback_data=f"usr_prof_{u['user_id']}")])
        buttons.append([InlineKeyboardButton("➕ VIP qo'shish", callback_data="vip_add")])
        buttons.append(_back("users"))
        await _edit(query, f"⭐ <b>VIP foydalanuvchilar</b> ({len(vips)} ta):", InlineKeyboardMarkup(buttons))

    elif data == "vip_add":
        _clear(context)
        context.user_data["waiting_vip_add"] = True
        await _edit(query,
                    "⭐ <b>VIP qo'shish</b>\n\nID yoki <code>@username</code> yuboring:",
                    InlineKeyboardMarkup([_back("users_vip")]))

    elif data == "blk_list":
        blk_users = get_blocked_users()
        if not blk_users:
            await _edit(query, "🚫 <b>Bloklangan</b>\n\nHech kim yo'q.",
                        InlineKeyboardMarkup([_back("users")]))
            return
        buttons = []
        for u in blk_users[:15]:
            name  = escape(u.get("first_name", "—"))
            uname = f" @{u['username']}" if u.get("username") else ""
            buttons.append([InlineKeyboardButton(f"👤 {name}{uname}", callback_data=f"usr_prof_{u['user_id']}")])
        buttons.append([InlineKeyboardButton("🔓 Ommaviy blok ochish", callback_data="blk_all")])
        buttons.append(_back("users"))
        await _edit(query, f"🚫 <b>Bloklangan</b> ({len(blk_users)} ta):", InlineKeyboardMarkup(buttons))

    elif data == "blk_all":
        await _edit(query,
                    "🔓 Barcha bloklangan foydalanuvchilardan blok olib tashlanadi. Tasdiqlaysizmi?",
                    InlineKeyboardMarkup([
                        [InlineKeyboardButton("✅ Ha, hammani ochish", callback_data="blk_all_ok")],
                        [InlineKeyboardButton("🔙 Bekor qilish",       callback_data="blk_list")],
                    ]))

    elif data == "blk_all_ok":
        count = unblock_all()
        await query.answer(f"✅ {count} ta blokdan chiqarildi!", show_alert=True)
        await _edit(query, "🚫 <b>Bloklangan</b>\n\nHech kim yo'q.", InlineKeyboardMarkup([_back("users")]))

    elif data.startswith("unblk_"):
        user_id = int(data.split("_", 1)[1])
        unblock_user(user_id)
        await query.answer("✅ Blok olib tashlandi!", show_alert=True)
        await _show_user_profile(query, context, user_id)

    elif data.startswith("vip_del_"):
        user_id = int(data.split("_", 2)[2])
        set_vip(user_id, False)
        await query.answer("✅ VIP olib tashlandi!", show_alert=True)
        await _show_user_profile(query, context, user_id)

    elif data.startswith("vip_add_id_"):
        user_id = int(data.split("_", 3)[3])
        set_vip(user_id, True)
        await query.answer("✅ VIP qo'shildi!", show_alert=True)
        await _show_user_profile(query, context, user_id)

    elif data.startswith("usr_prof_"):
        await _show_user_profile(query, context, int(data.split("_", 2)[2]))

    # ── Sozlamalar ────────────────────────────────────────────────────────────
    elif data == "settings":
        _clear(context)
        chan_on = get_setting("channel_check_enabled") == "true"
        await _edit(query, "⚙️ <b>Sozlamalar</b>",
                    InlineKeyboardMarkup([
                        [InlineKeyboardButton("📝 Matnlar",                           callback_data="texts")],
                        [InlineKeyboardButton("📌 Pinlangan xabar",                   callback_data="set_pin")],
                        [InlineKeyboardButton(f"{'🟢' if chan_on else '🔴'} Kanal obuna", callback_data="set_chan")],
                        _back(),
                    ]))

    elif data == "texts":
        _clear(context)
        buttons = [[InlineKeyboardButton(lbl, callback_data=f"txt_{key}")]
                   for key, lbl in TEXT_LABELS.items()]
        buttons.append(_back("settings"))
        await _edit(query, "📝 <b>Bot matnlari</b>:", InlineKeyboardMarkup(buttons))

    elif data.startswith("txt_edit_"):
        key = data.split("_", 2)[2]
        context.user_data["waiting_text_edit"] = key
        await _edit(query,
                    f"📝 <b>{TEXT_LABELS.get(key, key)}</b>\n\nYangi matnni yuboring:\n"
                    f"<i>HTML teglari: &lt;b&gt;, &lt;i&gt;, &lt;a href='...'&gt;</i>",
                    InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Bekor qilish", callback_data=f"txt_{key}")]]))

    elif data.startswith("txt_"):
        key = data.split("_", 1)[1]
        context.user_data.pop("waiting_text_edit", None)
        label   = TEXT_LABELS.get(key, key)
        current = get_text(key)
        display = escape(current[:300] + ("..." if len(current) > 300 else ""))
        await _edit(query,
                    f"📝 <b>{label}</b>\n\n📌 Hozirgi:\n<i>{display}</i>",
                    InlineKeyboardMarkup([
                        [InlineKeyboardButton("✏️ O'zgartirish", callback_data=f"txt_edit_{key}")],
                        _back("texts"),
                    ]))

    elif data == "set_pin":
        _clear(context)
        pin_on  = get_setting("pinned_enabled") == "true"
        pin_txt = get_setting("pinned_text")
        display = escape(pin_txt[:200]) if pin_txt else "<i>O'rnatilmagan</i>"
        await _edit(query,
                    f"📌 <b>Pinlangan xabar</b>\n\nHolat: {'🟢 Yoqiq' if pin_on else '🔴 O\'chiq'}\n\n{display}",
                    InlineKeyboardMarkup([
                        [InlineKeyboardButton("🔴 O'chirish" if pin_on else "🟢 Yoqish", callback_data="set_pin_tog")],
                        [InlineKeyboardButton("✏️ Matnni o'zgartirish", callback_data="set_pin_edit")],
                        _back("settings"),
                    ]))

    elif data == "set_pin_tog":
        cur = get_setting("pinned_enabled") == "true"
        set_setting("pinned_enabled", "false" if cur else "true")
        await query.answer("✅ O'zgartirildi!")
        pin_on  = get_setting("pinned_enabled") == "true"
        pin_txt = get_setting("pinned_text")
        display = escape(pin_txt[:200]) if pin_txt else "<i>O'rnatilmagan</i>"
        await _edit(query,
                    f"📌 <b>Pinlangan xabar</b>\n\nHolat: {'🟢 Yoqiq' if pin_on else '🔴 O\'chiq'}\n\n{display}",
                    InlineKeyboardMarkup([
                        [InlineKeyboardButton("🔴 O'chirish" if pin_on else "🟢 Yoqish", callback_data="set_pin_tog")],
                        [InlineKeyboardButton("✏️ Matnni o'zgartirish", callback_data="set_pin_edit")],
                        _back("settings"),
                    ]))

    elif data == "set_pin_edit":
        context.user_data["waiting_pinned_text"] = True
        await _edit(query, "📌 Yangi pinlangan xabarni yuboring (HTML ishlaydi):",
                    InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Bekor qilish", callback_data="set_pin")]]))

    elif data == "set_chan":
        _clear(context)
        chan_on = get_setting("channel_check_enabled") == "true"
        chan_id = get_setting("channel_id") or "<i>O'rnatilmagan</i>"
        await _edit(query,
                    f"🔔 <b>Kanal obuna</b>\n\nHolat: {'🟢 Yoqiq' if chan_on else '🔴 O\'chiq'}\nKanal: <code>{chan_id}</code>",
                    InlineKeyboardMarkup([
                        [InlineKeyboardButton("🔴 O'chirish" if chan_on else "🟢 Yoqish", callback_data="set_chan_tog")],
                        [InlineKeyboardButton("✏️ Kanal ID o'rnatish", callback_data="set_chan_id")],
                        _back("settings"),
                    ]))

    elif data == "set_chan_tog":
        cur = get_setting("channel_check_enabled") == "true"
        set_setting("channel_check_enabled", "false" if cur else "true")
        await query.answer("✅ O'zgartirildi!")
        chan_on = get_setting("channel_check_enabled") == "true"
        chan_id = get_setting("channel_id") or "<i>O'rnatilmagan</i>"
        await _edit(query,
                    f"🔔 <b>Kanal obuna</b>\n\nHolat: {'🟢 Yoqiq' if chan_on else '🔴 O\'chiq'}\nKanal: <code>{chan_id}</code>",
                    InlineKeyboardMarkup([
                        [InlineKeyboardButton("🔴 O'chirish" if chan_on else "🟢 Yoqish", callback_data="set_chan_tog")],
                        [InlineKeyboardButton("✏️ Kanal ID o'rnatish", callback_data="set_chan_id")],
                        _back("settings"),
                    ]))

    elif data == "set_chan_id":
        context.user_data["waiting_channel_id"] = True
        await _edit(query,
                    "✏️ Kanal @username yoki ID yuboring:\nMisol: <code>@mychannel</code>",
                    InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Bekor qilish", callback_data="set_chan")]]))

    # ── Adminlar (faqat ega) ──────────────────────────────────────────────────
    elif data == "admins":
        if uid != MAIN_ADMIN_ID:
            await query.answer("❌ Faqat bot egasi uchun!", show_alert=True)
            return
        _clear(context)
        await _edit(query, "👑 <b>Adminlar ro'yxati</b>", _admins_kb())

    elif data == "adm_add":
        if uid != MAIN_ADMIN_ID:
            await query.answer("❌ Faqat bot egasi uchun!", show_alert=True)
            return
        context.user_data["waiting_admin_id"] = True
        await _edit(query,
                    "👤 <b>Admin qo'shish</b>\n\nID yoki <code>@username</code> yuboring:",
                    InlineKeyboardMarkup([_back("admins")]))

    elif data.startswith("adm_info_"):
        admin_id = int(data.split("_", 2)[2])
        is_main  = (admin_id == MAIN_ADMIN_ID)
        u        = get_user(admin_id)
        name     = escape(u["first_name"]) if u else "—"
        added    = "—"
        if not is_main:
            raw = get_admin_added_at(admin_id)
            if raw:
                try:
                    added = datetime.fromisoformat(raw.replace("Z", "+00:00")).strftime("%d.%m.%Y")
                except Exception:
                    added = raw[:10]
        text  = f"👤 <b>{name}</b>\n\n🆔 <code>{admin_id}</code>\n"
        text += "👑 Asosiy admin\n" if is_main else f"📅 Qo'shilgan: {added}\n"
        buttons = []
        if not is_main:
            buttons.append([InlineKeyboardButton("🗑 O'chirish", callback_data=f"adm_del_{admin_id}")])
        buttons.append(_back("admins"))
        await _edit(query, text, InlineKeyboardMarkup(buttons))

    elif data.startswith("adm_del_"):
        if uid != MAIN_ADMIN_ID:
            await query.answer("❌ Faqat bot egasi uchun!", show_alert=True)
            return
        admin_id = int(data.split("_", 2)[2])
        if admin_id == MAIN_ADMIN_ID:
            await query.answer("❌ Asosiy adminni o'chirib bo'lmaydi!", show_alert=True)
            return
        remove_admin(admin_id)
        await query.answer("✅ Admin o'chirildi!", show_alert=True)
        await _edit(query, "👑 <b>Adminlar ro'yxati</b>", _admins_kb())

    # ── Xabar tugmalari ───────────────────────────────────────────────────────
    elif data.startswith("block_"):
        user_id = int(data.split("_", 1)[1])
        if is_admin(user_id):
            await query.answer("❌ Adminni bloklash mumkin emas!", show_alert=True)
            return
        mark_blocked(user_id)
        await query.answer("✅ Bloklandi!", show_alert=True)
        try:
            await query.edit_message_reply_markup(reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🚫 Bloklangan", callback_data="noop")
            ]]))
        except BadRequest:
            pass

    elif data.startswith("reply_"):
        user_id = int(data.split("_", 1)[1])
        u       = get_user(user_id)
        name    = escape(u["first_name"]) if u else str(user_id)
        uname   = f"@{u['username']}" if u and u.get("username") else "—"
        count   = get_user_message_count(user_id)
        is_vip  = u.get("vip", False) if u else False
        context.user_data["replying_to"] = {
            "user_id": user_id,
            "msg_id":  query.message.message_id,
            "chat_id": query.message.chat_id,
        }
        vip_str = " ⭐ VIP" if is_vip else ""
        await query.message.reply_text(
            f"✏️ <b>Javob yozilyapti</b>{vip_str}\n\n"
            f"👤 <b>{name}</b>  ·  {escape(uname)}\n"
            f"🆔 <code>{user_id}</code>\n"
            f"💬 Jami xabarlar: {count}\n\n"
            f"Matn, rasm, video, stiker — istalgan narsani yuboring.",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("❌ Bekor qilish", callback_data="rpl_cancel")
            ]]),
        )

    elif data == "rpl_cancel":
        context.user_data.pop("replying_to", None)
        await query.edit_message_text("❌ Javob bekor qilindi.")


# ─── Yordamchi funksiyalar ────────────────────────────────────────────────────

async def _show_user_profile(query, context, user_id: int) -> None:
    u = get_user(user_id)
    if not u:
        await query.answer("Foydalanuvchi topilmadi!", show_alert=True)
        return
    name      = escape(u.get("first_name", "—"))
    uname     = f"@{escape(u['username'])}" if u.get("username") else "—"
    is_blk    = u.get("is_blocked", False)
    is_vip    = u.get("vip", False)
    joined    = (u.get("joined_at") or "")[:10]
    msg_count = get_user_message_count(user_id)
    vip_str   = "Ha ⭐" if is_vip else "Yo'q"

    text = (
        f"👤 <b>{name}</b>\n\n"
        f"🆔 <code>{user_id}</code>  ·  {uname}\n"
        f"📅 Qo'shilgan: {joined}\n"
        f"💬 Xabarlar: {msg_count}\n"
        f"⭐ VIP: {vip_str}\n"
        f"🚫 Holat: {'Bloklangan' if is_blk else 'Faol'}"
    )
    buttons = [
        [
            InlineKeyboardButton("📩 Javob", callback_data=f"reply_{user_id}"),
            InlineKeyboardButton("🔓 Blokdan chiq" if is_blk else "🚫 Blokla",
                                 callback_data=f"unblk_{user_id}" if is_blk else f"block_{user_id}"),
        ],
        [InlineKeyboardButton(
            "⭐ VIP olib tashlash" if is_vip else "⭐ VIP qo'shish",
            callback_data=f"vip_del_{user_id}" if is_vip else f"vip_add_id_{user_id}",
        )],
        _back("users"),
    ]
    # Har doim yangi xabar sifatida — user xabarini o'zgartirmaydi
    await query.message.reply_text(text, reply_markup=InlineKeyboardMarkup(buttons), parse_mode="HTML")


async def _send_graph(query, context) -> None:
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        await query.message.reply_text("❌ matplotlib o'rnatilmagan.")
        return
    data   = get_user_growth(7)
    dates  = [d["date"][5:] for d in data]
    counts = [d["count"] for d in data]
    fig, ax = plt.subplots(figsize=(8, 4))
    fig.patch.set_facecolor("#FFFFFF")
    ax.set_facecolor("#F5F5F5")
    bars = ax.bar(dates, counts, color="#6C8EBF", width=0.55, edgecolor="none")
    ax.bar_label(bars, padding=3, fontsize=10)
    ax.set_title("So'nggi 7 kunda yangi foydalanuvchilar", fontsize=12, pad=10)
    ax.set_ylim(0, max(counts or [1]) + max(1, max(counts or [1]) * 0.25))
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    plt.tight_layout()
    buf = io.BytesIO()
    plt.savefig(buf, format="png", dpi=150, bbox_inches="tight")
    buf.seek(0)
    plt.close(fig)
    await context.bot.send_photo(
        chat_id=query.from_user.id,
        photo=buf,
        caption=f"📈 So'nggi 7 kun: <b>{sum(counts)}</b> ta yangi foydalanuvchi",
        parse_mode="HTML",
    )


def _admins_kb() -> InlineKeyboardMarkup:
    buttons = []
    for aid in get_all_admins():
        u    = get_user(aid)
        name = escape(u["first_name"]) if u else str(aid)
        lbl  = f"👑 {name}" if aid == MAIN_ADMIN_ID else f"👤 {name}"
        buttons.append([InlineKeyboardButton(lbl, callback_data=f"adm_info_{aid}")])
    buttons.append([InlineKeyboardButton("➕ Admin qo'shish", callback_data="adm_add")])
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
