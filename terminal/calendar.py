"""Catalyst calendar: sourced events, official FOMC/ECB calendars, recurring releases, past
Brazil/Mexico decisions and elections from em-macro, and a GDELT market-attention score.

Attention score (definition)
----------------------------
For each event query q (GDELT DOC 2.0 keywords in events.yaml, which name the country or its
institutions):

    share_30d(q)  = matching articles / all articles monitored by GDELT, last 30 days
    share_12m(q)  = the same over the last 12 months (the normal level for those keywords)
    score         = share_30d(q) / share_12m(q)      1.0 = normal coverage; 0.5 = half of normal

Each query is compared with its own normal level, not with other queries: comparing different
queries mostly measures how broad their wording is (the first version did that and flagged every
FOMC meeting). An event is **under-attended** when importance = 3, score < 0.5 and it is 30 or
more days away. One 12-month GDELT call per query gives both shares; daily results are kept in
data/terminal/attention.json as [date, matches_30d, total_30d, share_30d, share_12m].
"""

from __future__ import annotations

import csv
import datetime as dt
import io
import json
import logging
import os
import re
import statistics
import time
from pathlib import Path

import requests
import yaml

from terminal import store
from terminal.http import get

log = logging.getLogger(__name__)

CAL_PATH = store.DATA / "calendar.json"
ATT_PATH = store.DATA / "attention.json"
EVENTS_YAML = store.INPUTS / "events.yaml"
FED_URL = "https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm"
ECB_URL = "https://www.ecb.europa.eu/press/calendars/mgcgc/html/index.en.html"
EM_MACRO_RAW = "https://raw.githubusercontent.com/EthanC100/em-macro/main/"
GDELT = "https://api.gdeltproject.org/api/v2/doc/doc"
UNDER_ATTENDED_SCORE = 0.5
UNDER_ATTENDED_DAYS = 30
MONTHS = {m: i for i, m in enumerate(["january", "february", "march", "april", "may", "june", "july", "august",
                                       "september", "october", "november", "december"], 1)}

# Official dates as scraped on 2026-10-29, used only if the live scrape fails.
FOMC_FALLBACK = ["2026-12-09", "2027-01-27", "2027-03-17", "2027-04-28", "2027-06-09", "2027-07-28", "2027-09-15",
                 "2027-10-27", "2027-12-08"]
ECB_FALLBACK = ["2026-12-17", "2027-02-04", "2027-03-18", "2027-04-29", "2027-06-10", "2027-07-22", "2027-09-09",
                "2027-10-28", "2027-12-16"]


def slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")[:48]


def ev(date, country, typ, title, importance, status, source, query, note="", origin="manual", **extra) -> dict:
    d = {"date": str(date)[:10], "country": country, "type": typ, "title": title, "importance": int(importance),
         "status": status, "source": source, "query": query, "note": note, "origin": origin}
    d.update(extra)
    d["id"] = f"{d['date']}-{country.lower()}-{slug(title)}"
    return d


# --------------------------------------------------------------------------
# Official calendars
# --------------------------------------------------------------------------


def parse_fomc(html: str) -> list[str]:
    """Decision dates (second day of each meeting) from the Fed's FOMC calendar page."""
    out = []
    for m in re.finditer(r"(\d{4}) FOMC Meetings", html):
        year = int(m.group(1))
        nxt = html.find("FOMC Meetings", m.end())
        seg = html[m.end(): nxt if nxt > 0 else len(html)]
        for month, days in re.findall(r"fomc-meeting__month[^>]*>\s*<strong>([^<]+)</strong>.*?fomc-meeting__date[^>]*>([^<]+)<", seg, re.S):
            if "notation" in days.lower() or "unscheduled" in days.lower():
                continue
            month = month.strip().split("/")[-1].lower()
            mm = next((v for k, v in MONTHS.items() if k.startswith(month[:3])), None)
            last = re.findall(r"\d+", days)
            if mm and last:
                out.append(dt.date(year, mm, int(last[-1])).isoformat())
    return sorted(set(out))


def parse_ecb(html: str) -> list[str]:
    """Monetary policy decision days (the meeting day followed by the press conference)."""
    out = []
    for d, dd in re.findall(r"<dt>\s*([0-9/]+)\s*</dt>\s*<dd>(.*?)</dd>", html, re.S):
        text = re.sub(r"<[^>]+>", "", dd).lower()
        if "monetary policy meeting" in text and "non-monetary" not in text and "followed by press conference" in text:
            day, month, year = d.split("/")
            out.append(f"{year}-{month}-{day}")
    return sorted(set(out))


def official_meetings(notes: list[str]) -> list[dict]:
    events = []
    try:
        fomc = parse_fomc(get(FED_URL, timeout=60).text)
        if not fomc:
            raise RuntimeError("no meetings parsed")
        fomc_src = "scraped"
    except Exception as exc:  # noqa: BLE001
        notes.append(f"FOMC calendar scrape failed ({exc}); using the dates scraped on 2026-10-29.")
        fomc, fomc_src = FOMC_FALLBACK, "fallback"
    for d in fomc:
        events.append(ev(d, "GLOBAL", "rates", "FOMC decision", 3, "confirmed", FED_URL, '"Federal Reserve" FOMC',
                         note="Second day of the meeting; statement 14:00 ET.", origin=f"fed:{fomc_src}"))
    try:
        ecb = parse_ecb(get(ECB_URL, timeout=60).text)
        if not ecb:
            raise RuntimeError("no meetings parsed")
        ecb_src = "scraped"
    except Exception as exc:  # noqa: BLE001
        notes.append(f"ECB calendar scrape failed ({exc}); using the dates scraped on 2026-10-29.")
        ecb, ecb_src = ECB_FALLBACK, "fallback"
    for d in ecb:
        events.append(ev(d, "GLOBAL", "rates", "ECB monetary policy decision", 3, "confirmed", ECB_URL,
                         '"European Central Bank" "interest rates"', note="Day 2 of the meeting, press conference follows.",
                         origin=f"ecb:{ecb_src}"))
    return events


# --------------------------------------------------------------------------
# Recurring releases (generated by rule; all "estimated")
# --------------------------------------------------------------------------


def _prev_business(d: dt.date) -> dt.date:
    while d.weekday() >= 5:
        d -= dt.timedelta(days=1)
    return d


def _next_business(d: dt.date) -> dt.date:
    while d.weekday() >= 5:
        d += dt.timedelta(days=1)
    return d


def recurring(start: dt.date, end: dt.date) -> list[dict]:
    out = []
    d = start + dt.timedelta(days=(7 - start.weekday()) % 7)  # next Monday (or today)
    while d <= end:
        out.append(ev(d, "BR", "survey", "Focus survey (BCB)", 1, "estimated",
                      "https://www.bcb.gov.br/publicacoes/focus", '"Focus survey" Brazil',
                      note="Published Mondays ~08:25 BRT; moves to the next business day on holidays.", origin="rule:focus"))
        d += dt.timedelta(days=7)
    y, m = start.year, start.month
    while dt.date(y, m, 1) <= end:
        first = _next_business(dt.date(y, m, 1))
        if start <= first <= end:
            out.append(ev(first, "MX", "survey", "Banxico survey of private-sector economists", 1, "estimated",
                          "https://www.banxico.org.mx/publicaciones-y-prensa/encuestas-sobre-las-expectativas-de-los-especialistas-en-economia-del-sector-privado/",
                          "Banxico survey analysts", note="Usually the first business day of the month at 12:00 CDMX; holidays not adjusted.",
                          origin="rule:banxico_survey"))
        if m in (3, 5, 7, 9, 11):
            rep = _prev_business(dt.date(y, m, 22))
            if start <= rep <= end:
                out.append(ev(rep, "BR", "fiscal", "Bimonthly revenue and spending report (RARDP)", 2, "estimated",
                              "https://www.gov.br/planejamento/pt-br/assuntos/orcamento/relatorios-de-avaliacao",
                              'Brazil "primary deficit"', note="Due by the 22nd after each bimester (LRF art. 9); earlier business day when the 22nd is a weekend.",
                              origin="rule:rardp"))
        m += 1
        if m == 13:
            y, m = y + 1, 1
    return out


# --------------------------------------------------------------------------
# em-macro import (past events)
# --------------------------------------------------------------------------


def _em_macro_csv(path: str) -> list[dict]:
    local = os.environ.get("EM_MACRO_DIR")
    if local and (Path(local) / path).exists():
        text = (Path(local) / path).read_text()
    else:
        text = get(EM_MACRO_RAW + path, timeout=60).text
    return list(csv.DictReader(io.StringIO(text)))


def em_macro_events(notes: list[str]) -> list[dict]:
    out = []
    code = {"Brazil": "BR", "Mexico": "MX"}
    try:
        for r in _em_macro_csv("data/events/rate_decisions.csv"):
            if r["country"] not in code:
                continue
            bp = r.get("change_bp") or ""
            title = f"{r.get('policy_rate_name') or 'Policy rate'}: {r.get('decision', '')} {bp}bp to {r.get('rate_after_pct', '')}%"
            out.append(ev(r["announce_date"], code[r["country"]], "rates", title, 3, "past",
                          r.get("source") or EM_MACRO_RAW + "data/events/rate_decisions.csv", "",
                          origin="em-macro:rate_decisions", change_bp=r.get("change_bp"), expected_change_bp=r.get("expected_change_bp"),
                          scheduled=r.get("scheduled")))
        for r in _em_macro_csv("data/events/elections.csv"):
            if r["country"] not in code:
                continue
            out.append(ev(r["vote_date"], code[r["country"]], "election", f"{r['election']} (round {r.get('round', '')})", 3, "past",
                          r.get("actual_source") or EM_MACRO_RAW + "data/events/elections.csv", "", origin="em-macro:elections",
                          winner=r.get("winner"), poll_margin_pp=r.get("poll_margin_pp"), actual_margin_pp=r.get("actual_margin_pp")))
    except Exception as exc:  # noqa: BLE001
        notes.append(f"em-macro import failed: {exc}")
    return out


# --------------------------------------------------------------------------
# GDELT attention
# --------------------------------------------------------------------------

_last_call = 0.0


def gdelt_share(query: str, days: int = 30, base_days: int = 365, tries: int = 4) -> tuple[float, float, float | None]:
    """(matching articles over the last ``days``, all monitored articles over the same window,
    share over the last ``base_days``). Same request pattern as tension-index: timelinevolraw,
    one call every 6 seconds, back-off on the rate-limit notice."""
    global _last_call
    end = dt.datetime.now(dt.timezone.utc)
    params = {"query": query, "mode": "timelinevolraw", "format": "json",
              "startdatetime": (end - dt.timedelta(days=base_days)).strftime("%Y%m%d%H%M%S"),
              "enddatetime": end.strftime("%Y%m%d%H%M%S")}
    cut = (end - dt.timedelta(days=days)).strftime("%Y%m%d")
    delay = 10.0
    for _ in range(tries):
        wait = 6.0 - (time.monotonic() - _last_call)
        if wait > 0:
            time.sleep(wait)
        r = requests.get(GDELT, params=params, timeout=30)
        _last_call = time.monotonic()
        text = r.text
        if text.lstrip().startswith("{"):
            series = json.loads(text).get("timeline", [])
            rows = series[0]["data"] if series else []
            recent = [x for x in rows if str(x.get("date", ""))[:8] >= cut]
            v30, n30 = float(sum(x.get("value", 0) for x in recent)), float(sum(x.get("norm", 0) for x in recent))
            v_all, n_all = float(sum(x.get("value", 0) for x in rows)), float(sum(x.get("norm", 0) for x in rows))
            return v30, n30, (v_all / n_all) if n_all else None
        if r.status_code == 429 or "limit requests" in text:
            time.sleep(delay)
            delay = min(delay * 1.6, 90)
            continue
        raise RuntimeError(f"GDELT {r.status_code}: {text[:200]}")
    raise RuntimeError("GDELT kept returning its rate-limit notice")


def refresh_attention(events: list[dict], notes: list[str], do_fetch: bool = True) -> dict:
    att = json.loads(ATT_PATH.read_text()) if ATT_PATH.exists() else {"queries": {}}
    queries = {}
    for e in events:
        if e["query"]:
            queries.setdefault(e["query"], e["country"])
    today = store.today()
    failures = successes = 0
    deadline = time.monotonic() + 540  # the whole refresh gets nine minutes
    if do_fetch:
        for q, country in queries.items():
            if time.monotonic() > deadline:
                notes.append("GDELT attention refresh stopped at its 9-minute budget; remaining queries keep their last values.")
                break
            rec = att["queries"].setdefault(q, {"country": country, "history": []})
            rec["country"] = country
            if rec["history"] and rec["history"][-1][0] == today:
                continue
            try:
                v, n, base = gdelt_share(q)
                rec["history"].append([today, v, n, (v / n) if n else None, base])
                rec["last_success"] = store.now_iso()
                rec.pop("error", None)
                successes += 1
            except Exception as exc:  # noqa: BLE001  (includes timeouts)
                rec["error"] = f"{type(exc).__name__}: {exc}"[:200]
                failures += 1
                if failures >= 2 and not successes:
                    notes.append(f"GDELT attention not refreshed today ({exc}); showing the last values.")
                    break
    att["updated_at"] = store.now_iso()
    att["definition"] = ("score = share of GDELT-monitored articles matching the event's keywords over the last 30 days / "
                         "the same share over the last 12 months (1.0 = normal coverage); under-attended = importance 3, "
                         "score < 0.5, 30+ days away")
    ATT_PATH.write_text(json.dumps(att, ensure_ascii=False, indent=1) + "\n")
    return att


def score_events(events: list[dict], att: dict) -> None:
    latest = {}
    for q, rec in att.get("queries", {}).items():
        h = [r for r in rec.get("history", []) if len(r) >= 5 and r[3] is not None and r[4]]
        if h:
            latest[q] = h[-1]
    today = dt.date.today()
    for e in events:
        r = latest.get(e["query"])
        if r:
            e["attention"] = {"score": round(r[3] / r[4], 3), "share_30d": r[3], "share_12m": r[4], "as_of": r[0],
                              "source": "GDELT DOC 2.0 (timelinevolraw)", "query": e["query"]}
        else:
            e["attention"] = None
        days = (dt.date.fromisoformat(e["date"]) - today).days
        e["under_attended"] = bool(e["importance"] == 3 and e["attention"] and e["attention"]["score"] < UNDER_ATTENDED_SCORE
                                   and days >= UNDER_ATTENDED_DAYS)


# --------------------------------------------------------------------------
# Build
# --------------------------------------------------------------------------


def rating_reviews(notes: list[str]) -> list[dict]:
    """France rating reviews from the AFT table's 'next review' column (when it has been fetched)."""
    s = store.load_series("fr.ratings.aft")
    if not s or not s.get("history"):
        return []
    last = s["history"][-1][0]
    out = []
    for r in (x for x in s["history"] if x[0] == last):
        agency, cells = r[1], r[2] or []
        nxt = cells[3] if len(cells) > 3 else None
        try:
            d = dt.datetime.strptime(nxt, "%d %B %Y").date()
        except (TypeError, ValueError):
            continue
        out.append(ev(d, "FR", "ratings", f"{agency} sovereign rating review: France", 3, "confirmed", s["source_url"],
                      f'"{agency.split()[0]}" France rating', note=f"Next review date from the AFT ratings table (fetched {last}).",
                      origin="aft"))
    return out


AGENCIES = [("s&p", "S&P"), ("standard & poor", "S&P"), ("standard and poor", "S&P"), ("moody", "Moody's"), ("fitch", "Fitch"),
            ("dbrs", "DBRS"), ("morningstar", "DBRS"), ("kbra", "KBRA"), ("kroll", "KBRA"), ("scope", "Scope")]


def rating_key(e: dict) -> tuple | None:
    """(country, agency, date) for a rating-review event, with agency names normalised, else None."""
    if e.get("type") != "ratings":
        return None
    t = e["title"].lower()
    agency = next((name for k, name in AGENCIES if k in t), None)
    return (e["country"], agency, e["date"]) if agency else None


def dedupe_ratings(events: list[dict]) -> list[dict]:
    """One event per (country, agency, date): the AFT-sourced one wins over a hand-entered duplicate."""
    best: dict[tuple, dict] = {}
    for e in events:
        k = rating_key(e)
        if k and (k not in best or (e.get("origin") == "aft" and best[k].get("origin") != "aft")):
            best[k] = e
    return [e for e in events if (k := rating_key(e)) is None or best[k] is e]


BANK = {"BR": "Copom", "MX": "Banxico"}


def add_base_rates(events: list[dict], past: list[dict], n: int = 24) -> None:
    """Base rate for rate decisions from em-macro's history: how often the last n scheduled decisions
    changed the rate. Pre-fills the Full call form."""
    for c, bank in BANK.items():
        hist = [e for e in past if e["country"] == c and e["type"] == "rates" and str(e.get("scheduled", "Y")).upper().startswith("Y")]
        hist = sorted(hist, key=lambda e: e["date"])[-n:]
        if len(hist) < 8:
            continue
        changed = [e for e in hist if e.get("change_bp") not in (None, "", "0", "0.0") and float(e["change_bp"] or 0) != 0]
        cuts = sum(float(e["change_bp"]) < 0 for e in changed)
        last = hist[-1]
        text = (f"{bank} changed the rate at {len(changed)} of its last {len(hist)} scheduled decisions "
                f"({cuts} cuts, {len(changed) - cuts} hikes) since {hist[0]['date']}; last: {last['title']} on {last['date']} (em-macro)")
        for e in events:
            if e["country"] == c and e["type"] == "rates":
                e["base_rate"] = {"text": text, "changed": len(changed), "of": len(hist)}


def build(attention: bool = True) -> dict:
    notes: list[str] = []
    cfg = yaml.safe_load(EVENTS_YAML.read_text())
    today = dt.date.today()
    horizon = today + dt.timedelta(days=366)
    manual = [ev(e["date"], e["country"], e["type"], e["title"], e["importance"], e["status"], e.get("source", ""),
                 e.get("query", ""), e.get("note", "")) for e in cfg.get("events", [])]
    events = manual + official_meetings(notes) + rating_reviews(notes) + recurring(today, horizon)
    events = dedupe_ratings(events)
    seen, future = set(), []
    for e in sorted(events, key=lambda e: (e["date"], e["country"], -e["importance"])):
        if e["id"] in seen or not (today.isoformat() <= e["date"] <= horizon.isoformat()):
            continue
        seen.add(e["id"])
        future.append(e)
    att = refresh_attention(future, notes, do_fetch=attention)
    score_events(future, att)
    past = em_macro_events(notes)
    add_base_rates(future, past)
    cal = {"generated_at": store.now_iso(), "horizon": horizon.isoformat(), "events": future,
           "past_events": sorted(past, key=lambda e: e["date"]), "notes": cfg.get("notes", []) + notes,
           "attention_definition": att.get("definition"),
           "sources": {"manual": str(EVENTS_YAML.relative_to(store.ROOT)), "fomc": FED_URL, "ecb": ECB_URL,
                       "em_macro": EM_MACRO_RAW + "data/events/", "attention": GDELT}}
    CAL_PATH.write_text(json.dumps(cal, ensure_ascii=False, indent=1) + "\n")
    # record the calendar build like a source on the status page
    status = store.load_status()
    errs = [n for n in notes if "failed" in n or "not refreshed" in n]
    partial = [n for n in notes if "budget" in n]
    state = "error" if errs else ("partial" if partial else "ok")
    status.setdefault("sources", {})["calendar"] = {
        "name": "Catalyst calendar (events.yaml, Fed, ECB, em-macro, GDELT)", "country": "GLOBAL", "secret": None,
        "fallback_for": None, "release": "daily", "last_attempt": store.now_iso(),
        "state": state, "error": " | ".join(errs + partial) or None,
        "last_success": store.now_iso() if not errs else status.get("sources", {}).get("calendar", {}).get("last_success"),
        "series": ["calendar.json", "attention.json"], "n_series": len(future)}
    store.save_status(status)
    log.info("calendar: %d upcoming, %d past events; %d notes", len(future), len(past), len(notes))
    return cal
