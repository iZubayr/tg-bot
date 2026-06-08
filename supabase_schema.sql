-- ⚠️ Supabase SQL Editor ga copy-paste qiling va Run bosing
-- Agar jadvallar oldin yaratilgan bo'lsa avval o'chirib, qayta ishga tushiring

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

-- 5. Reply xarita (admin reply uchun)
CREATE TABLE IF NOT EXISTS message_map (
    id            SERIAL PRIMARY KEY,
    admin_msg_id  BIGINT NOT NULL,
    admin_chat_id BIGINT NOT NULL,
    user_id       BIGINT NOT NULL,
    created_at    TIMESTAMPTZ DEFAULT NOW()
);

-- ✅ RLS ni o'chiramiz
ALTER TABLE users         DISABLE ROW LEVEL SECURITY;
ALTER TABLE messages      DISABLE ROW LEVEL SECURITY;
ALTER TABLE admin_replies DISABLE ROW LEVEL SECURITY;
ALTER TABLE admins        DISABLE ROW LEVEL SECURITY;
ALTER TABLE message_map   DISABLE ROW LEVEL SECURITY;
