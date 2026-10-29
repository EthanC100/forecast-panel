"""Build the dashboard's data file (site/data.js) from this repo, gold-events, tension-index,
em-macro and a few public APIs. The site itself is static (site/index.html, app.js, style.css)
and reads ``window.PANEL_DATA`` from data.js, so it also works opened from disk.

Inputs
------
forecast-panel   data/tension_questions.yaml, data/panel_log.csv, data/aggregate_log.csv,
                 data/validation_summary.json, site/config.yaml, site/events.yaml
gold-events      data/forward_log.csv (my_prob_*, claude_prob_*, tension scores, gold model)
tension-index    data/tension_daily.csv (tension_index, gpr_nowcast)
em-macro         data/processed/daily_panel.csv (Y10_BR, Y10_MX, US10Y, FX_BR, FX_MX),
                 data/events/rate_decisions.csv, data/events/elections.csv,
                 results/repricing/signals_daily.csv, and the risk-model outputs when present
Polymarket       clob.polymarket.com/prices-history (daily market probability history)
Bundesbank       10y Bund yield, daily (api.statistiken.bundesbank.de)
ECB              long-term interest rates for France and Germany, monthly (data-api.ecb.europa.eu)

Every external fetch is optional: a failure leaves that block empty with a note, never a
failed build.
"""

from __future__ import annotations

import csv
import datetime as dt
import io
import json
import logging
import math
import os
from pathlib import Path

import numpy as np
import pandas as pd
import requests
import yaml

from forecast_panel import AGGREGATE_LOG_PATH, DATA_DIR, PANEL_LOG_PATH, ROOT, SOURCES
from forecast_panel.aggregate import brier
from forecast_panel.panel import load_panel_log
from forecast_panel.questions import load_questions, resolution_dates, resolved_outcomes
from forecast_panel.scoring import monday_snapshots, scorable
from forecast_panel.sources import _get

log = logging.getLogger(__name__)

SITE_DIR = ROOT / "site"
CONFIG_PATH = SITE_DIR / "config.yaml"
EVENTS_PATH = SITE_DIR / "events.yaml"
OUT_PATH = SITE_DIR / "data.js"

BUNDESBANK_10Y = ("https://api.statistiken.bundesbank.de/rest/download/BBSIS/"
                  "D.I.ZAR.ZI.EUR.S1311.B.A604.R10XX.R.A.A._Z._Z.A?format=csv&lang=en")
ECB_IRS = "https://data-api.ecb.europa.eu/service/data/IRS/M.FR+DE.L.L40.CI.0000.EUR.N.Z?format=csvdata&startPeriod={start}"
POLYMARKET_GAMMA = "https://gamma-api.polymarket.com/markets"
POLYMARKET_CLOB = "https://clob.polymarket.com/prices-history"

FORECASTERS = {"my_prob": "Me", "claude_prob": "Claude", "aggregate_extremized": "Panel aggregate"}


def _nan(x) -> bool:
    return x is None or (isinstance(x, float) and math.isnan(x))


def _f(x):
    """float or None (JSON-safe)."""
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(v) else round(v, 5)


def load_config() -> dict:
    with open(CONFIG_PATH) as f:
        return yaml.safe_load(f)


# --------------------------------------------------------------------------
# Other repositories
# --------------------------------------------------------------------------


class Repos:
    """Read a file from a sibling repo: a local checkout (<REPO>_DIR) or raw.githubusercontent.com."""

    def __init__(self, cfg: dict):
        self.cfg = cfg["repos"]
        self.notes: list[str] = []

    def text(self, repo: str, path: str) -> str | None:
        env = os.environ.get(repo.upper().replace("-", "_") + "_DIR")
        if env:
            p = Path(env) / path
            if p.exists():
                return p.read_text()
            self.notes.append(f"{repo}/{path}: not in local checkout {env}")
            return None
        c = self.cfg[repo]
        url = f"https://raw.githubusercontent.com/{c['owner']}/{repo}/{c['branch']}/{path}"
        try:
            return _get(url).text
        except Exception as exc:  # noqa: BLE001
            self.notes.append(f"{repo}/{path}: {exc}")
            return None

    def csv(self, repo: str, path: str, **kw) -> pd.DataFrame | None:
        t = self.text(repo, path)
        return pd.read_csv(io.StringIO(t), **kw) if t is not None else None


# --------------------------------------------------------------------------
# Questions and forecasts
# --------------------------------------------------------------------------


def polymarket_history(url: str, invert: bool) -> list[list]:
    """[[date, prob], ...] daily history of P(question) from the CLOB price history."""
    slug = url.rstrip("/").split("/")[-1].split("?")[0]
    items = _get(POLYMARKET_GAMMA, params={"slug": slug}).json()
    if not items:
        return []
    tokens = items[0].get("clobTokenIds")
    tokens = json.loads(tokens) if isinstance(tokens, str) else tokens
    hist = _get(POLYMARKET_CLOB, params={"market": tokens[0], "interval": "max", "fidelity": 1440}).json().get("history", [])
    out = {}
    for h in hist:
        d = dt.datetime.fromtimestamp(int(h["t"]), tz=dt.timezone.utc).strftime("%Y-%m-%d")
        p = float(h["p"])
        out[d] = round(1 - p if invert else p, 4)
    return [[d, p] for d, p in sorted(out.items())]


def forward_log_series(fwd: pd.DataFrame | None, column: str) -> list[list]:
    if fwd is None or column not in fwd.columns:
        return []
    g = fwd[["log_date", column]].dropna()
    return [[str(r.log_date)[:10], _f(getattr(r, column))] for r in g.itertuples()]


def latest_by_source(panel: pd.DataFrame, qid: str) -> dict:
    """Latest snapshot row per source for a question: {source: {prob, as_of, date, notes, ref}}."""
    g = panel[panel["question_id"] == qid]
    if g.empty:
        return {}
    last = g[g["date"] == g["date"].max()]
    out = {}
    for r in last.itertuples():
        out[r.source] = {"prob": _f(r.prob), "as_of": r.as_of if isinstance(r.as_of, str) else None,
                         "date": r.date, "notes": r.notes if isinstance(r.notes, str) else "",
                         "ref": r.ref if isinstance(r.ref, str) else ""}
    return out


def build_questions(cfg: dict, questions: list[dict], panel: pd.DataFrame, agg: pd.DataFrame,
                    fwd: pd.DataFrame | None, signals: pd.DataFrame | None, notes: list[str]) -> list[dict]:
    out = []
    for q in questions:
        qid = q["id"]
        ctx = (cfg.get("question_context") or {}).get(qid) or {"type": "conflict"}
        try:
            market_hist = polymarket_history(q.get("url", ""), bool(q.get("invert"))) if q.get("source") == "polymarket" else []
        except Exception as exc:  # noqa: BLE001
            notes.append(f"{qid}: Polymarket history failed: {exc}")
            market_hist = []
        # fall back to / extend with the logged snapshots
        logged = panel[(panel["question_id"] == qid) & (panel["source"] == "polymarket")].dropna(subset=["prob"])
        have = {d for d, _ in market_hist}
        for r in logged.itertuples():
            if r.date not in have:
                market_hist.append([r.date, _f(r.prob)])
        market_hist.sort()
        a = agg[agg["question_id"] == qid].sort_values("date") if not agg.empty else agg
        item = {
            "id": qid, "question": q["question"], "market": q.get("market"), "url": q.get("url"),
            "invert": bool(q.get("invert")), "resolution_date": str(q.get("resolution_date") or "")[:10],
            "resolved": bool(q.get("resolved")), "outcome": q.get("outcome") if q.get("outcome") in (0, 1) else None,
            "resolution_note": " ".join(str(q.get("resolution_note") or "").split()),
            "context": ctx,
            "market_history": market_hist,
            "latest": latest_by_source(panel, qid),
            "my_history": forward_log_series(fwd, f"my_prob_{qid}"),
            "claude_history": forward_log_series(fwd, f"claude_prob_{qid}"),
            "aggregate_history": [[r.date, _f(r.aggregate_plain), _f(r.aggregate_extremized)] for r in a.itertuples()] if len(a) else [],
        }
        if ctx.get("type") == "election" and signals is not None:
            for key in ("odds", "polls"):
                col = ctx.get(key)
                if col and col in signals.columns:
                    s = signals[col].dropna()
                    item[f"{key}_history"] = [[str(i)[:10], _f(v)] for i, v in s.items()]
                else:
                    item[f"{key}_history"] = []
                    notes.append(f"{qid}: {key} column {col!r} not in em-macro signals_daily.csv")
        out.append(item)
    return out


# --------------------------------------------------------------------------
# Scorecard: points = 100 x (market Brier - forecaster Brier) per resolved question
# --------------------------------------------------------------------------


def build_scorecard(questions: list[dict], panel: pd.DataFrame, agg: pd.DataFrame) -> dict:
    from forecast_panel.scoring import long_aggregates
    outcomes, res_dates = resolved_outcomes(questions), resolution_dates(questions)
    titles = {q["id"]: q["question"] for q in questions}
    both = pd.concat([panel[["date", "question_id", "source", "prob"]], long_aggregates(agg)], ignore_index=True) if not agg.empty else panel[["date", "question_id", "source", "prob"]]
    weekly = monday_snapshots(both)
    scored = scorable(weekly, outcomes, res_dates)
    market = scored[(scored["source"] == "polymarket") & scored["prob"].notna()][["date", "question_id", "prob"]].rename(columns={"prob": "p_market"})
    result = {"forecasters": {}, "weeks_logged": int(weekly["date"].nunique()) if not weekly.empty else 0,
              "resolved": [{"id": k, "question": titles[k], "outcome": v, "resolution_date": res_dates.get(k)} for k, v in outcomes.items()]}
    for f, label in FORECASTERS.items():
        mine = scored[(scored["source"] == f) & scored["prob"].notna()][["date", "question_id", "prob", "outcome"]]
        m = mine.merge(market, on=["date", "question_id"])
        per_q, running = [], 0.0
        for qid in sorted(outcomes, key=lambda k: (res_dates.get(k, ""), k)):
            g = m[m["question_id"] == qid]
            if g.empty:
                per_q.append({"id": qid, "resolution_date": res_dates.get(qid), "n_weeks": 0, "brier": None,
                              "market_brier": None, "points": None, "running_total": round(running, 2)})
                continue
            b, bm = brier(g["prob"], g["outcome"]), brier(g["p_market"], g["outcome"])
            pts = 100.0 * (bm - b)
            running += pts
            per_q.append({"id": qid, "resolution_date": res_dates.get(qid), "n_weeks": int(len(g)), "brier": round(b, 4),
                          "market_brier": round(bm, 4), "points": round(pts, 2), "running_total": round(running, 2)})
        # calibration over every scored weekly forecast
        bins = np.linspace(0, 1, 11)
        cal = []
        if len(mine):
            idx = np.clip(np.digitize(mine["prob"].values, bins[1:-1]), 0, 9)
            for b_i in range(10):
                sel = mine[idx == b_i]
                if len(sel):
                    cal.append({"bin": f"{bins[b_i]:.1f}-{bins[b_i+1]:.1f}", "n": int(len(sel)),
                                "mean_forecast": round(float(sel["prob"].mean()), 3), "observed": round(float(sel["outcome"].mean()), 3)})
        # current open forecasts, for the "pending" view
        open_rows = both[(both["source"] == f) & both["prob"].notna() & ~both["question_id"].isin(outcomes)]
        latest_open = {}
        for qid, g in open_rows.groupby("question_id"):
            latest_open[qid] = _f(g.sort_values("date")["prob"].iloc[-1])
        result["forecasters"][f] = {"label": label, "per_question": per_q, "total_points": round(running, 2),
                                    "n_scored_weeks": int(len(m)), "calibration": cal, "open": latest_open}
    return result


# --------------------------------------------------------------------------
# Indicators and countries
# --------------------------------------------------------------------------


def tension_block(repos: Repos, days: int = 90) -> dict:
    df = repos.csv("tension-index", "data/tension_daily.csv", usecols=["date", "tension_index", "gpr_nowcast", "tension_index_threats", "tension_index_acts"])
    if df is None:
        return {"series": [], "note": "tension-index unavailable"}
    df = df.dropna(subset=["tension_index"]).sort_values("date").tail(days)
    return {"series": [[r.date, _f(r.tension_index), _f(r.gpr_nowcast), _f(r.tension_index_threats), _f(r.tension_index_acts)] for r in df.itertuples()],
            "note": "GPR-scale geopolitical tension score from GDELT (tension_index) and the implied daily GPR print (gpr_nowcast); 1985-2019 average = 100."}


def gold_block(fwd: pd.DataFrame | None) -> dict:
    if fwd is None:
        return {"rows": [], "note": "gold-events forward_log.csv unavailable"}
    cols = ["log_date", "model_version", "data_as_of", "pred_gold_5d", "pred_silver_5d", "realised_gold_5d", "realised_silver_5d",
            "realised_through", "gpr_level", "gpr_change_week", "my_tension_score", "claude_tension_score", "note"]
    rows = []
    for r in fwd.sort_values("log_date").itertuples():
        d = {c: getattr(r, c, None) for c in cols if c in fwd.columns}
        rows.append({k: (_f(v) if isinstance(v, (int, float, np.floating)) else (None if (isinstance(v, float) and math.isnan(v)) else (str(v) if v is not None and v == v else None))) for k, v in d.items()})
    return {"rows": rows, "note": "Frozen gold-events model: expected 5-day log return of gold and silver from last week's control changes (placeholder input, see gold-events README)."}


def _series(df: pd.DataFrame, col: str, days: int) -> list[list]:
    if col not in df.columns:
        return []
    s = df[["date", col]].dropna().sort_values("date").tail(days)
    return [[str(r.date)[:10], _f(getattr(r, col))] for r in s.itertuples()]


def bundesbank_10y(days: int) -> tuple[list[list], str]:
    text = _get(BUNDESBANK_10Y).text
    rows = []
    for line in text.splitlines():
        parts = line.split(",")
        if len(parts) >= 2 and len(parts[0]) == 10 and parts[0][4] == "-":
            try:
                rows.append([parts[0], round(float(parts[1]), 3)])
            except ValueError:
                pass
    return rows[-days:], "Deutsche Bundesbank, yield on listed Federal securities, 10-year residual maturity, daily"


def ecb_long_rates(start_year: int) -> tuple[dict[str, list[list]], str]:
    text = _get(ECB_IRS.format(start=f"{start_year}-01")).text
    out: dict[str, list[list]] = {"FR": [], "DE": []}
    for r in csv.DictReader(io.StringIO(text)):
        c = r.get("REF_AREA")
        if c in out and r.get("OBS_VALUE"):
            out[c].append([r["TIME_PERIOD"] + "-01", round(float(r["OBS_VALUE"]), 3)])
    for v in out.values():
        v.sort()
    return out, "ECB, long-term interest rate for convergence purposes (10-year government bond benchmark), monthly average"


def risk_model_block(repos: Repos, cfg: dict, country_iso3: str, country_name: str) -> dict:
    paths = cfg["em_macro_risk_model"]
    files = {k: repos.csv("em-macro", p) for k, p in paths.items()}
    missing = [paths[k] for k, v in files.items() if v is None]
    if missing:
        # a failed fetch of a missing file is expected; do not keep it as a build note
        repos.notes[:] = [n for n in repos.notes if not any(m in n for m in missing)]
        return {"status": "not_built", "message": "model not yet built", "expected_files": list(paths.values())}

    def mine(df):
        for col in ("country", "iso3"):
            if col in df.columns:
                return df[df[col].astype(str).str.lower().isin([country_iso3.lower(), country_name.lower()])]
        return df.iloc[0:0]

    fv, fa, si = (mine(files[k]) for k in ("fair_value", "factors", "similar"))
    if fv.empty:
        return {"status": "not_built", "message": "model not yet built for this country", "expected_files": list(paths.values())}
    latest_date = str(fv["date"].max())[:10]
    fv_l, fa_l, si_l = fv[fv["date"].astype(str).str[:10] == latest_date], fa[fa["date"].astype(str).str[:10] == latest_date], si[si["date"].astype(str).str[:10] == latest_date]
    return {"status": "built", "date": latest_date,
            "fair_value": [{k: (_f(v) if isinstance(v, (int, float, np.floating)) else str(v)) for k, v in r.items()} for r in fv_l.to_dict("records")],
            "factors": [{k: (_f(v) if isinstance(v, (int, float, np.floating)) else str(v)) for k, v in r.items()} for r in fa_l.to_dict("records")],
            "similar_cases": [{k: (_f(v) if isinstance(v, (int, float, np.floating)) else str(v)) for k, v in r.items()} for r in si_l.to_dict("records")]}


def build_countries(cfg: dict, repos: Repos, notes: list[str]) -> dict:
    days = int(cfg.get("history_days", 730))
    panel = repos.csv("em-macro", "data/processed/daily_panel.csv")
    rates = repos.csv("em-macro", "data/events/rate_decisions.csv")
    elections = repos.csv("em-macro", "data/events/elections.csv")
    with open(EVENTS_PATH) as f:
        events = (yaml.safe_load(f) or {}).get("events") or []
    try:
        bund, bund_src = bundesbank_10y(days)
    except Exception as exc:  # noqa: BLE001
        notes.append(f"Bundesbank 10y: {exc}")
        bund, bund_src = [], ""
    try:
        ecb, ecb_src = ecb_long_rates(dt.date.today().year - 3)
    except Exception as exc:  # noqa: BLE001
        notes.append(f"ECB long-term rates: {exc}")
        ecb, ecb_src = {"FR": [], "DE": []}, ""
    today = dt.date.today().isoformat()
    out = {}
    for key, c in cfg["countries"].items():
        block = {"name": c["name"], "iso3": c["iso3"], "yield": {}, "spread": {}, "fx": {}, "events": [], "recent_decisions": [], "last_election": None}
        suf = c.get("em_macro_suffix")
        if suf and panel is not None:
            y = _series(panel, f"Y10_{suf}", days)
            us = dict(_series(panel, "US10Y", days * 2))
            block["yield"] = {"series": y, "label": f"{c['name']} 10-year yield (%)", "source": "em-macro daily_panel.csv"}
            block["spread"] = {"series": [[d, round(v - us[d], 3)] for d, v in y if d in us and us[d] is not None],
                               "label": f"Spread over {c['spread_over']} (pp)", "source": "em-macro: Y10 minus US10Y (FRED DGS10)"}
            if c.get("currency"):
                block["fx"] = {"series": _series(panel, f"FX_{suf}", days), "label": c["currency"], "source": "em-macro daily_panel.csv (FRED H.10)"}
        elif key == "france":
            fr, de_m = ecb.get("FR", []), dict(ecb.get("DE", []))
            block["yield"] = {"series": fr, "label": "France 10-year yield (%, monthly)", "source": ecb_src, "frequency": "monthly"}
            block["spread"] = {"series": [[d, round(v - de_m[d], 3)] for d, v in fr if d in de_m],
                               "label": "Spread over Germany (pp, monthly)", "source": "ECB long-term rates, France minus Germany", "frequency": "monthly"}
            block["germany_daily"] = {"series": bund, "label": "Germany 10-year Bund yield (%, daily)", "source": bund_src}
        if rates is not None and "country" in rates.columns:
            g = rates[rates["country"] == c["name"]].sort_values("announce_date").tail(6)
            block["recent_decisions"] = [{"date": str(r.announce_date)[:10], "decision": str(r.decision), "rate_after": _f(r.rate_after_pct),
                                          "change_bp": _f(r.change_bp)} for r in g.itertuples()]
        if elections is not None and "country" in elections.columns:
            g = elections[elections["country"] == c["name"]].sort_values("vote_date")
            if len(g):
                r = g.iloc[-1]
                block["last_election"] = {"date": str(r["vote_date"])[:10], "election": str(r["election"]), "winner": str(r.get("winner", "")),
                                          "poll_margin_pp": _f(r.get("poll_margin_pp")), "actual_margin_pp": _f(r.get("actual_margin_pp")),
                                          "odds_prob_favourite": _f(r.get("odds_prob_favourite"))}
        block["events"] = sorted([e for e in events if e.get("country") == key and str(e.get("date")) >= today], key=lambda e: str(e["date"]))
        for e in block["events"]:
            e["date"] = str(e["date"])
        block["risk_model"] = risk_model_block(repos, cfg, c["iso3"], c["name"])
        out[key] = block
    return out


# --------------------------------------------------------------------------
# Entry point
# --------------------------------------------------------------------------


def build(out_path: Path = OUT_PATH) -> dict:
    cfg = load_config()
    repos = Repos(cfg)
    notes: list[str] = []
    questions = load_questions()
    panel = load_panel_log(PANEL_LOG_PATH)
    agg = pd.read_csv(AGGREGATE_LOG_PATH, dtype={"date": str, "question_id": str}) if AGGREGATE_LOG_PATH.exists() else pd.DataFrame(columns=["date", "question_id", "aggregate_plain", "aggregate_extremized"])
    fwd = repos.csv("gold-events", "data/forward_log.csv")
    if fwd is not None:
        fwd["log_date"] = pd.to_datetime(fwd["log_date"]).dt.strftime("%Y-%m-%d")
    signals = repos.csv("em-macro", "results/repricing/signals_daily.csv", index_col=0) if any(
        (v or {}).get("type") == "election" for v in (cfg.get("question_context") or {}).values()) else None
    validation = json.loads((DATA_DIR / "validation_summary.json").read_text()) if (DATA_DIR / "validation_summary.json").exists() else None
    data = {
        "generated": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "sources": SOURCES,
        "questions": build_questions(cfg, questions, panel, agg, fwd, signals, notes),
        "scorecard": build_scorecard(questions, panel, agg),
        "tension": tension_block(repos),
        "gold": gold_block(fwd),
        "countries": build_countries(cfg, repos, notes),
        "validation": validation,
        "notes": notes + repos.notes,
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("window.PANEL_DATA = " + json.dumps(data, separators=(",", ":"), ensure_ascii=False) + ";\n")
    return data
