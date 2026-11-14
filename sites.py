"""
Адаптеры сайтов. Чтобы добавить новый сайт:
1. Напиши async-функцию fetch_<site>(session, query, s, page) -> list[dict]
2. Каждый dict: id, title, price (грн), url, photo, city, created, descr
3. Добавь её в ADAPTERS и включи в ENABLED_SITES (переменная Railway)
"""
import re
import aiohttp
import config

TIMEOUT = aiohttp.ClientTimeout(total=25)


def to_uah(price, cur):
    if price is None:
        return None
    cur = (cur or "UAH").upper()
    if cur == "USD":
        return price * config.USD_RATE
    if cur == "EUR":
        return price * config.EUR_RATE
    return float(price)


def clean(text):
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", text or "")).strip()


async def fetch_olx(session, query, s, page):
    params = {"offset": page * 40, "limit": 40, "query": query, "sort_by": "created_at:desc"}
    if s.get("max_price"):
        params["filter_float_price:to"] = s["max_price"]
    if s.get("min_price"):
        params["filter_float_price:from"] = s["min_price"]
    if s.get("condition") in ("new", "used"):
        params["filter_enum_state[0]"] = s["condition"]
    async with session.get("https://www.olx.ua/api/v1/offers/", params=params, timeout=TIMEOUT) as r:
        if r.status != 200:
            raise RuntimeError(f"OLX HTTP {r.status}")
        data = await r.json()
    out = []
    for o in data.get("data", []):
        price = cur = None
        for p in o.get("params", []):
            if p.get("key") == "price":
                v = p.get("value") or {}
                price, cur = v.get("value"), v.get("currency")
        loc = o.get("location") or {}
        city = (loc.get("city") or {}).get("name", "")
        region = (loc.get("region") or {}).get("name", "")
        photos = o.get("photos") or []
        photo = ""
        if photos:
            photo = photos[0].get("link", "").replace("{width}", "480").replace("{height}", "360")
        out.append({
            "id": f"olx:{o['id']}", "title": o.get("title", ""), "price": to_uah(price, cur),
            "url": o.get("url", ""), "photo": photo,
            "city": f"{city}, {region}".strip(", "), "created": o.get("created_time", ""),
            "descr": clean(o.get("description", ""))[:600],
        })
    return out


# --- ШАБЛОН для нового сайта (Aukro, Besplatka и т.д.) ---
# async def fetch_aukro(session, query, s, page):
#     ...
#     return [ {...}, {...} ]

ADAPTERS = {"olx": fetch_olx}
