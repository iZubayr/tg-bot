from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.error import BadRequest
from telegram.ext import ContextTypes

from config import MAIN_ADMIN_ID
from database import (
    get_stats, is_admin, get_all_admins,
    get_admin_added_at, remove_admin, get_user,
)


# ─── Klaviaturalar ────────────────────────────────────────────────────────────

def _main_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📊 Statistika", callback_data="stats")],
        [InlineKeyboardButton("📢 Broadcast",  callback_data="broadcast")],
        [InlineKeyboardButton("👥 Adminlar",   callback_data="admins")],
    ])


def _admins_keyboard() -> InlineKeyboardMarkup:
    """Adminlar ro'yxati — har biri button, pastda qo'shish va orqaga."""
    buttons = []
    for admin_id in get_all_admins():
        user_info = get_user(admin_id)
        name = user_info["first_name"] if user_info else str(admin_id)
        is_main = (admin_id == MAIN_ADMIN_ID)
        label = f"👑 {name}" if is_main else f"👤 {name}"
        buttons.append([InlineKeyboardButton(label, callback_data=f"adm_info_{admin_id}")])
    buttons.append([InlineKeyboardButton("➕ Admin qo'shish", callback_data="adm_add")])
    buttons.append([InlineKeyboardButton("🔙 Orqaga",         callback_data="back")])
    return InlineKeyboardMarkup(buttons)


# ─── /admin buyrug'i ──────────────────────────────────────────────────────────

async def admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_admin(update.effective_user.id):
        return

    context.user_data.pop("waiting_broadcast", None)
    context.user_data.pop("waiting_admin_id", None)

    await update.message.reply_text(
        "🛠 <b>Admin panel</b>\n\nQuyidagi bo'limlardan birini tanlang:",
        reply_markup=_main_menu_keyboard(),
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

    # ── Orqaga (asosiy menu) ─────────────────────────────────────────────────
    if data == "back":
        context.user_data.pop("waiting_broadcast", None)
        context.user_data.pop("waiting_admin_id", None)
        await _safe_edit(query,
            "🛠 <b>Admin panel</b>\n\nQuyidagi bo'limlardan birini tanlang:",
            _main_menu_keyboard(),
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
                # Ma'lumotlar o'zgarmagan — faqat notification
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
            "Barcha foydalanuvchilarga yuboriladigan xabarni yozing.\n"
            "<i>(Botni bloklagan foydalanuvchilar bundan mustasno)</i>",
            keyboard,
        )

    # ── Adminlar ro'yxati ────────────────────────────────────────────────────
    elif data == "admins":
        context.user_data.pop("waiting_admin_id", None)
        await _safe_edit(query,
            "👥 <b>Adminlar ro'yxati</b>\n\nAdmin tanlang yoki yangi qo'shing:",
            _admins_keyboard(),
        )

    # ── Admin qo'shish ───────────────────────────────────────────────────────
    elif data == "adm_add":
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

    # ── Admin ma'lumotlari ───────────────────────────────────────────────────
    elif data.startswith("adm_info_"):
        admin_id = int(data.split("_", 2)[2])
        is_main  = (admin_id == MAIN_ADMIN_ID)

        user_info = get_user(admin_id)
        name = user_info["first_name"] if user_info else "—"

        added_str = "—"
        if not is_main:
            raw = get_admin_added_at(admin_id)
            if raw:
                try:
                    dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
                    added_str = dt.strftime("%d.%m.%Y")
                except Exception:
                    added_str = raw[:10]

        text = (
            f"👤 <b>{name}</b>\n\n"
            f"🆔 <code>{admin_id}</code>\n"
        )
        text += "👑 Asosiy admin\n" if is_main else f"📅 Qo'shilgan: {added_str}\n"

        buttons = []
        if not is_main:
            buttons.append([InlineKeyboardButton("🗑 O'chirish", callback_data=f"adm_del_{admin_id}")])
        buttons.append([InlineKeyboardButton("🔙 Orqaga", callback_data="admins")])

        await _safe_edit(query, text, InlineKeyboardMarkup(buttons))

    # ── Admin o'chirish ──────────────────────────────────────────────────────
    elif data.startswith("adm_del_"):
        admin_id = int(data.split("_", 2)[2])

        if admin_id == MAIN_ADMIN_ID:
            await query.answer("❌ Asosiy adminni o'chirib bo'lmaydi!", show_alert=True)
            return

        remove_admin(admin_id)
        await query.answer(f"✅ Admin o'chirildi!", show_alert=True)

        await _safe_edit(query,
            "👥 <b>Adminlar ro'yxati</b>\n\nAdmin tanlang yoki yangi qo'shing:",
            _admins_keyboard(),
        )


# ─── Yordamchi: xavfsiz edit (Message is not modified ni tutadi) ──────────────

async def _safe_edit(query, text: str, keyboard: InlineKeyboardMarkup) -> None:
    try:
        await query.edit_message_text(text, reply_markup=keyboard, parse_mode="HTML")
    except BadRequest as e:
        if "Message is not modified" not in str(e):
            raise
