import os

BOT_TOKEN = os.environ["BOT_TOKEN"]
PORT = int(os.getenv("PORT", "8080"))

WEBAPP_URL = os.getenv("WEBAPP_URL", "").rstrip("/")
if not WEBAPP_URL and os.getenv("RAILWAY_PUBLIC_DOMAIN"):
    WEBAPP_URL = "https://" + os.environ["RAILWAY_PUBLIC_DOMAIN"]

# База: если на Railway подключен Volume в /data, храним там
DB_PATH = os.getenv("DB_PATH", "/data/deal.db" if os.path.isdir("/data") else "deal.db")

CHECK_INTERVAL = int(os.getenv("CHECK_INTERVAL", "300"))  # секунд между проверками
PAGES = int(os.getenv("PAGES", "2"))                       # страниц по 40 объявлений
ENABLED_SITES = [s.strip() for s in os.getenv("ENABLED_SITES", "olx").split(",") if s.strip()]

USD_RATE = float(os.getenv("USD_RATE", "41.5"))
EUR_RATE = float(os.getenv("EUR_RATE", "45"))
