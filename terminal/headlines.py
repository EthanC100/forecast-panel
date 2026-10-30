"""Headlines for the AI brief: GDELT DOC 2.0 article lists plus official press pages.

Every headline gets a stable id (h:<8 hex of its URL>) so the brief can cite it. A source that
fails is recorded with its error and the rest carry on; nothing here is retried around a block
(a 403 stays a 403 and shows up in the snapshot's source list).
"""

from __future__ import annotations

import datetime as dt
import email.utils
import hashlib
import html
import json
import logging
import re
import time
import xml.etree.ElementTree as ET

import requests

from terminal.http import UA, get

log = logging.getLogger(__name__)

GDELT = "https://api.gdeltproject.org/api/v2/doc/doc"
GDELT_QUERIES = [
    # (country, query); English-language coverage keeps titles readable
    ("FR", '(France OR French) (budget OR deficit OR rating OR censure OR "Le Pen" OR Bardella OR "bond yields") sourcelang:english'),
    ("BR", '(Brazil OR Brazilian) (Copom OR Selic OR fiscal OR Haddad OR Lula OR "real currency") sourcelang:english'),
    ("MX", '(Mexico OR Mexican) (peso OR Banxico OR Morena OR Sheinbaum OR tariffs OR Pemex) sourcelang:english'),
    ("US", '(USMCA OR "trade agreement") (Mexico OR Canada) review sourcelang:english'),
]

PRESS = [
    # key, body, country, kind, url
    ("bcb", "Banco Central do Brasil (press notes)", "BR", "atom", "https://www.bcb.gov.br/api/feed/sitebcb/sitefeeds/notasImprensa"),
    ("banxico", "Banco de México (press releases)", "MX", "links",
     "https://www.banxico.org.mx/publicaciones-y-prensa/comunicados-de-prensa-banxico/comunicados-de-prensa-banxico.html"),
    ("tesouro", "Tesouro Nacional (news)", "BR", "links", "https://www.gov.br/tesouronacional/pt-br/noticias"),
    ("shcp", "SHCP (press releases)", "MX", "gobmx", "https://www.gob.mx/shcp/archivo/prensa?idiom=es&order=DESC&page=1"),
    ("aft", "Agence France Trésor (news)", "FR", "links", "https://www.aft.gouv.fr/en/actualites"),
    ("assemblee", "Assemblée nationale (sitting reports)", "FR", "rss", "https://www2.assemblee-nationale.fr/feeds/detail/crs"),
    ("ustr", "USTR (press releases)", "US", "rss", "https://ustr.gov/rss.xml"),
]
# links: anchors on a list page whose href contains one of these path fragments
LINK_PATTERNS = {
    "banxico": r"/publicaciones-y-prensa/[^\"']+\.(?:html|pdf)",
    "tesouro": r"/tesouronacional/pt-br/noticias/[a-z0-9-]{12,}",
    "aft": r"/(?:en|fr)/(?:actualites|news)/[a-z0-9-]{8,}",
}


def hid(url: str) -> str:
    return "h:" + hashlib.sha1(url.encode()).hexdigest()[:8]


def _clean(s: str | None) -> str:
    s = html.unescape(re.sub(r"<[^>]+>", " ", s or ""))
    return re.sub(r"\s+", " ", s).strip()


def _date(s: str | None) -> str | None:
    if not s:
        return None
    s = s.strip()
    try:
        return dt.datetime.strptime(s, "%Y%m%dT%H%M%SZ").date().isoformat()  # GDELT seendate
    except ValueError:
        pass
    try:
        return dt.datetime.fromisoformat(s.replace("Z", "+00:00")).date().isoformat()
    except ValueError:
        pass
    try:
        return email.utils.parsedate_to_datetime(s).date().isoformat()
    except (TypeError, ValueError):
        pass
    m = re.match(r"(\d{4}-\d{2}-\d{2})", s)
    return m.group(1) if m else None


# --------------------------------------------------------------------------
# GDELT
# --------------------------------------------------------------------------

_last = 0.0


def gdelt_articles(query: str, hours: int = 48, n: int = 25, tries: int = 4) -> list[dict]:
    """Most relevant recent articles for a query (ArtList). Same pacing as the calendar: one call
    every 6 seconds and a growing back-off on the rate-limit notice."""
    global _last
    params = {"query": query, "mode": "ArtList", "format": "json", "maxrecords": n, "timespan": f"{hours}h",
              "sort": "HybridRel"}
    delay = 10.0
    for _ in range(tries):
        wait = 6.0 - (time.monotonic() - _last)
        if wait > 0:
            time.sleep(wait)
        r = requests.get(GDELT, params=params, headers={"User-Agent": UA}, timeout=30)
        _last = time.monotonic()
        text = r.text
        if text.lstrip().startswith("{"):
            return json.loads(text).get("articles") or []
        if not text.strip():
            return []
        if r.status_code == 429 or "limit requests" in text:
            time.sleep(delay)
            delay = min(delay * 1.6, 90)
            continue
        raise RuntimeError(f"GDELT {r.status_code}: {text[:200]}")
    raise RuntimeError("GDELT kept returning its rate-limit notice")


def from_gdelt(per_query: int = 8, budget_s: float = 360) -> tuple[list[dict], list[dict]]:
    out, status = [], []
    start = time.monotonic()
    for country, q in GDELT_QUERIES:
        if time.monotonic() - start > budget_s:
            status.append({"source": f"GDELT {country}", "ok": False, "n": 0, "error": "skipped: GDELT time budget used up"})
            continue
        try:
            arts = gdelt_articles(q)
            seen, kept = set(), 0
            for a in arts:
                title = _clean(a.get("title"))
                key = re.sub(r"\W+", " ", title.lower())[:80]
                if not title or key in seen or not a.get("url"):
                    continue
                seen.add(key)
                out.append({"id": hid(a["url"]), "title": title, "url": a["url"], "source": a.get("domain") or "GDELT",
                            "via": "GDELT DOC 2.0", "country": country, "date": _date(a.get("seendate")), "official": False})
                kept += 1
                if kept >= per_query:
                    break
            status.append({"source": f"GDELT {country}", "ok": True, "n": kept, "error": None})
        except Exception as exc:  # noqa: BLE001
            log.warning("GDELT %s: %s", country, exc)
            status.append({"source": f"GDELT {country}", "ok": False, "n": 0, "error": str(exc)[:200]})
    return out, status


# --------------------------------------------------------------------------
# Official press pages
# --------------------------------------------------------------------------

def _feed(text: str, kind: str) -> list[tuple[str, str, str | None, str]]:
    """(title, link, date, extra) from RSS 2.0 or Atom."""
    root = ET.fromstring(text.encode() if isinstance(text, str) else text)
    items = []
    if kind == "atom":
        ns = {"a": "http://www.w3.org/2005/Atom"}
        for e in root.findall("a:entry", ns):
            link = e.find("a:link", ns)
            items.append((_clean(e.findtext("a:title", "", ns)), link.get("href") if link is not None else "",
                          _date(e.findtext("a:updated", None, ns) or e.findtext("a:published", None, ns)),
                          _clean(e.findtext("a:summary", "", ns))))
    else:
        for e in root.iter("item"):
            descs = [_clean(d.text) for d in e.findall("description")]
            items.append((_clean(e.findtext("title")), (e.findtext("link") or "").strip(), _date(e.findtext("pubDate")),
                          descs[-1] if descs else ""))
    return items


def _gobmx(text: str, base: str = "https://www.gob.mx") -> list[tuple[str, str, str | None, str]]:
    """gob.mx archive pages answer with a jQuery fragment: <time datetime=...>, <h2>, <a href>."""
    t = text.replace("\\n", "\n").replace('\\"', '"').replace("\\/", "/")
    out = []
    for block in re.findall(r"<article>(.*?)</article>", t, re.S):
        title = _clean((re.search(r"<h2>(.*?)</h2>", block, re.S) or [None, ""])[1])
        href = (re.search(r'href="([^"]+)"', block) or [None, ""])[1]
        when = (re.search(r'datetime="([^"]+)"', block) or [None, None])[1]
        if title and href:
            out.append((title, href if href.startswith("http") else base + href, _date(when), ""))
    return out


def _links(text: str, key: str, base: str) -> list[tuple[str, str, str | None, str]]:
    out, seen = [], set()
    for href, label in re.findall(r'<a[^>]+href="([^"]+)"[^>]*>(.*?)</a>', text, re.S):
        label = _clean(label)
        if not re.search(LINK_PATTERNS[key], href) or len(label) < 20 or href in seen:
            continue
        seen.add(href)
        url = href if href.startswith("http") else re.match(r"https?://[^/]+", base).group(0) + href
        out.append((label, url, None, ""))
    return out


def _describe(url: str) -> str:
    """Meta description of a press-release page (gob.mx titles are only 'Comunicado No. N')."""
    try:
        t = get(url, timeout=30, retries=1).text
        m = re.search(r'<meta[^>]+(?:name|property)="(?:og:)?description"[^>]+content="([^"]+)"', t)
        return _clean(m.group(1)) if m else ""
    except Exception:  # noqa: BLE001
        return ""


def from_press(per_source: int = 5, max_age_days: int = 21) -> tuple[list[dict], list[dict]]:
    out, status = [], []
    cutoff = (dt.date.today() - dt.timedelta(days=max_age_days)).isoformat()
    for key, body, country, kind, url in PRESS:
        try:
            r = get(url, timeout=40, retries=1)
            if kind in ("rss", "atom"):
                items = _feed(r.text, kind)
            elif kind == "gobmx":
                items = _gobmx(r.text)
            else:
                items = _links(r.text, key, url)
            if not items and re.search(r"manuten|maintenance", r.text[:3000], re.I):
                raise RuntimeError("site shows a maintenance page")
            items = [x for x in items if x[1] and (x[2] is None or x[2] >= cutoff)][:per_source]
            for title, link, date, extra in items:
                if kind == "gobmx":
                    extra = _describe(link)
                if extra and extra.lower() != title.lower() and len(title) < 60:
                    title = f"{title}: {extra[:160]}"
                out.append({"id": hid(link), "title": title, "url": link, "source": body, "via": url,
                            "country": country, "date": date, "official": True})
            status.append({"source": body, "ok": True, "n": len(items), "error": None if items else "no recent items"})
        except Exception as exc:  # noqa: BLE001
            log.warning("press %s: %s", key, exc)
            status.append({"source": body, "ok": False, "n": 0, "error": f"{type(exc).__name__}: {exc}"[:200]})
    return out, status


def collect(lo: int = 20, hi: int = 40) -> tuple[list[dict], list[dict]]:
    """Official items first (they are the primary sources), then GDELT, balanced across countries,
    capped at ``hi``. Fewer than ``lo`` is recorded as a note, not padded."""
    press, s1 = from_press()
    news, s2 = from_gdelt()
    seen, out = set(), []
    for h in press:
        if h["id"] not in seen:
            seen.add(h["id"])
            out.append(h)
    by_c: dict[str, list[dict]] = {}
    for h in news:
        if h["id"] not in seen:
            seen.add(h["id"])
            by_c.setdefault(h["country"], []).append(h)
    while len(out) < hi and any(by_c.values()):
        for c in list(by_c):
            if by_c[c] and len(out) < hi:
                out.append(by_c[c].pop(0))
    return out, s1 + s2
