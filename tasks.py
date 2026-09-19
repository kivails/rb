from apscheduler.schedulers.asyncio import AsyncIOScheduler
from aiogram import Bot
from datetime import datetime, timedelta
import asyncio
import db, config
from utils import motivate

scheduler = AsyncIOScheduler()


async def recheck_subs(bot: Bot):
    users = await db.q("SELECT user_id FROM users WHERE banned=0", (), "all")
    for u in users:
        uid = u["user_id"]
        try:
            m1 = await bot.get_chat_member(config.CHANNEL_ID, uid)
            m2 = await bot.get_chat_member(config.CHAT_ID, uid)
            left = (m1.status in ("left", "kicked")) or (m2.status in ("left", "kicked"))
            if left:
                await bot.send_message(uid, "⚠️ Ты отписался от канала/чата. Функции бота ограничены!")
        except Exception:
            pass


async def daily_reminder(bot: Bot):
    users = await db.q("SELECT user_id, last_daily FROM users WHERE banned=0", (), "all")
    now = datetime.now()
    sent = 0
    for u in users:
        last = u["last_daily"]
        if not last or (now - datetime.fromisoformat(last)) > timedelta(hours=24):
            try:
                await bot.send_message(
                    u["user_id"],
                    "🎰 <b>Daily-бонус доступен!</b>\n\n"
                    "Забери свои RBX → нажми /start\n\n"
                    f"<i>{motivate()}</i>",
                )
                sent += 1
                await asyncio.sleep(0.05)
            except Exception:
                pass
    print(f"[daily_reminder] Отправлено: {sent}")


async def daily_broadcast(bot: Bot):
    try:
        with open("broadcast.txt", "r", encoding="utf-8") as f:
            text = f.read().strip()
    except FileNotFoundError:
        text = "🌸 Всем привет! Заходи каждый день за бонусами!"

    users = await db.q("SELECT user_id FROM users WHERE banned=0", (), "all")
    sent = 0
    for u in users:
        try:
            await bot.send_message(u["user_id"], text)
            sent += 1
            await asyncio.sleep(0.05)
        except Exception:
            pass
    print(f"[daily_broadcast] Отправлено: {sent}/{len(users)}")


async def cleanup_old_withdrawals():
    cutoff = (datetime.now() - timedelta(days=30)).isoformat()
    await db.q(
        "UPDATE withdrawals SET status='archived' WHERE status='pending' AND created_at < ?",
        (cutoff,),
    )


async def weekly_stats(bot: Bot):
    users = (await db.q("SELECT COUNT(*) c FROM users", (), "one"))["c"]
    bal = (await db.q("SELECT COALESCE(SUM(balance),0) s FROM users", (), "one"))["s"]
    earn = (await db.q("SELECT COALESCE(SUM(total_earned),0) s FROM users", (), "one"))["s"]
    text = (
        f"📊 <b>Недельный отчёт</b>\n\n"
        f"👥 Юзеров: {users}\n"
        f"💰 На балансах: {bal} RBX\n"
        f"📈 Всего заработано: {earn} RBX"
    )
    for adm in config.ADMIN_IDS:
        try:
            await bot.send_message(adm, text)
        except Exception:
            pass


def start(bot: Bot):
    scheduler.add_job(recheck_subs, "interval", hours=6, args=[bot], id="subs")
    scheduler.add_job(daily_reminder, "cron", hour=12, minute=0, args=[bot], id="daily_remind")
    scheduler.add_job(daily_broadcast, "cron", hour=18, minute=0, args=[bot], id="daily_bc")
    scheduler.add_job(cleanup_old_withdrawals, "cron", hour=4, minute=0, id="clean")
    scheduler.add_job(weekly_stats, "cron", day_of_week="mon", hour=9, minute=0, args=[bot], id="weekly")
    scheduler.start()
    print("✅ Scheduler запущен")
