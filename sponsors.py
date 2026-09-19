from aiogram import Bot
from aiogram.enums import ChatMemberStatus
import db


async def check_sponsor(bot: Bot, user_id: int, chat_id: str) -> bool:
    try:
        m = await bot.get_chat_member(chat_id, user_id)
        return m.status not in (ChatMemberStatus.LEFT, ChatMemberStatus.KICKED)
    except Exception:
        return False


async def list_active():
    return await db.q("SELECT * FROM sponsors WHERE active=1 ORDER BY id", (), "all")


async def already_done(user_id: int, sponsor_id: int) -> bool:
    r = await db.q(
        "SELECT 1 FROM sponsor_done WHERE user_id=? AND sponsor_id=?",
        (user_id, sponsor_id), "one",
    )
    return r is not None


async def mark_done(user_id: int, sponsor_id: int):
    from datetime import datetime
    await db.q(
        "INSERT INTO sponsor_done(user_id, sponsor_id, done_at) VALUES(?,?,?)",
        (user_id, sponsor_id, datetime.now().isoformat()),
    )
