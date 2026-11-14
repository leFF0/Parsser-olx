import hashlib
import hmac
import json
import os
import time
from urllib.parse import parse_qsl

from aiohttp import web

import config
import db

HERE = os.path.dirname(os.path.abspath(__file__))


def check_init_data(init_data):
    try:
        pairs = dict(parse_qsl(init_data, keep_blank_values=True))
        got = pairs.pop("hash", None)
        dcs = "\n".join(f"{k}={v}" for k, v in sorted(pairs.items()))
        secret = hmac.new(b"WebAppData", config.BOT_TOKEN.encode(), hashlib.sha256).digest()
        calc = hmac.new(secret, dcs.encode(), hashlib.sha256).hexdigest()
        if not got or not hmac.compare_digest(calc, got):
            return None
        if time.time() - int(pairs.get("auth_date", 0)) > 7 * 86400:
            return None
        return json.loads(pairs["user"])
    except Exception:
        return None


@web.middleware
async def auth(request, handler):
    if request.path.startswith("/api/"):
        user = check_init_data(request.headers.get("X-Init-Data", ""))
        if not user:
            return web.json_response({"error": "auth"}, status=401)
        await db.ensure_user(user["id"], user.get("language_code"))
        request["uid"] = user["id"]
    return await handler(request)


async def index(request):
    return web.FileResponse(os.path.join(HERE, "index.html"))


async def me(request):
    u = (await db.q("SELECT * FROM users WHERE id=?", (request["uid"],)))[0]
    return web.json_response({"user": u, "sites": config.ENABLED_SITES})


async def save_settings(request):
    d = await request.json()
    def n(k, lo, hi, dflt):
        try:
            return max(lo, min(hi, int(d.get(k, dflt))))
        except Exception:
            return dflt
    await db.x("UPDATE users SET lang=?, notify=?, quiet_from=?, quiet_to=?, daily_limit=?, tz=? WHERE id=?",
               ("ru" if d.get("lang") == "ru" else "uk", 1 if d.get("notify") else 0,
                n("quiet_from", 0, 23, 23), n("quiet_to", 0, 23, 7),
                n("daily_limit", 1, 200, 30), n("tz", -12, 14, 2), request["uid"]))
    return web.json_response({"ok": True})


async def list_searches(request):
    rows = await db.q("SELECT * FROM searches WHERE user_id=? ORDER BY id", (request["uid"],))
    for r in rows:
        r["count"] = (await db.q("SELECT COUNT(*) c FROM matches WHERE search_id=?", (r["id"],)))[0]["c"]
    return web.json_response(rows)


async def save_search(request):
    d = await request.json()
    uid = request["uid"]
    def i(k):
        try:
            return max(0, int(d.get(k) or 0))
        except Exception:
            return 0
    vals = (str(d.get("name") or "Пошук")[:60], str(d.get("keywords") or "")[:500],
            str(d.get("stop_words") or "")[:300], str(d.get("must_words") or "")[:300],
            i("min_price"), i("max_price"), min(i("discount"), 90), str(d.get("city") or "")[:60],
            str(d.get("sites") or "olx")[:100],
            d.get("condition") if d.get("condition") in ("any", "new", "used") else "any",
            1 if d.get("active", True) else 0, 1 if d.get("hide_sus") else 0)
    sid = d.get("id")
    if sid:
        await db.x("UPDATE searches SET name=?,keywords=?,stop_words=?,must_words=?,min_price=?,max_price=?,"
                   "discount=?,city=?,sites=?,condition=?,active=?,hide_sus=? WHERE id=? AND user_id=?",
                   vals + (sid, uid))
    else:
        await db.x("INSERT INTO searches(name,keywords,stop_words,must_words,min_price,max_price,discount,"
                   "city,sites,condition,active,hide_sus,user_id) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                   vals + (uid,))
    return web.json_response({"ok": True})


async def delete_search(request):
    sid = int(request.match_info["id"])
    await db.x("DELETE FROM matches WHERE search_id IN (SELECT id FROM searches WHERE id=? AND user_id=?)",
               (sid, request["uid"]))
    await db.x("DELETE FROM searches WHERE id=? AND user_id=?", (sid, request["uid"]))
    return web.json_response({"ok": True})


async def feed(request):
    uid = request["uid"]
    qs = request.query
    tab = qs.get("tab", "all")
    sort = "a.price ASC" if qs.get("sort") == "cheap" else "mts DESC"
    off = max(0, int(qs.get("offset", 0)))
    if tab == "fav":
        rows = await db.q(
            "SELECT a.*, 1 AS fav, f.rowid AS mts FROM favs f JOIN ads a ON a.id=f.ad_id "
            "WHERE f.user_id=? ORDER BY f.rowid DESC LIMIT 20 OFFSET ?", (uid, off))
    else:
        args = [uid, uid]
        extra = ""
        if qs.get("search"):
            extra = " AND s.id=?"
            args.append(int(qs["search"]))
        args.append(off)
        rows = await db.q(
            "SELECT a.*, MAX(m.ts) AS mts, "
            "EXISTS(SELECT 1 FROM favs f WHERE f.user_id=? AND f.ad_id=a.id) AS fav "
            "FROM matches m JOIN ads a ON a.id=m.ad_id JOIN searches s ON s.id=m.search_id "
            f"WHERE s.user_id=?{extra} GROUP BY a.id ORDER BY {sort} LIMIT 20 OFFSET ?", args)
    return web.json_response(rows)


async def toggle_fav(request):
    d = await request.json()
    uid, ad = request["uid"], str(d.get("ad_id"))
    if await db.q("SELECT 1 FROM favs WHERE user_id=? AND ad_id=?", (uid, ad)):
        await db.x("DELETE FROM favs WHERE user_id=? AND ad_id=?", (uid, ad))
        return web.json_response({"fav": False})
    await db.x("INSERT OR IGNORE INTO favs(user_id,ad_id) VALUES(?,?)", (uid, ad))
    return web.json_response({"fav": True})


def make_app():
    app = web.Application(middlewares=[auth])
    app.add_routes([
        web.get("/", index), web.get("/health", lambda r: web.Response(text="ok")),
        web.get("/api/me", me), web.post("/api/settings", save_settings),
        web.get("/api/searches", list_searches), web.post("/api/searches", save_search),
        web.delete("/api/searches/{id}", delete_search),
        web.get("/api/feed", feed), web.post("/api/fav", toggle_fav),
    ])
    return app
