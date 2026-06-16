import logging
from datetime import date, timedelta
from supabase import create_client, Client
from config import SUPABASE_URL, SUPABASE_KEY, MAIN_ADMIN_ID

logger = logging.getLogger(__name__)
_client: Client | None = None


def get_db() -> Client:
    global _client
    if _client is None:
        _client = create_client(SUPABASE_URL, SUPABASE_KEY)
    return _client


# ─── Matnlar ──────────────────────────────────────────────────────────────────
TEXT_LABELS = {
    "welcome":      "🏠 Salom xabari",
    "rate_limit":   "⏰ Limit xabari",
    "blocked":      "🚫 Blok xabari",
    "message_sent": "✅ Yuborildi xabari",
    "rate_reset":   "🔓 Limit tugadi xabari",
    "help":         "❓ Yordam xabari",
}
TEXT_DEFAULTS = {
    "welcome": (
        "Assalamu a'layk 👋\n\n"
        "Agar savolingiz yoki taklifingiz bo'lsa, shu yerga yozib qoldirishingiz mumkin 🙂\n\n"
        "Meni kuzatib borish uchun:\n"
        '👉 <a href="https://t.me/+4-8lpgLcdvU5ZTcy">Dev with Zubayr</a>\n'
        '👉 <a href="https://t.me/+uKrIs6gQR4JjYjFi">She\'rlar bog\'i 🍃</a>'
    ),
    "rate_limit":   "⚠️ Vaqtinchalik cheklov. 1 soatdan so'ng qayta yuboring.",
    "blocked":      "🚫 Siz bloklangansiz. Xabaringiz yetib bormaydi.",
    "message_sent": "✅ Xabaringiz yetkazildi, tez orada javob beriladi 🙂",
    "rate_reset":   "✅ Endi yana yozishingiz mumkin!",
    "help": (
        "❓ <b>Yordam</b>\n\n"
        "Bu bot orqali menga bevosita xabar yuborishingiz mumkin.\n\n"
        "<b>Buyruqlar:</b>\n"
        "/start — Botni qayta ishga tushirish\n"
        "/help — Ushbu yordam xabari (2 ta/kun)\n"
        "/info — Pinlangan e'lon\n\n"
        "Xabaringizni yuboring, imkon qadar tez javob beraman 🙂"
    ),
}


def get_text(key: str) -> str:
    try:
        r = get_db().table("bot_texts").select("value").eq("key", key).execute()
        if r.data:
            return r.data[0]["value"]
    except Exception:
        pass
    return TEXT_DEFAULTS.get(key, "")


def set_text(key: str, value: str) -> None:
    get_db().table("bot_texts").upsert({"key": key, "value": value}).execute()


# ─── Sozlamalar ───────────────────────────────────────────────────────────────
SETTING_DEFAULTS = {
    "reminder_enabled":      "false",
    "reminder_interval":     "2",
    "channel_check_enabled": "false",
    "channel_id":            "",
    "pinned_enabled":        "false",
    "pinned_text":           "",
    "rate_limit_count":      "5",
    "help_limit_count":      "2",
}


def get_setting(key: str) -> str:
    try:
        r = get_db().table("bot_settings").select("value").eq("key", key).execute()
        if r.data:
            return r.data[0]["value"]
        logger.warning(f"get_setting: '{key}' DB da topilmadi, default qaytarilyapti")
    except Exception as e:
        logger.error(f"get_setting('{key}') XATOSI: {e}")
    return SETTING_DEFAULTS.get(key, "")


def set_setting(key: str, value: str) -> None:
    try:
        get_db().table("bot_settings").upsert({"key": key, "value": value}).execute()
        logger.info(f"set_setting: '{key}' = '{value}'")
    except Exception as e:
        logger.error(f"set_setting('{key}') XATOSI: {e}")


# ─── Users ────────────────────────────────────────────────────────────────────
def get_or_create_user(user_id: int, first_name: str, username: str | None = None) -> dict | None:
    db = get_db()
    r = db.table("users").select("*").eq("user_id", user_id).execute()
    if r.data:
        db.table("users").update({"first_name": first_name, "username": username}).eq("user_id", user_id).execute()
        return r.data[0]
    new = db.table("users").insert({
        "user_id": user_id, "first_name": first_name, "username": username,
        "is_blocked": False, "vip": False, "msg_count": 0, "rate_reset_at": None,
        "help_count": 0, "help_date": "",
    }).execute()
    return new.data[0] if new.data else None


def get_user(user_id: int) -> dict | None:
    r = get_db().table("users").select("*").eq("user_id", user_id).execute()
    return r.data[0] if r.data else None


def update_user(user_id: int, **kwargs) -> None:
    get_db().table("users").update(kwargs).eq("user_id", user_id).execute()


def mark_blocked(user_id: int) -> None:
    get_db().table("users").update({"is_blocked": True}).eq("user_id", user_id).execute()


def unblock_user(user_id: int) -> None:
    get_db().table("users").update({"is_blocked": False}).eq("user_id", user_id).execute()


def unblock_all() -> int:
    try:
        r = get_db().table("users").select("user_id", count="exact").eq("is_blocked", True).execute()
        count = r.count or 0
        get_db().table("users").update({"is_blocked": False}).eq("is_blocked", True).execute()
        return count
    except Exception as e:
        logger.error(f"unblock_all: {e}")
        return 0


def set_vip(user_id: int, is_vip: bool) -> None:
    get_db().table("users").update({"vip": is_vip}).eq("user_id", user_id).execute()


def get_vip_users() -> list[dict]:
    try:
        r = get_db().table("users").select("user_id, first_name, username").eq("vip", True).execute()
        return r.data or []
    except Exception:
        return []


def get_blocked_users() -> list[dict]:
    try:
        r = get_db().table("users").select("user_id, first_name, username").eq("is_blocked", True).execute()
        return r.data or []
    except Exception:
        return []


def get_all_active_users() -> list[int]:
    r = get_db().table("users").select("user_id").eq("is_blocked", False).execute()
    return [row["user_id"] for row in r.data]


def get_user_message_count(user_id: int) -> int:
    try:
        r = get_db().table("messages").select("id", count="exact").eq("user_id", user_id).execute()
        return r.count or 0
    except Exception:
        return 0


def search_users(query: str) -> list[dict]:
    try:
        db  = get_db()
        sel = "user_id, first_name, username, is_blocked, vip"
        try:
            uid = int(query.lstrip("@").strip())
            r   = db.table("users").select(sel).eq("user_id", uid).execute()
            if r.data:
                return r.data
        except ValueError:
            pass
        clean = query.lstrip("@").strip()
        seen, results = set(), []
        r_u = db.table("users").select(sel).ilike("username",   f"%{clean}%").limit(10).execute()
        r_n = db.table("users").select(sel).ilike("first_name", f"%{clean}%").limit(10).execute()
        for row in (r_u.data or []) + (r_n.data or []):
            if row["user_id"] not in seen:
                seen.add(row["user_id"])
                results.append(row)
        return results[:10]
    except Exception:
        return []


def resolve_user_id(query: str) -> int | None:
    q = query.strip()
    try:
        return int(q.lstrip("@"))
    except ValueError:
        pass
    clean = q.lstrip("@").lower()
    try:
        r = get_db().table("users").select("user_id, username").ilike("username", f"%{clean}%").limit(5).execute()
        for row in (r.data or []):
            if (row.get("username") or "").lower() == clean:
                return row["user_id"]
        if r.data:
            return r.data[0]["user_id"]
    except Exception:
        pass
    return None


def get_stats() -> dict:
    db    = get_db()
    today = date.today().isoformat()
    try:
        total_r   = db.table("users").select("user_id", count="exact").execute()
        today_r   = db.table("users").select("user_id", count="exact").gte("joined_at", today).execute()
        blocked_r = db.table("users").select("user_id", count="exact").eq("is_blocked", True).execute()
        vip_r     = db.table("users").select("user_id", count="exact").eq("vip", True).execute()
        return {
            "total":   total_r.count   or 0,
            "today":   today_r.count   or 0,
            "blocked": blocked_r.count or 0,
            "vip":     vip_r.count     or 0,
        }
    except Exception as e:
        logger.error(f"get_stats: {e}")
        return {"total": 0, "today": 0, "blocked": 0, "vip": 0}


def get_user_growth(days: int = 7) -> list[dict]:
    try:
        r = get_db().table("users").select("joined_at").execute()
    except Exception:
        return []
    counts: dict[str, int] = {}
    for i in range(days):
        d = (date.today() - timedelta(days=days - 1 - i)).isoformat()
        counts[d] = 0
    for row in r.data:
        raw = row.get("joined_at", "")
        if raw:
            day = raw[:10]
            if day in counts:
                counts[day] += 1
    return [{"date": k, "count": v} for k, v in sorted(counts.items())]


# ─── /help kunlik limit ───────────────────────────────────────────────────────

def check_help_limit(user_id: int) -> bool:
    """True = ruxsat. Admin belgilagan kunlik limitga asoslanadi (Toshkent vaqti).
    Limit 0 bo'lsa — har doim False (butunlay cheklangan)."""
    limit = int(get_setting("help_limit_count") or 2)
    if limit <= 0:
        return False
    import pytz
    tz    = pytz.timezone("Asia/Tashkent")
    today = __import__("datetime").datetime.now(tz).date().isoformat()
    try:
        db_user = get_user(user_id)
        if not db_user:
            return True
        help_date  = db_user.get("help_date", "") or ""
        help_count = db_user.get("help_count", 0) or 0
        if help_date != today:
            return True          # Yangi kun — reset
        return help_count < limit
    except Exception:
        return True


def increment_help_count(user_id: int) -> None:
    """Toshkent vaqtiga ko'ra bugungi /help sonini oshiradi."""
    import pytz
    tz    = pytz.timezone("Asia/Tashkent")
    today = __import__("datetime").datetime.now(tz).date().isoformat()
    try:
        db_user = get_user(user_id)
        if not db_user:
            return
        help_date  = db_user.get("help_date", "") or ""
        help_count = db_user.get("help_count", 0) or 0
        if help_date != today:
            update_user(user_id, help_date=today, help_count=1)
        else:
            update_user(user_id, help_count=help_count + 1)
    except Exception as e:
        logger.error(f"increment_help_count: {e}")


# ─── Xabarlar ─────────────────────────────────────────────────────────────────
def save_message(user_id: int, text: str) -> None:
    get_db().table("messages").insert({"user_id": user_id, "text": text}).execute()


def save_admin_reply(admin_id: int, user_id: int, text: str) -> None:
    try:
        get_db().table("admin_replies").insert({"admin_id": admin_id, "user_id": user_id, "text": text}).execute()
    except Exception as e:
        logger.error(f"save_admin_reply: {e}")


# ─── Message map ──────────────────────────────────────────────────────────────
def save_message_map(admin_msg_id: int, admin_chat_id: int, user_id: int,
                     btn_msg_id: int = None, preview: str = "") -> None:
    get_db().table("message_map").insert({
        "admin_msg_id":    admin_msg_id,
        "admin_chat_id":   admin_chat_id,
        "user_id":         user_id,
        "btn_msg_id":      btn_msg_id or admin_msg_id,
        "message_preview": preview[:80],
        "status":          "pending",
    }).execute()


def get_message_map_row(admin_msg_id: int, admin_chat_id: int) -> dict | None:
    r = (get_db().table("message_map").select("*")
         .eq("admin_msg_id", admin_msg_id).eq("admin_chat_id", admin_chat_id).execute())
    return r.data[0] if r.data else None


def update_message_status(admin_msg_id: int, admin_chat_id: int, status: str) -> None:
    try:
        get_db().table("message_map").update({"status": status}) \
            .eq("admin_msg_id", admin_msg_id).eq("admin_chat_id", admin_chat_id).execute()
    except Exception as e:
        logger.error(f"update_message_status: {e}")


def get_pending_messages(admin_chat_id: int) -> list[dict]:
    try:
        r = (get_db().table("message_map")
             .select("admin_msg_id, user_id, message_preview, created_at")
             .eq("admin_chat_id", admin_chat_id).eq("status", "pending")
             .order("created_at", desc=False).limit(20).execute())
        return r.data or []
    except Exception:
        return []


# ─── Admin reply map (tahrirlash uchun) ──────────────────────────────────────
def save_admin_reply_map(admin_msg_id: int, admin_chat_id: int,
                         user_id: int, bot_msg_id: int) -> None:
    try:
        get_db().table("admin_reply_map").upsert({
            "admin_msg_id":  admin_msg_id,
            "admin_chat_id": admin_chat_id,
            "user_id":       user_id,
            "bot_msg_id":    bot_msg_id,
        }).execute()
    except Exception as e:
        logger.error(f"save_admin_reply_map: {e}")


def get_admin_reply_target(admin_msg_id: int, admin_chat_id: int) -> dict | None:
    try:
        r = (get_db().table("admin_reply_map").select("user_id, bot_msg_id")
             .eq("admin_msg_id", admin_msg_id).eq("admin_chat_id", admin_chat_id).execute())
        return r.data[0] if r.data else None
    except Exception:
        return None


# ─── Adminlar ─────────────────────────────────────────────────────────────────
def is_admin(user_id: int) -> bool:
    if user_id == MAIN_ADMIN_ID:
        return True
    try:
        r = get_db().table("admins").select("user_id").eq("user_id", user_id).execute()
        return bool(r.data)
    except Exception:
        return False


def add_admin(user_id: int) -> None:
    get_db().table("admins").upsert({"user_id": user_id}).execute()


def remove_admin(user_id: int) -> None:
    get_db().table("admins").delete().eq("user_id", user_id).execute()


def get_all_admins() -> list[int]:
    try:
        r   = get_db().table("admins").select("user_id").execute()
        ids = [row["user_id"] for row in r.data]
    except Exception:
        ids = []
    if MAIN_ADMIN_ID not in ids:
        ids.insert(0, MAIN_ADMIN_ID)
    return ids


def get_admin_added_at(user_id: int) -> str | None:
    try:
        r = get_db().table("admins").select("added_at").eq("user_id", user_id).execute()
        if r.data:
            return r.data[0].get("added_at")
    except Exception:
        pass
    return None
