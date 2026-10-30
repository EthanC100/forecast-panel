"""Horizons' Algorithm tab: data/terminal/algorithm.json, rebuilt in the summary step from em-macro's
frozen systematic strategy (results/systematic/positions.csv and paper_pnl.csv).

Each position keeps em-macro's fields (side, size, risk share, volatility, carry/trend/value z-scores).
Positions in instruments the paper book can price are marked copyable, with the book code, the
direction in the book's convention (long BRL = short USD/BRL; long a bond or the France-Bund spread =
gains when the yield or spread falls), the latest level and a suggested stop two monthly standard
deviations away (annual volatility / sqrt(12); for bonds the excess-return volatility is turned into
a yield move with the book's duration). Monthly paper P&L is shown against em-macro's carry basket.
"""

from __future__ import annotations

import csv
import io
import json
import logging
import math
import re

from terminal import book, store

log = logging.getLogger(__name__)
OUT = store.DATA / "algorithm.json"
SOURCE = book.EM_MACRO_RAW + "results/systematic/"
REPO = "https://github.com/EthanC100/em-macro/tree/main/results/systematic"
# em-macro instrument -> (book code, sign: +1 if em-macro's long is the book's long, -1 if it is the book's short)
BOOK_MAP = {"BRL": ("USDBRL", -1), "MXN": ("USDMXN", -1), "BR10Y": ("BR10Y", 1), "MX10Y": ("MX10Y", 1),
            "FR-DE": ("OATBUND", 1), "US10Y": ("US10Y", 1)}
COUNTRY = {"BRL": "Brazil", "BR10Y": "Brazil", "MXN": "Mexico", "MX10Y": "Mexico", "FR-DE": "France", "US10Y": "United States",
           "DE10Y": "Germany"}


def _f(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def country_of(row: dict) -> str:
    if row["instrument"] in COUNTRY:
        return COUNTRY[row["instrument"]]
    desc = row.get("description") or ""
    m = re.match(r"([A-Z][A-Za-z ]+?) 10y", desc)          # bonds and spreads: "South Africa 10y ..."
    if m:
        return m.group(1)
    m = re.search(r"\(([^)]+)\)\s*$", desc)              # currencies: "TRY vs USD (Turkey)"
    return m.group(1) if m else row["instrument"]


def copy_terms(cfg: dict, row: dict) -> dict | None:
    """Book code, direction, latest level and a suggested stop for a position the book can trade."""
    mapped = BOOK_MAP.get(row["instrument"])
    side = 1 if row["side"] == "long" else -1
    if not mapped or row["side"] not in ("long", "short"):
        return None
    code, sgn = mapped
    icfg = cfg["instruments"].get(code)
    if not icfg:
        return None
    inst = book.Instrument(code, icfg)
    last = inst.latest()
    vol = _f(row.get("instrument_vol_pct"))
    direction = "long" if side * sgn > 0 else "short"
    out = {"instrument": code, "name": icfg["name"], "direction": direction, "level": last[1] if last else None,
           "level_date": last[0] if last else None, "suggested_stop": None, "stop_basis": None}
    if not last or not vol:
        return out
    m2 = 2 * vol / math.sqrt(12)                      # two monthly standard deviations, % of notional
    g = (1 if direction == "long" else -1) * inst.favourable
    if inst.pct:
        dist = last[1] * m2 / 100.0
        basis = f"2 monthly sd = 2 x {vol:g}%/sqrt(12) = {m2:.2f}% of the level"
    else:
        dur = inst.duration(last[0], last[1]) or 0
        if not dur:
            return out
        dist = m2 / dur * (100.0 if inst.kind == "spread_bp" else 1.0)
        basis = f"2 monthly sd of the excess return ({m2:.2f}%) / duration {dur:g} = {dist:.2f}{' bp' if inst.kind == 'spread_bp' else ' pp of yield'}"
    nd = 4 if inst.kind == "fx" else 2
    out.update({"suggested_stop": round(last[1] - g * dist, nd), "stop_basis": basis})
    return out


def build_from(pos_text: str, pnl_text: str, cfg: dict) -> dict:
    pos = list(csv.DictReader(io.StringIO(pos_text)))
    rows = list(csv.DictReader(io.StringIO(pnl_text)))
    positions = []
    for r in pos:
        positions.append({"book": r["book"], "instrument": r["instrument"], "description": r["description"], "side": r["side"],
                          "size_pct_of_capital": _f(r.get("size_pct_of_capital")), "risk_share_pct": _f(r.get("risk_share_pct")),
                          "instrument_vol_pct": _f(r.get("instrument_vol_pct")), "carry_z": _f(r.get("carry_z")),
                          "trend_z": _f(r.get("trend_z")), "value_z": _f(r.get("value_z")),
                          "cost_pct_per_trade": _f(r.get("cost_pct_per_trade")), "country": country_of(r),
                          "copyable": copy_terms(cfg, r)})
    pnl, cb = [], 1.0
    for r in rows:
        net, basket = _f(r.get("net")), _f(r.get("carry_basket"))
        cb *= 1 + (basket or 0)
        pnl.append([r["month"], net, basket, _f(r.get("cumulative_net")), round(cb, 6), r.get("sample")])
    last12 = pnl[-12:]
    comp = lambda i: round(math.prod(1 + (x[i] or 0) for x in last12) - 1, 6) if last12 else None
    gross = sum(abs(p["size_pct_of_capital"] or 0) for p in positions)
    return {"generated_at": store.now_iso(), "source": SOURCE, "source_page": REPO,
            "as_of": pos[0]["as_of"] if pos else None, "effective_from": pos[0]["effective_from"] if pos else None,
            "positions": positions, "pnl": pnl, "pnl_columns": ["month", "net", "carry_basket", "cumulative_net", "cumulative_carry_basket", "sample"],
            "this_month": {"effective_from": pos[0]["effective_from"] if pos else None, "n_positions": len(positions),
                           "n_long": sum(p["side"] == "long" for p in positions), "n_short": sum(p["side"] == "short" for p in positions),
                           "gross_pct_of_capital": round(gross, 2), "n_copyable": sum(bool(p["copyable"]) for p in positions),
                           "last_month": {"month": pnl[-1][0], "net": pnl[-1][1], "carry_basket": pnl[-1][2]} if pnl else None,
                           "last_12m": {"from": last12[0][0], "to": last12[-1][0], "net": comp(1), "carry_basket": comp(2)} if last12 else None},
            "notes": ["em-macro's strategy is frozen and monthly: positions change at the start of each month.",
                      "Scores are z-scores across the strategy's universe: above 0 favours a long, below 0 a short.",
                      "The carry basket is em-macro's benchmark: long the highest-carry currencies, short the lowest.",
                      "Copyable positions are mapped to this paper book; the suggested stop is two monthly standard deviations away."]}


def build() -> dict | None:
    cfg = book.load_config()
    pos_t, pnl_t = book._em_macro_text("results/systematic/positions.csv"), book._em_macro_text("results/systematic/paper_pnl.csv")
    if not pos_t or not pnl_t:
        log.warning("algorithm: em-macro results/systematic not reachable; keeping the last file")
        return None
    out = build_from(pos_t, pnl_t, cfg)
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n")
    return out
