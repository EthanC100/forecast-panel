"""Policy playbook for the Horizons country pages: data/terminal/playbook.json.

Reads data/terminal/inputs/playbook.yaml (the government's approach, past episodes and what each
school of thought would say, all cited) and adds, for every episode, what followed at 6 and 24
months: inflation, real GDP growth, the currency against the US dollar and the 10-year yield, from
stored series (terminal/sources/history.py and the terminal's own series). A cell with no free data
or whose horizon is after the latest observation is null, with the reason. These show what followed,
not proof of cause.

Definitions (every outcome is measured from the month before the episode starts):
    inflation      12-month CPI inflation in the horizon month (%); annual average if only annual data
    growth         real GDP growth over four quarters in the quarter containing the horizon date (%);
                   the calendar-year rate if only annual data
    fx_pct         change in the currency's value against the US dollar (%); positive = stronger
    y10_bp         change in the 10-year government yield (basis points)
"""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import yaml

from terminal import store

SPEC = store.INPUTS / "playbook.yaml"
OUT = store.DATA / "playbook.json"
SCHOOLS = ["Keynesian", "Monetarist", "Austrian", "Supply-side", "MMT"]
HORIZONS = {"m6": 6, "m24": 24}
NO_FREE_DATA = "no free data"

# For each country and field, series in order of preference, with their frequency:
#   m monthly (or daily) level, q quarterly real GDP level, a annual rate (%)
SERIES = {
    "BR": {"inflation": [("br.ipca.yoy", "m"), ("hist.br.cpi_a", "a")], "growth": [("hist.br.gdp_q", "q"), ("hist.br.gdp_a", "a")],
           "fx": [("hist.br.fx_m", "m")], "y10": [("br.td.pre_longest", "m")]},
    "MX": {"inflation": [("hist.mx.cpi_yoy", "m"), ("hist.mx.cpi_a", "a")], "growth": [("hist.mx.gdp_q", "q"), ("hist.mx.gdp_a", "a")],
           "fx": [("hist.mx.fx_m", "m")], "y10": [("mx.10y.oecd_m", "m")]},
    "FR": {"inflation": [("hist.fr.cpi_yoy", "m"), ("hist.fr.cpi_a", "a")], "growth": [("hist.fr.gdp_q", "q"), ("hist.fr.gdp_a", "a")],
           "fx": [("hist.fr.fx_m", "m")], "y10": [("fr.oat10y.ecb_m", "m"), ("hist.fr.y10_m", "m")]},
    "AR": {"inflation": [("hist.ar.cpi_a", "a")], "growth": [("hist.ar.gdp_q", "q"), ("hist.ar.gdp_a", "a")],
           "fx": [("hist.ar.fx_m", "m")], "y10": []},
}
CURRENCY = {"BR": "real", "MX": "peso", "FR": "franc, then euro", "AR": "peso"}


def _d(s: str) -> dt.date:
    return dt.date.fromisoformat(str(s)[:10])


def add_months(d: dt.date, n: int) -> dt.date:
    y, m = divmod(d.month - 1 + n, 12)
    return dt.date(d.year + y, m + 1, 1)


class Series:
    """A stored series reduced to (date, value) pairs, sorted."""

    def __init__(self, sid: str, rows: list[tuple[dt.date, float]], meta: dict | None = None):
        self.id, self.rows, self.meta = sid, sorted(rows), meta or {}

    @classmethod
    def load(cls, sid: str) -> "Series | None":
        s = store.load_series(sid)
        if not s or not s.get("history"):
            return None
        rows = [(_d(r[0]), float(r[1])) for r in s["history"] if r[1] is not None]
        return cls(sid, rows, s)

    @property
    def first(self) -> dt.date:
        return self.rows[0][0]

    @property
    def last(self) -> dt.date:
        return self.rows[-1][0]

    def month(self, d: dt.date) -> float | None:
        """The observation in d's month (daily series: the last one in that month)."""
        vals = [v for x, v in self.rows if x.year == d.year and x.month == d.month]
        return vals[-1] if vals else None

    def year(self, y: int) -> float | None:
        vals = [v for x, v in self.rows if x.year == y]
        return vals[-1] if vals else None

    def yoy_quarter(self, d: dt.date) -> float | None:
        """Growth over four quarters for the quarter containing d (levels at quarter starts)."""
        q = dt.date(d.year, 3 * ((d.month - 1) // 3) + 1, 1)
        by = {x: v for x, v in self.rows}
        now, before = by.get(q), by.get(dt.date(q.year - 1, q.month, 1))
        if now is None or before in (None, 0):
            return None
        return 100 * (now / before - 1)


def _value(s: Series, freq: str, d: dt.date, field: str):
    if freq == "a":
        return s.year(d.year)
    if field == "growth" and freq == "q":
        return s.yoy_quarter(d)
    return s.month(d)


def _cell(cc: str, field: str, base: dt.date, at: dt.date, today: dt.date, loader) -> tuple[dict, dict]:
    """Start and horizon values for one field, from the first series that covers both dates."""
    cands = SERIES[cc].get(field, [])
    if not cands:
        return {}, {"reason": NO_FREE_DATA}
    reasons = []
    for sid, freq in cands:
        s = loader(sid)
        if s is None:
            reasons.append(f"{sid} not stored yet")
            continue
        if at > today or (freq != "a" and at > s.last) or (freq == "a" and at.year > s.last.year):
            reasons.append(f"after the latest data ({s.last.isoformat()})")
            continue
        start_d = dt.date(base.year - 1, 12, 31) if freq == "a" else base
        v0, v1 = _value(s, freq, start_d, field), _value(s, freq, at, field)
        if v1 is None or (field in ("fx", "y10") and v0 is None):
            reasons.append(f"{sid} starts {s.first.isoformat()}" if min(start_d, at) < s.first else f"{sid} has a gap")
            continue
        unit = {"a": "annual", "q": "quarterly", "m": "monthly"}[freq]
        return {"start": v0, "end": v1, "freq": unit}, {"series": sid, "freq": unit, "source": s.meta.get("source"),
                                                         "source_id": s.meta.get("source_id"), "url": s.meta.get("source_url")}
    return {}, {"reason": reasons[0] if all("after the latest" in r for r in reasons) else
                (NO_FREE_DATA if not any("not stored" in r for r in reasons) else reasons[0]), "tried": reasons}


def outcomes(ep: dict, today: dt.date | None = None, loader=Series.load) -> tuple[dict, dict, dict]:
    """(outcomes {m6, m24}, start values, per-field sources and null reasons)."""
    today = today or dt.date.today()
    cc = ep["country"]
    start = _d(ep["start"])
    base = add_months(dt.date(start.year, start.month, 1), -1)        # the month before the episode
    out, start_vals, srcs = {}, {}, {}
    for h, n in HORIZONS.items():
        at = add_months(dt.date(start.year, start.month, 1), n)
        row = {"date": at.isoformat()[:7]}
        for field in ("inflation", "growth", "fx", "y10"):
            c, src = _cell(cc, field, base, at, today, loader)
            srcs.setdefault(field, {})[h] = src
            if field == "inflation":
                row["inflation"] = _r(c.get("end"), 1)
                row["inflation_chg_pp"] = _r(c["end"] - c["start"], 1) if c.get("start") is not None and c.get("end") is not None else None
                start_vals.setdefault("inflation", _r(c.get("start"), 1))
            elif field == "growth":
                row["growth"] = _r(c.get("end"), 1)
                start_vals.setdefault("growth", _r(c.get("start"), 1))
            elif field == "fx":
                row["fx_pct"] = _r(100 * (c["start"] / c["end"] - 1), 1) if c and c["end"] else None
            else:
                row["y10"] = _r(c.get("end"), 2)
                row["y10_bp"] = round(100 * (c["end"] - c["start"])) if c else None
                start_vals.setdefault("y10", _r(c.get("start"), 2))
            if not c:
                row.setdefault("null_reasons", {})[{"fx": "fx_pct", "y10": "y10_bp"}.get(field, field)] = src["reason"]
        out[h] = row
    return out, {k: v for k, v in start_vals.items() if v is not None}, srcs


def _r(x, n):
    return None if x is None else round(x, n)


def _resolve(keys, sources: dict, works: dict) -> list[dict]:
    out = []
    for k in keys or []:
        if k in sources:
            out.append({"key": k, **sources[k]})
        elif k in works:
            w = works[k]
            out.append({"key": k, "label": f"{w['author']}, {w['title']} ({w['year']})", **w})
        else:
            raise KeyError(f"unknown citation {k!r}")
    return out


def build(today: dt.date | None = None, loader=Series.load) -> dict:
    spec = yaml.safe_load(SPEC.read_text())
    sources, works = spec.get("sources", {}), spec.get("works", {})
    episodes = []
    for ep in spec["episodes"]:
        oc, sv, srcs = outcomes(ep, today, loader)
        episodes.append({**{k: v for k, v in ep.items() if k != "cites"}, "currency": CURRENCY.get(ep["country"]),
                         "cites": _resolve(ep.get("cites"), sources, works), "start_values": sv,
                         "outcomes": oc, "outcome_sources": srcs})
    countries = {}
    for cc, c in spec["countries"].items():
        ap = c["approach"]
        countries[cc] = {
            "approach": {"summary": " ".join(ap["summary"].split()),
                         "policies": [{**{k: v for k, v in p.items() if k != "sources"}, "why": " ".join(p["why"].split()),
                                       "sources": _resolve(p.get("sources"), sources, works)} for p in ap["policies"]]},
            "episodes": [e for e in episodes if e["country"] == cc],
            "schools": [{**{k: v for k, v in s.items() if k != "cites"}, "view": " ".join(s["view"].split()),
                         "label": f"{s['school']} perspective", "cites": _resolve(s.get("cites"), sources, works)}
                        for s in spec["schools"].get(cc, [])]}
    out = {"generated_at": store.now_iso(), "disclaimer": spec["disclaimer"],
           "definitions": {"inflation": "12-month CPI inflation in the horizon month, % (annual average when only annual data exist)",
                           "inflation_chg_pp": "change in inflation since the month before the episode, percentage points",
                           "growth": "real GDP growth over four quarters in the quarter containing the horizon date, % (calendar year when only annual data exist)",
                           "fx_pct": "change in the currency's value against the US dollar since the month before the episode, %; positive = stronger",
                           "y10": "10-year government yield in the horizon month, %",
                           "y10_bp": "change in the 10-year yield since the month before the episode, basis points",
                           "position": "0 = interventionist / Keynesian, 100 = orthodox / monetarist",
                           "against": "Horizons' reading of which school the episode is hardest to square with; an interpretation, not a finding"},
           "schools": SCHOOLS, "countries": countries,
           "regional": [e for e in episodes if e["country"] not in spec["countries"]]}
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n")
    return out
