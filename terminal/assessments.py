"""Independent fiscal assessments (monthly): IFI (Brazil), HCFP and Cour des comptes (France),
México Evalúa and IMEF (Mexico).

For each body: find the latest publication (inputs/assessments.yaml), read its text (HTML or PDF),
summarise it in two or three lines with one key number via the Claude API (Batch API, the same
spend counter and cap as the brief), and validate: every number in the summary must appear in the
document (decimal commas and points both accepted) and the stated date's year must appear too.
A summary that fails is published with an "unverified" mark and its problems, never corrected.
Output: data/terminal/assessments.json.
"""

from __future__ import annotations

import hashlib
import html
import io
import json
import logging
import re
import xml.etree.ElementTree as ET

import yaml

from terminal import brief, store
from terminal.http import get

log = logging.getLogger(__name__)

SPEC = store.INPUTS / "assessments.yaml"
OUT = store.DATA / "assessments.json"
MAX_CHARS = 120_000
MONTHS = {m: i for i, m in enumerate("janeiro fevereiro marco março abril maio junho julho agosto setembro outubro novembro dezembro".split(), 1)}
MONTHS.update({"março": 3, "marco": 3, "abril": 4, "maio": 5, "junho": 6, "julho": 7, "agosto": 8, "setembro": 9, "outubro": 10,
               "novembro": 11, "dezembro": 12})


def _clean_html(t: str) -> str:
    t = re.sub(r"<(script|style|nav|footer|header)[^>]*>.*?</\1>", " ", t, flags=re.S | re.I)
    t = html.unescape(re.sub(r"<[^>]+>", " ", t))
    return re.sub(r"\s+", " ", t).strip()


def read_text(url: str) -> str:
    r = get(url, timeout=120, retries=1)
    if "pdf" in r.headers.get("Content-Type", "").lower() or url.lower().split("?")[0].endswith(".pdf") or r.content[:5] == b"%PDF-":
        from pypdf import PdfReader
        return re.sub(r"[ \t]+", " ", "\n".join((p.extract_text() or "") for p in PdfReader(io.BytesIO(r.content)).pages))
    text = r.text
    if re.search(r"Verificação de segurança|security check|captcha", text[:3000], re.I):
        raise RuntimeError("the page sits behind a browser security check")
    return _clean_html(text)


def _key(groups: tuple) -> tuple:
    out = []
    for g in groups:
        g = (g or "").lower()
        out.append(int(g) if g.isdigit() else MONTHS.get(g, 0))
    return tuple(out)


def discover(d: dict) -> dict | None:
    """The latest publication: {title, url, date, key, text?}."""
    kind = d["kind"]
    if kind == "links":
        page = get(d["url"], timeout=60, retries=1).text
        found = {}
        for m in re.finditer(r'href="([^"]+)"[^>]*>(.*?)</a>', page, re.S):
            mm = re.search(d["pattern"], m.group(1))
            if mm:
                url = m.group(1) if m.group(1).startswith("http") else re.match(r"https?://[^/]+", d["url"]).group(0) + m.group(1)
                k = _key(mm.groups())
                title = _clean_html(m.group(2)) or url.rsplit("/", 1)[-1].replace("-", " ")
                has_month = any((g or "").lower() in MONTHS for g in mm.groups())
                if k not in found or len(title) > len(found[k]["title"]):
                    found[k] = {"title": title, "url": url, "key": k,
                                "date": f"{k[0]}-{k[1]:02d}" if has_month and len(k) > 1 else None}
        return found[max(found)] if found else None
    if kind == "rss":
        root = ET.fromstring(get(d["url"], timeout=60, retries=1).content)
        ns = {"content": "http://purl.org/rss/1.0/modules/content/"}
        for it in root.iter("item"):
            title = _clean_html(it.findtext("title") or "")
            if any(k in title.lower() for k in d["keywords"]):
                body = it.findtext("content:encoded", None, ns)
                return {"title": title, "url": (it.findtext("link") or "").strip(), "date": _rss_date(it.findtext("pubDate")),
                        "text": _clean_html(body) if body else None}
        return None
    if kind == "wp":
        for p in get(d["url"], timeout=60, retries=1).json():
            title = _clean_html(p["title"]["rendered"])
            if any(k in title.lower() for k in d["keywords"]):
                return {"title": title, "url": p["link"], "date": p["date"][:10], "text": _clean_html(p.get("content", {}).get("rendered", ""))}
        return None
    if kind == "datagouv":
        try:
            ds = get(d["url"], timeout=60, retries=1).json()
            res = [r for r in ds.get("resources", []) if (r.get("format") or "").lower() == "pdf"]
            if res:
                r = max(res, key=lambda r: r.get("last_modified") or "")
                return {"title": f"{ds.get('title')}: {r.get('title')}", "url": r["url"], "date": (r.get("last_modified") or "")[:10]}
        except Exception as exc:  # noqa: BLE001
            log.warning("data.gouv.fr: %s", exc)
        return discover({"kind": "links", "url": d["fallback_url"], "pattern": d["pattern"]})
    raise ValueError(kind)


def _rss_date(s: str | None) -> str | None:
    import email.utils
    try:
        return email.utils.parsedate_to_datetime(s).date().isoformat()
    except (TypeError, ValueError):
        return None


def source_values(text: str) -> set[float]:
    """Every number in the document, read both as 1.234,5 (pt/fr/es) and as 1,234.5 (en)."""
    vals: set[float] = set()
    for tok in re.findall(r"\d[\d.,   ]*\d|\d", text):
        tok = tok.strip().replace(" ", " ").replace(" ", " ")
        for cand in (tok.replace(" ", "").replace(".", "").replace(",", "."), tok.replace(" ", "").replace(",", "")):
            try:
                vals.add(float(cand))
            except ValueError:
                pass
        for part in re.split(r"[ ]", tok):  # a space may separate two numbers rather than thousands
            for cand in (part.replace(".", "").replace(",", "."), part.replace(",", "")):
                try:
                    vals.add(float(cand))
                except ValueError:
                    pass
    return vals


SYSTEM = """You summarise publications by independent fiscal institutions and economists for a sovereign-debt research page.

From the document only, write:
- summary: two or three plain English sentences on the publication's main assessment of the public finances (targets, deficit, debt, risks, how it compares with the government's view).
- key_number: the single most important figure, as written in the document but with a decimal point instead of a decimal comma, and what it measures.
- date: the publication date stated in the document (YYYY-MM-DD, or YYYY-MM if only the month is given).
- stance: how the assessment compares with the government's own figures.

Every number you write must appear in the document. Do not compute new numbers or add outside knowledge."""

SCHEMA = {"type": "object", "additionalProperties": False, "required": ["summary", "key_number", "date", "stance"],
          "properties": {"summary": {"type": "string"},
                         "key_number": {"type": "object", "additionalProperties": False, "required": ["value", "what"],
                                        "properties": {"value": {"type": "string"}, "what": {"type": "string"}}},
                         "date": {"type": "string"},
                         "stance": {"type": "string", "enum": ["more cautious than the government", "in line with the government",
                                                               "more optimistic than the government", "not a comparison"]}}}


def validate(out: dict, text: str, hint_date: str | None) -> list[str]:
    vals = source_values(text)
    probs = []
    for field, t in (("summary", out.get("summary", "")), ("key number", out.get("key_number", {}).get("value", ""))):
        probs += [f"{field}: {p.replace('snapshot value', 'number in the document')}" for p in brief.check_text(t, vals)]
    year = (out.get("date") or "")[:4]
    if not (year.isdigit() and (year in text or (hint_date or "").startswith(year))):
        probs.append(f"date {out.get('date')!r} is not supported by the document")
    n = len(re.findall(r"[.!?](\s|$)", out.get("summary", "").strip()))
    if n > 3:
        probs.append(f"summary has {n} sentences (at most 3)")
    return probs


def run(force: bool = False, use_batch: bool = True) -> dict:
    spec = yaml.safe_load(SPEC.read_text())["bodies"]
    cfg = brief.conf()
    prev = {i["id"]: i for i in (json.loads(OUT.read_text()).get("items", []) if OUT.exists() else [])}
    items, reqs, docs = [], [], {}
    for b in spec:
        item = {"id": b["id"], "country": b["country"], "name": b["name"], "note": b.get("note"), "fetched_at": store.now_iso()}
        found, err = None, None
        try:
            found = discover(b["discover"])
        except Exception as exc:  # noqa: BLE001
            err = f"discovery failed: {type(exc).__name__}: {exc}"[:200]
        pinned = b.get("pinned")
        doc, text = None, None
        for cand in [c for c in (found, pinned) if c]:
            try:
                text = cand.get("text") or read_text(cand["url"])
                if len(text) > 400:
                    doc = cand
                    break
            except Exception as exc:  # noqa: BLE001
                err = f"{cand['url']}: {type(exc).__name__}: {exc}"[:240]
        if found and doc is not found:
            item["newer"] = {"title": found["title"], "url": found["url"], "date": found.get("date"),
                             "why": "listed, but its text could not be read automatically" + (f" ({err})" if err else "")}
        if not doc:
            item.update({"status": "unavailable", "error": err or "no publication found", "verified": None})
            items.append(item)
            continue
        item.update({"title": doc["title"], "url": doc["url"], "listed_date": doc.get("date"), "text_chars": len(text),
                     "truncated": len(text) > MAX_CHARS})
        h = hashlib.sha1(text[:MAX_CHARS].encode()).hexdigest()
        item["text_hash"] = h
        old = prev.get(b["id"])
        if old and old.get("text_hash") == h and old.get("summary") and not force:
            items.append({**old, "fetched_at": item["fetched_at"], "newer": item.get("newer"), "unchanged": True})
            continue
        docs[b["id"]] = (text, doc.get("date"))
        user = f"Publication: {doc['title']}\nURL: {doc['url']}\n\nDocument text:\n{text[:MAX_CHARS]}"
        reqs.append((f"a-{b['id']}", "assessments", {
            "model": cfg["models"]["assessments"], "max_tokens": cfg["max_tokens"]["assessments"], "system": SYSTEM,
            "messages": [{"role": "user", "content": user}],
            "output_config": {"effort": cfg["effort"]["assessments"], "format": {"type": "json_schema", "schema": SCHEMA}}}))
        items.append(item)
    sp = brief.load_spend()
    month, cap = brief.month_spend(sp), float(cfg["monthly_cap_usd"])
    if reqs and not store.secret("ANTHROPIC_API_KEY"):
        for it in items:
            if it["id"] in docs:
                it.update({"status": "no_ai", "verified": None, "error": "ANTHROPIC_API_KEY is not set"})
        reqs = []
    elif reqs and month >= cap:
        for it in items:
            if it["id"] in docs:
                it.update({"status": "skipped", "verified": None, "error": f"monthly AI cap reached (${month:.2f} of ${cap:.2f})"})
        reqs = []
    res = brief.call_all(reqs, cfg, sp, use_batch) if reqs else {}
    for it in items:
        if f"a-{it['id']}" not in res:
            continue
        out, e = res[f"a-{it['id']}"]
        if e:
            it.update({"status": "failed", "verified": False, "problems": [e]})
            continue
        text, hint = docs[it["id"]]
        probs = validate(out, text, hint)
        it.update({"status": "ok", "summary": out["summary"], "key_number": out["key_number"], "date": out["date"],
                   "stance": out["stance"], "verified": not probs, "problems": probs})
    if reqs:
        brief._write(brief.SPEND, sp)
    result = {"generated_at": store.now_iso(), "items": items,
              "rule": "Every number in a summary must appear in the cited document; failures are marked unverified, not corrected."}
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=1) + "\n")
    return result
