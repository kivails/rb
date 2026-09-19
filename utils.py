import random
import aiohttp
from gifs import GIFS


def line(ch="─", n=18):
    return ch * n


async def anime_gif(category="wave"):
    """Случайная гифка из waifu.pics, fallback на локальный словарь."""
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get(f"https://api.waifu.pics/sfw/{category}", timeout=aiohttp.ClientTimeout(total=5)) as r:
                if r.status == 200:
                    data = await r.json()
                    return data.get("url")
    except Exception:
        pass
    return pick_gif(category)


def pick_gif(key):
    g = GIFS.get(key) or GIFS.get("wave")
    return random.choice(g) if isinstance(g, list) else g


def progress_bar(v, mx, length=10):
    if mx <= 0:
        return "▱" * length
    f = min(int((v / mx) * length), length)
    return "▰" * f + "▱" * (length - f)


MOTIVATION = [
    "Ты справишься! 💪",
    "Ты сегодня молодец 🌟",
    "Так держать, сенпай! ✨",
    "Ещё чуть-чуть до мечты 🌸",
    "Робуксы сами себя не заработают 😉",
    "Ганбатте! 🎌",
    "Удачи, котик 🐱",
    "Ты лучший! 💖",
]


def motivate():
    return random.choice(MOTIVATION)


BADGES = {
    5: "🥉 Новичок",
    25: "🥈 Активный",
    100: "🥇 Профи",
    500: "👑 Легенда",
}


def badge_for_refs(refs):
    r = "🌱 Нет"
    for req, name in sorted(BADGES.items()):
        if refs >= req:
            r = name
    return r


def is_bad_nick(nick: str, banned: set) -> bool:
    return nick.lower().strip() in banned
