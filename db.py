import aiosqlite
import logging
from datetime import datetime
import config

_pg = None


def is_pg():
    return _pg is not None


def _ph(sql: str):
    """Конвертит ? → $1 $2 ... для PostgreSQL."""
    out, i = "", 1
    for ch in sql:
        if ch == "?":
            out += f"${i}"
            i += 1
        else:
            out += ch
    return out


async def init():
    global _pg
    if config.DATABASE_URL:
        try:
            import asyncpg
            _pg = await asyncpg.create_pool(config.DATABASE_URL, min_size=1, max_size=5)
            async with _pg.acquire() as c:
                await c.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    user_id BIGINT PRIMARY KEY, username TEXT, roblox_nick TEXT,
                    balance INTEGER DEFAULT 0, refs INTEGER DEFAULT 0, refs_lvl2 INTEGER DEFAULT 0,
                    referrer_id BIGINT, referrer_lvl2 BIGINT,
                    bio_done INTEGER DEFAULT 0, banned INTEGER DEFAULT 0,
                    reg_date TEXT, last_daily TEXT, streak INTEGER DEFAULT 0,
                    partner_percent INTEGER DEFAULT 0, total_earned INTEGER DEFAULT 0
                );
                CREATE TABLE IF NOT EXISTS promos (
                    code TEXT PRIMARY KEY, amount INTEGER, uses_left INTEGER,
                    created_by BIGINT, created_at TEXT, expires_at TEXT
                );
                CREATE TABLE IF NOT EXISTS promo_uses (
                    user_id BIGINT, code TEXT, used_at TEXT, UNIQUE(user_id, code));
                CREATE TABLE IF NOT EXISTS withdrawals (
                    id SERIAL PRIMARY KEY, user_id BIGINT, amount INTEGER, nick TEXT,
                    status TEXT DEFAULT 'pending', created_at TEXT, processed_at TEXT);
                CREATE TABLE IF NOT EXISTS history (
                    id SERIAL PRIMARY KEY, user_id BIGINT, amount INTEGER,
                    kind TEXT, note TEXT, created_at TEXT);
                CREATE TABLE IF NOT EXISTS sponsors (
                    id SERIAL PRIMARY KEY, title TEXT, url TEXT, chat_id TEXT,
                    reward INTEGER, active INTEGER DEFAULT 1);
                CREATE TABLE IF NOT EXISTS sponsor_done (
                    user_id BIGINT, sponsor_id INTEGER, done_at TEXT, UNIQUE(user_id, sponsor_id));
                CREATE TABLE IF NOT EXISTS ref_events (
                    id SERIAL PRIMARY KEY, referrer BIGINT, referred BIGINT,
                    created_at TEXT, ip TEXT);
                """)
            logging.info("✅ PostgreSQL подключен")
            return
        except Exception as e:
            logging.error(f"❌ PostgreSQL init fail: {e}")

    async with aiosqlite.connect("bot.db") as db:
        await db.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY, username TEXT, roblox_nick TEXT,
            balance INTEGER DEFAULT 0, refs INTEGER DEFAULT 0, refs_lvl2 INTEGER DEFAULT 0,
            referrer_id INTEGER, referrer_lvl2 INTEGER,
            bio_done INTEGER DEFAULT 0, banned INTEGER DEFAULT 0,
            reg_date TEXT, last_daily TEXT, streak INTEGER DEFAULT 0,
            partner_percent INTEGER DEFAULT 0, total_earned INTEGER DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS promos (
            code TEXT PRIMARY KEY, amount INTEGER, uses_left INTEGER,
            created_by INTEGER, created_at TEXT, expires_at TEXT
        );
        CREATE TABLE IF NOT EXISTS promo_uses (
            user_id INTEGER, code TEXT, used_at TEXT, UNIQUE(user_id, code));
        CREATE TABLE IF NOT EXISTS withdrawals (
            id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, amount INTEGER,
            nick TEXT, status TEXT DEFAULT 'pending', created_at TEXT, processed_at TEXT);
        CREATE TABLE IF NOT EXISTS history (
            id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, amount INTEGER,
            kind TEXT, note TEXT, created_at TEXT);
        CREATE TABLE IF NOT EXISTS sponsors (
            id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT, url TEXT,
            chat_id TEXT, reward INTEGER, active INTEGER DEFAULT 1);
        CREATE TABLE IF NOT EXISTS sponsor_done (
            user_id INTEGER, sponsor_id INTEGER, done_at TEXT, UNIQUE(user_id, sponsor_id));
        CREATE TABLE IF NOT EXISTS ref_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT, referrer INTEGER, referred INTEGER,
            created_at TEXT, ip TEXT);
        """)
        await db.commit()
    logging.info("✅ SQLite готов")


async def q(sql, params=(), fetch=None):
    if _pg:
        async with _pg.acquire() as c:
            sql_pg = _ph(sql)
            if fetch == "one":
                return await c.fetchrow(sql_pg, *params)
            if fetch == "all":
                return await c.fetch(sql_pg, *params)
            return await c.execute(sql_pg, *params)

    async with aiosqlite.connect("bot.db") as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(sql, params)
        if fetch == "one":
            return await cur.fetchone()
        if fetch == "all":
            return await cur.fetchall()
        await db.commit()
        return cur.lastrowid


async def get_user(uid):
    return await q("SELECT * FROM users WHERE user_id=?", (uid,), "one")


async def create_user(uid, username, referrer_id=None, referrer_lvl2=None):
    now = datetime.now().isoformat()
    if is_pg():
        await q(
            "INSERT INTO users(user_id,username,referrer_id,referrer_lvl2,reg_date) "
            "VALUES(?,?,?,?,?) ON CONFLICT (user_id) DO NOTHING",
            (uid, username, referrer_id, referrer_lvl2, now),
        )
    else:
        await q(
            "INSERT OR IGNORE INTO users(user_id,username,referrer_id,referrer_lvl2,reg_date) "
            "VALUES(?,?,?,?,?)",
            (uid, username, referrer_id, referrer_lvl2, now),
        )


async def add_balance(uid, amount, kind="system", note="", partner_bonus=True):
    await q(
        "UPDATE users SET balance=balance+?, total_earned=total_earned+? WHERE user_id=?",
        (amount, max(amount, 0), uid),
    )
    await q(
        "INSERT INTO history(user_id, amount, kind, note, created_at) VALUES(?,?,?,?,?)",
        (uid, amount, kind, note, datetime.now().isoformat()),
    )

    if partner_bonus and amount > 0:
        u = await get_user(uid)
        if not u:
            return
        if u["referrer_id"]:
            ref = await get_user(u["referrer_id"])
            if ref and ref["partner_percent"] > 0:
                bonus = amount * ref["partner_percent"] // 100
                if bonus > 0:
                    await q("UPDATE users SET balance=balance+? WHERE user_id=?",
                            (bonus, ref["user_id"]))
                    await q(
                        "INSERT INTO history(user_id,amount,kind,note,created_at) VALUES(?,?,?,?,?)",
                        (ref["user_id"], bonus, "partner", f"партнёрка с {uid}",
                         datetime.now().isoformat()),
                    )
        if u["referrer_lvl2"] and config.REF_LVL2_PERCENT > 0:
            bonus2 = int(amount * config.REF_LVL2_PERCENT)
            if bonus2 > 0:
                await q("UPDATE users SET balance=balance+? WHERE user_id=?",
                        (bonus2, u["referrer_lvl2"]))
                await q(
                    "INSERT INTO history(user_id,amount,kind,note,created_at) VALUES(?,?,?,?,?)",
                    (u["referrer_lvl2"], bonus2, "ref_lvl2", f"2-й уровень с {uid}",
                     datetime.now().isoformat()),
                )
