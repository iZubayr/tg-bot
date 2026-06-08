-- ⚠️ Supabase SQL Editor ga copy-paste qiling va Run bosing
-- Agar jadvallar oldin yaratilgan bo'lsa, yangi jadvallar qo'shiladi (mavjudlari saqlanadi)

-- 1. Foydalanuvchilar
CREATE TABLE IF NOT EXISTS users (
    user_id       BIGINT PRIMARY KEY,
    first_name    TEXT NOT NULL,
    username      TEXT,
    is_blocked    BOOLEAN DEFAULT FALSE,
    joined_at     TIMESTAMPTZ DEFAULT NOW(),
    msg_count     INTEGER DEFAULT 0,
    rate_reset_at TIMESTAMPTZ
);

-- 2. Foydalanuvchi xabarlari
CREATE TABLE IF NOT EXISTS messages (
    id         SERIAL PRIMARY KEY,
    user_id    BIGINT REFERENCES users(user_id) ON DELETE CASCADE,
    text       TEXT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- 3. Admin javoblari
CREATE TABLE IF NOT EXISTS admin_replies (
    id         SERIAL PRIMARY KEY,
    admin_id   BIGINT NOT NULL,
    user_id    BIGINT NOT NULL,
    text       TEXT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- 4. Adminlar
CREATE TABLE IF NOT EXISTS admins (
    user_id  BIGINT PRIMARY KEY,
    added_at TIMESTAMPTZ DEFAULT NOW()
);

-- 5. Reply xarita
CREATE TABLE IF NOT EXISTS message_map (
    id            SERIAL PRIMARY KEY,
    admin_msg_id  BIGINT NOT NULL,
    admin_chat_id BIGINT NOT NULL,
    user_id       BIGINT NOT NULL,
    created_at    TIMESTAMPTZ DEFAULT NOW()
);

-- 6. Bot matnlari (YANGI)
CREATE TABLE IF NOT EXISTS bot_texts (
    key        TEXT PRIMARY KEY,
    value      TEXT NOT NULL,
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Default matnlarni kiritish (mavjud bo'lsa o'zgartirmaydi)
INSERT INTO bot_texts (key, value) VALUES
    ('welcome',      E'Assalamu a\'layk 👋\n\nAgar savolingiz yoki taklifingiz bo\'lsa, shu yerga yozib qoldirishingiz mumkin 🙂\n\nMeni kuzatib borish uchun kanallarim:\n👉 <a href="https://t.me/+4-8lpgLcdvU5ZTcy">Dev with Zubayr</a>\n👉 <a href="https://t.me/+uKrIs6gQR4JjYjFi">She\'rlar bog\'i 🍃</a>'),
    ('rate_limit',   E'⚠️ Siz vaqtinchalik xabar yuborish chekloviga yetdingiz.\nIltimos, 1 soatdan so\'ng qayta yuboring.'),
    ('blocked',      '🚫 Siz bloklangansiz. Xabaringiz yetib bormaydi.'),
    ('message_sent', '✅ Xabaringiz yetkazildi, tez orada javob beriladi 🙂'),
    ('rate_reset',   '✅ Endi yana yozishingiz mumkin!')
ON CONFLICT (key) DO NOTHING;

-- RLS ni o'chiramiz
ALTER TABLE users         DISABLE ROW LEVEL SECURITY;
ALTER TABLE messages      DISABLE ROW LEVEL SECURITY;
ALTER TABLE admin_replies DISABLE ROW LEVEL SECURITY;
ALTER TABLE admins        DISABLE ROW LEVEL SECURITY;
ALTER TABLE message_map   DISABLE ROW LEVEL SECURITY;
ALTER TABLE bot_texts     DISABLE ROW LEVEL SECURITY;
