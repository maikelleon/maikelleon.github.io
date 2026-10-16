#!/usr/bin/env python3
"""Check every outside link on index.html.

Writes links-report.md. If any link is clearly dead (404, 410, or the site no
longer exists), it also writes broken.md, which the workflow turns into an
issue so you get an email. Sites that block automated checks (403, 429, and
similar) are listed as "could not verify" rather than broken.
"""
import concurrent.futures as cf
import re
import urllib.error
import urllib.request
from pathlib import Path
from html import unescape

ROOT = Path(__file__).resolve().parent.parent
INDEX = ROOT / "index.html"
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 13_5) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")
DEAD = {404, 410}


def check(url):
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "text/html,*/*"})
        with urllib.request.urlopen(req, timeout=25) as r:
            body = r.read(20000).decode("utf-8", "ignore")
            if "Content Unavailable For Legal Reasons" in body:
                return url, "unverified", "blocked in this region"
            return url, "ok", str(r.status)
    except urllib.error.HTTPError as e:
        return url, ("broken" if e.code in DEAD else "unverified"), f"HTTP {e.code}"
    except urllib.error.URLError as e:
        reason = str(e.reason)
        dead = "Name or service not known" in reason or "nodename nor servname" in reason
        return url, ("broken" if dead else "unverified"), reason[:80]
    except Exception as e:  # noqa: BLE001
        return url, "unverified", type(e).__name__


def main():
    html = INDEX.read_text()
    urls = sorted({unescape(u) for u in re.findall(r'href="(https?://[^"]+)"', html)
                   if "fonts.g" not in u})
    with cf.ThreadPoolExecutor(8) as ex:
        results = list(ex.map(check, urls))
    broken = [r for r in results if r[1] == "broken"]
    unver = [r for r in results if r[1] == "unverified"]
    ok = len(results) - len(broken) - len(unver)

    lines = [f"Checked {len(results)} links: {ok} working, {len(broken)} broken, {len(unver)} could not be verified.", ""]
    if broken:
        lines += ["### Broken", ""] + [f"- {u} ({why})" for u, _, why in broken] + [""]
    if unver:
        lines += ["### Could not verify (the site blocks automated checks; open them yourself if unsure)", ""]
        lines += [f"- {u} ({why})" for u, _, why in unver] + [""]
    report = "\n".join(lines)
    (ROOT / "links-report.md").write_text(report)
    if broken:
        (ROOT / "broken.md").write_text(
            "The monthly link check found links that no longer work. Replace or remove them with the "
            '"Remove an item" form, or ask Claude to fix them.\n\n' + report)
    print(report)


if __name__ == "__main__":
    main()
