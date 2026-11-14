import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.filters import CommandStart
from aiogram.types import (InlineKeyboardButton, InlineKeyboardMarkup, MenuButtonWebApp,
                           Message, WebAppInfo)
from aiohttp import web

import config
import db
import scanner
import server

logging.basicConfig(level=logging.INFO)

HELLO = {
    "uk": "Привіт! Я шукаю найдешевші телефони та ноутбуки на українських майданчиках і надсилаю їх тобі.\n\nВідкрий додаток, щоб налаштувати пошуки.",
    "ru": "Привет! Я ищу самые дешёвые телефоны и ноутбуки на украинских площадках и присылаю их тебе.\n\nОткрой приложение, чтобы настроить поиски.",
}
BTN = {"uk": "Відкрити додаток", "ru": "Открыть приложение"}


async def main():
    await db.init()
    bot = Bot(config.BOT_TOKEN, default=DefaultBotProperties(parse_mode="HTML"))
    dp = Dispatcher()

    @dp.message(CommandStart())
    async def start(m: Message):
        await db.ensure_user(m.from_user.id, m.from_user.language_code)
        lang = "ru" if (m.from_user.language_code or "").startswith("ru") else "uk"
        if not config.WEBAPP_URL:
            await m.answer("WEBAPP_URL не задан на сервере.")
            return
        kb = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text=BTN[lang], web_app=WebAppInfo(url=config.WEBAPP_URL))]])
        await m.answer(HELLO[lang], reply_markup=kb)

    runner = web.AppRunner(server.make_app())
    await runner.setup()
    await web.TCPSite(runner, "0.0.0.0", config.PORT).start()

    if config.WEBAPP_URL:
        try:
            await bot.set_chat_menu_button(menu_button=MenuButtonWebApp(
                text="Deals", web_app=WebAppInfo(url=config.WEBAPP_URL)))
        except Exception:
            logging.exception("menu button")

    asyncio.create_task(scanner.run_forever(bot))
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
