#!/usr/bin/env python3
"""Fetch visitor totals from GoatCounter for the dashboard on the controls page.

Needs the GOATCOUNTER_TOKEN secret (an API key created in GoatCounter) and the
"goatcounter" code in data/config.json. Writes one small JSON file with totals
for the last 30 days and the 30 days before. GoatCounter keeps nothing about
individual visitors, and neither does this file.

Usage:  python scripts/stats.py --out stats.json
        python scripts/stats.py --fixture tests/stats-fixture.json --out stats.json   (offline test)
"""
import datetime as dt
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONFIG = ROOT / "data" / "config.json"
DAYS = 30
LIST_LIMIT = 8
UA = "maikelleon-site-stats/1.0"


def stamp(t):
    return t.strftime("%Y-%m-%dT%H:%M:%SZ")


def make_api(code, token):
    base = f"https://{code}.goatcounter.com/api/v0"

    def api(path, **params):
        url = f"{base}{path}?{urllib.parse.urlencode(params)}"
        req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}",
                                                   "Content-Type": "application/json", "User-Agent": UA})
        for attempt in range(3):
            try:
                with urllib.request.urlopen(req, timeout=30) as r:
                    return json.loads(r.read().decode("utf-8"))
            except urllib.error.HTTPError as e:
                if e.code == 429 and attempt < 2:  # GoatCounter allows 4 requests a second
                    time.sleep(2 + attempt)
                    continue
                body = e.read().decode("utf-8", "replace")[:300]
                raise SystemExit(f"GoatCounter answered {e.code} for {path}: {body}")
            finally:
                time.sleep(0.3)
    return api


def hits(api, start, end):
    """Every page and click in the range, with a count per day."""
    params = dict(start=stamp(start), end=stamp(end), limit=100)
    try:
        return api("/stats/hits", group="day", **params)
    except SystemExit:
        return api("/stats/hits", daily="true", **params)  # older servers


def summarize(cur, prev, lists, start, days):
    """Shape the API answers into the file the dashboard reads."""
    day0 = start.date()
    daily = {(day0 + dt.timedelta(days=i)).isoformat(): 0 for i in range(days)}
    pages, clicks = [], []
    for h in cur.get("hits", []):
        row = {"name": (h.get("title") or h.get("path") or "").strip() or h.get("path", ""),
               "path": h.get("path", ""), "n": int(h.get("count") or 0)}
        if h.get("event"):
            clicks.append(row)
            continue
        pages.append(row)
        for s in h.get("stats", []):
            if s.get("day") in daily:
                daily[s["day"]] += int(s.get("daily") or 0)
    previous = sum(int(h.get("count") or 0) for h in prev.get("hits", []) if not h.get("event"))

    def ranked(rows):
        rows = [{"name": (r.get("name") or "").strip(), "n": int(r.get("count") or 0)} for r in rows]
        return sorted([r for r in rows if r["n"] > 0], key=lambda r: -r["n"])[:LIST_LIMIT]

    by_n = lambda rows: sorted([r for r in rows if r["n"] > 0], key=lambda r: -r["n"])[:LIST_LIMIT]  # noqa: E731
    return {
        "updated": stamp(dt.datetime.now(dt.timezone.utc).replace(microsecond=0)),
        "days": days,
        "total": sum(daily.values()),
        "previous": previous,
        "daily": [[d, n] for d, n in daily.items()],
        "pages": by_n(pages),
        "clicks": by_n(clicks),
        "countries": ranked(lists["locations"].get("stats", [])),
        "sources": ranked(lists["toprefs"].get("stats", [])),
        "devices": ranked(lists["sizes"].get("stats", [])),
        "systems": ranked(lists["systems"].get("stats", [])),
        "browsers": ranked(lists["browsers"].get("stats", [])),
    }


def main():
    out = Path(sys.argv[sys.argv.index("--out") + 1]) if "--out" in sys.argv else ROOT / "stats.json"
    now = dt.datetime.now(dt.timezone.utc).replace(minute=0, second=0, microsecond=0)
    end = now + dt.timedelta(hours=1)  # include the current hour
    start = (end - dt.timedelta(days=DAYS)).replace(hour=0)
    pstart = start - dt.timedelta(days=DAYS)

    if "--fixture" in sys.argv:
        fx = json.loads(Path(sys.argv[sys.argv.index("--fixture") + 1]).read_text())
        start = dt.datetime.fromisoformat(fx["start"]).replace(tzinfo=dt.timezone.utc)
        data = summarize(fx["hits"], fx["previous"], fx["lists"], start, DAYS)
    else:
        code = (json.loads(CONFIG.read_text()).get("goatcounter") or "").strip()
        token = (os.environ.get("GOATCOUNTER_TOKEN") or "").strip()
        if not code or not token:
            print("Visitor stats are not set up yet: the GoatCounter code or the GOATCOUNTER_TOKEN secret is missing.")
            return
        api = make_api(code, token)
        cur = hits(api, start, end)
        prev = hits(api, pstart, start)
        lists = {page: api(f"/stats/{page}", start=stamp(start), end=stamp(end), limit=LIST_LIMIT)
                 for page in ("locations", "toprefs", "sizes", "systems", "browsers")}
        data = summarize(cur, prev, lists, start, DAYS)

    out.write_text(json.dumps(data, indent=1, ensure_ascii=False) + "\n")
    top = data["countries"][0]["name"] if data["countries"] else "none yet"
    print(f"Visitors, last {DAYS} days: {data['total']} (previous {DAYS} days: {data['previous']}); "
          f"clicks counted: {sum(c['n'] for c in data['clicks'])}; top country: {top}.")


if __name__ == "__main__":
    main()
