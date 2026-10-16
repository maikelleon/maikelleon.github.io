#!/usr/bin/env python3
"""Apply one admin form (a GitHub issue) to data/content.json and rebuild index.html.

Usage: python scripts/from_issue.py <path to GitHub event JSON>
Writes a one-paragraph reply to reply.md, which the workflow posts on the issue.
Exit code 0 = applied, 3 = nothing changed (reply explains why).
"""
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import content  # noqa: E402

ROOT = HERE.parent
CONTENT = ROOT / "data" / "content.json"
REPLY = ROOT / "reply.md"


def parse_form(body):
    """GitHub issue forms render as '### Label' followed by the answer."""
    fields, current = {}, None
    for line in (body or "").replace("\r\n", "\n").split("\n"):
        m = re.match(r"^###\s+(.*\S)\s*$", line)
        if m:
            current = m.group(1).strip()
            fields[current] = []
        elif current is not None:
            fields[current].append(line)
    out = {}
    for k, v in fields.items():
        text = "\n".join(v).strip()
        out[k] = "" if text == "_No response_" else text
    return out


def year_of(s):
    s = (s or "").strip()
    return int(s) if s.isdigit() else (s or None)


def parse_links(text):
    links = []
    for line in (text or "").splitlines():
        line = line.strip().strip("<>")
        if not line:
            continue
        if "|" in line:
            label, url = [p.strip() for p in line.rsplit("|", 1)]
            links.append({"label": label, "url": url})
        else:
            links.append({"url": line})
    return [l for l in links if l["url"].startswith(("http://", "https://"))]


def main():
    event = json.loads(Path(sys.argv[1]).read_text())
    issue = event["issue"]
    title, f = issue["title"], parse_form(issue.get("body"))
    data = json.loads(CONTENT.read_text())
    kind = (re.match(r"^\[(\w+)\]", title) or [None, ""])[1].lower()
    msg = None

    if kind == "media":
        t = f.get("Type", "")
        mtype = "news" if t.startswith("News") else "podcast" if t.startswith("Podcast") else "tv"
        item = {"type": mtype, "outlet": f.get("Outlet and program", ""), "title": f.get("Title", ""),
                "year": year_of(f.get("Year")), "links": parse_links(f.get("Link or links"))}
        if not item["title"]:
            return done(3, "The title was missing, so nothing was added.")
        data["media"].append(item)
        msg = f'Added the media card "{item["title"]}" ({item["outlet"]}).'

    elif kind == "award":
        k = "certification" if f.get("Kind", "").startswith("Cert") else "award"
        item = {"kind": k, "year": f.get("Year", ""), "en": f.get("Text in English", ""),
                "es": f.get("Text in Spanish (optional)", "")}
        if not item["en"]:
            return done(3, "The English text was missing, so nothing was added.")
        data["awards"].append(item)
        msg = f'Added to Honors: "{item["en"]}".'

    elif kind == "talk":
        item = {"year": f.get("Year", ""), "en": f.get("Text in English", ""),
                "es": f.get("Text in Spanish (optional)", ""), "url": f.get("Link (optional)", "")}
        if not item["en"]:
            return done(3, "The English text was missing, so nothing was added.")
        data["talks"].append(item)
        msg = f'Added to Talks: "{item["en"]}".'

    elif kind == "announcement":
        if f.get("What to do", "").startswith("Remove"):
            data["announcement"] = {"show": False, "en": "", "es": "", "link": ""}
            msg = "Removed the announcement banner."
        else:
            en = f.get("Announcement in English", "")
            if not en:
                return done(3, "No English text was given, so the banner was not changed.")
            data["announcement"] = {"show": True, "en": en, "es": f.get("Announcement in Spanish (optional)", ""),
                                    "link": f.get('Link for "Details" (optional)', "")}
            msg = f'The banner now reads: "{en}".'

    elif kind == "sections":
        box = f.get("Sections to show", "")
        checked = lambda word: bool(re.search(rf"- \[[xX]\]\s*{word}", box))
        data["sections"] = {"consulting": checked("Consulting"), "talks": checked("Talks")}
        shown = [k for k, v in data["sections"].items() if v] or ["none"]
        msg = "Sections shown: " + ", ".join(shown) + "."

    elif kind == "remove":
        where = {"Media": "media", "Honors": "awards", "Talks": "talks"}.get(f.get("Section", ""))
        words = f.get("A few words from its title or text", "").lower()
        if not where or not words:
            return done(3, "The section or the words to match were missing, so nothing was removed.")
        hits = [i for i, it in enumerate(data[where])
                if words in (it.get("title", "") + " " + it.get("en", "") + " " + it.get("es", "")).lower()]
        if len(hits) != 1:
            return done(3, f'"{words}" matched {len(hits)} items in {f.get("Section")}, so nothing was removed. '
                           "Try a few more distinctive words.")
        gone = data[where].pop(hits[0])
        msg = f'Removed "{gone.get("title") or gone.get("en")}" from {f.get("Section")}.'

    else:
        return done(3, "This issue does not match one of the site forms, so nothing changed.")

    CONTENT.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
    content.INDEX.write_text(content.render(content=data))
    return done(0, msg + " The site updates within a few minutes.")


def done(code, text):
    REPLY.write_text(text + "\n")
    print(text)
    return code


if __name__ == "__main__":
    sys.exit(main())
