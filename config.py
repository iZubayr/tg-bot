import os
import sys
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN:     str = os.getenv("BOT_TOKEN",     "").strip()
SUPABASE_URL:  str = os.getenv("SUPABASE_URL",  "").strip()
SUPABASE_KEY:  str = os.getenv("SUPABASE_KEY",  "").strip()
MAIN_ADMIN_ID: int = int(os.getenv("MAIN_ADMIN_ID", "0").strip())

_errors = []
if not BOT_TOKEN:     _errors.append("BOT_TOKEN")
if not SUPABASE_URL:  _errors.append("SUPABASE_URL")
if not SUPABASE_KEY:  _errors.append("SUPABASE_KEY")
if not MAIN_ADMIN_ID: _errors.append("MAIN_ADMIN_ID")

if _errors:
    print(f"[XATO] O'rnatilmagan: {', '.join(_errors)}")
    print("MUHIM: SUPABASE_KEY uchun 'service_role' (eyJ... bilan boshlangan) kalit kerak!")
    print("Supabase > Settings > API > Legacy API Keys > service_role")
    sys.exit(1)

RATE_LIMIT:      int   = 5
RATE_WINDOW:     int   = 3600
BROADCAST_DELAY: float = 0.05
