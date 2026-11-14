# Deals bot: дешёвые телефоны и ноутбуки (Mini App)

Все файлы лежат в корне репозитория, без папок.

## Railway
1. New Project → Deploy from GitHub repo.
2. Variables: `BOT_TOKEN` (из @BotFather).
3. Settings → Networking → Generate Domain (WEBAPP_URL подставится сам).
4. Рекомендуется: Volume, mount path `/data`, чтобы база не стиралась при деплое.
5. Напиши боту /start.

Необязательные переменные: CHECK_INTERVAL (300), PAGES (2), ENABLED_SITES (olx), USD_RATE, EUR_RATE.
