from fastapi import FastAPI, Form, Cookie, Header, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
import aiosqlite
import secrets
import hmac
import hashlib
import json
from urllib.parse import parse_qsl

import config

app = FastAPI(title="Rubux Admin")
sessions = {}

BASE = """<!doctype html><html><head><meta charset="utf-8">
<title>🌸 Rubux Admin</title>
<style>
body{background:#0e0e1a;color:#fff;font-family:Inter,sans-serif;margin:0}
.wrap{max-width:1100px;margin:40px auto;padding:20px}
h1{background:linear-gradient(90deg,#ff7ac6,#7a5cff);-webkit-background-clip:text;color:transparent}
.card{background:#1a1a2e;border-radius:16px;padding:20px;margin:12px 0;box-shadow:0 4px 24px #0008}
.grid{display:grid;grid-template-columns:repeat(4,1fr);gap:12px}
.num{font-size:28px;font-weight:700;color:#ff7ac6}
button{background:linear-gradient(90deg,#ff7ac6,#7a5cff);border:0;color:#fff;padding:10px 18px;border-radius:10px;cursor:pointer}
input,textarea{background:#252540;border:1px solid #333;color:#fff;padding:10px;border-radius:10px;width:100%;box-sizing:border-box;margin:4px 0}
table{width:100%;border-collapse:collapse}
th,td{padding:8px;text-align:left;border-bottom:1px solid #252540}
a{color:#ff7ac6}
.badge{padding:4px 10px;border-radius:8px;font-size:12px}
.ok{background:#1a4a2a;color:#7fff9a}
.pend{background:#4a3a1a;color:#ffd97a}
.no{background:#4a1a1a;color:#ff7a7a}
</style></head><body><div class="wrap">{body}</div></body></html>"""


def auth(s: str = Cookie(None)):
    return s in sessions


@app.get("/admin", response_class=HTMLResponse)
async def index(s: str = Cookie(None)):
    if not auth(s):
        return BASE.format(body="""
        <h1>🌸 Rubux Admin</h1>
        <div class="card"><form method="post" action="/login">
          <input name="pw" type="password" placeholder="Пароль">
          <button style="margin-top:10px">Войти</button>
        </form></div>""")

    async with aiosqlite.connect("bot.db") as db:
        db.row_factory = aiosqlite.Row
        users = (await (await db.execute("SELECT COUNT(*) c FROM users")).fetchone())["c"]
        pend = (await (await db.execute("SELECT COUNT(*) c FROM withdrawals WHERE status='pending'")).fetchone())["c"]
        bal = (await (await db.execute("SELECT COALESCE(SUM(balance),0) s FROM users")).fetchone())["s"]
        earn = (await (await db.execute("SELECT COALESCE(SUM(total_earned),0) s FROM users")).fetchone())["s"]
        tops = await (await db.execute(
            "SELECT username,user_id,balance,refs,banned FROM users ORDER BY balance DESC LIMIT 15"
        )).fetchall()
        wds = await (await db.execute(
            "SELECT * FROM withdrawals ORDER BY id DESC LIMIT 20"
        )).fetchall()
        sps = await (await db.execute(
            "SELECT * FROM sponsors ORDER BY id DESC"
        )).fetchall()

    rows = "".join(
        f"<tr><td>@{t['username'] or t['user_id']}</td><td>{t['balance']}</td>"
        f"<td>{t['refs']}</td><td>{'🚫' if t['banned'] else '✅'}</td>"
        f"<td><a href='/ban/{t['user_id']}'>"
        f"{'Разбан' if t['banned'] else 'Бан'}</a></td></tr>"
        for t in tops
    )
    wr = "".join(
        f"<tr><td>#{w['id']}</td><td>{w['user_id']}</td><td>{w['amount']}</td>"
        f"<td>{w['nick']}</td><td><span class='badge "
        f"{'ok' if w['status']=='approved' else 'pend' if w['status']=='pending' else 'no'}'>"
        f"{w['status']}</span></td></tr>"
        for w in wds
    )
    sr = "".join(
        f"<tr><td>#{s['id']}</td><td>{s['title']}</td><td>{s['chat_id']}</td>"
        f"<td>{s['reward']}</td><td>{'✅' if s['active'] else '❌'}</td></tr>"
        for s in sps
    )

    body = f"""
    <h1>🌸 Rubux Admin</h1>
    <div class="grid">
      <div class="card"><div>Юзеров</div><div class="num">{users}</div></div>
      <div class="card"><div>Заявок</div><div class="num">{pend}</div></div>
      <div class="card"><div>RBX на балансах</div><div class="num">{bal}</div></div>
      <div class="card"><div>Всего заработано</div><div class="num">{earn}</div></div>
    </div>
    <div class="card"><h3>🏆 Топ</h3>
      <table><tr><th>Юзер</th><th>Баланс</th><th>Рефов</th><th>Статус</th><th>Действие</th></tr>{rows}</table>
    </div>
    <div class="card"><h3>💸 Заявки</h3>
      <table><tr><th>ID</th><th>UID</th><th>Сумма</th><th>Ник</th><th>Статус</th></tr>{wr}</table>
    </div>
    <div class="card"><h3>🎯 Спонсоры</h3>
      <table><tr><th>ID</th><th>Название</th><th>Chat</th><th>Награда</th><th>Активен</th></tr>{sr}</table>
      <form method="post" action="/sponsor/add" style="margin-top:12px">
        <input name="title" placeholder="Название" required>
        <input name="url" placeholder="URL">
        <input name="chat_id" placeholder="@channel">
        <input name="reward" type="number" placeholder="Награда" required>
        <button>➕ Добавить</button>
      </form>
    </div>
    <div class="card"><a href="/logout">Выйти</a></div>"""
    return BASE.format(body=body)


@app.post("/login")
async def login(pw: str = Form(...)):
    if pw != config.WEB_PASSWORD:
        return RedirectResponse("/admin", 302)
    s = secrets.token_urlsafe(32)
    sessions[s] = True
    r = RedirectResponse("/admin", 302)
    r.set_cookie("session", s, httponly=True)
    return r


@app.get("/logout")
async def logout(s: str = Cookie(None)):
    sessions.pop(s, None)
    r = RedirectResponse("/admin", 302)
    r.delete_cookie("session")
    return r


@app.get("/ban/{uid}")
async def ban(uid: int, s: str = Cookie(None)):
    if not auth(s):
        return RedirectResponse("/admin", 302)
    async with aiosqlite.connect("bot.db") as db:
        cur = await db.execute("SELECT banned FROM users WHERE user_id=?", (uid,))
        r = await cur.fetchone()
        if r:
            await db.execute(
                "UPDATE users SET banned=? WHERE user_id=?",
                (0 if r[0] else 1, uid),
            )
            await db.commit()
    return RedirectResponse("/admin", 302)


@app.post("/sponsor/add")
async def sp_add(
    title: str = Form(...),
    url: str = Form(""),
    chat_id: str = Form(...),
    reward: int = Form(...),
    s: str = Cookie(None),
):
    if not auth(s):
        return RedirectResponse("/admin", 302)
    async with aiosqlite.connect("bot.db") as db:
        await db.execute(
            "INSERT INTO sponsors(title,url,chat_id,reward,active) VALUES(?,?,?,?,1)",
            (title, url, chat_id, reward),
        )
        await db.commit()
    return RedirectResponse("/admin", 302)


# ================= WebApp API =================
def check_webapp_init(init_data: str) -> dict:
    try:
        pairs = dict(parse_qsl(init_data, keep_blank_values=True))
        hash_ = pairs.pop("hash", "")
        data_check = "\n".join(f"{k}={v}" for k, v in sorted(pairs.items()))
        secret = hmac.new(b"WebAppData", config.BOT_TOKEN.encode(), hashlib.sha256).digest()
        calc = hmac.new(secret, data_check.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(calc, hash_):
            return None
        return json.loads(pairs.get("user", "{}"))
    except Exception:
        return None


@app.get("/api/me")
async def api_me(x_init_data: str = Header(None)):
    user = check_webapp_init(x_init_data or "")
    if not user:
        raise HTTPException(401)
    async with aiosqlite.connect("bot.db") as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("SELECT * FROM users WHERE user_id=?", (user["id"],))
        u = await cur.fetchone()
    if not u:
        raise HTTPException(404)
    return {
        "first_name": user.get("first_name"),
        "roblox_nick": u["roblox_nick"],
        "balance": u["balance"],
        "refs": u["refs"],
        "min_withdraw": config.MIN_WITHDRAW,
    }


# Статика WebApp
try:
    app.mount("/app", StaticFiles(directory="webapp", html=True), name="webapp")
except Exception:
    pass
