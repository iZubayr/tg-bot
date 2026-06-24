# 🤖 Telegram Feedback (Aloqa) Bot

Ushbu bot foydalanuvchilar va ma'murlar (adminlar) o'rtasida ishonchli va xavfsiz muloqotni ta'minlovchi mukammal aloqa botidir. Bot **Python** tilida, **python-telegram-bot** kutubxonasining so'nggi asinxron versiyasi va ma'lumotlar ombori sifatida **Supabase (PostgreSQL)** yordamida yaratilgan.

---

## 🚀 Xususiyatlari

### 👤 Foydalanuvchilar uchun:
* **Har xil turdagi xabarlar:** Bot orqali matn, rasm, video, audio, ovozli xabar (voice), video xabar (round video), stiker, GIF va fayllarni adminlarga yuborish imkoniyati.
* **Xabarlarni tahrirlash:** Foydalanuvchi yuborgan xabarini tahrirlasa, u admin panelda ham tahrirlangan shaklda ko'rinadi.
* **Kanalga a'zolik majburiyati (OP - Required Subscription):** Admin tomonidan yoqilgan bo'lsa, foydalanuvchi ma'lum bir kanalga a'zo bo'lmaguncha botdan foydalana olmaydi.
* **Rate Limit (Cheklovlar):** Botdan haddan tashqari ko'p foydalanishni va spamni oldini olish maqsadida soatlik xabar yuborish limiti (sozlanuvchan). Cheklovga tushgan foydalanuvchiga taqiq qachon tugashini aniq vaqt ko'rsatkichlarida (masalan, "X soat Y daqiqa") ko'rsatib boradi.
* **Rate Reset avtomatik tiklanishi:** Bot restart bo'lganda ham foydalanuvchilarning rate limit cheklovidan chiqish vaqti (APScheduler job) bazadagi ma'lumotlar asosida avtomatik ravishedan qayta tiklanadi.
* **Dinamik /help limiti:** Kunlik `/help` buyrug'idan foydalanish limiti.
* **Pinlangan e'lon:** `/info` buyrug'i orqali adminlar tomonidan barcha foydalanuvchilarga yuborilgan va pin qilingan e'lonni ko'rish.

### 🛠 Adminlar uchun (Interaktiv Admin Panel):
* `/admin` buyrug'i yoki `🛠 Admin panel` tugmasi orqali ochiladigan inline interaktiv boshqaruv paneli.
* **Statistika:** Jami a'zolar, bugun qo'shilganlar, VIP va bloklangan foydalanuvchilar soni.
* **Xabarlar tizimi:**
  * **Javobsiz xabarlar:** Kelgan va javob berilmagan xabarlarni ko'rish va to'g'ridan-to'g'ri panel orqali javob yozish.
  * **Eslatma (Reminder):** Javob berilmagan xabarlar bo'lsa, adminlarga har $N$ soatda eslatib turuvchi avtomatik bildirishnoma tizimi (APScheduler yordamida).
* **Foydalanuvchilar boshqaruvi:**
  * Foydalanuvchilarni ID, ism yoki `@username` orqali qidirish.
  * Foydalanuvchilarni bloklash va blokdan chiqarish (shuningdek, barcha bloklanganlarni bir marta bosish bilan ommaviy ochish).
  * **VIP tizimi:** VIP foydalanuvchilarni qo'shish va o'chirish (VIP foydalanuvchilarga hech qanday rate limit qo'llanilmaydi).
* **Sozlamalar paneli:**
  * **Bot matnlarini tahrirlash:** Botning `welcome`, `rate_limit`, `blocked`, `message_sent` va `help` matnlarini to'g'ridan-to'g'ri admin panel orqali o'zgartirish (HTML teglarni qo'llab-quvvatlaydi).
  * **Majburiy obuna:** Kanal ID (`@username` yoki private `-100...` formatida) kiritish, ulanishni sinab ko'rish (Test) va obunani yoqish/o'chirish.
  * **Rate Limit sozlamalari:** Soatiga ruxsat etiladigan xabarlar sonini dinamik o'zgartirish.
  * **Kunlik /help limiti:** Foydalanuvchilar uchun `/help` limitini o'zgartirish.
  * **Asosiy Admin huquqlari (Owner):** Faqat asosiy bot egasigina boshqa adminlarni qo'shishi yoki o'chirishi mumkin.
* **Broadcast (Ommaviy xabar):** Barcha foydalanuvchilarga matn, rasm, video yoki boshqa mediani bir vaqtda tarqatish.

---

## 🛠 Texnologiyalar va Kutubxonalar

* **Python 3.9+**
* **python-telegram-bot** (v21.10) — Botning asinxron arxitekturasi uchun.
* **Supabase Client** (v2.15.1) — Ma'lumotlarni saqlash va boshqarish uchun.
* **APScheduler** (v3.10.4) — Adminlarga davriy eslatmalar yuborish uchun.
* **aiohttp** — Render/Heroku platformalarida bot "uyquga" ketib qolmasligi va sog'lom ishlashi uchun o'rnatilgan veb-server (Health Check).

---

## ⚙️ Sozlash va O'rnatish

### 1. Ma'lumotlar bazasini sozlash (Supabase)
1. [Supabase](https://supabase.com/) sahifasida yangi loyiha oching.
2. Loyihangizning **SQL Editor** bo'limiga o'ting.
3. Loyihadagi [supabase_schema.sql](file:///D:/User/Developer/claude%20memory/tg%20bot/supabase_schema.sql) faylining tarkibini SQL Editor'ga joylashtiring va **Run** tugmasini bosing.
4. Bu SQL kod barcha kerakli jadvallarni, birlamchi sozlamalarni yaratadi va xavfsizlik qoidalarini (RLS) moslashtiradi.

### 2. Atrof-muhit o'zgaruvchilarini sozlash (`.env`)
Loyiha ildiz katalogida `.env` faylini yarating va quyidagi parametrlarni kiriting:

```env
BOT_TOKEN=1234567890:ABCdefGhIJKlmNoPQRsTUVwxyZ  # BotFather bergan token
SUPABASE_URL=https://your-project-id.supabase.co  # Supabase API URL
SUPABASE_KEY=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...  # MUHIM: Service Role API Key!
MAIN_ADMIN_ID=987654321  # Bot egasining Telegram ID raqami
```

> [!IMPORTANT]
> `SUPABASE_KEY` sifatida **anon public** kalit emas, balki **service_role** kalitidan foydalanish zarur. Chunki adminlik amallarida ma'lumotlarni o'zgartirish huquqi talab etiladi.
> Uni topish: *Supabase > Settings > API > API Keys > service_role (secret)*.

### 3. Kutubxonalarni o'rnatish (Virtual Muhitda)

Tizimda Python o'rnatilganligini tekshiring va quyidagi buyruqlarni bajaring:

```bash
# Virtual muhit yaratish
python -m venv venv

# Virtual muhitni faollashtirish (Windows)
.\venv\Scripts\activate

# Virtual muhitni faollashtirish (Mac/Linux)
source venv/bin/activate

# Kerakli kutubxonalarni yuklash
pip install -r requirements.txt
```

---

## 🚀 Botni Ishga Tushirish

### Mahalliy kompyuterda (Local Run):
```bash
python bot.py
```

### Serverda ishga tushirish (Procfile orqali):
Loyiha ichida `Procfile` mavjud bo'lib, u Heroku yoki Render kabi platformalarga yuklanganda botni qanday ishga tushirishni belgilaydi:
```text
web: python bot.py
```

Deploy qilingandan so'ng, platforma `aiohttp` orqali yaratilgan `http://0.0.0.0:10000/` manzilini kuzatadi va botning doimiy ishlab turishini ta'minlaydi.

---

## 🗄 Ma'lumotlar Bazasi Tuzilishi (Jadvallar)

* **`users`** — Bot a'zolari va ularning holati (VIP, bloklangan, /help va rate-limit hisoblagichlari).
* **`messages`** — Foydalanuvchilar tomonidan yuborilgan xabarlar tarixi.
* **`admin_replies`** — Adminlar tomonidan yo'llangan javoblar tarixi.
* **`admins`** — Qo'shimcha tayinlangan adminlar ro'yxati.
* **`message_map`** — Admin panelga kelgan xabar bilan asl foydalanuvchining bog'liqligi (javob yozish va statusni boshqarish uchun).
* **`admin_reply_map`** — Adminlar javobini tahrirlaganda, foydalanuvchi tomonida ham tahrirlanishini ta'minlovchi xabarlar xaritasi.
* **`bot_texts`** — Botning barcha tizimli matnlari (Welcome, Rate Limit xabari va hk).
* **`bot_settings`** — Tizim sozlamalari (Eslatma holati, kanal ID, rate-limit cheklov miqdori).

---

## 📝 Litsenziya

Ushbu loyiha shaxsiy va tijoriy maqsadlarda foydalanish uchun ochiq (Open Source). 
Istaganingizcha o'zgartirishingiz va o'z ehtiyojlaringizga moslashtirishingiz mumkin.
