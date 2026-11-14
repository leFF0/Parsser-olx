import aiosqlite
from config import DB_PATH

_db = None

SCHEMA = """
CREATE TABLE IF NOT EXISTS users(
  id INTEGER PRIMARY KEY, lang TEXT DEFAULT 'uk', notify INTEGER DEFAULT 1,
  quiet_from INTEGER DEFAULT 23, quiet_to INTEGER DEFAULT 7,
  daily_limit INTEGER DEFAULT 30, tz INTEGER DEFAULT 2);
CREATE TABLE IF NOT EXISTS searches(
  id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, name TEXT,
  keywords TEXT DEFAULT '', stop_words TEXT DEFAULT '', must_words TEXT DEFAULT '',
  min_price INTEGER DEFAULT 0, max_price INTEGER DEFAULT 0, discount INTEGER DEFAULT 0,
  city TEXT DEFAULT '', sites TEXT DEFAULT 'olx', condition TEXT DEFAULT 'any',
  active INTEGER DEFAULT 1, hide_sus INTEGER DEFAULT 0);
CREATE TABLE IF NOT EXISTS ads(
  id TEXT PRIMARY KEY, site TEXT, title TEXT, price REAL, url TEXT, photo TEXT,
  city TEXT, created TEXT, descr TEXT, sus INTEGER DEFAULT 0, first_seen INTEGER);
CREATE TABLE IF NOT EXISTS matches(
  search_id INTEGER, ad_id TEXT, notified INTEGER DEFAULT 0, ts INTEGER,
  PRIMARY KEY(search_id, ad_id));
CREATE TABLE IF NOT EXISTS favs(user_id INTEGER, ad_id TEXT, PRIMARY KEY(user_id, ad_id));
CREATE TABLE IF NOT EXISTS sent(user_id INTEGER, day TEXT, n INTEGER DEFAULT 0, PRIMARY KEY(user_id, day));
"""

DEFAULTS = {
    "uk": [("Телефони до 2000 грн", "iphone, samsung galaxy, xiaomi redmi, смартфон", 2000),
           ("Ноутбуки до 6000 грн", "ноутбук, thinkpad, macbook, lenovo, asus, acer, hp, dell", 6000)],
    "ru": [("Телефоны до 2000 грн", "iphone, samsung galaxy, xiaomi redmi, смартфон", 2000),
           ("Ноутбуки до 6000 грн", "ноутбук, thinkpad, macbook, lenovo, asus, acer, hp, dell", 6000)],
}


async def init():
    global _db
    _db = await aiosqlite.connect(DB_PATH)
    _db.row_factory = aiosqlite.Row
    await _db.executescript(SCHEMA)
    await _db.commit()


async def q(sql, args=()):
    cur = await _db.execute(sql, args)
    rows = await cur.fetchall()
    return [dict(r) for r in rows]


async def x(sql, args=()):
    """Выполнить запись, вернуть (lastrowid, rowcount)."""
    cur = await _db.execute(sql, args)
    await _db.commit()
    return cur.lastrowid, cur.rowcount


async def ensure_user(uid, lang_code):
    lang = "ru" if (lang_code or "").startswith("ru") else "uk"
    if await q("SELECT 1 FROM users WHERE id=?", (uid,)):
        return False
    await x("INSERT INTO users(id, lang) VALUES(?,?)", (uid, lang))
    for name, kw, mx in DEFAULTS[lang]:
        await x("INSERT INTO searches(user_id,name,keywords,max_price) VALUES(?,?,?,?)", (uid, name, kw, mx))
    return True
