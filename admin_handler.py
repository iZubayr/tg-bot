from datetime import datetime
from html import escape
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.error import BadRequest
from telegram.ext import ContextTypes

from config import MAIN_ADMIN_ID
from database import (
    get_stats, is_admin, get_all_admins,
    get_admin_added_at, remove_admin, get_user,
    mark_blocked, unblock_user, get_blocked_users,
    get_text, set_text, TEXT_LABELS, get_all_texts,
)


# ─── Klaviaturalar ────────────────────────────────────────────────────────────

def _main_menu_keyboard(caller_id: int) -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton("📊 Statistika", callback_data="stats")],
        [InlineKeyboardButton("📢 Broadcast",  callback_data="broadcast")],
    ]
    # Adminlar bo'limi faqat egaga ko'rinadi
    if caller_id == MAIN_ADMIN_ID:
        buttons.append([InlineKeyboardButton("👥 Adminlar", callback_data="admins")])
    buttons.append([InlineKeyboardButton("📝 Matnlar",    callback_data="texts")])
    buttons.append([InlineKeyboardButton("🚫 Bloklangan", callback_data="blk_list")])
    return InlineKeyboardMarkup(buttons)


def _admins_keyboard() -> InlineKeyboardMarkup:
    buttons = []
    for admin_id in get_all_admins():
        user_info = get_user(admin_id)
        name = escape(user_info["first_name"]) if user_info else str(admin_id)
        is_main = (admin_id == MAIN_ADMIN_ID)
        label = f"👑 {name}" if is_main else f"👤 {name}"
        buttons.append([InlineKeyboardButton(label, callback_data=f"adm_info_{admin_id}")])
    buttons.append([InlineKeyboardButton("➕ Admin qo'shish", callback_data="adm_add")])
    buttons.append([InlineKeyboardButton("🔙 Orqaga",         callback_data="back")])
    return InlineKeyboardMarkup(buttons)


def _texts_keyboard() -> InlineKeyboardMarkup:
    buttons = []
    for key, label in TEXT_LABELS.items():
        buttons.append([InlineKeyboardButton(label, callback_data=f"txt_{key}")])
    buttons.append([InlineKeyboardButton("🔙 Orqaga", callback_data="back")])
    return InlineKeyboardMarkup(buttons)


def _blocked_list_keyboard(users: list[dict]) -> InlineKeyboardMarkup:
    buttons = []
    for u in users[:20]:
        name  = escape(u.get("first_name", "—"))
        uid   = u["user_id"]
        uname = f" @{u['username']}" if u.get("username") else ""
        buttons.append([InlineKeyboardButton(f"👤 {name}{uname}", callback_data=f"blk_info_{uid}")])
    buttons.append([InlineKeyboardButton("🔙 Orqaga", callback_data="back")])
    return InlineKeyboardMarkup(buttons)


# ─── /admin buyrug'i ──────────────────────────────────────────────────────────

async def admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_admin(update.effective_user.id):
        return

    context.user_data.pop("waiting_broadcast",  None)
    context.user_data.pop("waiting_admin_id",   None)
    context.user_data.pop("waiting_text_edit",  None)

    await update.message.reply_text(
        "🛠 <b>Admin panel</b>\n\nQuyidagi bo'limlardan birini tanlang:",
        reply_markup=_main_menu_keyboard(update.effective_user.id),
        parse_mode="HTML",
    )


# ─── Callback handler ─────────────────────────────────────────────────────────

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query

    if not is_admin(query.from_user.id):
        await query.answer("❌ Ruxsat yo'q!", show_alert=True)
        return

    await query.answer()
    data = query.data

    # ── Orqaga ──────────────────────────────────────────────────────────────
    if data == "back":
        context.user_data.pop("waiting_broadcast", None)
        context.user_data.pop("waiting_admin_id",  None)
        context.user_data.pop("waiting_text_edit", None)
        await _safe_edit(query,
            "🛠 <b>Admin panel</b>\n\nQuyidagi bo'limlardan birini tanlang:",
            _main_menu_keyboard(query.from_user.id),
        )

    # ── Statistika ───────────────────────────────────────────────────────────
    elif data == "stats":
        stats = get_stats()
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔄 Yangilash", callback_data="stats")],
            [InlineKeyboardButton("🔙 Orqaga",    callback_data="back")],
        ])
        text = (
            f"📊 <b>Statistika</b>\n\n"
            f"👥 Jami foydalanuvchilar: <b>{stats['total']}</b>\n"
            f"🆕 Bugun yangi:           <b>{stats['today']}</b>\n"
            f"🚫 Botni bloklagan:       <b>{stats['blocked']}</b>"
        )
        try:
            await query.edit_message_text(text, reply_markup=keyboard, parse_mode="HTML")
        except BadRequest as e:
            if "Message is not modified" in str(e):
                await query.answer("✅ Ma'lumotlar allaqachon yangi!", show_alert=False)
            else:
                raise

    # ── Broadcast ────────────────────────────────────────────────────────────
    elif data == "broadcast":
        context.user_data["waiting_broadcast"] = True
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔙 Orqaga", callback_data="back")],
        ])
        await _safe_edit(query,
            "📢 <b>Broadcast</b>\n\n"
            "Barcha foydalanuvchilarga yuboriladigan xabarni yuboring.\n"
            "<i>Matn, rasm, video, stiker, GIF — barchasi qabul qilinadi.</i>",
            keyboard,
        )

    # ── Adminlar ro'yxati (faqat ega) ────────────────────────────────────────
    elif data == "admins":
        if query.from_user.id != MAIN_ADMIN_ID:
            await query.answer("❌ Bu bo'lim faqat bot egasi uchun!", show_alert=True)
            return
        context.user_data.pop("waiting_admin_id", None)
        await _safe_edit(query,
            "👥 <b>Adminlar ro'yxati</b>\n\nAdmin tanlang yoki yangi qo'shing:",
            _admins_keyboard(),
        )

    elif data == "adm_add":
        if query.from_user.id != MAIN_ADMIN_ID:
            await query.answer("❌ Bu bo'lim faqat bot egasi uchun!", show_alert=True)
            return
        context.user_data["waiting_admin_id"] = True
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔙 Orqaga", callback_data="admins")],
        ])
        await _safe_edit(query,
            "👤 <b>Admin qo'shish</b>\n\n"
            "Yangi adminning Telegram ID sini yuboring.\n"
            "<i>ID ni bilish uchun: @userinfobot</i>",
            keyboard,
        )

    elif data.startswith("adm_info_"):
        admin_id = int(data.split("_", 2)[2])
        is_main  = (admin_id == MAIN_ADMIN_ID)

        user_info = get_user(admin_id)
        name = escape(user_info["first_name"]) if user_info else "—"

        added_str = "—"
        if not is_main:
            raw = get_admin_added_at(admin_id)
            if raw:
                try:
                    dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
                    added_str = dt.strftime("%d.%m.%Y")
                except Exception:
                    added_str = raw[:10]

        text = f"👤 <b>{name}</b>\n\n🆔 <code>{admin_id}</code>\n"
        text += "👑 Asosiy admin\n" if is_main else f"📅 Qo'shilgan: {added_str}\n"

        buttons = []
        if not is_main:
            buttons.append([InlineKeyboardButton("🗑 O'chirish", callback_data=f"adm_del_{admin_id}")])
        buttons.append([InlineKeyboardButton("🔙 Orqaga", callback_data="admins")])
        await _safe_edit(query, text, InlineKeyboardMarkup(buttons))

    elif data.startswith("adm_del_"):
        if query.from_user.id != MAIN_ADMIN_ID:
            await query.answer("❌ Bu bo'lim faqat bot egasi uchun!", show_alert=True)
            return
        admin_id = int(data.split("_", 2)[2])
        if admin_id == MAIN_ADMIN_ID:
            await query.answer("❌ Asosiy adminni o'chirib bo'lmaydi!", show_alert=True)
            return
        remove_admin(admin_id)
        await query.answer("✅ Admin o'chirildi!", show_alert=True)
        await _safe_edit(query,
            "👥 <b>Adminlar ro'yxati</b>\n\nAdmin tanlang yoki yangi qo'shing:",
            _admins_keyboard(),
        )

    # ── Matnlar bo'limi ──────────────────────────────────────────────────────
    elif data == "texts":
        context.user_data.pop("waiting_text_edit", None)
        await _safe_edit(query,
            "📝 <b>Bot matnlari</b>\n\nO'zgartirish uchun matn turini tanlang:",
            _texts_keyboard(),
        )

    elif data.startswith("txt_edit_"):
        # txt_edit_ ni txt_ dan OLDIN tekshirish kerak
        key = data.split("_", 2)[2]
        context.user_data["waiting_text_edit"] = key
        label = TEXT_LABELS.get(key, key)
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔙 Bekor qilish", callback_data=f"txt_{key}")],
        ])
        await _safe_edit(query,
            f"📝 <b>{label}</b>\n\n"
            f"Yangi matnni yuboring:\n"
            f"<i>HTML teglari ishlatsa bo'ladi: &lt;b&gt;, &lt;i&gt;, &lt;a href='...'&gt;</i>",
            keyboard,
        )

    elif data.startswith("txt_"):
        key = data.split("_", 1)[1]
        context.user_data.pop("waiting_text_edit", None)
        label   = TEXT_LABELS.get(key, key)
        current = get_text(key)
        display = escape(current[:300] + ("..." if len(current) > 300 else ""))
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("✏️ O'zgartirish", callback_data=f"txt_edit_{key}")],
            [InlineKeyboardButton("🔙 Orqaga",        callback_data="texts")],
        ])
        await _safe_edit(query,
            f"📝 <b>{label}</b>\n\n"
            f"📌 Hozirgi matn:\n<i>{display}</i>",
            keyboard,
        )

    # ── Bloklangan foydalanuvchilar ──────────────────────────────────────────
    elif data == "blk_list":
        users = get_blocked_users()
        if not users:
            text = "🚫 <b>Bloklangan foydalanuvchilar</b>\n\nHech kim bloklangani yo'q."
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 Orqaga", callback_data="back")]
            ])
        else:
            text = f"🚫 <b>Bloklangan foydalanuvchilar</b> ({len(users)} ta)\n\nFoydalanuvchini tanlang:"
            keyboard = _blocked_list_keyboard(users)
        await _safe_edit(query, text, keyboard)

    elif data.startswith("blk_info_"):
        user_id = int(data.split("_", 2)[2])
        u = get_user(user_id)
        if not u:
            await query.answer("Foydalanuvchi topilmadi", show_alert=True)
            return
        name  = escape(u.get("first_name", "—"))
        uname = f"@{escape(u['username'])}" if u.get("username") else "—"
        text = (
            f"👤 <b>{name}</b>\n\n"
            f"🆔 <code>{user_id}</code>\n"
            f"📱 {uname}\n"
            f"🚫 Hozirda bloklangan"
        )
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔓 Blokdan chiqarish", callback_data=f"unblk_{user_id}")],
            [InlineKeyboardButton("🔙 Orqaga",             callback_data="blk_list")],
        ])
        await _safe_edit(query, text, keyboard)

    elif data.startswith("unblk_"):
        user_id = int(data.split("_", 1)[1])
        unblock_user(user_id)
        await query.answer("✅ Blok olib tashlandi!", show_alert=True)
        # Yangilangan ro'yxatni ko'rsat
        users = get_blocked_users()
        if not users:
            text = "🚫 <b>Bloklangan foydalanuvchilar</b>\n\nHech kim bloklangani yo'q."
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 Orqaga", callback_data="back")]
            ])
        else:
            text = f"🚫 <b>Bloklangan foydalanuvchilar</b> ({len(users)} ta)\n\nFoydalanuvchini tanlang:"
            keyboard = _blocked_list_keyboard(users)
        await _safe_edit(query, text, keyboard)

    # ── Foydalanuvchini bloklash (xabar tagidagi tugma) ──────────────────────
    elif data.startswith("block_"):
        user_id = int(data.split("_", 1)[1])
        if is_admin(user_id):
            await query.answer("❌ Adminni bloklash mumkin emas!", show_alert=True)
            return
        mark_blocked(user_id)
        await query.answer("✅ Foydalanuvchi bloklandi!", show_alert=True)
        # Blokla tugmasini olib tashlaymiz
        try:
            await query.edit_message_reply_markup(reply_markup=None)
        except BadRequest:
            pass


# ─── Yordamchi ────────────────────────────────────────────────────────────────

async def _safe_edit(query, text: str, keyboard: InlineKeyboardMarkup) -> None:
    try:
        await query.edit_message_text(text, reply_markup=keyboard, parse_mode="HTML")
    except BadRequest as e:
        if "Message is not modified" not in str(e):
            raise
