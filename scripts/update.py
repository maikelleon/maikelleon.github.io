#!/usr/bin/env python3
"""Refresh the publications and metrics on index.html.

Sources:
  * ORCID (the list of works)
  * OpenAlex (journal, volume, issue, pages, authors, open-access copy for each DOI)
  * Google Scholar profile (citations, h-index, i10-index), best effort
  * ORCID peer reviews (journals reviewed for; names looked up in OpenAlex)

Only the parts of index.html between the <!-- NAME:START --> and
<!-- NAME:END --> markers are rewritten. Everything else is left alone.
If a source cannot be reached, the current content is kept.

Usage:  python scripts/update.py            (live)
        python scripts/update.py --fixture tests/fixture.json   (offline test)
"""
import datetime as dt
import html
import json
import re
import sys
import time
import unicodedata
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))
import content  # noqa: E402  (research numbers, media, honors, talks, reviews, banner, sections; publisher names)
CONFIG = ROOT / "data" / "config.json"
CONTENT = ROOT / "data" / "content.json"
INDEX = ROOT / "index.html"
CACHE = ROOT / "data" / "works.json"
UA = "maikelleon-site-updater/1.0 (mailto:mleon@miami.edu)"

MONTHS_ES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio",
             "agosto", "septiembre", "octubre", "noviembre", "diciembre"]


# ---------------------------------------------------------------- fetching
def get(url, accept="application/json", tries=3):
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": accept})
            with urllib.request.urlopen(req, timeout=30) as r:
                return r.read().decode("utf-8", "replace")
        except Exception as e:  # noqa: BLE001
            if i == tries - 1:
                raise
            time.sleep(2 * (i + 1))


def fetch_orcid(orcid):
    data = json.loads(get(f"https://pub.orcid.org/v3.0/{orcid}/works"))
    works = []
    for g in data.get("group", []):
        s = g["work-summary"][0]
        dois = [x["external-id-value"].strip().lower()
                for x in g.get("external-ids", {}).get("external-id", [])
                if x.get("external-id-type") == "doi"]
        pd = s.get("publication-date") or {}
        year = (pd.get("year") or {}).get("value")
        t = s.get("title") or {}
        title = ((t.get("title") or {}).get("value") or "").strip()
        sub = ((t.get("subtitle") or {}).get("value") or "").strip()
        if sub and sub.lower() not in title.lower():
            title = f"{title}: {sub}"
        works.append({
            "title": title,
            "type": s.get("type", ""),
            "year": int(year) if year else None,
            "journal": ((s.get("journal-title") or {}).get("value") or "").strip(),
            "dois": dois,
        })
    return works


def fetch_openalex(dois):
    out = {}
    dois = sorted(set(dois))
    for i in range(0, len(dois), 40):
        chunk = "|".join(dois[i:i + 40])
        url = ("https://api.openalex.org/works?per-page=50&select=doi,title,publication_year,"
               "publication_date,type,primary_location,biblio,authorships,open_access,best_oa_location,is_retracted&filter=doi:"
               + urllib.parse.quote(chunk, safe="|:/"))
        data = json.loads(get(url))
        for w in data.get("results", []):
            if not w.get("doi"):
                continue
            doi = w["doi"].replace("https://doi.org/", "").lower()
            src = ((w.get("primary_location") or {}).get("source") or {})
            b = w.get("biblio") or {}
            oa = w.get("open_access") or {}
            out[doi] = {
                "title": w.get("title") or "",
                "year": w.get("publication_year"),
                "date": w.get("publication_date") or "",
                "type": w.get("type") or "",
                "journal": src.get("display_name") or "",
                "volume": b.get("volume") or "",
                "issue": b.get("issue") or "",
                "first_page": b.get("first_page") or "",
                "last_page": b.get("last_page") or "",
                "authors": [a["author"]["display_name"] for a in w.get("authorships") or []],
                "pdf": (w.get("best_oa_location") or {}).get("pdf_url") or "",
                "oa_url": (oa.get("oa_url") or "") if oa.get("is_oa") else "",
                "publisher": src.get("host_organization_name") or "",
                "retracted": bool(w.get("is_retracted")),
            }
        time.sleep(0.5)
    return out


def fetch_crossref(dois):
    """Fill gaps OpenAlex leaves (authors or venue missing, recent proceedings)."""
    out = {}
    for d in dois:
        try:
            m = json.loads(get(f"https://api.crossref.org/works/{urllib.parse.quote(d)}?mailto=mleon@miami.edu"))["message"]
        except Exception:  # noqa: BLE001
            continue
        parts = ((m.get("issued") or {}).get("date-parts") or [[None]])[0]
        page = (m.get("page") or "").replace("–", "-")
        first, _, last = page.partition("-")
        title = ((m.get("title") or [""])[0] or "").strip()
        sub = ((m.get("subtitle") or [""])[0] or "").strip()
        if sub and sub.lower() not in title.lower():
            title = f"{title}: {sub}"
        out[d] = {
            "title": title,
            "year": parts[0],
            "date": "-".join(f"{x:02d}" if i else str(x) for i, x in enumerate(parts) if x),
            "type": m.get("type") or "",
            "journal": ((m.get("container-title") or [""])[0] or (m.get("event") or {}).get("name") or ""),
            "volume": m.get("volume") or "",
            "issue": m.get("issue") or "",
            "first_page": first,
            "last_page": last,
            "authors": [" ".join(" ".join(x for x in (a.get("given"), a.get("family")) if x).split())
                        for a in m.get("author") or []],
            "publisher": m.get("publisher") or "",
        }
        time.sleep(0.3)
    return out


def fetch_reviews(orcid):
    """Journal names from the peer-review section of ORCID (each ISSN looked up in OpenAlex)."""
    data = json.loads(get(f"https://pub.orcid.org/v3.0/{orcid}/peer-reviews"))
    issns = []
    for g in data.get("group", []):
        for x in g.get("external-ids", {}).get("external-id", []):
            v = (x.get("external-id-value") or "").strip()
            if v.lower().startswith("issn:"):
                issns.append(v[5:])
    found = {}
    for i in dict.fromkeys(issns):
        try:
            src = json.loads(get(f"https://api.openalex.org/sources/issn:{urllib.parse.quote(i)}"))
        except Exception:  # noqa: BLE001
            continue
        n = (src.get("display_name") or "").strip()
        if n and n not in found:
            found[n] = (src.get("host_organization_name") or "").strip()
    return list(found.items())  # [(journal, publisher as OpenAlex spells it), ...]


def merge_reviews(journals, cfg, content_mod):
    """Add journals found in ORCID to reviewed_for in content.json. Never removes any."""
    data = json.loads(CONTENT.read_text())
    key = content_mod.journal_key
    name = lambda x: x if isinstance(x, str) else x.get("journal", "")  # noqa: E731
    have = {key(name(x)) for x in data.get("reviewed_for", [])} | {key(n) for n in cfg.get("reviews_exclude", [])}
    added = []
    for n, pub in journals:
        if key(n) not in have:
            added.append({"journal": n, "publisher": content_mod.publisher_name(pub)})
            have.add(key(n))
    if added:
        data["reviewed_for"] = data.get("reviewed_for", []) + added
        CONTENT.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
    return added


def merge_sources(oa, cr):
    """Crossref fills only what OpenAlex is missing."""
    for d, rec in cr.items():
        if d not in oa:
            oa[d] = rec
            continue
        for k, v in rec.items():
            if v and not oa[d].get(k):
                oa[d][k] = v
    return oa


def fetch_scholar(user):
    """Best effort. Google often blocks automated requests; return None then."""
    try:
        req = urllib.request.Request(
            f"https://scholar.google.com/citations?user={user}&hl=en",
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                                   "(KHTML, like Gecko) Chrome/124.0 Safari/537.36",
                     "Accept-Language": "en-US,en;q=0.9"})
        with urllib.request.urlopen(req, timeout=30) as r:
            page = r.read().decode("utf-8", "replace")
        vals = re.findall(r'<td class="gsc_rsb_std">(\d+)</td>', page)
        if len(vals) >= 6:
            return {"citations": int(vals[0]), "h_index": int(vals[2]), "i10_index": int(vals[4])}
    except Exception:  # noqa: BLE001
        pass
    return None


# ---------------------------------------------------------------- shaping
def is_me(full, cfg):
    return full in cfg["my_name_variants"] or "maikel" in full.lower()


def full_author(full, cfg):
    full = " ".join(full.split())
    return "Maikel Leon" if is_me(full, cfg) else full


def name_key(full):
    """('tucker', 'c') style key, accent-insensitive, for matching students."""
    plain = unicodedata.normalize("NFKD", full).encode("ascii", "ignore").decode().lower()
    parts = [x for x in re.split(r"[\s.]+", plain) if x]
    return (parts[-1], parts[0][0]) if len(parts) > 1 else (plain, "")


def short_author(full, cfg):
    if is_me(full, cfg):
        return cfg["my_name_display"]
    parts = full.replace("León", "Leon").split()
    if len(parts) == 1:
        return parts[0]
    last = parts[-1]
    initials = " ".join(p[0] + "." for p in parts[:-1] if p and p[0].isalpha())
    return f"{last}, {initials}"


def join_authors(names):
    if len(names) == 1:
        return names[0]
    if len(names) == 2:
        return f"{names[0]}, & {names[1]}"
    return ", ".join(names[:-1]) + ", & " + names[-1]


def pages_of(oa):
    f, l = str(oa.get("first_page") or ""), str(oa.get("last_page") or "")
    if not f:
        return ""
    if not l or l == f:
        return f.lstrip("0") or f
    return f"{f}–{l}"


def build(orcid_works, oa, cfg):
    journals = {k.lower(): v for k, v in cfg["journals"].items()}
    overrides = {k.lower(): v for k, v in cfg.get("overrides", {}).items()}
    exclude = {d.lower() for d in cfg.get("exclude", [])}
    venues = {k.lower(): v for k, v in cfg.get("venue_names", {}).items()}
    featured, everything, seen = [], [], set()

    for w in orcid_works:
        # pick the DOI that OpenAlex knows, preferring one in a featured journal
        best = None
        for d in w["dois"]:
            info = oa.get(d)
            if info and info["journal"].lower() in journals:
                best = d
                break
        if not best:
            best = next((d for d in w["dois"] if d in oa), w["dois"][0] if w["dois"] else None)
        info = oa.get(best, {}) if best else {}
        if info.get("retracted") or re.match(r"\s*(retracted\b|retraction\b)", info.get("title") or w["title"], re.I):
            continue  # retracted papers and retraction notices stay off the site
        key = best or w["title"].lower()
        if key in seen:
            continue
        seen.add(key)

        year = w["year"] or info.get("year")
        entry = {
            "doi": best,
            "title": info.get("title") or w["title"],
            "year": year,
            "type": w["type"],
            "journal_raw": info.get("journal") or w["journal"],
            "volume": str(info.get("volume") or "").lstrip("0"),
            "issue": str(info.get("issue") or "").lstrip("0"),
            "pages": pages_of(info),
            "authors": [short_author(a, cfg) for a in info.get("authors", [])],
            "authors_full": [full_author(a, cfg) for a in info.get("authors", [])],
            "date": info.get("date", ""),
            "pdf": info.get("pdf", ""),
            "oa_url": info.get("oa_url", ""),
            "publisher": info.get("publisher", ""),
            "src_type": info.get("type", ""),
        }
        entry.update({k: v for k, v in overrides.get(best or "", {}).items()})
        everything.append(entry)

        j = journals.get(entry["journal_raw"].lower())
        if j and best and best not in exclude and entry["authors"]:
            entry["journal"] = j["name"]
            entry["if"] = j.get("if")
            featured.append(entry)
        entry["journal_raw"] = venues.get(entry["journal_raw"].lower(), entry["journal_raw"])

    key = lambda e: (e["year"] or 0, e.get("date") or "")
    featured.sort(key=key, reverse=True)
    everything.sort(key=key, reverse=True)
    return featured, everything


# ---------------------------------------------------------------- rendering
E = html.escape


BIB_TYPE = {"journal-article": "article", "conference-paper": "inproceedings", "book-chapter": "incollection",
            "book": "book", "preprint": "misc", "other": "misc"}
SRC_TYPE = {"article": "article", "journal-article": "article", "proceedings-article": "inproceedings",
            "book-chapter": "incollection", "book": "book", "preprint": "misc", "posted-content": "misc"}
BIB_VENUE = {"article": "journal", "inproceedings": "booktitle", "incollection": "booktitle"}
STOPWORDS = {"a", "an", "the", "on", "of", "for", "and", "to", "in", "with", "from", "toward", "towards", "via", "using"}
_KEYS, _USED = {}, set()


def ascii_fold(s):
    return unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode()


def bib_escape(s):
    return re.sub(r"([&%$#_])", r"\\\1", s or "")


def bib_title(t):
    """Brace acronyms and mixed-case words (AI, GPT-5, LLMs) so citation styles keep their capitals."""
    def protect(w):
        core = re.sub(r"^\W+|\W+$", "", w)
        tricky = any(c.isupper() for c in core[1:]) or (any(c.isdigit() for c in core) and any(c.isalpha() for c in core))
        return w.replace(core, "{" + core + "}", 1) if core and tricky else w
    return " ".join(protect(w) for w in bib_escape(t).replace("–", "--").replace("—", "---").split(" "))


def bib_key(e):
    """leon2026cognitive: first author, year, first meaningful title word. Stable per paper."""
    ident = (e.get("doi") or e.get("title") or "").lower()
    if ident in _KEYS:
        return _KEYS[ident]
    first = (e.get("authors_full") or ["anon"])[0].split() or ["anon"]
    last = re.sub(r"[^a-z]", "", ascii_fold(first[-1]).lower()) or "anon"
    words = [re.sub(r"[^a-z0-9]", "", ascii_fold(w).lower()) for w in (e.get("title") or "").split()]
    word = next((w for w in words if w and w not in STOPWORDS), "")
    base = key = f"{last}{e.get('year') or ''}{word}"
    n = 1
    while key in _USED:
        n += 1
        key = f"{base}{chr(96 + n)}"
    _USED.add(key)
    _KEYS[ident] = key
    return key


def bibtex(e):
    """A complete-as-possible BibTeX entry for one paper."""
    if e.get("journal"):  # featured journal article
        typ = "article"
    elif e.get("src_type") == "proceedings-article":
        typ = "inproceedings"
    else:
        typ = BIB_TYPE.get(e.get("type")) or SRC_TYPE.get(e.get("src_type"), "misc")
    venue = e.get("journal") or e.get("journal_raw") or ""
    fields = [("author", " and ".join(e.get("authors_full") or [])),
              ("title", bib_title(e.get("title", ""))),
              (BIB_VENUE.get(typ, "howpublished"), bib_escape(venue)),
              ("year", str(e.get("year") or "")),
              ("volume", str(e.get("volume") or "")),
              ("number", str(e.get("issue") or "")),
              ("pages", str(e.get("pages") or "").replace("–", "--")),
              ("publisher", bib_escape(content.publisher_name(e.get("publisher")))),
              ("doi", e.get("doi") or ""),
              ("url", f"https://doi.org/{e['doi']}" if e.get("doi") else "")]
    body = ",\n".join(f"  {k} = {{{v}}}" for k, v in fields if v)
    return f"@{typ}{{{bib_key(e)},\n{body}\n}}"


def paper_tools(e):
    """PDF (or another free copy) and a BibTeX button for one paper; the DOI link is the caller's."""
    out = ""
    doi_url = f"https://doi.org/{e['doi']}".lower() if e.get("doi") else ""
    if e.get("pdf"):
        out += f'<a class="tool" href="{E(e["pdf"])}" target="_blank" rel="noopener">PDF</a>'
    elif e.get("oa_url") and e["oa_url"].lower().rstrip("/") != doi_url:
        out += (f'<a class="tool" href="{E(e["oa_url"])}" target="_blank" rel="noopener">'
                '<span class="en">Open access</span><span class="es">Acceso abierto</span></a>')
    if e.get("authors_full"):  # no BibTeX without authors; it would be incomplete
        out += f'<button type="button" class="tool bib" data-key="{E(bib_key(e))}" data-bib="{E(bibtex(e))}">BibTeX</button>'
    return out


def extra_links(doi, links):
    """Links shown beside a paper, from paper_links in config.json (keyed by DOI)."""
    out = ""
    for l in links.get((doi or "").lower(), []):
        if not l.get("url"):
            continue
        ic = f'<svg class="ico-s" aria-hidden="true"><use href="#i-{E(l["icon"])}"/></svg>' if l.get("icon") else ""
        en, es = E(l.get("en") or l["url"]), E(l.get("es") or l.get("en") or l["url"])
        label = en if en == es else f'<span class="en">{en}</span><span class="es">{es}</span>'
        out += f'<a class="xl" href="{E(l["url"])}" target="_blank" rel="noopener">{ic}{label}</a>'
    return out


def render_pub(e, links=None):
    venue = f'<i>{E(e["journal"])}</i>'
    bits = ""
    if e["volume"]:
        bits += f', {E(e["volume"])}'
        if e["issue"]:
            bits += f'({E(e["issue"])})'
    if e["pages"]:
        bits += f', {E(e["pages"])}'
    authors = E(join_authors(e["authors"]))
    meta = f'<a class="doi" href="https://doi.org/{E(e["doi"])}" target="_blank" rel="noopener">doi:{E(e["doi"])}</a>'
    if e.get("if") is not None:
        meta += f'<span class="if">IF {e["if"]:.1f}</span>'
    meta += paper_tools(e) + extra_links(e["doi"], links or {})
    return (f'        <li><span class="yr">{e["year"]}</span><div><span class="pt">{E(e["title"])}</span>'
            f'<span class="pv">{authors} {venue}{bits}</span><span class="meta">{meta}</span></div></li>\n')


def render_pubs(featured, links=None):
    if not featured:
        return None
    one = lambda e: render_pub(e, links)  # noqa: E731
    top = featured[0]["year"]
    recent = [e for e in featured if e["year"] == top]
    earlier = [e for e in featured if e["year"] != top]
    out = f'      <h3 class="first">{top}</h3>\n      <ol class="pubs">\n' + "".join(map(one, recent[:3])) + "      </ol>\n"
    if recent[3:]:
        out += ('      <details class="fold">\n'
                f'        <summary><h3><span class="en">More from {top}</span><span class="es">Más de {top}</span></h3>'
                f'<span class="fold-n">{len(recent) - 3}</span></summary>\n'
                '      <ol class="pubs">\n' + "".join(map(one, recent[3:])) + "      </ol>\n      </details>\n")
    if earlier:
        out += ('      <details class="fold">\n'
                '        <summary><h3><span class="en">Earlier</span><span class="es">Anteriores</span></h3>'
                f'<span class="fold-n">{len(earlier)}</span></summary>\n'
                '      <ol class="pubs">\n' + "".join(map(one, earlier)) + "      </ol>\n      </details>\n")
    return out


def render_students(everything, cfg):
    """Papers co-authored with the students listed in config.json."""
    keys = {name_key(n) for n in cfg.get("students", [])}
    extras = {k.lower(): v for k, v in cfg.get("student_extras", {}).items()}
    links = {k.lower(): v for k, v in cfg.get("paper_links", {}).items()}
    rows = []
    for e in everything:
        names = e.get("authors_full") or []
        if not keys or not any(name_key(a) in keys for a in names):
            continue
        authors = names[0] if len(names) == 1 else ", ".join(names[:-1]) + " & " + names[-1]
        bits = ""
        if e.get("volume"):
            bits += f', {E(e["volume"])}' + (f'({E(e["issue"])})' if e.get("issue") else "")
        if e.get("pages"):
            bits += f', {E(e["pages"])}'
        venue = f' · <i>{E(e["journal_raw"])}</i>{bits}' if e.get("journal_raw") else ""
        meta = ""
        if e.get("doi"):
            meta += f'<a class="doi" href="https://doi.org/{E(e["doi"])}" target="_blank" rel="noopener">doi:{E(e["doi"])}</a>'
        x = extras.get((e.get("doi") or "").lower(), {})
        if x.get("badge_en"):
            meta += (f'<span class="if award"><span class="en">{E(x["badge_en"])}</span>'
                     f'<span class="es">{E(x.get("badge_es") or x["badge_en"])}</span></span>')
        if x.get("code"):
            meta += (f'<a class="doi" href="{E(x["code"])}" target="_blank" rel="noopener">'
                     '<span class="en">Code</span><span class="es">Código</span></a>')
        meta += paper_tools(e) + extra_links(e.get("doi"), links)
        rows.append(f'        <li><span class="yr">{e["year"] or ""}</span><div><span class="pt">{E(e["title"])}</span>'
                    f'<span class="pv">{E(authors)}{venue}</span><span class="meta">{meta}</span></div></li>\n')
    if not rows:
        return None
    return ('      <details class="fold">\n'
                '        <summary><h3><span class="en">Papers with students</span><span class="es">Artículos con estudiantes</span></h3>'
                f'<span class="fold-n">{len(rows)}</span></summary>\n'
            '      <ol class="pubs">\n' + "".join(rows) + "      </ol>\n      </details>\n")


TYPE_LABEL = {"journal-article": ("Journal article", "Artículo"), "conference-paper": ("Conference paper", "Ponencia"),
              "book-chapter": ("Book chapter", "Capítulo de libro"), "preprint": ("Preprint", "Preprint")}


def render_all(everything):
    n = len(everything)
    rows = []
    for e in everything:
        en, es = TYPE_LABEL.get(e["type"], ("Other", "Otro"))
        venue = E(e["journal_raw"]) + " · " if e["journal_raw"] else ""
        title = E(e["title"])
        if e["doi"]:
            title = f'<a href="https://doi.org/{E(e["doi"])}" target="_blank" rel="noopener">{title}</a>'
        rows.append(f'          <li><span class="yr">{e["year"] or ""}</span><span><span class="wt">{title}</span>'
                    f'<span class="wv">{venue}<span class="en">{en}</span><span class="es">{es}</span></span>'
                    f'<span class="meta">{paper_tools(e)}</span></span></li>\n')
    return ('      <details class="fold">\n'
                '        <summary><h3><span class="en">All works in ORCID</span><span class="es">Todas las obras en ORCID</span></h3>'
                f'<span class="fold-n">{n}</span></summary>\n'
            '        <ol class="works">\n' + "".join(rows) + '        </ol>\n      </details>\n')


def render_updated(today):
    return (f'<span class="en">Updated {today:%B %Y}</span>'
            f'<span class="es">Actualizado en {MONTHS_ES[today.month - 1]} de {today.year}</span>')


def replace_block(doc, name, content, inline=False):
    pat = re.compile(rf"(<!-- {name}:START -->)(.*?)(\s*<!-- {name}:END -->)" if not inline
                     else rf"(<!-- {name}:START -->)(.*?)(<!-- {name}:END -->)", re.S)
    if not pat.search(doc):
        raise SystemExit(f"Marker {name} not found in index.html")
    sep = "" if inline else "\n"
    return pat.sub(lambda m: m.group(1) + sep + content.rstrip("\n") + m.group(3), doc, count=1)


# ---------------------------------------------------------------- main
def main():
    cfg = json.loads(CONFIG.read_text())
    fixture = None
    if "--fixture" in sys.argv:
        fixture = json.loads(Path(sys.argv[sys.argv.index("--fixture") + 1]).read_text())

    report = []
    try:
        orcid_works = fixture["orcid"] if fixture else fetch_orcid(cfg["orcid"])
        all_dois = [d for w in orcid_works for d in w["dois"]]
        oa = fixture["openalex"] if fixture else fetch_openalex(all_dois)
        gaps = sorted({d for d in all_dois if d not in oa or not oa[d].get("authors") or not oa[d].get("journal")})
        cr = fixture.get("crossref", {}) if fixture else fetch_crossref(gaps)
        oa = merge_sources(oa, cr)
        featured, everything = build(orcid_works, oa, cfg)
        report.append(f"ORCID: {len(orcid_works)} works; featured journal articles: {len(featured)}")
    except Exception as e:  # noqa: BLE001
        featured, everything = [], []
        report.append(f"Could not reach ORCID/OpenAlex ({e}); publications left unchanged.")

    scholar = None if fixture else fetch_scholar(cfg["scholar_user"])
    if scholar:
        cfg["metrics"].update(scholar)
        cfg["metrics"]["checked"] = dt.date.today().strftime("%Y-%m")
        CONFIG.write_text(json.dumps(cfg, indent=2, ensure_ascii=False) + "\n")
        report.append(f"Google Scholar: {scholar}")
    else:
        report.append("Google Scholar did not respond to the update (common); kept saved numbers "
                      f"{cfg['metrics']['citations']} / h {cfg['metrics']['h_index']} / i10 {cfg['metrics']['i10_index']}.")

    doc = INDEX.read_text()
    pubs = render_pubs(featured, {k.lower(): v for k, v in cfg.get("paper_links", {}).items()})
    if pubs:
        doc = replace_block(doc, "PUBS", pubs)
        doc = replace_block(doc, "ALLWORKS", render_all(everything))
        CACHE.write_text(json.dumps({"featured": featured, "all": everything}, indent=1, ensure_ascii=False))
        students = render_students(everything, cfg)
        if students and "<!-- STUDENTS:START -->" in doc:
            doc = replace_block(doc, "STUDENTS", students)
    doc = replace_block(doc, "UPDATED", render_updated(dt.date.today()), inline=True)
    if not fixture:
        try:
            journals = fetch_reviews(cfg["orcid"])
            added = merge_reviews(journals, cfg, content)
            report.append(f"ORCID peer reviews: {len(journals)} journals; "
                          + (f"added {', '.join(a['journal'] for a in added)}." if added else "nothing new."))
        except Exception as e:  # noqa: BLE001
            report.append(f"Could not read peer reviews from ORCID ({e}); the reviewer list was left unchanged.")
    doc = content.render(doc=doc, cfg=cfg)
    INDEX.write_text(doc)
    print("\n".join(report))


if __name__ == "__main__":
    main()
