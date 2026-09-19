import asyncio
import random
import logging
from datetime import datetime, timedelta

from aiogram import Bot, Dispatcher, F, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode, ChatMemberStatus
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.redis import RedisStorage
from aiogram.types import (
    Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton,
    ReplyKeyboardMarkup, KeyboardButton, WebAppInfo,
)

import config
import db
import tasks
import ratelimit
import keep_alive
from utils import pick_gif, motivate, progress_bar, badge_for_refs, is_bad_nick, anime_gif
from sponsors import check_sponsor, list_active, already_done, mark_done

# === Sentry ===
if config.SENTRY_DSN:
    import sentry_sdk
    sentry_sdk.init(dsn=config.SENTRY_DSN, traces_sample_rate=0.1)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)

bot = Bot(config.BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
storage = RedisStorage.from_url(config.REDIS_URL)
dp = Dispatcher(storage=storage)
router = Router()
dp.include_router(router)

CAPTCHA_EMOJI = ["🍎", "🍌", "🍇", "🍒", "🥝", "🍑", "🍓", "🍉"]


class FSMS(StatesGroup):
    captcha = State()
    nick = State()
    promo = State()
    w_amount = State()
    w_nick = State()
    w_bio = State()
    adm_promo = State()
    adm_bc = State()
    adm_sponsor = State()


# ================= HELPERS =================
async def check_sub(uid):
    try:
        m1 = await bot.get_chat_member(config.CHANNEL_ID, uid)
        m2 = await bot.get_chat_member(config.CHAT_ID, uid)
        return (
            m1.status not in (ChatMemberStatus.LEFT, ChatMemberStatus.KICKED)
            and m2.status not in (ChatMemberStatus.LEFT, ChatMemberStatus.KICKED)
        )
    except Exception:
        return False


def sub_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📢 Канал", url=config.CHANNEL_URL)],
        [InlineKeyboardButton(text="💬 Чат", url=config.CHAT_URL)],
        [InlineKeyboardButton(text="✨ Я подписался ✨", callback_data="check_sub")],
    ])


def main_menu():
    rows = [
        [KeyboardButton(text="🌸 Профиль"), KeyboardButton(text="🎀 Реф-ссылка")],
        [KeyboardButton(text="🎁 Промокод"), KeyboardButton(text="🎰 Daily")],
        [KeyboardButton(text="💸 Вывод"), KeyboardButton(text="📋 Задания")],
        [KeyboardButton(text="🏆 Топ рефов"), KeyboardButton(text="💰 Топ баланса")],
        [KeyboardButton(text="🧾 История"), KeyboardButton(text="❓ Помощь")],
    ]
    if config.WEBAPP_URL:
        rows.append([KeyboardButton(
            text="💎 Открыть кабинет",
            web_app=WebAppInfo(url=config.WEBAPP_URL),
        )])
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True)


# ================= START =================
@router.message(CommandStart())
async def cmd_start(msg: Message, state: FSMContext):
    if not ratelimit.allow(msg.from_user.id, "start", 2):
        return

    args = msg.text.split()
    ref = None
    if len(args) > 1 and args[1].startswith("ref"):
        try:
            r = int(args[1][3:])
            if r != msg.from_user.id:
                ref = r
        except ValueError:
            pass

    u = await db.get_user(msg.from_user.id)
    if not u:
        ref_lvl2 = None
        if ref:
            ref_u = await db.get_user(ref)
            if ref_u:
                ref_lvl2 = ref_u["referrer_id"]
        await db.create_user(msg.from_user.id, msg.from_user.username, ref, ref_lvl2)

        if ref:
            await db.add_balance(ref, config.REF_REWARD, "ref", f"реферал {msg.from_user.id}")
            await db.q("UPDATE users SET refs=refs+1 WHERE user_id=?", (ref,))
            await db.q(
                "INSERT INTO ref_events(referrer, referred, created_at) VALUES(?,?,?)",
                (ref, msg.from_user.id, datetime.now().isoformat()),
            )
            try:
                g = await anime_gif("happy")
                await bot.send_video(
                    ref, g,
                    caption=f"🎉 <b>Новый реферал!</b>\n\n+{config.REF_REWARD} RBX\n{motivate()}",
                )
            except Exception:
                pass

    u = await db.get_user(msg.from_user.id)
    if u["banned"]:
        await msg.answer("🚫 Ты забанен.")
        return

    target = random.choice(CAPTCHA_EMOJI)
    opts = random.sample([e for e in CAPTCHA_EMOJI if e != target], 3) + [target]
    random.shuffle(opts)
    await state.update_data(cap=target)

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=e, callback_data=f"cap_{e}")] for e in opts
    ])

    g = await anime_gif("wave")
    try:
        await msg.answer_video(
            g,
            caption=(
                f"👋 <b>Привет, {msg.from_user.first_name}!</b>\n\n"
                f"Я помогу тебе заработать <b>Robux</b> 💎\n\n"
                f"🎯 Нажми на <b>{target}</b>"
            ),
            reply_markup=kb,
        )
    except Exception:
        await msg.answer(f"👋 Пройди капчу: нажми <b>{target}</b>", reply_markup=kb)
    await state.set_state(FSMS.captcha)


@router.callback_query(F.data.startswith("cap_"), FSMS.captcha)
async def cap_ans(cb: CallbackQuery, state: FSMContext):
    d = await state.get_data()
    if cb.data[4:] == d["cap"]:
        try:
            await cb.message.delete()
        except Exception:
            pass
        g = await anime_gif("happy")
        try:
            await cb.message.answer_video(g, caption="✅ <b>Капча пройдена!</b>")
        except Exception:
            await cb.message.answer("✅ OK!")
        await state.clear()
        await sub_gate(cb.message)
    else:
        g = await anime_gif("cry")
        try:
            await cb.message.answer_video(g, caption="❌ Неверно!")
        except Exception:
            await cb.answer("❌ Неверно!", show_alert=True)


async def sub_gate(msg):
    await msg.answer(
        f"📌 <b>Подпишись на канал и чат:</b>\n\n"
        f"📢 {config.CHANNEL_URL}\n💬 {config.CHAT_URL}\n\n"
        f"<i>Затем жми кнопку ↓</i>",
        reply_markup=sub_kb(),
        disable_web_page_preview=True,
    )


@router.callback_query(F.data == "check_sub")
async def chk(cb: CallbackQuery, state: FSMContext):
    if await check_sub(cb.from_user.id):
        try:
            await cb.message.delete()
        except Exception:
            pass
        u = await db.get_user(cb.from_user.id)
        if not u["roblox_nick"]:
            await cb.message.answer("📝 Введи <b>Roblox ник</b>:")
            await state.set_state(FSMS.nick)
        else:
            g = await anime_gif("wave")
            try:
                await cb.message.answer_video(
                    g,
                    caption=f"✅ Подписка OK!\n\n{motivate()}",
                    reply_markup=main_menu(),
                )
            except Exception:
                await cb.message.answer("🏠 Меню:", reply_markup=main_menu())
    else:
        await cb.answer("❌ Не подписан!", show_alert=True)


@router.message(FSMS.nick)
async def save_nick(msg: Message, state: FSMContext):
    nick = msg.text.strip()
    if not (3 <= len(nick) <= 30):
        await msg.answer("❌ Ник 3–30 символов.")
        return
    if is_bad_nick(nick, config.BANNED_NICKS):
        await msg.answer("❌ Этот ник запрещён.")
        return
    await db.q("UPDATE users SET roblox_nick=? WHERE user_id=?", (nick, msg.from_user.id))
    await state.clear()
    await msg.answer(f"✅ Ник <b>{nick}</b> сохранён!", reply_markup=main_menu())


# ================= GATE =================
@router.message()
async def gate(msg: Message, state: FSMContext):
    if await state.get_state() is not None:
        return
    if not ratelimit.allow(msg.from_user.id, "cmd", 1):
        return

    u = await db.get_user(msg.from_user.id)
    if not u:
        await cmd_start(msg, state)
        return
    if u["banned"]:
        await msg.answer("🚫 Забанен.")
        return
    if not await check_sub(msg.from_user.id):
        await sub_gate(msg)
        return
    if not u["roblox_nick"]:
        await msg.answer("📝 Введи Roblox ник:")
        await state.set_state(FSMS.nick)
        return
    await menu_handler(msg, state)


# ================= MENU =================
async def menu_handler(msg: Message, state: FSMContext):
    t = msg.text
    uid = msg.from_user.id
    u = await db.get_user(uid)

    if t == "🌸 Профиль":
        bar = progress_bar(u["balance"] % 100, 100)
        cap = (
            f"╭───────────────────╮\n   🌸 <b>Профиль</b> 🌸\n╰───────────────────╯\n\n"
            f"🎮 {u['roblox_nick']}\n"
            f"💰 Баланс: <b>{u['balance']} RBX</b>\n   {bar}\n"
            f"👥 Рефералов: <b>{u['refs']}</b> (2-й ур: {u['refs_lvl2']})\n"
            f"🏅 {badge_for_refs(u['refs'])}\n"
            f"🔥 Серия: <b>{u['streak']}</b>\n"
            f"💎 Партнёрка: <b>{u['partner_percent']}%</b>\n"
            f"📈 Всего заработано: <b>{u['total_earned']} RBX</b>\n\n"
            f"<i>{motivate()}</i>"
        )
        g = await anime_gif("smile")
        try:
            await msg.answer_video(g, caption=cap)
        except Exception:
            await msg.answer(cap)

    elif t == "🎀 Реф-ссылка":
        link = f"https://t.me/{(await bot.get_me()).username}?start=ref{uid}"
        cap = (
            f"🎀 <b>Реф-ссылка</b>\n\n<code>{link}</code>\n\n"
            f"💎 +{config.REF_REWARD} RBX за друга\n"
            f"🎁 +{int(config.REF_LVL2_PERCENT * 100)}% со 2-го уровня\n\n"
            f"<i>Отправляй друзьям! 🚀</i>"
        )
        g = await anime_gif("happy")
        try:
            await msg.answer_video(g, caption=cap)
        except Exception:
            await msg.answer(cap)

    elif t == "🎁 Промокод":
        await msg.answer("🎁 Введи промокод:")
        await state.set_state(FSMS.promo)

    elif t == "🎰 Daily":
        await daily(msg, uid, u)

    elif t == "💸 Вывод":
        if u["balance"] < config.MIN_WITHDRAW:
            g = await anime_gif("cry")
            cap = f"💔 Минимум: <b>{config.MIN_WITHDRAW} RBX</b>\nУ тебя: {u['balance']}"
            try:
                await msg.answer_video(g, caption=cap)
            except Exception:
                await msg.answer(cap)
            return
        cap = (
            f"💸 <b>Вывод Robux</b>\n\n"
            f"💰 Баланс: <b>{u['balance']} RBX</b>\n"
            f"📉 Комиссия: {int(config.COMMISSION * 100)}%\n"
            f"⏳ Срок: 1–7 дней\n\n"
            f"⚠️ <b>Обязательно</b> в био Telegram:\n"
            f"«<i>лучший бот для бесплатных робуксов {config.BIO_LINK}</i>»\n\n"
            f"Введи сумму:"
        )
        g = await anime_gif("wink")
        try:
            await msg.answer_video(g, caption=cap)
        except Exception:
            await msg.answer(cap)
        await state.set_state(FSMS.w_amount)

    elif t == "📋 Задания":
        sps = await list_active()
        if not sps:
            await msg.answer("📋 Пока нет заданий 🌱")
            return
        rows = [
            [InlineKeyboardButton(
                text=f"🎯 {s['title']} (+{s['reward']} RBX)",
                callback_data=f"sp_{s['id']}",
            )]
            for s in sps
        ]
        await msg.answer(
            "📋 <b>Задания</b>\n\nВыполни — получи RBX!",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
        )

    elif t == "🏆 Топ рефов":
        rows = await db.q(
            "SELECT username, user_id, refs FROM users ORDER BY refs DESC LIMIT 10",
            (), "all",
        )
        s = "🏆 <b>Топ рефов</b>\n\n"
        medals = ["🥇", "🥈", "🥉"] + ["🎖"] * 7
        for i, r in enumerate(rows):
            n = f"@{r['username']}" if r["username"] else f"id{r['user_id']}"
            s += f"{medals[i]} {n} — <b>{r['refs']}</b>\n"
        g = await anime_gif("dance")
        try:
            await msg.answer_video(g, caption=s)
        except Exception:
            await msg.answer(s)

    elif t == "💰 Топ баланса":
        rows = await db.q(
            "SELECT username, user_id, balance FROM users ORDER BY balance DESC LIMIT 10",
            (), "all",
        )
        s = "💰 <b>Топ баланса</b>\n\n"
        medals = ["👑", "🥈", "🥉"] + ["💎"] * 7
        for i, r in enumerate(rows):
            n = f"@{r['username']}" if r["username"] else f"id{r['user_id']}"
            s += f"{medals[i]} {n} — <b>{r['balance']} RBX</b>\n"
        g = await anime_gif("dance")
        try:
            await msg.answer_video(g, caption=s)
        except Exception:
            await msg.answer(s)

    elif t == "🧾 История":
        rows = await db.q(
            "SELECT amount, kind, note, created_at FROM history "
            "WHERE user_id=? ORDER BY id DESC LIMIT 15",
            (uid,), "all",
        )
        s = "🧾 <b>История:</b>\n\n"
        for r in rows:
            sign = "➕" if r["amount"] >= 0 else "➖"
            s += f"{sign} <b>{r['amount']}</b> · <i>{r['kind']}</i> · {r['created_at'][:16]}\n"
        await msg.answer(s or "Пусто 🌱")

    elif t == "❓ Помощь":
        await msg.answer(
            "❓ <b>Помощь</b>\n\n"
            "• Приглашай друзей → RBX\n"
            "• Промокоды\n• Daily-бонус\n• Задания\n\n"
            f"💸 Минимум: {config.MIN_WITHDRAW} RBX\n"
            f"⏳ Срок: 1–7 дней\n\n"
            f"⚠️ В био: «<i>лучший бот для бесплатных робуксов {config.BIO_LINK}</i>»"
        )


# ================= DAILY =================
async def daily(msg, uid, u):
    now = datetime.now()
    last = datetime.fromisoformat(u["last_daily"]) if u["last_daily"] else None
    if last and (now - last) < timedelta(hours=24):
        left = timedelta(hours=24) - (now - last)
        h, m = left.seconds // 3600, (left.seconds % 3600) // 60
        g = await anime_gif("cry")
        cap = f"⏳ Daily уже получен!\nПриходи через <b>{h}ч {m}м</b>"
        try:
            await msg.answer_video(g, caption=cap)
        except Exception:
            await msg.answer(cap)
        return

    streak = (u["streak"] or 0) + 1 if last and (now - last) < timedelta(hours=48) else 1
    rw = random.randint(config.DAILY_MIN, config.DAILY_MAX)
    bonus = config.STREAK_BONUS if streak % 7 == 0 else 0
    total = rw + bonus
    await db.add_balance(uid, total, "daily", f"streak {streak}")
    await db.q(
        "UPDATE users SET last_daily=?, streak=? WHERE user_id=?",
        (now.isoformat(), streak, uid),
    )

    g = await anime_gif("happy")
    cap = (
        f"🎰 <b>Daily!</b>\n\n💎 +{rw} RBX\n🔥 Серия: {streak}\n"
        + (f"🎁 Бонус: +{bonus}\n" if bonus else "")
        + f"\n<b>Итого: +{total} RBX</b>\n\n<i>{motivate()}</i>"
    )
    try:
        await msg.answer_video(g, caption=cap)
    except Exception:
        await msg.answer(cap)


# ================= SPONSORS =================
@router.callback_query(F.data.startswith("sp_"))
async def sp_cb(cb: CallbackQuery):
    sid = int(cb.data.split("_")[1])
    uid = cb.from_user.id
    sp = await db.q("SELECT * FROM sponsors WHERE id=? AND active=1", (sid,), "one")
    if not sp:
        await cb.answer("Задание недоступно")
        return
    if await already_done(uid, sid):
        await cb.answer("✅ Уже выполнено!")
        return
    if not await check_sponsor(bot, uid, sp["chat_id"]):
        await cb.answer("❌ Сначала подпишись!", show_alert=True)
        return
    await mark_done(uid, sid)
    await db.add_balance(uid, sp["reward"], "sponsor", sp["title"])
    g = await anime_gif("happy")
    try:
        await bot.send_video(uid, g, caption=f"🎉 +{sp['reward']} RBX за «{sp['title']}»!")
    except Exception:
        await cb.answer(f"+{sp['reward']} RBX!", show_alert=True)


# ================= PROMO =================
@router.message(FSMS.promo)
async def promo_apply(msg: Message, state: FSMContext):
    code = msg.text.strip().upper()
    uid = msg.from_user.id
    p = await db.q("SELECT * FROM promos WHERE code=?", (code,), "one")
    if not p or p["uses_left"] <= 0:
        g = await anime_gif("cry")
        try:
            await msg.answer_video(g, caption="💔 Промокод не найден.", reply_markup=main_menu())
        except Exception:
            await msg.answer("Промокод не найден", reply_markup=main_menu())
        await state.clear()
        return
    if p["expires_at"] and datetime.fromisoformat(p["expires_at"]) < datetime.now():
        await msg.answer("❌ Промокод истёк.", reply_markup=main_menu())
        await state.clear()
        return
    used = await db.q(
        "SELECT 1 FROM promo_uses WHERE user_id=? AND code=?", (uid, code), "one",
    )
    if used:
        await msg.answer("❌ Уже активирован.", reply_markup=main_menu())
        await state.clear()
        return
    await db.q(
        "INSERT INTO promo_uses(user_id, code, used_at) VALUES(?,?,?)",
        (uid, code, datetime.now().isoformat()),
    )
    await db.q("UPDATE promos SET uses_left=uses_left-1 WHERE code=?", (code,))
    await db.add_balance(uid, p["amount"], "promo", code)

    g = await anime_gif("happy")
    try:
        await msg.answer_video(g, caption=f"🎁 +{p['amount']} RBX!", reply_markup=main_menu())
    except Exception:
        await msg.answer(f"+{p['amount']} RBX", reply_markup=main_menu())
    await state.clear()


# ================= WITHDRAW =================
@router.message(FSMS.w_amount)
async def w_amt(msg: Message, state: FSMContext):
    try:
        amt = int(msg.text)
    except ValueError:
        await msg.answer("❌ Число!")
        return
    u = await db.get_user(msg.from_user.id)
    if amt < config.MIN_WITHDRAW:
        await msg.answer(f"Мин. {config.MIN_WITHDRAW}")
        return
    if amt > u["balance"]:
        await msg.answer("Мало средств")
        return
    await state.update_data(w_amount=amt)
    await msg.answer("🎮 Roblox ник:")
    await state.set_state(FSMS.w_nick)


@router.message(FSMS.w_nick)
async def w_nick(msg: Message, state: FSMContext):
    await state.update_data(w_nick=msg.text.strip())
    await msg.answer(
        f"📸 Скриншот био:\n«<i>лучший бот для бесплатных робуксов {config.BIO_LINK}</i>»"
    )
    await state.set_state(FSMS.w_bio)


@router.message(FSMS.w_bio, F.photo)
async def w_bio(msg: Message, state: FSMContext):
    d = await state.get_data()
    uid = msg.from_user.id
    amt = d["w_amount"]
    nick = d["w_nick"]
    wid = await db.q(
        "INSERT INTO withdrawals(user_id, amount, nick, created_at) VALUES(?,?,?,?)",
        (uid, amt, nick, datetime.now().isoformat()),
    )
    await db.q("UPDATE users SET balance=balance-? WHERE user_id=?", (amt, uid))
    await db.q("UPDATE users SET bio_done=1 WHERE user_id=?", (uid,))
    await db.q(
        "INSERT INTO history(user_id, amount, kind, note, created_at) VALUES(?,?,?,?,?)",
        (uid, -amt, "withdraw", f"#{wid}", datetime.now().isoformat()),
    )

    for adm in config.ADMIN_IDS:
        try:
            await bot.send_photo(
                adm, msg.photo[-1].file_id,
                caption=(
                    f"💸 <b>Заявка #{wid}</b>\n"
                    f"👤 @{msg.from_user.username or '—'} (<code>{uid}</code>)\n"
                    f"🎮 {nick}\n💰 {amt} RBX"
                ),
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                    InlineKeyboardButton(text="✅", callback_data=f"wd_ok_{wid}"),
                    InlineKeyboardButton(text="❌", callback_data=f"wd_no_{wid}"),
                ]]),
            )
        except Exception:
            pass

    g = await anime_gif("wave")
    try:
        await msg.answer_video(
            g, caption="✅ Заявка отправлена! 1–7 дней.", reply_markup=main_menu(),
        )
    except Exception:
        await msg.answer("✅ Заявка отправлена!", reply_markup=main_menu())
    await state.clear()


@router.message(FSMS.w_bio)
async def w_bio_bad(msg: Message):
    await msg.answer("❌ Нужно фото.")


@router.callback_query(F.data.startswith("wd_"))
async def wd_act(cb: CallbackQuery):
    if cb.from_user.id not in config.ADMIN_IDS:
        await cb.answer("Нет доступа")
        return
    _, act, wid = cb.data.split("_")
    wid = int(wid)
    w = await db.q("SELECT * FROM withdrawals WHERE id=?", (wid,), "one")
    if not w or w["status"] != "pending":
        await cb.answer("Уже обработано")
        return
    st = "approved" if act == "ok" else "rejected"
    await db.q(
        "UPDATE withdrawals SET status=?, processed_at=? WHERE id=?",
        (st, datetime.now().isoformat(), wid),
    )
    if st == "rejected":
        await db.add_balance(w["user_id"], w["amount"], "refund", f"#{wid}", partner_bonus=False)
    try:
        txt = (
            "✅ Заявка одобрена! 1–7 дней 🌸"
            if st == "approved"
            else "❌ Отклонена. Возврат 💔"
        )
        await bot.send_message(w["user_id"], txt)
    except Exception:
        pass
    try:
        await cb.message.edit_caption(
            caption=(cb.message.caption or "") + f"\n→ {st.upper()}"
        )
    except Exception:
        pass


# ================= ADMIN =================
@router.message(Command("admin"))
async def adm(msg: Message):
    if msg.from_user.id not in config.ADMIN_IDS:
        return
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Промокод", callback_data="ap_add")],
        [InlineKeyboardButton(text="🎯 Спонсор", callback_data="ap_sp")],
        [InlineKeyboardButton(text="📊 Стата", callback_data="ap_stats")],
        [InlineKeyboardButton(text="📢 Рассылка", callback_data="ap_bc")],
        [InlineKeyboardButton(text="💸 Заявки", callback_data="ap_wd")],
    ])
    await msg.answer("🛠 <b>Админка</b>", reply_markup=kb)


@router.callback_query(F.data == "ap_add")
async def ap_add(cb: CallbackQuery, state: FSMContext):
    if cb.from_user.id not in config.ADMIN_IDS:
        return
    await cb.message.answer("Формат: <code>КОД СУММА КОЛ-ВО [ДНЕЙ_ЖИЗНИ]</code>")
    await state.set_state(FSMS.adm_promo)


@router.message(FSMS.adm_promo)
async def ap_save(msg: Message, state: FSMContext):
    if msg.from_user.id not in config.ADMIN_IDS:
        return
    parts = msg.text.split()
    try:
        c, a, u = parts[0], int(parts[1]), int(parts[2])
        exp = (
            (datetime.now() + timedelta(days=int(parts[3]))).isoformat()
            if len(parts) > 3 else None
        )
    except Exception:
        await msg.answer("❌ Формат")
        return
    try:
        await db.q(
            "INSERT INTO promos(code,amount,uses_left,created_by,created_at,expires_at) "
            "VALUES(?,?,?,?,?,?)",
            (c.upper(), a, u, msg.from_user.id, datetime.now().isoformat(), exp),
        )
        await msg.answer(f"✅ {c.upper()} · {a} RBX · {u}")
    except Exception:
        await msg.answer("Уже есть")
    await state.clear()


@router.callback_query(F.data == "ap_sp")
async def ap_sp(cb: CallbackQuery, state: FSMContext):
    if cb.from_user.id not in config.ADMIN_IDS:
        return
    await cb.message.answer(
        "Формат: <code>НАЗВАНИЕ | ССЫЛКА | @chat_id | НАГРАДА</code>"
    )
    await state.set_state(FSMS.adm_sponsor)


@router.message(FSMS.adm_sponsor)
async def ap_sp_save(msg: Message, state: FSMContext):
    if msg.from_user.id not in config.ADMIN_IDS:
        return
    try:
        t, url, ch, rw = [x.strip() for x in msg.text.split("|")]
        await db.q(
            "INSERT INTO sponsors(title,url,chat_id,reward,active) VALUES(?,?,?,?,1)",
            (t, url, ch, int(rw)),
        )
        await msg.answer(f"✅ Спонсор «{t}» добавлен")
    except Exception:
        await msg.answer("❌ Формат: Название | ссылка | @chat | 5")
    await state.clear()


@router.callback_query(F.data == "ap_stats")
async def ap_stats(cb: CallbackQuery):
    if cb.from_user.id not in config.ADMIN_IDS:
        return
    users = (await db.q("SELECT COUNT(*) c FROM users", (), "one"))["c"]
    pend = (await db.q(
        "SELECT COUNT(*) c FROM withdrawals WHERE status='pending'", (), "one",
    ))["c"]
    bal = (await db.q("SELECT COALESCE(SUM(balance),0) s FROM users", (), "one"))["s"]
    await cb.message.answer(f"👥 {users}\n💸 Заявок: {pend}\n💰 Баланс: {bal}")


@router.callback_query(F.data == "ap_bc")
async def ap_bc(cb: CallbackQuery, state: FSMContext):
    if cb.from_user.id not in config.ADMIN_IDS:
        return
    await cb.message.answer("Текст:")
    await state.set_state(FSMS.adm_bc)


@router.message(FSMS.adm_bc)
async def ap_bc_send(msg: Message, state: FSMContext):
    if msg.from_user.id not in config.ADMIN_IDS:
        return
    rows = await db.q("SELECT user_id FROM users WHERE banned=0", (), "all")
    ok = 0
    for r in rows:
        try:
            await bot.send_message(r["user_id"], msg.text)
            ok += 1
        except Exception:
            pass
        await asyncio.sleep(0.05)
    await msg.answer(f"✅ {ok}/{len(rows)}")
    await state.clear()


@router.callback_query(F.data == "ap_wd")
async def ap_wd(cb: CallbackQuery):
    if cb.from_user.id not in config.ADMIN_IDS:
        return
    rows = await db.q(
        "SELECT * FROM withdrawals WHERE status='pending' ORDER BY id DESC LIMIT 10",
        (), "all",
    )
    s = "💸 Заявки:\n\n" + "".join(
        f"#{r['id']} · {r['user_id']} · {r['amount']} · {r['nick']}\n" for r in rows
    )
    await cb.message.answer(s or "Пусто")


# ================= RUN =================
async def main():
    await db.init()
    tasks.start(bot)
    http_task = await keep_alive.start_in_background()
    print("🤖 Бот запущен")
    try:
        await dp.start_polling(bot)
    finally:
        http_task.cancel()
        try:
            await http_task
        except asyncio.CancelledError:
            pass


if __name__ == "__main__":
    asyncio.run(main())
