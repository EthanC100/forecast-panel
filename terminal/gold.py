"""Gold page data: data/terminal/gold.json, rebuilt in the summary step.

    prices     gold and silver (daily: Yahoo COMEX front-month futures, else Stooq or LBMA spot; the World Bank's monthly average when no
               daily price is stored), with 1-week, 1-month and 1-year changes and a 1-year z-score
    drivers    real interest rates (US 10-year TIPS), the dollar (broad index), war and political tension
               (Geopolitical Risk index) and central-bank buying (IMF reporters), each with a plain reading
    model      the frozen gold model's latest weekly expected move from EthanC100/gold-events
    episodes   past episodes (data/terminal/inputs/gold_episodes.yaml) with moves computed from the series
    upcoming   US political events and FOMC meetings in the next 120 days

Every number comes from a stored series or a fetched file, with its source.
"""

from __future__ import annotations

import csv
import datetime as dt
import io
import json
import logging
import math
import re

import yaml

from terminal import store
from terminal.http import get

log = logging.getLogger(__name__)

OUT = store.DATA / "gold.json"
EPISODES = store.INPUTS / "gold_episodes.yaml"
GE_RAW = "https://raw.githubusercontent.com/EthanC100/gold-events/main/"
GE_REPO = "https://github.com/EthanC100/gold-events"
UPCOMING_DAYS = 120


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------

def _obs(sid: str) -> tuple[list[tuple[str, float]], dict]:
    s = store.load_series(sid) or {}
    return [(r[0], float(r[1])) for r in s.get("history", []) if isinstance(r[1], (int, float))], s


def _on_or_before(obs, date: str):
    last = None
    for d, v in obs:
        if d > date:
            break
        last = (d, v)
    return last


def _on_or_after(obs, date: str):
    return next(((d, v) for d, v in obs if d >= date), None)


def _shift(date: str, days: int) -> str:
    return (dt.date.fromisoformat(date) + dt.timedelta(days=days)).isoformat()


def _pct(a, b):
    return None if a is None or b is None or a == 0 else round(100 * (b / a - 1), 2)


def _r(x, n=2):
    return None if x is None else round(x, n)


def _meta(s: dict) -> dict:
    return {"series": s.get("id"), "source": s.get("source"), "source_id": s.get("source_id"), "url": s.get("source_url"),
            "frequency": s.get("frequency")}


# --------------------------------------------------------------------------
# prices
# --------------------------------------------------------------------------

def price_block(daily: str, monthly: str) -> dict | None:
    obs, s = _obs(daily)
    degraded = None
    if not obs:
        obs, s = _obs(monthly)
        degraded = "No daily price is stored (Yahoo, Stooq and LBMA unreachable), so this is the World Bank's monthly average."
    if not obs:
        return None
    d, v = obs[-1]
    out = {"value": v, "date": d, **_meta(s), "degraded": degraded, "unit": s.get("unit")}
    for key, days in (("chg_1w_pct", 7), ("chg_1m_pct", 30), ("chg_1y_pct", 365)):
        if s.get("frequency") == "monthly" and days < 30:
            out[key] = None                                   # a monthly average has no weekly change
            continue
        p = _on_or_before(obs, _shift(d, -days))
        out[key] = _pct(p[1], v) if p and p[0] < d else None
    year = [x for t, x in obs if t > _shift(d, -365)]
    if len(year) >= 10:
        m = sum(year) / len(year)
        sd = math.sqrt(sum((x - m) ** 2 for x in year) / (len(year) - 1))
        out["z_1y"] = _r((v - m) / sd) if sd > 0 else None
        out["high_1y"], out["low_1y"] = max(year), min(year)
    else:
        out["z_1y"] = None
    out["history_from"] = obs[0][0]
    return out


# --------------------------------------------------------------------------
# drivers
# --------------------------------------------------------------------------

def _change(obs, days: int):
    if not obs:
        return None, None
    d, v = obs[-1]
    p = _on_or_before(obs, _shift(d, -days))
    return (p[1] if p and p[0] < d else None), v


def drivers() -> list[dict]:
    out = []
    # real yields
    obs, s = _obs("us.tips10")
    if obs:
        prev, v = _change(obs, 30)
        ch = None if prev is None else round((v - prev) * 100)
        trend = ("up" if ch > 0 else "down" if ch < 0 else "unchanged") if ch is not None else None
        out.append({"id": "real_yield", "name": "Real interest rates (US 10-year TIPS yield)", "value": v, "date": obs[-1][0],
                    "unit": "%", "chg_1m": ch, "chg_unit": "bp", **_meta(s),
                    "reading": (f"The 10-year real yield is {v:.2f}%, {trend}" + (f" {abs(ch)}bp over the past month" if ch else "") + ". "
                                "Gold pays no interest, so a higher real yield raises the cost of holding it: rising real yields "
                                "are a headwind for gold and falling ones a tailwind. gold-events finds the link is not stable: gold's "
                                "sensitivity to real yields was near zero before 2013, strong in 2014-2021 and weaker now."),
                    "finding_url": GE_REPO + "#findings"})
    # dollar
    obs, s = _obs("us.usd.broad")
    if obs:
        prev, v = _change(obs, 30)
        ch = _pct(prev, v)
        out.append({"id": "dollar", "name": "The US dollar (broad trade-weighted index)", "value": v, "date": obs[-1][0],
                    "unit": s.get("unit"), "chg_1m": ch, "chg_unit": "%", **_meta(s),
                    "reading": ("The dollar index is " + (f"{'up' if ch > 0 else 'down'} {abs(ch):.1f}%" if ch else "flat") +
                                " over the past month. Gold is priced in dollars, so a weaker dollar makes it cheaper for "
                                "buyers paying in other currencies and tends to lift its dollar price; a stronger dollar does the reverse.")})
    # geopolitical risk
    obs, s = _obs("gl.gpr")
    if obs:
        d, v = obs[-1]
        recent = [x for t, x in obs if t > _shift(d, -7)]
        avg7 = sum(recent) / len(recent)
        ten = sorted(x for t, x in obs if t > _shift(d, -3650))
        pctile = round(100 * sum(1 for x in ten if x <= avg7) / len(ten)) if ten else None
        prev = [x for t, x in obs if _shift(d, -37) < t <= _shift(d, -30)]
        ch = round(avg7 - sum(prev) / len(prev), 1) if prev else None
        out.append({"id": "gpr", "name": "War and political tension (Geopolitical Risk index)", "value": round(avg7, 1), "date": d,
                    "unit": "7-day average; 100 = the 1985-2019 average", "chg_1m": ch, "chg_unit": "points", "percentile_10y": pctile, **_meta(s),
                    "reading": (f"The index averaged {avg7:.0f} over the past week (100 is the 1985-2019 average), higher than "
                                f"{pctile}% of days in the past ten years. Gold often gains when tension spikes because investors "
                                "buy it as a store of value outside the financial system. gold-events finds the index helps explain gold's "
                                "weekly moves alongside real yields and the dollar, and that its effect has grown since 2020."),
                    "finding_url": GE_REPO + "#findings"})
    # central-bank buying
    obs, s = _obs("gl.cbgold")
    if obs:
        d, v = obs[-1]
        last12 = [x for t, x in obs if t > _shift(d, -365)]
        prev12 = [x for t, x in obs if _shift(d, -730) < t <= _shift(d, -365)]
        out.append({"id": "cb_buying", "name": "Central-bank gold buying (IMF reporters)", "value": v, "date": d, "unit": "tonnes in the month",
                    "last_12m_tonnes": round(sum(last12), 1), "prior_12m_tonnes": round(sum(prev12), 1) if prev12 else None,
                    "chg_1m": None, "chg_unit": None, **_meta(s),
                    "reading": (f"Central banks reporting to the IMF added {sum(last12):,.0f} tonnes in the 12 months to {d[:7]}"
                                + (f", against {sum(prev12):,.0f} tonnes in the 12 months before" if prev12 else "") + ". "
                                "Official buying is demand that does not depend on interest rates; gold-events finds last month's buying "
                                "does not help predict next week's move, so read it as background, not a timing signal. "
                                "The latest months are incomplete until every reporter files, so they understate buying."),
                    "finding_url": GE_REPO + "#findings"})
    return out


# --------------------------------------------------------------------------
# frozen model (gold-events)
# --------------------------------------------------------------------------

def _f(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def _logpct(x):
    return None if x is None else round(100 * (math.exp(x) - 1), 2)


def parse_forward_log(text: str) -> list[dict]:
    rows = list(csv.DictReader(io.StringIO(text)))
    out = []
    for r in rows:
        if not r.get("log_date"):
            continue
        out.append({"log_date": r["log_date"], "version": r.get("model_version"), "data_as_of": r.get("data_as_of"),
                    "pred_gold_5d_pct": _logpct(_f(r.get("pred_gold_5d"))), "pred_silver_5d_pct": _logpct(_f(r.get("pred_silver_5d"))),
                    "realised_gold_5d_pct": _logpct(_f(r.get("realised_gold_5d"))),
                    "realised_silver_5d_pct": _logpct(_f(r.get("realised_silver_5d"))),
                    "gpr_level": _r(_f(r.get("gpr_level")), 1), "note": r.get("note") or None})
    return out


def model(fetch=None) -> dict:
    fetch = fetch or (lambda path: get(GE_RAW + path, timeout=60).text)
    try:
        rows = parse_forward_log(fetch("data/forward_log.csv"))
    except Exception as exc:  # noqa: BLE001
        log.warning("gold-events forward log: %s", exc)
        return {"available": False, "note": f"gold-events forward log not reachable: {exc}"[:300], "source_url": GE_REPO}
    if not rows:
        return {"available": False, "note": "gold-events has not logged a week yet.", "source_url": GE_REPO}
    last = rows[-1]
    done = [r for r in rows if r["realised_gold_5d_pct"] is not None and r["pred_gold_5d_pct"] is not None]
    hits = sum(1 for r in done if (r["realised_gold_5d_pct"] > 0) == (r["pred_gold_5d_pct"] > 0))
    return {"available": True, **{k: last[k] for k in ("log_date", "version", "data_as_of", "pred_gold_5d_pct", "pred_silver_5d_pct")},
            "source_url": GE_REPO + "/blob/main/data/forward_log.csv", "scorecard_url": GE_REPO + "/blob/main/reports/forward_scorecard.md",
            "n_scored": len(done), "direction_hits": hits,
            "note": ("Expected move over the next 5 trading days from the frozen gold-events model "
                     f"({last['version']}): its regression on last week's changes in real yields, the dollar, VIX and the "
                     "Geopolitical Risk index. The model predicts log returns; shown here as percentage changes. "
                     f"Out of sample it has been scored on {len(done)} week{'s' if len(done) != 1 else ''} so far."),
            "recent": rows[-8:]}


def midterm_study(fetch=None) -> dict | None:
    """The 'All midterms' averages for gold from gold-events' reports/midterms.md."""
    fetch = fetch or (lambda path: get(GE_RAW + path, timeout=60).text)
    try:
        text = fetch("reports/midterms.md")
    except Exception as exc:  # noqa: BLE001
        log.warning("gold-events midterms report: %s", exc)
        return None
    gold = text.split("## Gold", 1)[-1].split("## Silver", 1)[0]
    m = re.search(r"\|\s*All midterms\s*\|\s*(\d+)\s*\|([^\n]+)", gold)
    if not m:
        return None
    cells = [c.strip() for c in m.group(2).strip().strip("|").split("|")]
    names = ["raw_1d", "net_1d", "raw_5d", "net_5d", "raw_20d", "net_20d"]
    vals = {n: _f(c.replace("%", "").replace("+", "")) for n, c in zip(names, cells)}
    return {"n": int(m.group(1)), **vals, "unit": "% (log returns)", "url": GE_REPO + "/blob/main/reports/midterms.md",
            "note": "Average gold move after every US midterm since 2002 (1994 and 1998 lack data); net = after removing "
                    "the part explained by the dollar and real yields over the same days. gold-events' verdict: one or two years "
                    "drive the averages, so there is no reliable midterm effect."}


# --------------------------------------------------------------------------
# episodes
# --------------------------------------------------------------------------

def _move(daily: str, monthly: str, start: str, days: int) -> tuple[float | None, str | None]:
    """% change from the last close before `start` to `days` later; monthly averages when no daily series covers it."""
    obs, _ = _obs(daily)
    if obs and obs[0][0] < start:
        a, b = _on_or_before(obs, _shift(start, -1)), _on_or_before(obs, _shift(start, days))
        if a and b and b[0] > a[0] and b[0] >= _shift(start, days - 7):
            return _pct(a[1], b[1]), "daily"
    obs, _ = _obs(monthly)
    if obs and obs[0][0] < start:
        a = _on_or_before(obs, _shift(start, -1))                          # the month before the episode
        b = _on_or_after(obs, _shift(start, days))
        if a and b:
            return _pct(a[1], b[1]), "monthly averages"
    return None, None


def _level_change(sid: str, start: str, days: int, scale: float = 1.0):
    obs, _ = _obs(sid)
    if not obs or obs[0][0] >= start:
        return None
    a, b = _on_or_before(obs, _shift(start, -1)), _on_or_before(obs, _shift(start, days))
    if not a or not b or b[0] <= a[0] or b[0] < _shift(start, days - 7):
        return None
    return round((b[1] - a[1]) * scale, 1)


def episodes(today: str) -> list[dict]:
    spec = yaml.safe_load(EPISODES.read_text()) if EPISODES.exists() else {}
    out = []
    for e in spec.get("episodes", []):
        start = str(e["start"])
        moves, basis = {}, set()
        for label, days in (("1m", 30), ("6m", 182), ("24m", 730)):
            if _shift(start, days) > today:
                moves[f"gold_pct_{label}"] = moves[f"silver_pct_{label}"] = None
                continue
            g, gb = _move("gl.gold", "gl.gold.wb_m", start, days)
            sv, sb = _move("gl.silver", "gl.silver.wb_m", start, days)
            moves[f"gold_pct_{label}"], moves[f"silver_pct_{label}"] = g, sv
            basis |= {x for x in (gb, sb) if x}
        moves["real_yield_bp_6m"] = _level_change("us.tips10", start, 182, 100) if _shift(start, 182) <= today else None
        obs, _ = _obs("us.usd.broad")
        a = _on_or_before(obs, _shift(start, -1)) if obs and obs[0][0] < start else None
        b = _on_or_before(obs, _shift(start, 182)) if a and _shift(start, 182) <= today else None
        moves["dollar_pct_6m"] = _pct(a[1], b[1]) if a and b else None
        cb = None
        obs, _ = _obs("gl.cbgold")
        if obs and obs[0][0] < start and _shift(start, 365) <= today:
            cb = round(sum(v for d, v in obs if start <= d < _shift(start, 365)), 1)
        moves["cb_tonnes_12m"] = cb
        out.append({"id": e["id"], "name": e["name"], "start": start, "summary": e["summary"], "cites": e.get("cites", []),
                    "moves": moves, "basis": " and ".join(sorted(basis)) or None,
                    "note": "Moves are measured from the last price before the start date. They show what followed, not what caused it."})
    return out


# --------------------------------------------------------------------------
# upcoming events
# --------------------------------------------------------------------------

FOMC_WATCH = ("The rate decision and the statement. A cut, or a signal that cuts are coming, tends to lower real yields "
              "and weaken the dollar, which supports gold; a hawkish surprise does the opposite.")


def upcoming(today: str, study: dict | None) -> list[dict]:
    spec = yaml.safe_load(EPISODES.read_text()) if EPISODES.exists() else {}
    end = _shift(today, UPCOMING_DAYS)
    out = []
    for p in spec.get("political", []):
        d = str(p["date"])
        if today <= d <= end:
            row = {"date": d, "title": p["title"], "kind": "election", "importance": p.get("importance", 2), "summary": p.get("summary"),
                   "what_to_watch": p.get("what_to_watch"), "source_url": p.get("source_url")}
            if "midterm" in p["title"].lower() and study:
                row["study"] = study
            out.append(row)
    s = store.load_series("us.fomc.meetings") or {}
    for r in s.get("history", []):
        if today <= r[0] <= end:
            sep = bool(r[2]) if len(r) > 2 else False
            out.append({"date": r[0], "first_day": r[1] if len(r) > 1 else None, "title": "FOMC rate decision" + (" and projections" if sep else ""),
                        "kind": "fed", "importance": 3 if sep else 2,
                        "what_to_watch": FOMC_WATCH + (" This meeting also publishes the Fed's economic projections, "
                                                      "including the 'dot plot' of expected rates." if sep else ""),
                        "source_url": s.get("source_url")})
    return sorted(out, key=lambda x: x["date"])


# --------------------------------------------------------------------------
# build
# --------------------------------------------------------------------------

def build(today: str | None = None, fetch=None) -> dict:
    today = today or store.today()
    gold = price_block("gl.gold", "gl.gold.wb_m")
    silver = price_block("gl.silver", "gl.silver.wb_m")
    ratio = None
    if gold and silver and silver["value"] and not gold.get("degraded") and not silver.get("degraded"):
        ratio = {"value": round(gold["value"] / silver["value"], 1), "date": min(gold["date"], silver["date"]),
                 "meaning": "Ounces of silver one ounce of gold buys. It rises when investors prefer gold's safety to silver's industrial demand."}
    study = midterm_study(fetch)
    out = {"generated_at": store.now_iso(), "as_of": today,
           "prices": {"gold": gold, "silver": silver, "ratio": ratio},
           "drivers": drivers(), "model": model(fetch), "episodes": episodes(today), "upcoming": upcoming(today, study),
           "not_included": ["US CPI and jobs-report dates: the BLS release calendar refuses automated requests (HTTP 403)."]}
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n")
    return out
