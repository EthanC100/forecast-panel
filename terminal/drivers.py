"""External drivers: how each instrument has co-moved with global drivers, and what that implies.

Per instrument (USD/BRL, USD/MXN, EUR/USD, France OAT-Bund spread, Brazil 10-year proxy, US 10-year):

    univariate   beta of the instrument's change on each driver's change, over the last 1 year and
                 3 years, with heteroskedasticity-robust (HC1) standard errors and R squared
    stability    the 1-year beta re-estimated at each month end over the last five years, +-2 SE
    model        a 3-year multivariate regression on the instrument's drivers (coefficients,
                 covariance, residual sd): what-if sliders and the attribution use it
    attribution  each of the last 8 weeks (months for monthly instruments): the move split into
                 what the drivers explain (beta x the driver's move) and the local remainder

Frequencies: weekly (Friday to Friday) when the instrument and its drivers are daily series;
monthly averages when the instrument or a driver is only monthly (the ECB spreads, iron ore and
soybeans). Brazil has both: a weekly model on the daily drivers and a monthly model that adds iron
ore and soy. Changes are in % for currencies, the dollar index, oil and commodities, in basis points
for yields and spreads, and in points for the VIX.

These are descriptions of typical co-movement, not forecasts or causal effects.
"""

from __future__ import annotations

import datetime as dt
import json
import logging
import math

import numpy as np
import pandas as pd

from terminal import store

log = logging.getLogger(__name__)

OUT = store.DATA / "drivers.json"

# key: (label, series candidates, change unit, unit move for sentences, monthly only)
DRIVERS = {
    "usd": ("the dollar (broad index)", ["us.usd.broad"], "pct", 1.0, False),
    "us10y": ("the US 10-year yield", ["us.ust10y"], "bp", 10.0, False),
    "us2y": ("the US 2-year yield", ["us.ust2y"], "bp", 10.0, False),
    "vix": ("the VIX", ["us.vix"], "pt", 5.0, False),
    "brent": ("the oil price (Brent)", ["gl.brent"], "pct", 10.0, False),
    "iron": ("the iron ore price", ["gl.ironore"], "pct", 10.0, True),
    "soy": ("the soybean price", ["gl.soy"], "pct", 10.0, True),
    "bund": ("the Bund yield", ["de.bund10y", "de.bund10y.ecb_m"], "bp", 10.0, False),
    "eur": ("the euro (EUR/USD)", ["eu.eurusd"], "pct", 1.0, False),
    "itsp": ("Italy's spread over Bunds", ["it.spread.btp_bund.ecb_m"], "bp", 10.0, True),
    "essp": ("Spain's spread over Bunds", ["es.spread.bono_bund.ecb_m"], "bp", 10.0, True),
}

# code: (label, country, series candidates, change unit, how a rise reads, drivers, model drivers)
INSTRUMENTS = {
    "USDMXN": ("USD/MXN", "MX", ["mx.usdmxn.fix"], "pct", "peso", ["usd", "us10y", "us2y", "brent", "vix"],
               ["usd", "us10y", "brent", "vix"]),
    "USDBRL": ("USD/BRL", "BR", ["br.usdbrl.ptax"], "pct", "real", ["usd", "us10y", "us2y", "vix", "iron", "soy"],
               ["usd", "us10y", "vix"]),
    "BR10Y": ("Brazil 10-year proxy", "BR", ["br.td.pre_longest"], "bp", None, ["usd", "us10y", "us2y", "vix", "iron", "soy"],
              ["usd", "us10y", "vix"]),
    "EURUSD": ("EUR/USD", "FR", ["eu.eurusd"], "pct", "euro", ["us2y", "bund", "brent", "vix"], ["us2y", "bund", "brent", "vix"]),
    "OATBUND": ("France OAT-Bund spread", "FR", ["fr.spread.oat_bund", "fr.spread.oat_bund.ecb_m"], "bp", None,
                ["bund", "eur", "itsp", "essp", "vix"], ["bund", "eur", "itsp", "vix"]),
    "US10Y": ("US 10-year", "US", ["us.ust10y"], "bp", None, ["us2y", "usd", "brent", "vix"], ["us2y", "brent", "vix"]),
}
# Brazil's commodity drivers only exist monthly: a second, monthly model includes them
MONTHLY_MODELS = {"USDBRL": ["usd", "us10y", "vix", "iron", "soy"], "BR10Y": ["usd", "us10y", "vix", "iron", "soy"]}
# book instruments without their own model borrow one
PROXY_MODEL = {"DI27": "BR10Y", "DI29": "BR10Y", "DI31": "BR10Y"}
YEARS = {"1y": 1, "3y": 3}
PER_YEAR = {"W": 52, "M": 12}


def _load(cands: list[str]) -> tuple[str | None, pd.Series | None, dict | None]:
    for sid in cands:
        s = store.load_series(sid)
        if s and s.get("history"):
            rows = [(r[0], r[1]) for r in s["history"] if isinstance(r[1], (int, float))]
            if len(rows) > 30:
                ser = pd.Series([v for _, v in rows], index=pd.to_datetime([d for d, _ in rows])).sort_index()
                return sid, ser[~ser.index.duplicated(keep="last")], s
    return None, None, None


def _is_monthly(meta: dict | None, ser: pd.Series) -> bool:
    if meta and "month" in str(meta.get("frequency", "")):
        return True
    return ser.index.to_series().diff().dt.days.median() > 20


def changes(ser: pd.Series, unit: str, freq: str) -> pd.Series:
    """Weekly (Friday close) or monthly-average changes in the unit's terms."""
    if freq == "W":
        lv = ser.resample("W-FRI").last().dropna()
    else:
        lv = ser.resample("MS").mean().dropna()
    if unit == "pct":
        ch = 100 * lv.pct_change()
    elif unit == "bp":
        ch = lv.diff()
    else:
        ch = lv.diff()
    return ch.dropna()


def _to_bp(meta: dict | None) -> float:
    """Yields stored in % move in hundredths; spreads stored in bp move as they are."""
    unit = (meta or {}).get("unit", "")
    return 1.0 if unit.strip() == "bp" else 100.0


def ols_uni(y: np.ndarray, x: np.ndarray) -> dict | None:
    n = len(y)
    if n < 8:
        return None
    xm, ym = x.mean(), y.mean()
    sxx = ((x - xm) ** 2).sum()
    if sxx <= 0:
        return None
    b = ((x - xm) * (y - ym)).sum() / sxx
    a = ym - b * xm
    e = y - a - b * x
    se = math.sqrt(((x - xm) ** 2 * e ** 2).sum()) / sxx * math.sqrt(n / (n - 2))  # HC1
    sst = ((y - ym) ** 2).sum()
    r2 = 1 - (e ** 2).sum() / sst if sst > 0 else 0.0
    return {"beta": round(float(b), 4), "se": round(float(se), 4), "r2": round(float(r2), 3), "n": int(n)}


def ols_multi(y: np.ndarray, X: np.ndarray) -> dict | None:
    n, k = X.shape
    if n < k + 10:
        return None
    Z = np.column_stack([np.ones(n), X])
    try:
        ZtZi = np.linalg.inv(Z.T @ Z)
    except np.linalg.LinAlgError:
        return None
    coef = ZtZi @ Z.T @ y
    e = y - Z @ coef
    s2 = float((e ** 2).sum() / (n - k - 1))
    cov = s2 * ZtZi
    sst = ((y - y.mean()) ** 2).sum()
    return {"intercept": float(coef[0]), "beta": [float(c) for c in coef[1:]], "cov": cov[1:, 1:].tolist(),
            "se": [float(math.sqrt(max(cov[i, i], 0))) for i in range(1, k + 1)], "resid_sd": math.sqrt(s2),
            "r2": float(1 - (e ** 2).sum() / sst) if sst > 0 else 0.0, "n": int(n)}


def _frame(y: pd.Series, xs: dict[str, pd.Series]) -> pd.DataFrame:
    df = pd.concat({"y": y, **xs}, axis=1, join="inner").dropna()
    return df


def _window(df: pd.DataFrame, years: int, end=None) -> pd.DataFrame:
    end = end if end is not None else df.index.max()
    return df[(df.index > end - pd.DateOffset(years=years)) & (df.index <= end)]


def sentence(inst: tuple, drv: tuple, beta: float) -> str:
    """'When the dollar rises 1%, USD/MXN usually rises 1.56% (the peso weakens about 1.56%).'"""
    label, _, _, iunit, asset = inst[:5]
    dlabel, dunit, move = drv[0], drv[2], drv[3]
    dmove = {"pct": f"{move:g}%", "bp": f"{move:g}bp", "pt": f"{move:g} points"}[dunit]
    eff = beta * move
    if iunit == "pct":
        s = f"When {dlabel} rises {dmove}, {label} usually {'rises' if eff >= 0 else 'falls'} {abs(eff):.2f}%"
        if asset and label.startswith("USD/"):
            s += f" (the {asset} {'weakens' if eff >= 0 else 'strengthens'} about {abs(eff):.2f}%)"
        elif asset:
            s += f" (the {asset} {'strengthens' if eff >= 0 else 'weakens'})"
        return s + "."
    if "spread" in label:
        verb = "widens" if eff >= 0 else "narrows"
    else:
        verb = "rises" if eff >= 0 else "falls"
    return f"When {dlabel} rises {dmove}, the {label} usually {verb} {abs(eff):.1f}bp."


def _attribution(df: pd.DataFrame, names: list[str], model: dict, inst: tuple, freq: str, n: int = 8, last_obs=None) -> list[dict]:
    out = []
    label, country, asset = inst[0], inst[1], inst[4]
    cname = "euro-specific news" if label == "EUR/USD" else {"MX": "Mexico", "BR": "Brazil", "FR": "France", "US": "the US"}.get(country, country)
    unit = "%" if inst[3] == "pct" else "bp"
    for ts, row in df.tail(n).iterrows():
        parts = [{"driver": k, "contrib": round(float(model["beta"][i] * row[k]), 3), "driver_move": round(float(row[k]), 3)}
                 for i, k in enumerate(names)]
        explained = sum(p["contrib"] for p in parts)
        move = float(row["y"])
        local = move - explained
        start = (ts - (pd.Timedelta(days=7) if freq == "W" else pd.DateOffset(months=1))).date().isoformat()
        partial = freq == "W" and last_obs is not None and ts > last_obs   # the week is still in progress
        end = (min(ts, last_obs) if partial else ts).date().isoformat()
        out.append({"end": end, "start": start, "partial": bool(partial), "move": round(move, 3), "explained": round(explained, 3),
                    "local": round(local, 3), "parts": parts,
                    "reading": reading(move, parts, local, label, asset, cname, unit, "week" if freq == "W" else "month")})
    return out


def reading(move: float, parts: list[dict], local: float, label: str, asset: str | None, cname: str, unit: str, per: str) -> str:
    """One line: 'Most of this week's peso fall (USD/MXN +0.94%) came from the dollar, not Mexico.'"""
    if abs(move) < 1e-9:
        return f"{label} was unchanged this {per}."
    if asset:
        up = (move < 0) if label.startswith("USD/") else (move > 0)
        what = f"{asset} {'rise' if up else 'fall'}"
    elif "spread" in label:
        what = f"{label} {'widening' if move > 0 else 'narrowing'}"
    else:
        what = f"{label} {'rise' if move > 0 else 'fall'}"
    amt = f"{label} {'+' if move > 0 else '-'}{abs(move):.2f}%" if unit == "%" else f"{'+' if move > 0 else '-'}{abs(move):.0f}bp"
    big = max(parts, key=lambda p: abs(p["contrib"])) if parts else None
    glob = sum(p["contrib"] for p in parts if p["contrib"] * move > 0)
    dl = DRIVERS[big["driver"]][0] if big else "global drivers"
    if big and big["contrib"] * move > 0 and abs(big["contrib"]) >= 0.5 * abs(move):
        return f"Most of this {per}'s {what} ({amt}) came from {dl}, not {cname}."
    if glob and abs(glob) >= 0.5 * abs(move):
        return f"Most of this {per}'s {what} ({amt}) lines up with global drivers, led by {dl}."
    if local * move > 0 and abs(local) >= 0.5 * abs(move):
        return f"Most of this {per}'s {what} ({amt}) was local to {cname}; global drivers explain little of it."
    return f"This {per}'s {what} ({amt}) was a mix of global drivers and local news."


def _stability(df: pd.DataFrame, k: str, years: int = 1, span_years: int = 5) -> list[list]:
    pts = []
    ends = df.index[df.index >= df.index.max() - pd.DateOffset(years=span_years)]
    ends = pd.Series(ends, index=ends).resample("ME").last().dropna()
    for end in ends:
        w = _window(df, years, end)
        r = ols_uni(w["y"].values, w[k].values)
        if r:
            pts.append([end.date().isoformat(), r["beta"], round(r["beta"] - 2 * r["se"], 4), round(r["beta"] + 2 * r["se"], 4)])
    return pts


def build() -> dict:
    loaded = {k: _load(v[1]) for k, v in DRIVERS.items()}
    out = {"generated_at": store.now_iso(), "drivers": {}, "instruments": {}, "trades": [],
           "notes": ["Betas describe how the instrument has typically moved alongside each driver; they are not forecasts or causal effects.",
                     "Standard errors are heteroskedasticity-robust (HC1) for the single-driver betas and classical for the multi-driver model.",
                     "Weekly = Friday-to-Friday changes; monthly = changes in monthly averages. A 1-year monthly window has only 12 points, so its standard errors are wide.",
                     "Iron ore and soybeans are monthly IMF prices (via FRED): no free official daily series exists, so Brazil's commodity betas use a monthly model."]}
    for k, (label, cands, unit, move, monthly_only) in DRIVERS.items():
        sid, ser, meta = loaded[k]
        out["drivers"][k] = {"label": label, "series": sid, "unit": unit, "unit_move": move, "monthly_only": monthly_only,
                             "available": ser is not None, "as_of": ser.index.max().date().isoformat() if ser is not None else None}

    def driver_changes(k: str, freq: str) -> pd.Series | None:
        sid, ser, meta = loaded[k]
        if ser is None:
            return None
        if freq == "W" and (DRIVERS[k][4] or _is_monthly(meta, ser)):
            # a daily driver may fall back to a monthly series (the Bund before the daily feed loads)
            if not DRIVERS[k][4] and len(DRIVERS[k][1]) > 1:
                for alt in DRIVERS[k][1]:
                    a_sid, a_ser, a_meta = _load([alt])
                    if a_ser is not None and not _is_monthly(a_meta, a_ser):
                        return changes(a_ser * (_to_bp(a_meta) if DRIVERS[k][2] == "bp" else 1), DRIVERS[k][2], freq)
            return None
        mult = _to_bp(meta) if DRIVERS[k][2] == "bp" else 1
        return changes(ser * mult, DRIVERS[k][2], freq)

    for code, inst in INSTRUMENTS.items():
        label, country, cands, iunit, asset, drv_all, drv_model = inst
        sid, ser, meta = _load(cands)
        if ser is None:
            out["instruments"][code] = {"label": label, "country": country, "available": False}
            continue
        freq = "M" if _is_monthly(meta, ser) else "W"
        y = changes(ser * (_to_bp(meta) if iunit == "bp" else 1), iunit, freq)
        res = {"label": label, "country": country, "series": sid, "unit": iunit, "asset": asset, "freq": freq,
               "as_of": ser.index.max().date().isoformat(), "available": True, "univariate": [], "stability": {}}
        for k in drv_all:
            f = "M" if (DRIVERS[k][4] or freq == "M") else "W"
            yk = y if f == freq else changes(ser * (_to_bp(meta) if iunit == "bp" else 1), iunit, f)
            xk = driver_changes(k, f)
            if xk is None:
                res["univariate"].append({"driver": k, "freq": f, "available": False})
                continue
            df = _frame(yk, {k: xk})
            row = {"driver": k, "freq": f, "available": True}
            for wn, yrs in YEARS.items():
                w = _window(df, yrs)
                r = ols_uni(w["y"].values, w[k].values)
                if r:
                    r.update({"start": w.index.min().date().isoformat(), "end": w.index.max().date().isoformat()})
                row[wn] = r
            if row.get("3y"):
                row["sentence"] = sentence(inst, DRIVERS[k], row["3y"]["beta"])
                row["driver_sd"] = round(float(_window(df, 3)[k].std()), 4)
            res["univariate"].append(row)
            res["stability"][k] = _stability(df, k)
        # multivariate models: the instrument's own frequency, and Brazil's monthly model with commodities
        for name, f, ks in [("model", freq, drv_model)] + ([("monthly_model", "M", MONTHLY_MODELS[code])] if code in MONTHLY_MODELS else []):
            yk = y if f == freq else changes(ser * (_to_bp(meta) if iunit == "bp" else 1), iunit, f)
            xs = {k: driver_changes(k, f) for k in ks}
            xs = {k: v for k, v in xs.items() if v is not None}
            if not xs:
                continue
            df = _frame(yk, xs)
            w = _window(df, 3)
            names = list(xs)
            m = ols_multi(w["y"].values, w[names].values)
            if not m:
                continue
            m.update({"freq": f, "drivers": names, "start": w.index.min().date().isoformat(), "end": w.index.max().date().isoformat(),
                      "driver_sd": {k: round(float(w[k].std()), 4) for k in names}})
            m["beta"] = [round(b, 4) for b in m["beta"]]
            m["se"] = [round(b, 4) for b in m["se"]]
            m["cov"] = [[round(c, 6) for c in r] for r in m["cov"]]
            m["resid_sd"], m["r2"], m["intercept"] = round(m["resid_sd"], 4), round(m["r2"], 3), round(m["intercept"], 4)
            res[name] = m
            if name == "model":
                res["attribution"] = _attribution(df, names, m, inst, f, last_obs=ser.index.max())
        out["instruments"][code] = res
    out["trades"] = trade_exposures(out)
    OUT.write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")) + "\n")
    return out


def trade_exposures(dr: dict) -> list[dict]:
    """For each open paper trade: the driver whose one-sd move changes P&L the most."""
    state = store.ROOT / "data" / "book" / "state.json"
    if not state.exists():
        return []
    st = json.loads(state.read_text())
    out = []
    for v in st.get("trades", []):
        if v.get("status") != "open":
            continue
        code = v["open"]["instrument"]
        mcode = PROXY_MODEL.get(code, code)
        inst = dr["instruments"].get(mcode)
        icfg = st["instruments"].get(code, {})
        fill = v["fill"]
        if not inst or not inst.get("available"):
            out.append({"trade_id": v["trade_id"], "instrument": code, "note": "no driver model for this instrument"})
            continue
        rows = []
        for u in inst["univariate"]:
            if not u.get("available") or not u.get("3y"):
                continue
            sd = u["driver_sd"]
            dmove = u["3y"]["beta"] * sd                   # instrument move for a one-sd driver move
            if icfg.get("kind") == "fx":
                pnl = fill["direction_sign"] * fill["notional_usd"] * dmove / 100.0
            else:
                pnl = -fill["direction_sign"] * fill["notional_usd"] * (fill.get("duration") or 0) * dmove / 10000.0
            rows.append({"driver": u["driver"], "freq": u["freq"], "driver_sd": sd, "instrument_move": round(dmove, 4),
                         "pnl_usd": round(pnl, 2), "r2": u["3y"]["r2"]})
        rows.sort(key=lambda r: -abs(r["pnl_usd"]))
        out.append({"trade_id": v["trade_id"], "instrument": code, "model": mcode, "direction": fill["direction_sign"],
                    "notional_usd": fill["notional_usd"], "biggest": rows[0] if rows else None, "all": rows})
    return out
