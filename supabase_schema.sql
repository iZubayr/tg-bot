-- Supabase SQL Editor ga copy-paste qiling va Run bosing
-- Mavjud jadvallar o'zgarmaydi, faqat yangilar qo'shiladi

-- ─── 1. Users ──────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS users (
    user_id       BIGINT PRIMARY KEY,
    first_name    TEXT NOT NULL,
    username      TEXT,
    is_blocked    BOOLEAN DEFAULT FALSE,
    vip           BOOLEAN DEFAULT FALSE,
    joined_at     TIMESTAMPTZ DEFAULT NOW(),
    msg_count     INTEGER DEFAULT 0,
    rate_reset_at TIMESTAMPTZ,
    help_count    INTEGER DEFAULT 0,
    help_date     TEXT DEFAULT ''
);

-- Mavjud jadvalga yangi ustunlar qo'shish (agar yo'q bo'lsa)
ALTER TABLE users ADD COLUMN IF NOT EXISTS vip        BOOLEAN DEFAULT FALSE;
ALTER TABLE users ADD COLUMN IF NOT EXISTS help_count INTEGER DEFAULT 0;
ALTER TABLE users ADD COLUMN IF NOT EXISTS help_date  TEXT DEFAULT '';

-- ─── 2. Messages ───────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS messages (
    id         SERIAL PRIMARY KEY,
    user_id    BIGINT REFERENCES users(user_id) ON DELETE CASCADE,
    text       TEXT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- ─── 3. Admin replies ──────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS admin_replies (
    id         SERIAL PRIMARY KEY,
    admin_id   BIGINT NOT NULL,
    user_id    BIGINT NOT NULL,
    text       TEXT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- ─── 4. Adminlar ───────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS admins (
    user_id  BIGINT PRIMARY KEY,
    added_at TIMESTAMPTZ DEFAULT NOW()
);

-- ─── 5. Message map ────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS message_map (
    id              SERIAL PRIMARY KEY,
    admin_msg_id    BIGINT NOT NULL,
    admin_chat_id   BIGINT NOT NULL,
    user_id         BIGINT NOT NULL,
    btn_msg_id      BIGINT,
    status          TEXT DEFAULT 'pending',
    message_preview TEXT DEFAULT '',
    created_at      TIMESTAMPTZ DEFAULT NOW()
);
ALTER TABLE message_map ADD COLUMN IF NOT EXISTS btn_msg_id      BIGINT;
ALTER TABLE message_map ADD COLUMN IF NOT EXISTS status          TEXT DEFAULT 'pending';
ALTER TABLE message_map ADD COLUMN IF NOT EXISTS message_preview TEXT DEFAULT '';

-- ─── 6. Admin reply map (xabar tahrirlash uchun) ───────────────────────────
CREATE TABLE IF NOT EXISTS admin_reply_map (
    id            SERIAL PRIMARY KEY,
    admin_msg_id  BIGINT NOT NULL,
    admin_chat_id BIGINT NOT NULL,
    user_id       BIGINT NOT NULL,
    bot_msg_id    BIGINT NOT NULL,
    created_at    TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(admin_msg_id, admin_chat_id)
);

-- ─── 7. Bot matnlari ───────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS bot_texts (
    key        TEXT PRIMARY KEY,
    value      TEXT NOT NULL,
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

INSERT INTO bot_texts (key, value) VALUES
    ('welcome',
     E'Assalamu a\'layk 👋\n\nSavolingiz bo\'lsa yozib qoldiring 🙂'),
    ('rate_limit',
     E'⚠️ Vaqtinchalik cheklov. 1 soatdan so\'ng qayta yuboring.'),
    ('blocked',
     '🚫 Siz bloklangansiz. Xabaringiz yetib bormaydi.'),
    ('message_sent',
     '✅ Xabaringiz yetkazildi, tez orada javob beriladi 🙂'),
    ('rate_reset',
     '✅ Endi yana yozishingiz mumkin!'),
    ('help',
     E'❓ <b>Yordam</b>\n\nBu bot orqali menga bevosita xabar yuborishingiz mumkin.\n\n<b>Buyruqlar:</b>\n/start — Botni qayta ishga tushirish\n/help — Ushbu yordam xabari (2 ta/kun)\n/info — Pinlangan e\'lon\n\nXabaringizni yuboring, imkon qadar tez javob beraman 🙂')
ON CONFLICT (key) DO NOTHING;

-- ─── 8. Bot sozlamalari ────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS bot_settings (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

INSERT INTO bot_settings (key, value) VALUES
    ('reminder_enabled',      'false'),
    ('reminder_interval',     '2'),
    ('channel_check_enabled', 'false'),
    ('channel_id',            ''),
    ('pinned_enabled',        'false'),
    ('pinned_text',           ''),
    ('rate_limit_count',      '5'),
    ('help_limit_count',      '2')
ON CONFLICT (key) DO NOTHING;

-- ─── 9. Jadval broadcast ───────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS scheduled_broadcasts (
    id           SERIAL PRIMARY KEY,
    admin_id     BIGINT NOT NULL,
    from_chat_id BIGINT NOT NULL,
    message_id   BIGINT NOT NULL,
    scheduled_at TIMESTAMPTZ NOT NULL,
    created_at   TIMESTAMPTZ DEFAULT NOW()
);

-- ─── RLS o'chirish ─────────────────────────────────────────────────────────
ALTER TABLE users                DISABLE ROW LEVEL SECURITY;
ALTER TABLE messages             DISABLE ROW LEVEL SECURITY;
ALTER TABLE admin_replies        DISABLE ROW LEVEL SECURITY;
ALTER TABLE admins               DISABLE ROW LEVEL SECURITY;
ALTER TABLE message_map          DISABLE ROW LEVEL SECURITY;
ALTER TABLE admin_reply_map      DISABLE ROW LEVEL SECURITY;
ALTER TABLE bot_texts            DISABLE ROW LEVEL SECURITY;
ALTER TABLE bot_settings         DISABLE ROW LEVEL SECURITY;
ALTER TABLE scheduled_broadcasts DISABLE ROW LEVEL SECURITY;
