"""
Kino bot  |  pip install "aiogram>=3.7" aiosqlite
Ishga tushirish:  python kino_bot.py
"""
import asyncio
import html
import logging
import time
import os
from threading import Thread
from flask import Flask

app = Flask('')

@app.route('/')
def home():
    return "Bot 24/7 ishlayapti!"

def run():
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)

def keep_alive():
    t = Thread(target=run)
    t.start()


import aiosqlite
from aiogram import Bot, Dispatcher, F, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.filters import Command, CommandStart, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (CallbackQuery, KeyboardButton, Message,
                           ReplyKeyboardMarkup)
from aiogram.utils.keyboard import InlineKeyboardBuilder

# ===================== SOZLAMALAR =====================
BOT_TOKEN = "8264257921:AAEc67Pls7PhDzbogCkO4sGtCH3Zni_xkms"
ADMINS = [8895200115]          # admin Telegram ID lari
DB_PATH = "kino.db"
REMIND_EVERY = 3600           # 1 soat (sekund)
# ======================================================

router = Router()
db: aiosqlite.Connection


# ---------------------- DATABASE ----------------------
async def init_db():
    global db
    db = await aiosqlite.connect(DB_PATH)
    db.row_factory = aiosqlite.Row
    await db.executescript("""
    CREATE TABLE IF NOT EXISTS users(
        id INTEGER PRIMARY KEY, name TEXT, username TEXT,
        joined INTEGER, banned INTEGER DEFAULT 0,
        premium_until INTEGER DEFAULT 0,
        sub_ok INTEGER DEFAULT 0, last_remind INTEGER DEFAULT 0);
    CREATE TABLE IF NOT EXISTS movies(
        code INTEGER PRIMARY KEY, file_id TEXT, ftype TEXT,
        caption TEXT, premium INTEGER DEFAULT 0);
    CREATE TABLE IF NOT EXISTS channels(
        chat_id INTEGER PRIMARY KEY, title TEXT, link TEXT);
    CREATE TABLE IF NOT EXISTS payments(
        id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER,
        file_id TEXT, ftype TEXT, status TEXT DEFAULT 'pending');
    CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, value TEXT);
    """)
    await db.commit()


async def q(sql, args=(), one=False, commit=False):
    cur = await db.execute(sql, args)
    if commit:
        await db.commit()
        return cur.lastrowid
    rows = await cur.fetchall()
    return (rows[0] if rows else None) if one else rows


async def get_setting(key, default=""):
    r = await q("SELECT value FROM settings WHERE key=?", (key,), one=True)
    return r["value"] if r else default


async def set_setting(key, value):
    await q("INSERT OR REPLACE INTO settings VALUES(?,?)", (key, value), commit=True)


def is_admin(uid):
    return uid in ADMINS


def is_premium(user):
    return bool(user) and user["premium_until"] > time.time()


async def give_premium(uid, days):
    u = await q("SELECT premium_until FROM users WHERE id=?", (uid,), one=True)
    start = max(time.time(), u["premium_until"]) if u else time.time()
    await q("UPDATE users SET premium_until=? WHERE id=?",
            (int(start + days * 86400), uid), commit=True)


# ---------------------- OBUNA TEKSHIRISH ----------------------
async def unsubscribed(bot: Bot, uid: int):
    result = []
    for ch in await q("SELECT * FROM channels"):
        try:
            m = await bot.get_chat_member(ch["chat_id"], uid)
            if m.status in ("left", "kicked"):
                result.append(ch)
        except Exception as e:
            logging.warning("get_chat_member xato (%s): %s", ch["chat_id"], e)
    return result


def sub_kb(channels):
    kb = InlineKeyboardBuilder()
    for ch in channels:
        kb.button(text=f"📢 {ch['title']}", url=ch["link"])
    kb.button(text="✅ Tekshirish", callback_data="check_sub")
    kb.adjust(1)
    return kb.as_markup()


# ---------------------- KLAVIATURALAR ----------------------
ADMIN_KB = ReplyKeyboardMarkup(resize_keyboard=True, keyboard=[
    [KeyboardButton(text="➕ Kino qo'shish"), KeyboardButton(text="🗑 Kino o'chirish")],
    [KeyboardButton(text="📢 Kanal qo'shish"), KeyboardButton(text="❌ Kanal o'chirish")],
    [KeyboardButton(text="👥 Foydalanuvchilar"), KeyboardButton(text="📊 Statistika")],
    [KeyboardButton(text="💳 Karta sozlash"), KeyboardButton(text="💰 Narx sozlash")],
])


# ---------------------- HOLATLAR ----------------------
class AddMovie(StatesGroup):
    tariff = State(); video = State(); code = State()

class DelMovie(StatesGroup):
    code = State()

class AddChannel(StatesGroup):
    data = State()

class SetCard(StatesGroup):
    text = State()

class SetPrice(StatesGroup):
    text = State()

class Buy(StatesGroup):
    check = State()


# ======================= FOYDALANUVCHI =======================
@router.message(CommandStart())
async def start(m: Message, state: FSMContext, bot: Bot):
    await state.clear()
    u = m.from_user
    await q("""INSERT INTO users(id,name,username,joined) VALUES(?,?,?,?)
               ON CONFLICT(id) DO UPDATE SET name=excluded.name, username=excluded.username""",
            (u.id, u.full_name, u.username, int(time.time())), commit=True)

    if is_admin(u.id):
        return await m.answer("👑 Admin panel", reply_markup=ADMIN_KB)

    row = await q("SELECT banned FROM users WHERE id=?", (u.id,), one=True)
    if row["banned"]:
        return await m.answer("⛔ Siz bloklangansiz.")

    bad = await unsubscribed(bot, u.id)
    if bad:
        await q("UPDATE users SET sub_ok=0 WHERE id=?", (u.id,), commit=True)
        return await m.answer("Botdan foydalanish uchun kanallarga obuna bo'ling 👇",
                              reply_markup=sub_kb(bad))
    await q("UPDATE users SET sub_ok=1 WHERE id=?", (u.id,), commit=True)
    await m.answer("🎬 Xush kelibsiz! Kino kodini yuboring.")


@router.callback_query(F.data == "check_sub")
async def check_sub(c: CallbackQuery, bot: Bot):
    bad = await unsubscribed(bot, c.from_user.id)
    if bad:
        return await c.answer("❗ Hali hamma kanalga obuna bo'lmadingiz", show_alert=True)
    await q("UPDATE users SET sub_ok=1 WHERE id=?", (c.from_user.id,), commit=True)
    await c.message.edit_text("✅ Rahmat! Endi kino kodini yuboring.")


@router.message(StateFilter(None), F.text.regexp(r"^\d+$"))
async def get_movie(m: Message, bot: Bot):
    uid = m.from_user.id
    user = await q("SELECT * FROM users WHERE id=?", (uid,), one=True)
    if not user:
        return await m.answer("Avval /start bosing.")
    if user["banned"]:
        return await m.answer("⛔ Siz bloklangansiz.")

    if not is_admin(uid):
        bad = await unsubscribed(bot, uid)
        if bad:
            return await m.answer("Avval kanallarga obuna bo'ling 👇", reply_markup=sub_kb(bad))

    movie = await q("SELECT * FROM movies WHERE code=?", (int(m.text),), one=True)
    if not movie:
        return await m.answer("❌ Bunday kodli kino topilmadi.")

    if movie["premium"] and not is_admin(uid) and not is_premium(user):
        kb = InlineKeyboardBuilder()
        kb.button(text="💎 Tarifni sotib olish", callback_data="buy")
        return await m.answer(
            "🔒 Bu kino <b>pullik tarif</b> uchun.\nKo'rish uchun tarifni sotib oling.",
            reply_markup=kb.as_markup())

    cap = movie["caption"] or f"🎬 Kod: {movie['code']}"
    if movie["ftype"] == "video":
        await m.answer_video(movie["file_id"], caption=cap)
    else:
        await m.answer_document(movie["file_id"], caption=cap)


# ---------------------- SOTIB OLISH ----------------------
@router.callback_query(F.data == "buy")
async def buy(c: CallbackQuery, state: FSMContext):
    card = await get_setting("card", "Karta hali kiritilmagan")
    price = await get_setting("price", "—")
    days = await get_setting("days", "30")
    await state.set_state(Buy.check)
    await c.message.answer(
        f"💎 <b>Pullik tarif</b>\n💰 Narx: {html.escape(price)} so'm\n⏳ Muddat: {days} kun\n\n"
        f"💳 To'lov kartasi:\n<code>{html.escape(card)}</code>\n\n"
        "To'lovni amalga oshirib, <b>chek rasmini</b> shu yerga yuboring.")
    await c.answer()


@router.message(Buy.check, F.photo | F.document)
async def got_check(m: Message, state: FSMContext, bot: Bot):
    if m.photo:
        fid, ft = m.photo[-1].file_id, "photo"
    else:
        fid, ft = m.document.file_id, "document"
    pid = await q("INSERT INTO payments(user_id,file_id,ftype) VALUES(?,?,?)",
                  (m.from_user.id, fid, ft), commit=True)
    kb = InlineKeyboardBuilder()
    kb.button(text="✅ Tasdiqlash", callback_data=f"pay_ok:{pid}")
    kb.button(text="❌ Rad etish", callback_data=f"pay_no:{pid}")
    cap = (f"💳 Yangi to'lov #{pid}\n👤 {html.escape(m.from_user.full_name)} "
           f"(<code>{m.from_user.id}</code>)")
    for a in ADMINS:
        try:
            if ft == "photo":
                await bot.send_photo(a, fid, caption=cap, reply_markup=kb.as_markup())
            else:
                await bot.send_document(a, fid, caption=cap, reply_markup=kb.as_markup())
        except Exception as e:
            logging.warning("Adminga yuborilmadi %s: %s", a, e)
    await state.clear()
    await m.answer("⏳ Chek adminga yuborildi. Tasdiqlanishini kuting.")


@router.message(Buy.check)
async def check_wrong(m: Message):
    await m.answer("Iltimos, chek rasmini yuboring.")


@router.callback_query(F.data.startswith("pay_"))
async def pay_decision(c: CallbackQuery, bot: Bot):
    if not is_admin(c.from_user.id):
        return await c.answer()
    action, pid = c.data.split(":")
    p = await q("SELECT * FROM payments WHERE id=?", (int(pid),), one=True)
    if not p or p["status"] != "pending":
        return await c.answer("Allaqachon ko'rib chiqilgan", show_alert=True)
    if action == "pay_ok":
        days = int(await get_setting("days", "30"))
        await give_premium(p["user_id"], days)
        await q("UPDATE payments SET status='ok' WHERE id=?", (p["id"],), commit=True)
        await bot.send_message(p["user_id"],
                               f"✅ To'lov tasdiqlandi! Pullik tarif {days} kunga faollashdi 🎉")
        mark = "✅ Tasdiqlandi"
    else:
        await q("UPDATE payments SET status='no' WHERE id=?", (p["id"],), commit=True)
        await bot.send_message(p["user_id"], "❌ To'lovingiz rad etildi. Admin bilan bog'laning.")
        mark = "❌ Rad etildi"
    await c.message.edit_caption(caption=(c.message.caption or "") + f"\n\n{mark}")
    await c.answer(mark)


# ======================= ADMIN: KINO =======================
@router.message(Command("admin"))
async def admin_cmd(m: Message, state: FSMContext):
    if is_admin(m.from_user.id):
        await state.clear()
        await m.answer("👑 Admin panel", reply_markup=ADMIN_KB)


@router.message(F.text == "➕ Kino qo'shish", F.from_user.id.in_(ADMINS))
async def add_movie(m: Message, state: FSMContext):
    await state.clear()
    kb = InlineKeyboardBuilder()
    kb.button(text="🆓 Tekin", callback_data="tar:0")
    kb.button(text="💎 Pullik", callback_data="tar:1")
    await state.set_state(AddMovie.tariff)
    await m.answer("Qaysi tarifga qo'shamiz?", reply_markup=kb.as_markup())


@router.callback_query(AddMovie.tariff, F.data.startswith("tar:"))
async def add_movie_tariff(c: CallbackQuery, state: FSMContext):
    await state.update_data(premium=int(c.data.split(":")[1]))
    await state.set_state(AddMovie.video)
    await c.message.edit_text("🎞 Kinoni (video yoki fayl) yuboring:")


@router.message(AddMovie.video, F.video | F.document)
async def add_movie_file(m: Message, state: FSMContext):
    if m.video:
        await state.update_data(file_id=m.video.file_id, ftype="video")
    else:
        await state.update_data(file_id=m.document.file_id, ftype="document")
    await state.update_data(caption=m.caption or "")
    await state.set_state(AddMovie.code)
    await m.answer("🔢 Kino kodini yozing (faqat raqam):")


@router.message(AddMovie.code, F.text.regexp(r"^\d+$"))
async def add_movie_code(m: Message, state: FSMContext):
    d = await state.get_data()
    code = int(m.text)
    await q("INSERT OR REPLACE INTO movies VALUES(?,?,?,?,?)",
            (code, d["file_id"], d["ftype"], d["caption"], d["premium"]), commit=True)
    await state.clear()
    t = "💎 pullik" if d["premium"] else "🆓 tekin"
    await m.answer(f"✅ Kino qo'shildi.\nKod: <b>{code}</b> | Tarif: {t}", reply_markup=ADMIN_KB)


@router.message(F.text == "🗑 Kino o'chirish", F.from_user.id.in_(ADMINS))
async def del_movie(m: Message, state: FSMContext):
    await state.set_state(DelMovie.code)
    await m.answer("O'chiriladigan kino kodini yuboring:")


@router.message(DelMovie.code, F.text.regexp(r"^\d+$"))
async def del_movie_code(m: Message, state: FSMContext):
    r = await q("SELECT 1 FROM movies WHERE code=?", (int(m.text),), one=True)
    if r:
        await q("DELETE FROM movies WHERE code=?", (int(m.text),), commit=True)
        await m.answer("🗑 Kino o'chirildi.", reply_markup=ADMIN_KB)
    else:
        await m.answer("❌ Bunday kod topilmadi.", reply_markup=ADMIN_KB)
    await state.clear()


# ======================= ADMIN: KANAL =======================
@router.message(F.text == "📢 Kanal qo'shish", F.from_user.id.in_(ADMINS))
async def add_channel(m: Message, state: FSMContext):
    await state.set_state(AddChannel.data)
    await m.answer(
        "Kanalni yuboring (bot kanalda ADMIN bo'lishi shart!):\n\n"
        "Ochiq kanal: <code>@kanal_nomi</code>\n"
        "Yopiq kanal: <code>-1001234567890 https://t.me/+invitelink</code>")


@router.message(AddChannel.data, F.text)
async def add_channel_data(m: Message, state: FSMContext, bot: Bot):
    parts = m.text.split()
    ident = parts[0]
    try:
        chat = await bot.get_chat(int(ident) if ident.lstrip("-").isdigit() else ident)
    except Exception as e:
        return await m.answer(f"❌ Kanal topilmadi: {e}")
    link = parts[1] if len(parts) > 1 else f"https://t.me/{ident.lstrip('@')}"
    await q("INSERT OR REPLACE INTO channels VALUES(?,?,?)",
            (chat.id, chat.title, link), commit=True)
    await state.clear()
    await m.answer(f"✅ Kanal qo'shildi: {html.escape(chat.title)}", reply_markup=ADMIN_KB)


@router.message(F.text == "❌ Kanal o'chirish", F.from_user.id.in_(ADMINS))
async def del_channel(m: Message):
    chs = await q("SELECT * FROM channels")
    if not chs:
        return await m.answer("Kanallar yo'q.")
    kb = InlineKeyboardBuilder()
    for ch in chs:
        kb.button(text=f"🗑 {ch['title']}", callback_data=f"delch:{ch['chat_id']}")
    kb.adjust(1)
    await m.answer("Qaysi kanalni o'chiramiz?", reply_markup=kb.as_markup())


@router.callback_query(F.data.startswith("delch:"), F.from_user.id.in_(ADMINS))
async def del_channel_cb(c: CallbackQuery):
    await q("DELETE FROM channels WHERE chat_id=?", (int(c.data.split(":")[1]),), commit=True)
    await c.message.edit_text("🗑 Kanal o'chirildi.")


# ======================= ADMIN: KARTA / NARX =======================
@router.message(F.text == "💳 Karta sozlash", F.from_user.id.in_(ADMINS))
async def card_set(m: Message, state: FSMContext):
    await state.set_state(SetCard.text)
    await m.answer("Karta raqami va egasini yuboring.\nMasalan: <code>8600 1234 5678 9012 — Ali Valiyev</code>")


@router.message(SetCard.text, F.text)
async def card_save(m: Message, state: FSMContext):
    await set_setting("card", m.text)
    await state.clear()
    await m.answer("✅ Karta saqlandi.", reply_markup=ADMIN_KB)


@router.message(F.text == "💰 Narx sozlash", F.from_user.id.in_(ADMINS))
async def price_set(m: Message, state: FSMContext):
    await state.set_state(SetPrice.text)
    await m.answer("Narx va muddatni yuboring: <code>narx kun</code>\nMasalan: <code>30000 30</code>")


@router.message(SetPrice.text, F.text.regexp(r"^\d+\s+\d+$"))
async def price_save(m: Message, state: FSMContext):
    price, days = m.text.split()
    await set_setting("price", price)
    await set_setting("days", days)
    await state.clear()
    await m.answer(f"✅ Narx: {price} so'm, muddat: {days} kun", reply_markup=ADMIN_KB)


# ======================= ADMIN: STATISTIKA =======================
@router.message(F.text == "📊 Statistika", F.from_user.id.in_(ADMINS))
async def stats(m: Message):
    now = int(time.time())
    total = (await q("SELECT COUNT(*) c FROM users", one=True))["c"]
    prem = (await q("SELECT COUNT(*) c FROM users WHERE premium_until>?", (now,), one=True))["c"]
    ban = (await q("SELECT COUNT(*) c FROM users WHERE banned=1", one=True))["c"]
    mv = (await q("SELECT COUNT(*) c FROM movies", one=True))["c"]
    mvp = (await q("SELECT COUNT(*) c FROM movies WHERE premium=1", one=True))["c"]
    await m.answer(f"📊 <b>Statistika</b>\n👥 Foydalanuvchilar: {total}\n💎 Premium: {prem}\n"
                   f"⛔ Bloklangan: {ban}\n🎬 Kinolar: {mv} (pullik: {mvp})")


# ======================= ADMIN: FOYDALANUVCHILAR =======================
PAGE = 10


async def users_page(page: int):
    rows = await q("SELECT * FROM users ORDER BY joined DESC LIMIT ? OFFSET ?",
                   (PAGE, page * PAGE))
    total = (await q("SELECT COUNT(*) c FROM users", one=True))["c"]
    kb = InlineKeyboardBuilder()
    for r in rows:
        mark = "⛔" if r["banned"] else ("💎" if is_premium(r) else "👤")
        kb.button(text=f"{mark} {r['name'][:25]} ({r['id']})", callback_data=f"u:{r['id']}")
    kb.adjust(1)
    nav = InlineKeyboardBuilder()
    if page > 0:
        nav.button(text="⬅️", callback_data=f"up:{page-1}")
    if (page + 1) * PAGE < total:
        nav.button(text="➡️", callback_data=f"up:{page+1}")
    kb.attach(nav)
    return f"👥 Foydalanuvchilar ({total}) — {page+1}-sahifa", kb.as_markup()


@router.message(F.text == "👥 Foydalanuvchilar", F.from_user.id.in_(ADMINS))
async def users_list(m: Message):
    text, kb = await users_page(0)
    await m.answer(text + "\n\nID bo'yicha qidirish: <code>/user 123456</code>", reply_markup=kb)


@router.callback_query(F.data.startswith("up:"), F.from_user.id.in_(ADMINS))
async def users_nav(c: CallbackQuery):
    text, kb = await users_page(int(c.data.split(":")[1]))
    await c.message.edit_text(text, reply_markup=kb)


async def user_card(uid: int):
    u = await q("SELECT * FROM users WHERE id=?", (uid,), one=True)
    if not u:
        return None, None
    if is_premium(u):
        left = max(1, int((u["premium_until"] - time.time()) // 86400))
        prem = f"💎 Premium ({left} kun qoldi)"
    else:
        prem = "🆓 Tekin"
    un = f"@{u['username']}" if u["username"] else "—"
    text = (f"👤 <b>{html.escape(u['name'])}</b>\nID: <code>{u['id']}</code>\nUsername: {un}\n"
            f"Tarif: {prem}\nHolat: {'⛔ bloklangan' if u['banned'] else '✅ faol'}")
    kb = InlineKeyboardBuilder()
    kb.button(text="✅ Blokdan chiqarish" if u["banned"] else "⛔ Bloklash", callback_data=f"ub:{uid}")
    kb.button(text="💎 Premium berish", callback_data=f"ug:{uid}")
    kb.button(text="❌ Premium olish", callback_data=f"ur:{uid}")
    kb.button(text="🔙 Ro'yxat", callback_data="up:0")
    kb.adjust(1)
    return text, kb.as_markup()


@router.callback_query(F.data.regexp(r"^u:\d+$"), F.from_user.id.in_(ADMINS))
async def user_open(c: CallbackQuery):
    text, kb = await user_card(int(c.data.split(":")[1]))
    await c.message.edit_text(text, reply_markup=kb)


@router.message(Command("user"), F.from_user.id.in_(ADMINS))
async def user_search(m: Message):
    arg = m.text.split()[-1]
    if not arg.isdigit():
        return await m.answer("Misol: /user 123456")
    text, kb = await user_card(int(arg))
    await m.answer(text or "❌ Topilmadi", reply_markup=kb)


@router.callback_query(F.data.regexp(r"^u[bgr]:\d+$"), F.from_user.id.in_(ADMINS))
async def user_action(c: CallbackQuery, bot: Bot):
    action, uid = c.data.split(":")
    uid = int(uid)
    if action == "ub":
        await q("UPDATE users SET banned=1-banned WHERE id=?", (uid,), commit=True)
    elif action == "ug":
        days = int(await get_setting("days", "30"))
        await give_premium(uid, days)
        try:
            await bot.send_message(uid, f"🎁 Sizga {days} kunlik pullik tarif berildi!")
        except Exception:
            pass
    elif action == "ur":
        await q("UPDATE users SET premium_until=0 WHERE id=?", (uid,), commit=True)
    text, kb = await user_card(uid)
    await c.message.edit_text(text, reply_markup=kb)
    await c.answer("Bajarildi")


# ======================= HAR 1 SOATDA ESLATMA =======================
async def reminder_loop(bot: Bot):
    """Start bosib, kanallarga obuna bo'lmasdan chiqib ketganlarga har soatda eslatadi."""
    while True:
        await asyncio.sleep(REMIND_EVERY)
        try:
            if not await q("SELECT 1 FROM channels LIMIT 1"):
                continue
            now = int(time.time())
            users = await q("SELECT id FROM users WHERE banned=0 AND last_remind<?",
                            (now - REMIND_EVERY + 60,))
            for u in users:
                if is_admin(u["id"]):
                    continue
                try:
                    bad = await unsubscribed(bot, u["id"])
                    await q("UPDATE users SET sub_ok=?, last_remind=? WHERE id=?",
                            (0 if bad else 1, now, u["id"]), commit=True)
                    if bad:
                        await bot.send_message(
                            u["id"], "👋 Botdan foydalanish uchun kanallarga obuna bo'ling 👇",
                            reply_markup=sub_kb(bad))
                except Exception as e:  # foydalanuvchi botni bloklagan va h.k.
                    logging.info("Eslatma yuborilmadi %s: %s", u["id"], e)
                await asyncio.sleep(0.05)  # Telegram limitidan oshmaslik uchun
        except Exception:
            logging.exception("reminder_loop xato")


# ======================= MAIN =======================
async def main():
    logging.basicConfig(level=logging.INFO)
    await init_db() 
if __name__ == "__main__":
    keep_alive()
    asyncio.run(main())
