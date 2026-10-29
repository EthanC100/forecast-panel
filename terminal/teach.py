"""Build data/terminal/teach.json: the em-macro numbers behind the "How this works" cards and the
what-if sliders. Everything comes from em-macro's published results; nothing is re-estimated here.

  drivers      what moves each market: the risk model's coefficients (effect of a one-standard-
               deviation change), with each factor's contribution change over the last 12 months
  waterfall    the fair-value breakdown: baseline + each factor's contribution = fair value, vs actual
  systematic   this month's carry / trend / value scores and positions of em-macro's strategy
  event_study  average move around past elections and rate decisions (days 1, 5, 20) with the range
  what_if      per-unit effects for the country-page sliders, with their standard errors
"""

from __future__ import annotations

import json
import logging
import math

import numpy as np
import pandas as pd

from terminal import emmacro, store

log = logging.getLogger("terminal")
OUT = store.DATA / "teach.json"
ISO = {"FR": "FRA", "BR": "BRA", "MX": "MEX"}
ISO2 = {"BR": "BR", "MX": "MX"}
POST_HOC = "post-hoc model: chosen after the 2020+ test; not a clean out-of-sample result"

PLAIN = {
    "gross debt, % GDP": "Government debt",
    "fiscal deficit, % GDP": "Budget deficit",
    "debt trajectory (3y avg change, pp/yr)": "Debt rising or falling",
    "debt held abroad, %": "Debt owned by foreigners",
    "central bank independence (CBIE)": "Central bank independence",
    "inflation minus target, pp": "Inflation above target",
    "real policy rate, %": "Real interest rate",
    "government seat share, %": "Government's share of seats",
    "governments in prior 5 years": "Government turnover",
    "governing parties' economic position (V-Party, + = right)": "Government left/right (V-Party)",
    "governing parties' populism (V-Party)": "Government populism",
    "governing parties' economic position (CHES)": "Government left/right (CHES)",
    "populist party in government (PopuList)": "Populist party in government",
    "governance (WGI mean)": "Quality of governance",
    "judicial constraints (V-Dem)": "Courts' checks on government",
    "high-court independence (V-Dem)": "High-court independence",
    "current account, % GDP": "Current-account balance",
    "reserves, months of imports": "FX reserves",
    "IMF programme": "IMF programme",
    "average rating (notches)": "Credit rating",
    "US 10y yield, %": "US 10-year yield",
    "VIX (log)": "Global risk appetite (VIX)",
    "ECB deposit rate, %": "ECB interest rate",
    "debt x government seat share": "Debt combined with a weak government",
    "policy rate minus fed funds, pp": "Interest-rate gap to the US",
    "commodity prices": "Commodity prices",
}


def plain(label: str) -> str:
    if label.startswith("commodity "):
        return "Commodity prices: " + label.split(" ", 1)[1].split(":")[0].replace("_", " ")
    return PLAIN.get(label, label)


def _factors(file: str, asset: str, iso: str) -> pd.DataFrame:
    f = emmacro.frame(file)
    return f[(f.country == iso) & (f.asset == asset)]


def drivers(code: str) -> list[dict]:
    iso = ISO[code]
    out = []
    specs = [("spread", "results/risk_model/fit_v2_posthoc/coefficients_spread_" + ("eu" if code == "FR" else "em") + ".csv",
              "results/risk_model/factors.csv", "spread_bp", "bp of spread", POST_HOC, "spread vs " + ("Bund" if code == "FR" else "US Treasuries"))]
    if code in ("BR", "MX"):
        specs.append(("currency", "results/risk_model/fit/coefficients_fx.csv", "results/risk_model/fx_factors.csv", "fx_pct",
                      "% of the real exchange rate (+ = weaker)", "v1 currency equation, fitted 2005-2019", "currency vs USD"))
    for kind, coef_file, fac_file, asset, unit, model, target in specs:
        c = emmacro.frame(coef_file)
        c = c[~c.term.str.startswith("commod_") | c.term.str.endswith(":" + ISO2.get(code, "--"))]
        c = c[c.coef_per_sd.notna()]
        fac = _factors(fac_file, asset, iso)
        last = fac.date.max()
        prev = sorted(d for d in fac.date.unique() if d <= str(int(last[:4]) - 1) + last[4:])
        prev = prev[-1] if prev else None
        cur = fac[fac.date == last].set_index("factor").contribution
        old = fac[fac.date == prev].set_index("factor").contribution if prev else None
        rows = []
        for _, r in c.iterrows():
            lab = r.label
            # commodity terms are summed in the factor file under one label
            key = "commodity prices" if r.term.startswith("commod_") else lab
            d12 = None
            if old is not None and key in cur.index and key in old.index:
                d12 = round(float(cur[key] - old[key]), 2)
            rows.append({"term": r.term, "label": lab, "plain": plain(lab if not r.term.startswith("commod_") else r.term.replace("commod_", "commodity ")),
                         "effect_per_sd": round(float(r.coef_per_sd), 2), "t": round(float(r.t_dk), 2),
                         "significant": abs(float(r.t_dk)) >= 2, "lag_months": int(r.lag_months),
                         "contribution_now": round(float(cur[key]), 2) if key in cur.index else None, "change_12m": d12})
        rows.sort(key=lambda x: -abs(x["effect_per_sd"]))
        out.append({"kind": kind, "target": target, "unit": unit, "model": model, "as_of": last, "compare_to": prev,
                    "rows": rows[:10], "n_factors": len(rows),
                    "source_url": emmacro.url(coef_file)})
    return out


def waterfall(code: str) -> dict:
    iso = ISO[code]
    fac = _factors("results/risk_model/factors.csv", "spread_bp", iso)
    last = fac.date.max()
    cur = fac[fac.date == last]
    base = cur[cur.factor.str.startswith("baseline")]
    rest = cur[~cur.factor.str.startswith("baseline")].copy()
    rest["abs"] = rest.contribution.abs()
    rest = rest.sort_values("abs", ascending=False)
    top, other = rest.head(6), rest.iloc[6:]
    fv = emmacro.frame("results/risk_model/fair_value.csv")
    fv = fv[(fv.country == iso) & (fv.date == last)]
    steps = [{"label": "Country baseline (2005-19 average)", "value": round(float(base.contribution.sum()), 2), "kind": "base"}]
    steps += [{"label": plain(r.factor), "model_label": r.factor, "value": round(float(r.contribution), 2), "kind": "factor"} for _, r in top.iterrows()]
    steps.append({"label": f"{len(other)} other factors", "value": round(float(other.contribution.sum()), 2), "kind": "factor"})
    return {"as_of": last, "unit": "bp", "target": "10-year spread vs " + ("Bund" if code == "FR" else "US Treasuries"),
            "steps": steps, "fair_value": round(float(fv.fair_value.iloc[0]), 2) if len(fv) else round(float(cur.contribution.sum()), 2),
            "actual": round(float(fv.actual.iloc[0]), 2) if len(fv) else None, "model": POST_HOC,
            "source_url": emmacro.url("results/risk_model/factors.csv")}


def systematic() -> dict:
    p = emmacro.frame("results/systematic/positions.csv")
    rows = []
    for _, r in p.iterrows():
        zs = [x for x in (r.carry_z, r.trend_z, r.value_z) if x == x]
        rows.append({"book": r.book, "instrument": r.instrument, "description": r.description, "side": r.side,
                     "size_pct": float(r.size_pct_of_capital), "carry_z": _f(r.carry_z), "trend_z": _f(r.trend_z), "value_z": _f(r.value_z),
                     "score": round(sum(zs) / len(zs), 3) if zs else None})
    return {"as_of": str(p.as_of.iloc[0]), "effective_from": str(p.effective_from.iloc[0]), "rows": rows,
            "universe": {"fx": 10, "bond": 13},
            "formula": ["carry = what the position pays: policy-rate gap to the US for currencies; yield minus funding rate for bonds",
                        "trend = average z-score of the past 12-month and 3-month returns",
                        "value = cheapness: real exchange rate vs its 5-year average (currencies); spread minus the risk model's fair value (bonds)",
                        "score = (z(carry) + z(trend) + z(value)) / 3, z-scored across each book every month",
                        "rank each book: long the top third, short the bottom third, nothing in the middle third",
                        "size = 1 / trailing 36-month volatility; each book scaled to 10% volatility; books mixed 50/50"],
            "note": "em-macro publishes only the positions it takes (top and bottom thirds); the middle third is not listed.",
            "source_url": emmacro.url("results/systematic/positions.csv")}


def _f(x):
    return None if x != x else round(float(x), 3)


def event_study() -> dict:
    m = pd.concat([emmacro.frame("results/fit/event_moves.csv"), emmacro.frame("results/test/event_moves.csv")])
    groups = [("election", ["general", "presidential", "presidential_r2", "legislative"], "Elections"),
              ("rate_decision", ["hike"], "Rate hikes"), ("rate_decision", ["cut"], "Rate cuts"), ("rate_decision", ["hold"], "Rate holds")]
    out = {}
    for c in ("BR", "MX"):
        out[c] = []
        for et, subs, label in groups:
            for asset, unit, sign, name in (("FX", "%", -1, "USD/" + ("BRL" if c == "BR" else "MXN")), ("Y10", "bp", 1, "10-year yield")):
                d = m[(m.country == c) & (m.event_type == et) & m.subtype.isin(subs) & (m.asset == asset)]
                d = d.dropna(subset=["ab_1", "ab_5", "ab_20"])
                if len(d) < 3:
                    continue
                path = [{"day": 0, "mean": 0.0, "lo": 0.0, "hi": 0.0}]
                for h in (1, 5, 20):
                    v = sign * d[f"ab_{h}"].astype(float).to_numpy()
                    lo, hi = (np.percentile(v, 10), np.percentile(v, 90)) if len(v) >= 10 else (v.min(), v.max())
                    path.append({"day": h, "mean": round(float(v.mean()), 3), "median": round(float(np.median(v)), 3),
                                 "lo": round(float(lo), 3), "hi": round(float(hi), 3)})
                out[c].append({"group": label, "event_type": et, "subtypes": subs, "asset": name, "unit": unit, "n": int(len(d)),
                               "range": "10th-90th percentile" if len(d) >= 10 else "min-max", "path": path,
                               "first": str(d.event_date.min()), "last": str(d.event_date.max())})
    return {"groups": out, "measure": "abnormal move (net of the dollar, US 10-year and VIX) from the day before the event",
            "missing": "em-macro has no event-study results for rating actions or budgets, and none for France, so those are not shown.",
            "source_url": emmacro.url("results/test/event_moves.csv")}


def what_if() -> dict:
    w = emmacro.frame("results/risk_model/what_if.csv")
    inp = emmacro.frame("data/processed/risk_model_input.csv")
    out = {}
    for code, iso in ISO.items():
        cur = inp[inp["c"] == code].sort_values("month")
        last = cur.dropna(subset=["seat_share"]).iloc[-1] if len(cur) else None
        seat = float(last.seat_share) if last is not None else None
        # the "loses its majority" scenario: -10 pp for governments already in a minority, else down to 45%
        seat_ref = -10.0 if (seat is None or seat < 50) else 45.0 - seat
        items = []
        for scen, key, unit_per, label, smin, smax, step, now in (
                ("deficit_plus1", "deficit", 1.0, "Budget deficit, change in % of GDP", -2, 3, 0.25,
                 None if last is None else round(float(last.deficit), 2)),
                ("downgrade_1", "rating", 1.0, "Credit rating, notches of downgrade (average of S&P, Moody's, Fitch)", -2, 3, 1, None),
                ("lose_majority", "seat_share", seat_ref, "Government seat share, change in percentage points", -20, 10, 1,
                 None if seat is None else round(seat, 1)),
                ("populism_plus1sd", "populism", 1.0, "Governing parties' populism, change in standard deviations", -2, 2, 0.25, None)):
            per = {}
            for asset in ("spread_bp", "fx_pct"):
                r = w[(w.country == iso) & (w.asset == asset) & (w.scenario == scen)]
                if r.empty:
                    continue
                r = r.iloc[-1]
                # the rating slider counts notches of downgrade, so em-macro's one-notch estimate is per unit
                per[asset] = {"per_unit": round(float(r.estimate) / unit_per, 4),
                              "se_per_unit": round(abs(float(r.se) / unit_per), 4), "as_of": r.date, "description": r.description}
            items.append({"key": key, "scenario": scen, "label": label, "min": smin, "max": smax, "step": step, "now": now, "effects": per,
                          "unit_note": (f"em-macro's scenario is {seat_ref:+.1f} pp" if key == "seat_share" else None)})
        out[code] = items
    return {"countries": out, "band": "90% band = ±1.645 × the combined standard error (factors treated as independent)",
            "caveat": "Linear extrapolation of em-macro's what-if estimates, holding everything else fixed. Bands cover parameter "
                      "uncertainty only. The Brazil and Mexico seat-share effect reflects 2005-2019 co-movement, not a causal estimate.",
            "currency_note": "Currency effects are % changes in the real exchange rate, + = weaker local currency (v1 currency equation).",
            "source_url": emmacro.url("results/risk_model/what_if.csv")}


def build() -> dict:
    out = {"generated_at": store.now_iso(), "em_macro": emmacro.RAW, "countries": {}}
    for code in ISO:
        c = {}
        for name, fn in (("drivers", drivers), ("waterfall", waterfall)):
            try:
                c[name] = fn(code)
            except Exception as exc:                                     # noqa: BLE001
                log.warning("teach %s %s: %s", code, name, exc)
                c[name] = {"error": str(exc)}
        out["countries"][code] = c
    for name, fn in (("systematic", systematic), ("event_study", event_study), ("what_if", what_if)):
        try:
            out[name] = fn()
        except Exception as exc:                                         # noqa: BLE001
            log.warning("teach %s: %s", name, exc)
            out[name] = {"error": str(exc)}
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=1, default=lambda x: None if isinstance(x, float) and math.isnan(x) else str(x)) + "\n")
    return out
