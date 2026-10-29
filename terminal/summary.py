"""Build data/terminal/summary.json, the single file the terminal site reads first.

Every number carries `meta`: source, source_id, source_url, as_of (the observation date),
fetched_at, and an evidence badge from inputs/evidence.yaml. Freshness (green < 1 day, amber
< 1 week, red older) is computed in the browser from `as_of`, so it is right at view time.
"""

from __future__ import annotations

import datetime as dt
import json
import math
import statistics

import yaml

from terminal import store

SUMMARY_PATH = store.DATA / "summary.json"

TILES = [
    # key, label, candidate series (first that exists wins), change unit, country, decimals
    ("usdbrl", "USD/BRL", ["br.usdbrl.ptax"], "pct", "BR", 4),
    ("usdmxn", "USD/MXN", ["mx.usdmxn.fix"], "pct", "MX", 4),
    ("di27", "Brazil DI Jan-27", ["br.di.f27", "br.di.f27.proxy"], "bp", "BR", 2),
    ("di29", "Brazil DI Jan-29", ["br.di.f29", "br.di.f29.proxy"], "bp", "BR", 2),
    ("di31", "Brazil DI Jan-31", ["br.di.f31", "br.di.f31.proxy"], "bp", "BR", 2),
    ("br10y", "Brazil 10-year proxy", ["br.td.pre_longest"], "bp", "BR", 2),
    ("oatbund", "France OAT-Bund spread", ["fr.spread.oat_bund", "fr.spread.oat_bund.ecb_m"], "diff", "FR", 1),
    ("us10y", "US 10-year", ["us.ust10y"], "bp", "US", 2),
    ("mx10y", "Mexico 10-year (context)", ["mx.mbono10y.auction", "mx.10y.oecd_m"], "bp", "MX", 2),
]
SOURCE_OF_SERIES = {"br.di": "b3_di", "fr.spread.oat_bund": "webstat", "mx.": "banxico_api", "br.td": "tesouro",
                    "br.usdbrl": "bcb_sgs", "us.": "fred_api"}

COUNTRIES = {
    "FR": {"name": "France", "charts": [["fr.spread.oat_bund", "fr.spread.oat_bund.ecb_m"], ["fr.oat10y", "fr.oat10y.ecb_m"],
                                         ["de.bund10y"]], "survey": [], "cot": None},
    "BR": {"name": "Brazil", "charts": [["br.usdbrl.ptax"], ["br.di.f27", "br.di.f27.proxy"], ["br.di.f29", "br.di.f29.proxy"],
                                        ["br.di.f31", "br.di.f31.proxy"], ["br.td.pre_longest"],
                                        ["br.td.ipca_longest"], ["br.selic.target"]],
           "survey": [("br.focus.ipca", "IPCA inflation"), ("br.focus.selic", "Selic, year end"), ("br.focus.brl", "USD/BRL, year end"),
                      ("br.focus.gdp", "GDP growth"), ("br.focus.primary", "Primary balance, % GDP")], "cot": "br.cot.brl"},
    "MX": {"name": "Mexico", "charts": [["mx.usdmxn.fix"], ["mx.policy.target"], ["mx.tiie28"], ["mx.mbono10y.auction", "mx.10y.oecd_m"]],
           "survey": [("mx.survey.inflation", "Headline inflation, year end"), ("mx.survey.gdp", "GDP growth"),
                      ("mx.survey.usdmxn", "USD/MXN, year end"), ("mx.survey.balance", "Public balance, % GDP")], "cot": "mx.cot.mxn"},
}


def _yaml(name: str) -> dict:
    p = store.INPUTS / f"{name}.yaml"
    return yaml.safe_load(p.read_text()) if p.exists() else {}


EVIDENCE = None


def evidence(key: str) -> dict:
    global EVIDENCE
    if EVIDENCE is None:
        EVIDENCE = _yaml("evidence")
    table = EVIDENCE.get("series", {})
    if key in table:
        return table[key]
    best = max((k for k in table if key.startswith(k)), key=len, default=None)
    return table[best] if best else EVIDENCE.get("default", {"badge": "untested", "reason": ""})


def meta_of(s: dict, as_of: str | None = None, **extra) -> dict:
    m = {"source": s.get("source"), "source_id": s.get("source_id"), "source_url": s.get("source_url"),
         "as_of": as_of or s.get("last"), "fetched_at": s.get("fetched_at"), "frequency": s.get("frequency"),
         "series": s.get("id"), "evidence": evidence(s.get("id", ""))}
    m.update(extra)
    return m


def first_series(ids: list[str]) -> tuple[dict | None, bool]:
    for i, sid in enumerate(ids):
        s = store.load_series(sid)
        if s and s.get("history"):
            return s, i > 0
    return None, False


def values(s: dict) -> list[tuple[str, float]]:
    return [(r[0], r[1]) for r in s["history"] if r[1] is not None and isinstance(r[1], (int, float))]


def _before(obs: list[tuple[str, float]], date: dt.date, tolerance_days: int):
    prior = [o for o in obs if o[0] <= date.isoformat()]
    if not prior:
        return None
    d, v = prior[-1]
    return (d, v) if (date - dt.date.fromisoformat(d)).days <= tolerance_days else None


def change(level: float, prev, unit: str):
    if prev is None or prev[1] in (None, 0):
        return None
    if unit == "pct":
        return round(100 * (level / prev[1] - 1), 3)
    if unit == "bp":
        return round(100 * (level - prev[1]), 1)
    return round(level - prev[1], 1)


def stats(s: dict, unit: str) -> dict:
    obs = values(s)
    d_last, level = obs[-1]
    last = dt.date.fromisoformat(d_last)
    w = _before(obs, last - dt.timedelta(days=7), 5)
    m = _before(obs, last - dt.timedelta(days=30), 12)
    year = [v for d, v in obs if d > (last - dt.timedelta(days=365)).isoformat()]
    z = None
    if len(year) >= 10:
        sd = statistics.pstdev(year)
        z = round((level - statistics.fmean(year)) / sd, 2) if sd > 0 else None
    return {"level": level, "as_of": d_last, "chg_1w": change(level, w, unit), "chg_1m": change(level, m, unit),
            "chg_1w_from": w[0] if w else None, "chg_1m_from": m[0] if m else None, "z_1y": z, "n_1y": len(year)}


def tiles(status: dict) -> list[dict]:
    out = []
    for key, label, ids, unit, country, dec in TILES:
        s, fallback = first_series(ids)
        t = {"key": key, "label": label, "country": country, "unit_change": unit, "decimals": dec, "series_candidates": ids}
        if not s:
            src = next((v for k, v in SOURCE_OF_SERIES.items() if ids[0].startswith(k)), None)
            st = status.get("sources", {}).get(src or "", {})
            t.update({"missing": True, "reason": short_error(st.get("error")), "source_key": src,
                      "meta": {"source": st.get("name"), "evidence": evidence(ids[0]), "as_of": None}})
            out.append(t)
            continue
        t.update(stats(s, unit))
        t["unit"] = s.get("unit")
        note = None
        if s.get("proxy"):
            t["label"] = label + " (proxy)"
            t["proxy"] = True
            note = s.get("proxy_note")
        elif fallback:
            note = f"fallback: {s['name']} ({s.get('frequency')}); the preferred daily series is not available"
        if s["id"] == "br.td.pre_longest":
            note = f"bond used: {s['history'][-1][3]} maturing {s['history'][-1][2]}"
        t["meta"] = meta_of(s, t["as_of"], note=note)
        out.append(t)
    return out


def latest_by_ref(s: dict) -> tuple[str | None, dict]:
    """For a survey table keyed (date, ref): the latest survey date and {ref: row} on it."""
    if not s or not s.get("history"):
        return None, {}
    last = s["history"][-1][0]
    return last, {r[1]: r for r in s["history"] if r[0] == last}


def dispersion_percentile(s: dict, field: str, horizon: int, current: float, years: int = 10) -> float | None:
    """Percentile of `current` dispersion among past readings at the same horizon (ref year - survey year)."""
    fi = s["fields"].index(field) + 2
    cutoff = (dt.date.fromisoformat(s["last"]) - dt.timedelta(days=365 * years)).isoformat()
    hist = [r[fi] for r in s["history"] if r[0] >= cutoff and r[fi] is not None and int(r[1]) - int(r[0][:4]) == horizon]
    if len(hist) < 20 or current is None:
        return None
    return round(100 * sum(1 for x in hist if x <= current) / len(hist), 1)


def survey_block(sid: str, label: str) -> dict | None:
    s = store.load_series(sid)
    date, rows = latest_by_ref(s)
    if not date:
        return None
    year = int(date[:4])
    out = {"label": label, "series": sid, "meta": meta_of(s, date), "unit": s.get("unit"), "rows": []}
    for h in (0, 1):
        r = rows.get(str(year + h))
        if not r:
            continue
        rec = dict(zip(s["fields"], r[2:]))
        out["rows"].append({"ref": str(year + h), "median": rec.get("median"), "sd": rec.get("sd"),
                            "respondents": rec.get("respondents"), "min": rec.get("min"), "max": rec.get("max"),
                            "sd_pct_10y": dispersion_percentile(s, "sd", h, rec.get("sd"))})
    return out


def cot_block(sid: str | None) -> dict | None:
    s = store.load_series(sid) if sid else None
    if not s or not s.get("history"):
        return None
    f = s["fields"]
    last = s["history"][-1]
    cutoff = (dt.date.fromisoformat(last[0]) - dt.timedelta(days=3 * 365)).isoformat()
    out = {"series": sid, "meta": meta_of(s, last[0]), "as_of": last[0], "rows": []}
    for name, label in (("lev_money_net", "Leveraged funds, net"), ("asset_mgr_net", "Asset managers, net"),
                        ("noncomm_net", "Non-commercial (legacy), net")):
        i = f.index(name) + 1
        cur = last[i]
        hist = [r[i] for r in s["history"] if r[0] >= cutoff and r[i] is not None]
        pct = round(100 * sum(1 for x in hist if x <= cur) / len(hist), 1) if (cur is not None and len(hist) >= 52) else None
        out["rows"].append({"label": label, "value": cur, "pct_3y": pct, "n_3y": len(hist)})
    out["open_interest"] = last[f.index("open_interest") + 1]
    return out


def fiscal_rows(country: str) -> list[dict]:
    out = []
    for row in (_yaml("fiscal_gap").get("countries") or {}).get(country, []) or []:
        indep = []
        for i in row.get("independent", []):
            item = dict(i)
            if i.get("auto"):
                s = store.load_series(i["auto"])
                date, rows = latest_by_ref(s)
                r = rows.get(str(row["year"])) if date else None
                item["value"] = r[2] if r else None
                item["source"] = s.get("source_url") if s else None
                item["as_of"] = date
                item["source_label"] = s.get("source") if s else None
                item["verified"] = True
            indep.append(item)
        vals = [x["value"] for x in indep if isinstance(x.get("value"), (int, float))]
        off = (row.get("official") or {}).get("value")
        gap = round(off - statistics.median(vals), 2) if (off is not None and vals) else None
        out.append({**row, "independent": indep, "gap": gap})
    return out


def ratings_block() -> dict:
    s = store.load_series("fr.ratings.aft")
    if s and s.get("history"):
        last = s["history"][-1][0]
        return {"origin": "aft", "as_of": last, "meta": meta_of(s, last),
                "rows": [{"agency": r[1], "cells": r[2], "dates": r[3]} for r in s["history"] if r[0] == last]}
    y = _yaml("france_ratings")
    return {"origin": "manual", "as_of": str(y.get("as_of")), "source": y.get("source"), "rows": y.get("ratings", []),
            "meta": {"source": "Hand-maintained table (data/terminal/inputs/france_ratings.yaml); AFT page not reachable",
                     "source_url": y.get("source"), "as_of": str(y.get("as_of")), "evidence": evidence("ratings")}}


def markets_block(country: str, n: int = 6) -> list[dict]:
    out = []
    pm = store.DATA / "markets" / "polymarket.json"
    if pm.exists():
        snap = json.loads(pm.read_text())
        ms = [m for m in snap["events"] if m["country"] == country and m.get("yes") is not None]
        for m in sorted(ms, key=lambda m: -m["volume"])[:n]:
            out.append({"venue": "Polymarket", "question": m["question"], "prob": m["yes"], "volume": m["volume"],
                        "end_date": m["end_date"], "url": f"https://polymarket.com/event/{m['event_slug']}",
                        "meta": {"source": "Polymarket Gamma API", "source_id": f"market {m['id']}", "as_of": snap["fetched_at"],
                                 "evidence": evidence("pm.")}})
    ks = store.DATA / "markets" / "kalshi.json"
    if ks.exists():
        snap = json.loads(ks.read_text())
        ms = [m for m in snap["markets"] if m["country"] == country and m.get("last_price") is not None]
        for m in sorted(ms, key=lambda m: -(m.get("volume") or 0))[:n]:
            out.append({"venue": "Kalshi", "question": f"{m['event']}: {m['title']}", "prob": m["last_price"], "volume": m.get("volume"),
                        "end_date": m.get("close_time"), "url": f"https://kalshi.com/markets/{(m.get('series_ticker') or '').lower()}",
                        "meta": {"source": "Kalshi trade API", "source_id": m["ticker"], "as_of": snap["fetched_at"],
                                 "evidence": evidence("ks.")}})
    return out


MISSING_NAMES = {"br.di.f27": "DI1 Jan-27", "br.di.f29": "DI1 Jan-29", "br.di.f31": "DI1 Jan-31",
                 "fr.spread.oat_bund": "France OAT-Bund spread (daily)", "fr.oat10y": "France 10-year OAT (daily)"}


def short_error(err: str | None) -> str:
    """One readable line from a stored exception string (the full text stays on the status page)."""
    if not err:
        return "not fetched yet"
    for pat, msg in (("Read timed out", "source timed out on the last run"), ("403", "source refused the request (HTTP 403)"),
                     ("secret", err), ("Connection", "could not connect to the source")):
        if pat in err:
            return msg
    return err.split(":")[0][:80]


def chart_list(groups: list[list[str]]) -> list[dict]:
    out = []
    for ids in groups:
        s, fallback = first_series(ids)
        if s:
            out.append({"series": s["id"], "name": s["name"], "unit": s.get("unit"), "fallback": fallback and not s.get("proxy"),
                        "proxy": bool(s.get("proxy")), "proxy_note": s.get("proxy_note"), "meta": meta_of(s)})
        else:
            out.append({"series": ids[0], "missing": True, "name": MISSING_NAMES.get(ids[0], ids[0]), "meta": {"evidence": evidence(ids[0])}})
    return out


def build() -> dict:
    status = store.load_status()
    cal = json.loads((store.DATA / "calendar.json").read_text()) if (store.DATA / "calendar.json").exists() else {"events": []}
    today = dt.date.today().isoformat()
    upcoming = [e for e in cal.get("events", []) if e["date"] >= today]
    nxt = [e for e in upcoming if e["importance"] >= 2][:3]
    countries = {}
    for c, cfg in COUNTRIES.items():
        countries[c] = {"name": cfg["name"], "charts": chart_list(cfg["charts"]),
                        "fiscal_gap": fiscal_rows(c),
                        "surveys": [b for b in (survey_block(sid, label) for sid, label in cfg["survey"]) if b],
                        "cot": cot_block(cfg["cot"]), "markets": markets_block(c),
                        "events": [e for e in upcoming if e["country"] == c][:12]}
    countries["FR"]["ratings"] = ratings_block()
    out = {"generated_at": store.now_iso(), "tiles": tiles(status), "next_catalysts": nxt,
           "countries": countries, "status": status,
           "evidence_legend": {"tested_leads": "Tested-leads", "tested_no_lead": "Tested-no-lead",
                               "untested": "Untested", "context": "Context"},
           "evidence_defaults": {k: evidence(k) for k in ("countdown", "attention", "fiscal_gap", "ratings")}}
    SUMMARY_PATH.write_text(json.dumps(out, ensure_ascii=False, indent=1, default=lambda x: None if isinstance(x, float) and math.isnan(x) else str(x)) + "\n")
    return out
