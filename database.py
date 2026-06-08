import logging
from datetime import date
from supabase import create_client, Client
from config import SUPABASE_URL, SUPABASE_KEY, MAIN_ADMIN_ID


logger = logging.getLogger(__name__)
_client: Client | None = None


def get_db() -> Client:
    global _client
    if _client is None:
        _client = create_client(SUPABASE_URL, SUPABASE_KEY)
    return _client


# ─── Users ────────────────────────────────────────────────────────────────────

def get_or_create_user(user_id: int, first_name: str, username: str | None = None) -> dict | None:
    db = get_db()
    result = db.table("users").select("*").eq("user_id", user_id).execute()

    if result.data:
        db.table("users").update({
            "first_name": first_name,
            "username":   username,
        }).eq("user_id", user_id).execute()
        return result.data[0]

    new = db.table("users").insert({
        "user_id":       user_id,
        "first_name":    first_name,
        "username":      username,
        "is_blocked":    False,
        "msg_count":     0,
        "rate_reset_at": None,
    }).execute()
    return new.data[0] if new.data else None


def get_user(user_id: int) -> dict | None:
    result = get_db().table("users").select("*").eq("user_id", user_id).execute()
    return result.data[0] if result.data else None


def update_user(user_id: int, **kwargs) -> None:
    get_db().table("users").update(kwargs).eq("user_id", user_id).execute()


def mark_blocked(user_id: int) -> None:
    get_db().table("users").update({"is_blocked": True}).eq("user_id", user_id).execute()


def get_all_active_users() -> list[int]:
    result = get_db().table("users").select("user_id").eq("is_blocked", False).execute()
    return [r["user_id"] for r in result.data]


def get_stats() -> dict:
    db = get_db()
    today = date.today().isoformat()
    try:
        total_r   = db.table("users").select("user_id", count="exact").execute()
        today_r   = db.table("users").select("user_id", count="exact").gte("joined_at", today).execute()
        blocked_r = db.table("users").select("user_id", count="exact").eq("is_blocked", True).execute()
        return {
            "total":   total_r.count   or 0,
            "today":   today_r.count   or 0,
            "blocked": blocked_r.count or 0,
        }
    except Exception as e:
        logger.error(f"get_stats xatosi: {e}")
        return {"total": 0, "today": 0, "blocked": 0}


# ─── Messages (foydalanuvchi xabarlari) ──────────────────────────────────────

def save_message(user_id: int, text: str) -> None:
    get_db().table("messages").insert({
        "user_id": user_id,
        "text":    text,
    }).execute()


# ─── Admin javoblari ──────────────────────────────────────────────────────────

def save_admin_reply(admin_id: int, user_id: int, text: str) -> None:
    try:
        get_db().table("admin_replies").insert({
            "admin_id": admin_id,
            "user_id":  user_id,
            "text":     text,
        }).execute()
    except Exception as e:
        logger.error(f"save_admin_reply xatosi: {e}")


# ─── Message map (reply uchun) ────────────────────────────────────────────────

def save_message_map(admin_msg_id: int, admin_chat_id: int, user_id: int) -> None:
    get_db().table("message_map").insert({
        "admin_msg_id":  admin_msg_id,
        "admin_chat_id": admin_chat_id,
        "user_id":       user_id,
    }).execute()


def get_user_from_map(admin_msg_id: int, admin_chat_id: int) -> int | None:
    result = (
        get_db()
        .table("message_map")
        .select("user_id")
        .eq("admin_msg_id",  admin_msg_id)
        .eq("admin_chat_id", admin_chat_id)
        .execute()
    )
    return result.data[0]["user_id"] if result.data else None


# ─── Admins ───────────────────────────────────────────────────────────────────

def is_admin(user_id: int) -> bool:
    if user_id == MAIN_ADMIN_ID:
        return True
    try:
        result = get_db().table("admins").select("user_id").eq("user_id", user_id).execute()
        return bool(result.data)
    except Exception:
        return False


def add_admin(user_id: int) -> None:
    get_db().table("admins").upsert({"user_id": user_id}).execute()


def remove_admin(user_id: int) -> None:
    get_db().table("admins").delete().eq("user_id", user_id).execute()


def get_all_admins() -> list[int]:
    try:
        result = get_db().table("admins").select("user_id").execute()
        ids = [r["user_id"] for r in result.data]
    except Exception:
        ids = []
    if MAIN_ADMIN_ID not in ids:
        ids.insert(0, MAIN_ADMIN_ID)
    return ids


def get_admin_added_at(user_id: int) -> str | None:
    try:
        result = get_db().table("admins").select("added_at").eq("user_id", user_id).execute()
        if result.data:
            return result.data[0].get("added_at")
    except Exception:
        pass
    return None
