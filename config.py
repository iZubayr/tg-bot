import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN: str = os.getenv("BOT_TOKEN", "")
SUPABASE_URL: str = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY: str = os.getenv("SUPABASE_KEY", "")
MAIN_ADMIN_ID: int = int(os.getenv("MAIN_ADMIN_ID", "0"))

# Rate limiting
RATE_LIMIT: int = 5       # soatda max xabar soni
RATE_WINDOW: int = 3600   # 1 soat (soniyada)

# Broadcast delay (Telegram: max ~20 xabar/soniya xavfsiz)
BROADCAST_DELAY: float = 0.05
