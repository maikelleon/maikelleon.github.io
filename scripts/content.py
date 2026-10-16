#!/usr/bin/env python3
"""Render data/content.json (media, awards, talks, skills, journals reviewed
for, announcement, section visibility), the research numbers, and the analytics tag into index.html.

Run on its own to rebuild those parts:  python scripts/content.py
"""
import html
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONTENT = ROOT / "data" / "content.json"
CONFIG = ROOT / "data" / "config.json"
INDEX = ROOT / "index.html"
E = html.escape

ACTION = {"tv": ("Watch", "Ver", "play"), "video": ("Watch", "Ver", "play"),
          "podcast": ("Listen", "Escuchar", "play"), "radio": ("Listen", "Escuchar", "play"),
          "news": ("Read", "Leer", "doc"), "article": ("Read", "Leer", "doc")}


def icon(name):
    """Small line icon from the sprite at the top of index.html."""
    return f'<svg class="ico-s" aria-hidden="true"><use href="#i-{name}"/></svg>'


def bi(en, es=""):
    """English/Spanish pair; if no Spanish is given, the English shows in both languages."""
    en, es = (en or "").strip(), (es or "").strip()
    if not es or es == en:
        return E(en)
    return f'<span class="en">{E(en)}</span><span class="es">{E(es)}</span>'


def last_year(y):
    """'2022–26' -> 2026, '2019' -> 2019, None -> 0 (sorts last)."""
    nums = re.findall(r"\d{2,4}", str(y or ""))
    if not nums:
        return 0
    n = nums[-1]
    return int(n) + 2000 if len(n) == 2 else int(n)


def link(url, inner):
    return f'<a href="{E(url)}" target="_blank" rel="noopener">{inner}</a>'


VISIBLE_CELLS = 3  # one full row of three cards; a multi-segment card takes two cells


def render_media(items):
    items = sorted(items, key=lambda m: last_year(m.get("year")), reverse=True)
    out, cells = [], []
    for m in items:
        links = [l for l in m.get("links", []) if l.get("url")]
        year = str(m.get("year") or "")
        head = f'<span class="outlet">{E(m.get("outlet", ""))}</span><span class="mt">{E(m.get("title", ""))}</span>'
        if len(links) > 1 or (links and links[0].get("label")):
            segs = "".join(f'            <li>{link(l["url"], E(l.get("label") or l["url"]))}</li>\n' for l in links)
            n = len(links)
            count = (f'<span class="en">{n} segments</span><span class="es">{n} segmentos</span>' if n > 1
                     else '<span class="en">Watch</span><span class="es">Ver</span>')
            md = " · ".join(x for x in [year, count] if x)
            out.append(f'        <li class="wide">{head}\n          <ol class="seg">\n{segs}          </ol>\n'
                       f'          <span class="md">{md}</span></li>\n')
            cells.append(2)
        else:
            en, es, ic = ACTION.get(m.get("type", "tv"), ACTION["tv"])
            act = link(links[0]["url"], f'{icon(ic)}<span class="en">{en}</span><span class="es">{es}</span>') if links else ""
            md = " · ".join(x for x in [year, act] if x)
            out.append(f'        <li>{head}<span class="md">{md}</span></li>\n')
            cells.append(1)
    # newest cards that fit exactly one row stay open; everything else, in order, goes in the fold
    keep, used = [], 0
    for i, c in enumerate(cells):
        if used + c <= VISIBLE_CELLS:
            keep.append(i)
            used += c
        if used == VISIBLE_CELLS:
            break
    html_out = '      <ul class="media">\n' + "".join(out[i] for i in keep) + "      </ul>\n"
    rest = [o for i, o in enumerate(out) if i not in keep]
    if rest:
        html_out += ('      <details class="fold">\n'
                     '        <summary><h3><span class="en">More appearances</span><span class="es">Más apariciones</span></h3>'
                     f'<span class="fold-n">{len(rest)}</span></summary>\n'
                     '      <ul class="media">\n' + "".join(rest) + "      </ul>\n      </details>\n")
    return html_out


def render_list(items):
    items = sorted(items, key=lambda a: last_year(a.get("year")), reverse=True)
    out = []
    for a in items:
        text = bi(a.get("en"), a.get("es"))
        if a.get("url"):
            text = link(a["url"], text)
        out.append(f'        <li><span class="yr">{E(str(a.get("year", "")))}</span><span>{text}</span></li>\n')
    return "".join(out)


def journal_key(name):
    """Comparison key for journal names: case, '&' versus 'and', and punctuation are ignored."""
    return " ".join(re.findall(r"\w+", (name or "").casefold().replace("&", " and ")))


PUBLISHERS = {  # names as databases spell them -> how the site shows them
    "elsevier": "Elsevier", "elsevier bv": "Elsevier", "elsevier inc": "Elsevier", "elsevier ltd": "Elsevier",
    "ieee": "IEEE", "ieee computer society": "IEEE", "institute of electrical and electronics engineers": "IEEE",
    "mdpi": "MDPI", "mdpi ag": "MDPI", "multidisciplinary digital publishing institute": "MDPI",
    "springer": "Springer Nature", "springer nature": "Springer Nature", "springer science business media": "Springer Nature",
    "springer international publishing": "Springer Nature", "biomed central": "Springer Nature", "bmc": "Springer Nature",
    "taylor and francis": "Taylor & Francis", "informa uk limited": "Taylor & Francis",
    "wiley": "Wiley", "john wiley and sons": "Wiley", "wiley blackwell": "Wiley",
}


def publisher_name(raw):
    raw = (raw or "").strip()
    return PUBLISHERS.get(journal_key(raw), raw)


def render_reviews(items, exclude=()):
    """Journals reviewed for, grouped by publisher, each listed once. Returns (html, count)."""
    skip = {journal_key(n) for n in exclude}
    seen, groups = set(), {}
    for it in items:
        name = (it if isinstance(it, str) else it.get("journal", "")).strip()
        pub = "" if isinstance(it, str) else publisher_name(it.get("publisher"))
        k = journal_key(name)
        if not name or k in seen or k in skip:
            continue
        seen.add(k)
        groups.setdefault(pub, []).append(name)
    rows = []
    for pub in sorted(groups, key=lambda p: (p == "", p.casefold())):
        label = E(pub) if pub else '<span class="en">Other</span><span class="es">Otras</span>'
        names = "&nbsp;· ".join(E(n) for n in sorted(groups[pub], key=str.casefold))
        rows.append(f'          <li><span class="yr">{label}</span><span>{names}</span></li>\n')
    return "".join(rows), len(seen)


def render_skills(groups):
    """Skill chips in labeled groups. Returns (html, count)."""
    out, n = [], 0
    for g in groups:
        chips = "".join(f"<li>{bi(x.get('en'), x.get('es'))}</li>" for x in g.get("items", []) if (x.get("en") or "").strip())
        if not chips:
            continue
        n += chips.count("<li>")
        out.append(f'          <div><p class="sk-h">{bi(g.get("en"), g.get("es"))}</p><ul class="chips">{chips}</ul></div>\n')
    return "".join(out), n


def render_metrics(cfg):
    """Research numbers: Google Scholar citations and h-index, with a link to the profile."""
    m = cfg.get("metrics", {})
    cites = m.get("citations", 0)
    cites = f"{int(cites):,}" if str(cites).isdigit() else E(str(cites))
    h = E(str(m.get("h_index", "")))
    user = E(cfg.get("scholar_user", ""))
    return ('        <div class="facts">\n'
            f'          <span><strong>{cites}</strong><span class="en">citations</span><span class="es">citas</span></span>\n'
            f'          <span><strong>{h}</strong><span class="en">h-index</span><span class="es">índice h</span></span>\n'
            '        </div>\n'
            f'        <p class="src"><a class="ext" href="https://scholar.google.com/citations?user={user}" '
            'target="_blank" rel="noopener">Google Scholar</a></p>\n')


def render_announce(a):
    if not a.get("show") or not (a.get("en") or "").strip():
        return ""
    text = bi(a.get("en"), a.get("es"))
    more = ""
    if (a.get("link") or "").strip():
        more = link(a["link"].strip(), '<span class="en">Details</span><span class="es">Detalles</span>')
    return f'<div class="announce" role="note"><div class="wrap"><span>{text}</span>{more}</div></div>'


def render_analytics(code):
    code = (code or "").strip()
    if not code:
        return ""
    return (f'<script data-goatcounter="https://{E(code)}.goatcounter.com/count" async '
            f'src="https://gc.zgo.at/count.js"></script>')


def set_block(doc, name, content):
    pat = re.compile(rf"(<!-- {name}:START -->)(.*?)([ \t]*<!-- {name}:END -->)", re.S)
    if not pat.search(doc):
        raise SystemExit(f"Marker {name} not found in index.html")
    body = ("\n" + content.rstrip("\n") + "\n") if content else "\n"
    return pat.sub(lambda m: m.group(1) + body + m.group(3), doc, count=1)


def set_visible(doc, key, visible):
    def fix(m):
        tag = re.sub(r"\s+hidden(?=[\s>])", "", m.group(0))
        return tag if visible else tag[:-1] + " hidden>"
    return re.sub(rf'<[a-z]+[^>]*data-toggle="{key}"[^>]*>', fix, doc)


def set_tones(doc):
    """Visible sections alternate black and white after the light hero, whatever is hidden."""
    tones, i = ["t-black", "t-white"], 0

    def fix(m):
        nonlocal i
        tag = m.group(0)
        if re.search(r"\shidden(?=[\s>])", tag):
            return tag
        tag = re.sub(r'class="t-\w+"', f'class="{tones[i % 2]}"', tag, count=1)
        i += 1
        return tag
    return re.sub(r'<section id="\w+"[^>]*>', fix, doc)


def render(doc=None, content=None, cfg=None):
    content = content or json.loads(CONTENT.read_text())
    cfg = cfg or json.loads(CONFIG.read_text())
    doc = doc if doc is not None else INDEX.read_text()
    doc = set_block(doc, "METRICS", render_metrics(cfg))
    doc = set_block(doc, "MEDIA", render_media(content.get("media", [])))
    doc = set_block(doc, "AWARDS", render_list([a for a in content.get("awards", []) if a.get("kind", "award") == "award"]))
    doc = set_block(doc, "CERTS", render_list([a for a in content.get("awards", []) if a.get("kind") == "certification"]))
    doc = set_block(doc, "TALKS", render_list(content.get("talks", [])))
    reviews, n_reviews = render_reviews(content.get("reviewed_for", []), cfg.get("reviews_exclude", []))
    doc = set_block(doc, "REVIEWS", reviews)
    doc = set_visible(doc, "reviews", n_reviews > 0)
    skills, n_skills = render_skills(content.get("skills", []))
    doc = set_block(doc, "SKILLS", skills)
    doc = set_visible(doc, "skills", n_skills > 0)
    doc = set_block(doc, "ANNOUNCE", render_announce(content.get("announcement", {})))
    doc = set_block(doc, "ANALYTICS", render_analytics(cfg.get("goatcounter")))
    counts = {"talks": len(content.get("talks", [])),
              "certs": len([a for a in content.get("awards", []) if a.get("kind") == "certification"]),
              "reviews": n_reviews}
    for key, n in counts.items():
        doc = re.sub(rf'(<span class="fold-n" data-count="{key}">)\d*(</span>)', rf"\g<1>{n}\g<2>", doc)
    for key, vis in content.get("sections", {}).items():
        doc = set_visible(doc, key, bool(vis))
    return set_tones(doc)


if __name__ == "__main__":
    INDEX.write_text(render())
    print("Rebuilt media, honors, talks, skills, journals reviewed for, announcement, sections and analytics.")
