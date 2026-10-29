#!/usr/bin/env python3
"""Price-drop wishlist. Usage: wishlist.py add|list|remove|check. Env: NTFY_TOPIC, WISHLIST_DB."""
import argparse
import json
import os
import re
import sqlite3
import sys
import time

import requests
from bs4 import BeautifulSoup

DB = os.environ.get("WISHLIST_DB", os.path.join(os.path.dirname(os.path.abspath(__file__)), "wishlist.db"))
TOPIC = os.environ.get("NTFY_TOPIC")
MAX_FAILS = 3  # consecutive extraction failures before we notify
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:128.0) Gecko/20100101 Firefox/128.0"


def db():
    con = sqlite3.connect(DB)
    con.executescript("""
        CREATE TABLE IF NOT EXISTS items(id INTEGER PRIMARY KEY, url TEXT UNIQUE, name TEXT,
            selector TEXT, last_price REAL, fails INTEGER DEFAULT 0);
        CREATE TABLE IF NOT EXISTS prices(item_id INTEGER, ts INTEGER, price REAL);
    """)
    return con


def to_float(s):
    """'1.299,00' / '1,299.00' / '49.99 EUR' -> float."""
    s = re.sub(r"[^\d.,]", "", str(s))
    if "," in s and "." in s:
        dec = "," if s.rfind(",") > s.rfind(".") else "."
        s = s.replace("." if dec == "," else ",", "").replace(dec, ".")
    elif "," in s:
        s = s.replace(",", ".") if len(s.rsplit(",", 1)[1]) != 3 else s.replace(",", "")
    return float(s)


def _offers(node):
    if isinstance(node, list):
        for n in node:
            yield from _offers(n)
    elif isinstance(node, dict):
        if "price" in node or "lowPrice" in node:
            yield node.get("price", node.get("lowPrice"))
        for v in node.values():
            if isinstance(v, (dict, list)):
                yield from _offers(v)


def extract_price(html, selector=None):
    soup = BeautifulSoup(html, "html.parser")
    if selector:
        el = soup.select_one(selector)
        if el:
            return to_float(el.get("content") or el.get_text())
    for tag in soup.find_all("script", type="application/ld+json"):
        try:
            for p in _offers(json.loads(tag.string or "")):
                if p not in (None, ""):
                    return to_float(p)
        except (ValueError, TypeError):
            continue
    meta = soup.find("meta", property="product:price:amount")
    if meta and meta.get("content"):
        return to_float(meta["content"])
    raise ValueError("no price found")


def fetch_price(url, selector):
    r = requests.get(url, headers={"User-Agent": UA}, timeout=20)
    r.raise_for_status()
    return extract_price(r.text, selector)


def notify(title, msg, url=None):
    print(f"{title}: {msg}")
    if not TOPIC:
        return
    h = {"Title": title}
    if url:
        h["Click"] = url
    requests.post(f"https://ntfy.sh/{TOPIC}", data=msg.encode(), headers=h, timeout=20)


def cmd_add(a):
    price = fetch_price(a.url, a.selector)  # raises if unreadable: fail loudly
    con = db()
    cur = con.execute("INSERT INTO items(url,name,selector,last_price) VALUES(?,?,?,?)",
                      (a.url, a.name or a.url, a.selector, price))
    con.execute("INSERT INTO prices VALUES(?,?,?)", (cur.lastrowid, int(time.time()), price))
    con.commit()
    print(f"added #{cur.lastrowid} at {price}")


def cmd_list(_):
    for i, n, p, u in db().execute("SELECT id,name,last_price,url FROM items"):
        print(f"#{i}  {p}  {n}  {u}")


def cmd_remove(a):
    con = db()
    con.execute("DELETE FROM prices WHERE item_id=?", (a.id,))
    con.execute("DELETE FROM items WHERE id=?", (a.id,))
    con.commit()


def cmd_check(_):
    con = db()
    for i, url, name, sel, last, fails in con.execute(
            "SELECT id,url,name,selector,last_price,fails FROM items").fetchall():
        try:
            price = fetch_price(url, sel)
        except Exception as e:  # one bad item must not stop the rest
            fails += 1
            con.execute("UPDATE items SET fails=? WHERE id=?", (fails, i))
            if fails == MAX_FAILS:
                notify("Wishlist: can't read price", f"{name}: {e}", url)
            continue
        con.execute("UPDATE items SET fails=0 WHERE id=?", (i,))
        if price != last:
            notify("Price change", f"{name}: {last} -> {price}", url)
            con.execute("UPDATE items SET last_price=? WHERE id=?", (price, i))
            con.execute("INSERT INTO prices VALUES(?,?,?)", (i, int(time.time()), price))
    con.commit()


def self_test():
    ld = '<script type="application/ld+json">{"@type":"Product","offers":{"price":"49.99"}}</script>'
    assert extract_price(ld) == 49.99
    assert extract_price('<meta property="product:price:amount" content="1.299,00">') == 1299.0
    assert extract_price('<span class="p">$ 12,50</span>', ".p") == 12.5
    try:
        extract_price("<html></html>")
        raise SystemExit("expected ValueError")
    except ValueError:
        pass
    print("ok")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("add")
    p.add_argument("url")
    p.add_argument("--name")
    p.add_argument("--selector")
    p.set_defaults(f=cmd_add)
    sub.add_parser("list").set_defaults(f=cmd_list)
    p = sub.add_parser("remove")
    p.add_argument("id", type=int)
    p.set_defaults(f=cmd_remove)
    sub.add_parser("check").set_defaults(f=cmd_check)
    sub.add_parser("test").set_defaults(f=lambda _: self_test())
    a = ap.parse_args()
    a.f(a)
