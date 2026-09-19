import os
from dotenv import load_dotenv

load_dotenv()

# === Telegram ===
BOT_TOKEN = os.getenv("BOT_TOKEN", "")
ADMIN_IDS = [int(x.strip()) for x in os.getenv("ADMIN_IDS", "").split(",") if x.strip()]
CHANNEL_ID = os.getenv("CHANNEL_ID", "@your_channel")
CHAT_ID = os.getenv("CHAT_ID", "@your_chat")
CHANNEL_URL = os.getenv("CHANNEL_URL", "https://t.me/your_channel")
CHAT_URL = os.getenv("CHAT_URL", "https://t.me/your_chat")
BIO_LINK = os.getenv("BIO_LINK", "https://t.me/your_bot")

# === Экономика ===
REF_REWARD = 1
REF_LVL2_PERCENT = 0.05
MIN_WITHDRAW = 10
COMMISSION = 0.10

DAILY_MIN = 1
DAILY_MAX = 5
STREAK_BONUS = 20

# === Инфраструктура ===
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
DATABASE_URL = os.getenv("DATABASE_URL") or None

# === Web ===
WEB_HOST = os.getenv("WEB_HOST", "0.0.0.0")
WEB_PORT = int(os.getenv("WEB_PORT", "8080"))
WEB_PASSWORD = os.getenv("WEB_PASSWORD", "change_me")
WEBAPP_URL = os.getenv("WEBAPP_URL", "")

# === Мониторинг ===
SENTRY_DSN = os.getenv("SENTRY_DSN", "")
PING_SECRET = os.getenv("PING_SECRET", "keepalive_secret")

# === Защита ===
BANNED_NICKS = {
    "admin", "administrator", "support", "moderator", "mod", "owner",
    "rubux", "rubuxbot", "official", "help", "helper", "system", "root"
}
MIN_ACCOUNT_AGE_DAYS = 3
REF_COOLDOWN_SEC = 30
RATE_LIMIT_SEC = 1
