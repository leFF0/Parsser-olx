import asyncio
import html
import logging
import random
import re
import statistics
import time
from datetime import datetime, timedelta, timezone

import aiohttp
from aiogram.exceptions import TelegramForbiddenError
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

import config
import db
import sites

log = logging.getLogger("scanner")

BASE_STOP = ["запчаст", "розбит", "разбит", "не включа", "не вмика", "icloud lock",
             "під ремонт", "под ремонт", "на розбір", "на разбор", "залочен"]
SUS_WORDS = ["предоплат", "передоплат", "тільки на карт", "только на карт",
             "пишіть в телеграм", "пишите в телеграм", "пишіть у viber", "пишите в вайбер",
             "доставка олх без", "ексклюзивна ціна"]
TEXTS = {
    "uk": {"open": "Відкрити", "sus": "⚠️ Підозріло", "city": "📍"},
    "ru": {"open": "Открыть", "sus": "⚠️ Подозрительно", "city": "📍"},
}


def split(s):
    return [w.strip().lower() for w in re.split(r"[,\n;]+", s or "") if w.strip()]


def fmt_price(p):
    return f"{int(p):,}".replace(",", " ") + " ₴"


def suspicion(ad, median):
    text = (ad["title"] + " " + ad["descr"]).lower()
    score = 0
    if any(w in text for w in SUS_WORDS):
        score += 40
    if median and ad["price"] < median * 0.35:
        score += 35
    if len(ad["descr"]) < 20:
        score += 15
    if not ad["photo"]:
        score += 15
    return min(score, 100)


def passes(ad, s, tokens, median):
    t = ad["title"].lower()
    full = t + " " + ad["descr"].lower()
    p = ad["price"]
    if not p or p <= 0:
        return False
    if not all(w in t for w in tokens):
        return False
    if s["min_price"] and p < s["min_price"]:
        return False
    if s["max_price"] and p > s["max_price"]:
        return False
    if any(w in t for w in BASE_STOP):
        return False
    if any(w in full for w in split(s["stop_words"])):
        return False
    must = split(s["must_words"])
    if must and not all(w in full for w in must):
        return False
    if s["city"] and s["city"].lower() not in ad["city"].lower():
        return False
    if s["discount"] and median and p > median * (1 - s["discount"] / 100):
        return False
    return True


async def fetch_cached(session, cache, site, query, s):
    key = (site, query, s["min_price"], s["max_price"], s["condition"])
    if key in cache:
        return cache[key]
    ads = []
    for page in range(config.PAGES):
        try:
            ads += await sites.ADAPTERS[site](session, query, s, page)
        except Exception as e:
            log.warning("fetch %s '%s' p%d failed: %s", site, query, page, e)
            break
        await asyncio.sleep(random.uniform(1, 2.5))
    cache[key] = ads
    return ads


async def cycle(bot, session):
    searches = await db.q("SELECT s.* FROM searches s JOIN users u ON u.id=s.user_id WHERE s.active=1")
    cache = {}
    now = int(time.time())
    for s in searches:
        first = not await db.q("SELECT 1 FROM matches WHERE search_id=? LIMIT 1", (s["id"],))
        found = {}
        for query in split(s["keywords"]):
            tokens = query.split()
            for site in split(s["sites"]):
                if site not in sites.ADAPTERS or site not in config.ENABLED_SITES:
                    continue
                ads = await fetch_cached(session, cache, site, query, s)
                prices = [a["price"] for a in ads if a["price"]]
                median = statistics.median(prices) if len(prices) >= 8 else None
                for ad in ads:
                    if ad["id"] in found or not passes(ad, s, tokens, median):
                        continue
                    ad["sus"] = suspicion(ad, median)
                    if s["hide_sus"] and ad["sus"] >= 50:
                        continue
                    found[ad["id"]] = ad
        ordered = sorted(found.values(), key=lambda a: a["price"])
        for i, ad in enumerate(ordered):
            await db.x(
                "INSERT OR IGNORE INTO ads(id,site,title,price,url,photo,city,created,descr,sus,first_seen) "
                "VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                (ad["id"], ad["id"].split(":")[0], ad["title"], ad["price"], ad["url"], ad["photo"],
                 ad["city"], ad["created"], ad["descr"], ad["sus"], now))
            # при первом запуске поиска уведомляем только о 3 самых дешёвых
            notified = 1 if (first and i >= 3) else 0
            await db.x("INSERT OR IGNORE INTO matches(search_id,ad_id,notified,ts) VALUES(?,?,?,?)",
                       (s["id"], ad["id"], notified, now))
    await flush(bot)


def in_quiet(h, qf, qt):
    if qf == qt:
        return False
    return qf <= h < qt if qf < qt else (h >= qf or h < qt)


async def flush(bot):
    now = int(time.time())
    await db.x("UPDATE matches SET notified=1 WHERE notified=0 AND ts<?", (now - 12 * 3600,))
    for u in await db.q("SELECT * FROM users WHERE notify=1"):
        local = datetime.now(timezone.utc) + timedelta(hours=u["tz"])
        if in_quiet(local.hour, u["quiet_from"], u["quiet_to"]):
            continue
        day = local.strftime("%Y-%m-%d")
        row = await db.q("SELECT n FROM sent WHERE user_id=? AND day=?", (u["id"], day))
        left = u["daily_limit"] - (row[0]["n"] if row else 0)
        if left <= 0:
            continue
        pend = await db.q(
            "SELECT a.*, m.search_id, s.name AS sname FROM matches m "
            "JOIN searches s ON s.id=m.search_id JOIN ads a ON a.id=m.ad_id "
            "WHERE s.user_id=? AND m.notified=0 ORDER BY a.price LIMIT ?", (u["id"], left))
        done = set()
        for ad in pend:
            if ad["id"] not in done:
                done.add(ad["id"])
                try:
                    await send_ad(bot, u, ad)
                except TelegramForbiddenError:
                    await db.x("UPDATE users SET notify=0 WHERE id=?", (u["id"],))
                    break
                except Exception as e:
                    log.warning("send failed: %s", e)
                await db.x("INSERT INTO sent(user_id,day,n) VALUES(?,?,1) "
                           "ON CONFLICT(user_id,day) DO UPDATE SET n=n+1", (u["id"], day))
                await asyncio.sleep(0.6)
            await db.x("UPDATE matches SET notified=1 WHERE ad_id=? AND search_id IN "
                       "(SELECT id FROM searches WHERE user_id=?)", (ad["id"], u["id"]))


async def send_ad(bot, u, ad):
    t = TEXTS.get(u["lang"], TEXTS["uk"])
    lines = [f"<b>{fmt_price(ad['price'])}</b>  {html.escape(ad['title'][:120])}"]
    if ad["city"]:
        lines.append(f"{t['city']} {html.escape(ad['city'])}")
    if ad["sus"] >= 50:
        lines.append(t["sus"])
    lines.append(f"<i>{html.escape(ad['sname'])}</i>")
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=t["open"], url=ad["url"])]])
    text = "\n".join(lines)
    if ad["photo"]:
        try:
            await bot.send_photo(u["id"], ad["photo"], caption=text, reply_markup=kb)
            return
        except TelegramForbiddenError:
            raise
        except Exception:
            pass
    await bot.send_message(u["id"], text, reply_markup=kb)


async def run_forever(bot):
    headers = {"User-Agent": "Mozilla/5.0 (Linux; Android 13) AppleWebKit/537.36 Chrome/124 Mobile Safari/537.36",
               "Accept": "application/json", "Accept-Language": "uk-UA,uk;q=0.9"}
    async with aiohttp.ClientSession(headers=headers) as session:
        while True:
            try:
                await cycle(bot, session)
            except Exception:
                log.exception("cycle failed")
            await asyncio.sleep(config.CHECK_INTERVAL)
