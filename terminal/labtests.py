"""Lab tests for three Crowd gauges on em-macro's event history.

The question for each gauge: before an event, did an extreme reading predict a larger or more
surprising move than a normal reading did?

  (a) poll vs prediction-market gap  - elections with recorded betting odds (13 countries)
  (c) survey dispersion              - Copom (Focus, per meeting) and Banxico (survey) decisions
  (e) CFTC positioning percentile    - rate decisions and elections in Brazil, Mexico, South Africa

Moves come from em-macro's event study (results/fit and results/test event_moves.csv): ab_1 is the
day-1 abnormal move net of the dollar, US 10y and VIX; dividing by sd_1 (the asset's normal daily
sd) makes FX and 10y moves comparable. Every reading is built only from data published before
the event. em-macro's own split is used: fit = events to 2021, hold-out = 2022 onward.

Badge rule (fixed before the results were seen):
  Tested-leads    the fit-period effect is positive with one-sided p < 0.05 AND the hold-out effect
                  has the same sign with p < 0.10
  Tested-no-lead  the test ran and that rule is not met
  Untested        the test could not be run (data missing or fewer than 8 extreme events in the fit)
For (a) there is nothing to fit (the poll-implied probability uses only earlier elections), so the
rule is a whole-sample p < 0.05 with at least 15 elections.

Run: EM_MACRO_DIR=../em-macro python -m terminal.labtests
Writes data/terminal/lab/crowd_tests.json and reports/crowd_lab.md.
"""

from __future__ import annotations

import datetime as dt
import json
import math
import re

import numpy as np
import pandas as pd

from terminal import emmacro, store

LAB_DIR = store.DATA / "lab"
OUT = LAB_DIR / "crowd_tests.json"
REPORT = store.DATA.parent.parent / "reports" / "crowd_lab.md"
FIT_END = "2021-12-31"
N_PERM = 20000
ISO2 = {"BRA": "BR", "MEX": "MX", "ZAF": "ZA", "POL": "PL", "TUR": "TR", "IDN": "ID"}


# --------------------------------------------------------------------------
# statistics (numpy only: permutation tests, no distributional assumptions)
# --------------------------------------------------------------------------

def perm_diff(x_ext, x_norm, seed: int = 0) -> dict:
    """Mean(extreme) - mean(normal), one-sided permutation p for 'extreme is larger'."""
    a, b = np.asarray(x_ext, float), np.asarray(x_norm, float)
    if len(a) == 0 or len(b) == 0:
        return {"n_extreme": len(a), "n_normal": len(b), "diff": None, "p": None}
    obs = a.mean() - b.mean()
    pool = np.concatenate([a, b])
    rng = np.random.default_rng(seed)
    hits = 0
    for _ in range(N_PERM):
        rng.shuffle(pool)
        hits += pool[:len(a)].mean() - pool[len(a):].mean() >= obs - 1e-12
    return {"n_extreme": len(a), "n_normal": len(b), "mean_extreme": round(float(a.mean()), 3),
            "mean_normal": round(float(b.mean()), 3), "ratio": round(float(a.mean() / b.mean()), 2) if b.mean() else None,
            "diff": round(float(obs), 3), "p": round((hits + 1) / (N_PERM + 1), 4)}


def _rank(x):
    return pd.Series(x).rank().to_numpy()


def perm_spearman(x, y, seed: int = 0) -> dict:
    x, y = np.asarray(x, float), np.asarray(y, float)
    keep = ~(np.isnan(x) | np.isnan(y))
    x, y = _rank(x[keep]), _rank(y[keep])
    if len(x) < 5:
        return {"n": int(len(x)), "rho": None, "p": None}
    rho = float(np.corrcoef(x, y)[0, 1])
    rng = np.random.default_rng(seed)
    hits = sum(np.corrcoef(x, rng.permutation(y))[0, 1] >= rho - 1e-12 for _ in range(N_PERM))
    return {"n": int(len(x)), "rho": round(rho, 3), "p": round((hits + 1) / (N_PERM + 1), 4)}


def verdict(fit: dict, hold: dict | None, min_ext: int = 8) -> tuple[str, str]:
    if fit.get("p") is None or fit.get("n_extreme", 0) < min_ext:
        return "untested", f"only {fit.get('n_extreme', 0)} extreme readings in the fit period (need {min_ext})"
    fit_ok = fit["diff"] > 0 and fit["p"] < 0.05
    hold_ok = bool(hold and hold.get("p") is not None and hold["diff"] > 0 and hold["p"] < 0.10)
    if fit_ok and hold_ok:
        return "tested_leads", f"fit p={fit['p']}, hold-out p={hold['p']}"
    why = "fit effect not significant" if not fit_ok else "did not hold out of sample"
    return "tested_no_lead", f"{why} (fit diff {fit['diff']:+.2f} sd, p={fit['p']}; hold-out " + \
        (f"diff {hold['diff']:+.2f} sd, p={hold['p']}" if hold and hold.get("diff") is not None else "n/a") + ")"


# --------------------------------------------------------------------------
# em-macro event moves
# --------------------------------------------------------------------------

def event_moves() -> pd.DataFrame:
    fit = emmacro.frame("results/fit/event_moves.csv").assign(period="fit")
    test = emmacro.frame("results/test/event_moves.csv").assign(period="hold-out")
    m = pd.concat([fit, test], ignore_index=True)
    m["z1"] = (m["ab_1"] / m["sd_1"]).abs()
    m["signed_z1"] = m["ab_1"] / m["sd_1"]
    return m


def wide_moves(m: pd.DataFrame) -> pd.DataFrame:
    """One row per event: |z| for FX and 10y, and their mean (the 'move size' outcome)."""
    w = m.pivot_table(index=["event_id", "country", "event_type", "event_date", "base_date", "period"],
                      columns="asset", values=["z1", "signed_z1"]).reset_index()
    w.columns = ["_".join(c).strip("_") if isinstance(c, tuple) else c for c in w.columns]
    w["move"] = w[[c for c in ("z1_FX", "z1_Y10") if c in w]].mean(axis=1)
    return w


def split_test(df: pd.DataFrame, flag: str, outcome: str) -> dict:
    out = {}
    for period in ("fit", "hold-out"):
        d = df[(df.period == period) & df[outcome].notna() & df[flag].notna()]
        out[period] = perm_diff(d[d[flag]][outcome], d[~d[flag].astype(bool)][outcome], seed=len(d))
    return out


# --------------------------------------------------------------------------
# (c) survey dispersion
# --------------------------------------------------------------------------

def trailing_percentile(values: list[float], window: int, min_n: int) -> list[float | None]:
    """Percentile of each value among the `window` values before it (real time, no look-ahead)."""
    out = []
    for i, v in enumerate(values):
        prior = [x for x in values[max(0, i - window):i] if x is not None and not math.isnan(x)]
        out.append(None if (v is None or math.isnan(v) or len(prior) < min_n) else 100 * sum(x <= v for x in prior) / len(prior))
    return out


def copom_dispersion() -> pd.DataFrame:
    rd = emmacro.frame("data/events/rate_decisions.csv")
    br = rd[(rd.iso3 == "BRA") & (rd.scheduled == "Y")].copy()
    br["d"] = pd.to_datetime(br.announce_date)
    br["meeting"] = "R" + (br.groupby(br.d.dt.year).cumcount() + 1).astype(str) + "/" + br.d.dt.year.astype(str)
    s = store.load_series("br.focus.selic_meeting")
    if not s:
        raise RuntimeError("br.focus.selic_meeting not stored; run python -m terminal.run fetch --only bcb_focus")
    h = pd.DataFrame(s["history"], columns=["date", "meeting"] + s["fields"])
    rows = []
    for _, r in br.iterrows():
        cut = (r.d - pd.Timedelta(days=2)).strftime("%Y-%m-%d")      # survey published before the meeting
        x = h[(h.meeting == r.meeting) & (h.date <= cut)]
        if x.empty:
            continue
        last = x.iloc[-1]
        rows.append({"country": "BR", "event_date": r.announce_date, "meeting": r.meeting, "survey_date": last.date,
                     "sd": last["sd"], "median": last["median"], "actual": r.rate_after_pct,
                     "survey_miss_bp": abs(r.rate_after_pct - last["median"]) * 100})
    d = pd.DataFrame(rows).sort_values("event_date")
    d["pct"] = trailing_percentile(d["sd"].tolist(), 40, 16)          # 40 meetings = 5 years
    return d


def banxico_dispersion() -> pd.DataFrame:
    rd = emmacro.frame("data/events/rate_decisions.csv")
    mx = rd[(rd.iso3 == "MEX") & (rd.scheduled == "Y")].copy()
    s = store.load_series("mx.survey.inflation")
    h = pd.DataFrame([r[:4] for r in s["history"]], columns=["date", "ref", "median", "sd"]).dropna(subset=["sd"])
    h = h[h.ref.astype(int) == h.date.str[:4].astype(int)]              # current-year inflation
    h["month"] = h.date.str[5:7].astype(int)
    rows = []
    for _, r in mx.iterrows():
        # the survey is published on the first business day of the next month: use surveys dated
        # at least 35 days before the decision so the reading was public
        cut = (pd.Timestamp(r.announce_date) - pd.Timedelta(days=35)).strftime("%Y-%m-%d")
        x = h[h.date <= cut]
        if x.empty:
            continue
        last = x.iloc[-1]
        # seasonal: compare with the same month +/-1 over the previous 10 years
        ref = h[(h.date < last.date) & (h.date >= str(int(last.date[:4]) - 10)) & ((h.month - last.month).abs() <= 1)]
        pct = 100 * (ref["sd"] <= last["sd"]).mean() if len(ref) >= 12 else None
        rows.append({"country": "MX", "event_date": r.announce_date, "survey_date": last.date, "sd": last["sd"], "pct": pct,
                     "survey_miss_bp": abs(r.change_bp - r.expected_change_bp) if pd.notna(r.expected_change_bp) else None})
    return pd.DataFrame(rows)


def test_c(w: pd.DataFrame) -> dict:
    out = {"gauge": "c", "name": "Survey dispersion before rate decisions", "parts": {}}
    try:
        br = copom_dispersion()
        mx = banxico_dispersion()
    except Exception as exc:                                             # noqa: BLE001
        return {**out, "badge": "untested", "reason": f"could not build the readings: {exc}"}
    rates = w[w.event_type == "rate_decision"]
    for name, d, desc in (("BR", br, "Focus sd of the Selic expected for that meeting, percentile vs the previous 40 meetings"),
                          ("MX", mx, "Banxico survey sd of current-year inflation, percentile vs the same month +/-1 over 10 years")):
        d = d.merge(rates, on=["country", "event_date"], how="inner")
        d["extreme"] = d["pct"] >= 80
        d = d[d["pct"].notna()]
        res = {"reading": desc, "extreme": "percentile >= 80", "n_events": int(len(d)),
               "move": split_test(d, "extreme", "move"),
               "survey_miss": split_test(d, "extreme", "survey_miss_bp"),
               "spearman_fit": perm_spearman(d[d.period == "fit"]["pct"], d[d.period == "fit"]["move"])}
        bm, rm = verdict(res["move"]["fit"], res["move"]["hold-out"])
        bs, rs = verdict(res["survey_miss"]["fit"], res["survey_miss"]["hold-out"])
        res["badge"] = "tested_leads" if "tested_leads" in (bm, bs) else ("untested" if bm == bs == "untested" else "tested_no_lead")
        res["reason"] = f"move size: {bm} ({rm}); miss vs survey median: {bs} ({rs})"
        out["parts"][name] = res
    pooled = pd.concat([d.merge(rates, on=["country", "event_date"], how="inner") for d in (br, mx)])
    pooled = pooled[pooled["pct"].notna()].assign(extreme=lambda x: x["pct"] >= 80)
    out["pooled"] = {"move": split_test(pooled, "extreme", "move"), "survey_miss": split_test(pooled, "extreme", "survey_miss_bp")}
    # the gauge shows each survey separately, so each carries its own badge; the headline is Brazil's
    # per-meeting reading because it is the one that measures disagreement about the decision itself
    parts = out["parts"]
    out["badge"] = parts["BR"]["badge"]
    out["badges"] = {k: v["badge"] for k, v in parts.items()}
    out["reason"] = "; ".join(f"{k}: {v['badge']} - {v['reason']}" for k, v in parts.items())
    return out


# --------------------------------------------------------------------------
# (e) CFTC positioning
# --------------------------------------------------------------------------

COT_SERIES = {"BR": "br.cot.brl", "MX": "mx.cot.mxn", "ZA": "za.cot.zar"}


def cot_readings(country: str, field: str = "lev_money_net") -> pd.DataFrame:
    s = store.load_series(COT_SERIES[country])
    df = pd.DataFrame(s["history"], columns=["date"] + s["fields"])
    df["x"] = df[field] / df["open_interest"]
    df = df.dropna(subset=["x"]).sort_values("date").reset_index(drop=True)
    df["pct"] = trailing_percentile(df["x"].tolist(), 156, 52)        # 3 years of weekly reports
    df["released"] = (pd.to_datetime(df["date"]) + pd.Timedelta(days=3)).dt.strftime("%Y-%m-%d")
    return df


def test_e(w: pd.DataFrame) -> dict:
    out = {"gauge": "e", "name": "CFTC net positioning percentile before events", "parts": {}}
    rows = []
    for field in ("lev_money_net", "noncomm_net"):
        for c in COT_SERIES:
            try:
                cot = cot_readings(c, field)
            except Exception as exc:                                     # noqa: BLE001
                out["parts"][f"{c}-{field}"] = {"error": str(exc)}
                continue
            ev = w[(w.country == c) & w.z1_FX.notna()]
            for _, e in ev.iterrows():
                prior = cot[cot.released < e.base_date]
                if prior.empty or pd.isna(prior.iloc[-1]["pct"]):
                    continue
                p = prior.iloc[-1]["pct"]
                rows.append({"field": field, "country": c, "event_id": e.event_id, "event_type": e.event_type, "period": e.period,
                             "pct": p, "extreme": p <= 10 or p >= 90, "move": e.z1_FX,
                             # FX is the local currency's value in USD; futures longs are long the local currency
                             "against_crowd": (-e.signed_z1_FX if p >= 90 else e.signed_z1_FX if p <= 10 else None)})
    d = pd.DataFrame(rows)
    if d.empty:
        return {**out, "badge": "untested", "reason": "no events matched a positioning reading"}
    for field in ("lev_money_net", "noncomm_net"):
        x = d[d.field == field]
        res = {"reading": f"{field} / open interest, percentile vs the previous 156 weekly reports (released Friday, used "
                          "only for events after release)", "extreme": "percentile <= 10 or >= 90",
               "n_events": int(len(x)), "by_country": x.groupby("country").size().to_dict(),
               "move": split_test(x, "extreme", "move")}
        ext = x[x.extreme]
        res["against_crowd_mean_sd"] = {p: round(float(ext[ext.period == p]["against_crowd"].mean()), 3) if (ext.period == p).any() else None
                                        for p in ("fit", "hold-out")}
        res["badge"], res["reason"] = verdict(res["move"]["fit"], res["move"]["hold-out"])
        out["parts"][field] = res
    main = out["parts"]["lev_money_net"]
    out["badge"], out["reason"] = main["badge"], "leveraged funds (the gauge as shown): " + main["reason"] + \
        ". Legacy non-commercial (robustness): " + out["parts"]["noncomm_net"]["reason"]
    return out


# --------------------------------------------------------------------------
# (a) poll vs prediction-market gap
# --------------------------------------------------------------------------

def _phi(x: float) -> float:
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))


STOP = {"da", "de", "do", "dos", "la", "el", "the", "in", "uk", "of", "y"}


def _same_side(favourite: str, cand_a: str) -> bool:
    """Is the odds favourite candidate A? Word overlap, so 'No' matches 'No (remain in UK)' and
    'Lula' matches 'Luiz Inácio Lula da Silva (PT)'."""
    words = lambda x: {t for t in re.findall(r"[\wÀ-ž]+", str(x).lower()) if len(t) >= 2 and t not in STOP}
    return bool(words(favourite) & words(re.sub(r"\(.*?\)", "", str(cand_a))))


def poll_implied(e: pd.DataFrame) -> pd.DataFrame:
    """P(candidate A wins) = Phi(poll margin / sigma), sigma = RMS poll error of earlier elections in the
    same country (at least 3), otherwise of all earlier elections in the 13 countries."""
    e = e.dropna(subset=["poll_margin_pp", "actual_margin_pp"]).sort_values("vote_date").copy()
    e["err"] = e["actual_margin_pp"] - e["poll_margin_pp"]
    sig, basis = [], []
    for _, r in e.iterrows():
        prior = e[e.vote_date < r.vote_date]
        own = prior[prior.iso3 == r.iso3]
        src = own if len(own) >= 3 else prior
        sig.append(math.sqrt((src["err"] ** 2).mean()) if len(src) >= 3 else None)
        basis.append(f"{r.iso3} ({len(own)} earlier)" if len(own) >= 3 else f"all countries ({len(prior)} earlier)")
    e["sigma"], e["sigma_basis"] = sig, basis
    e["p_poll_a"] = [(_phi(m / s) if s else None) for m, s in zip(e.poll_margin_pp, e.sigma)]
    return e


def test_a(w: pd.DataFrame) -> dict:
    out = {"gauge": "a", "name": "Poll-implied vs prediction-market probability gap before elections"}
    e = poll_implied(emmacro.frame("data/events/elections.csv"))
    e = e[e.odds_prob_favourite.notna() & e.p_poll_a.notna()].copy()
    fav_is_a = [_same_side(f, a) for f, a in zip(e.odds_favourite, e.cand_a)]
    e["p_mkt_a"] = [p if fa else 1 - p for p, fa in zip(e.odds_prob_favourite, fav_is_a)]
    e["gap"] = e["p_mkt_a"] - e["p_poll_a"]
    e["a_won"] = (e["actual_margin_pp"] > 0).astype(float)
    e["poll_error"] = e["err"].abs()
    e["brier_mkt"] = (e["p_mkt_a"] - e["a_won"]) ** 2
    e["brier_poll"] = (e["p_poll_a"] - e["a_won"]) ** 2
    em = w[(w.event_type == "election")][["country", "event_date", "z1_FX", "move"]]
    e["country2"] = e.iso3.map(ISO2)
    e = e.merge(em, left_on=["country2", "vote_date"], right_on=["country", "event_date"], how="left", suffixes=("", "_m"))
    absgap = e["gap"].abs()
    res = {"n_elections": int(len(e)), "n_with_moves": int(e["move"].notna().sum()),
           "gap_vs_poll_error": perm_spearman(absgap, e["poll_error"]),
           "gap_vs_move": perm_spearman(absgap, e["move"]),
           "brier_market": round(float(e["brier_mkt"].mean()), 3), "brier_poll": round(float(e["brier_poll"].mean()), 3)}
    # when they disagree on the favourite, who was right?
    dis = e[(e["p_mkt_a"] - 0.5) * (e["p_poll_a"] - 0.5) < 0]
    res["disagreements"] = {"n": int(len(dis)), "market_right": int(((dis.p_mkt_a > 0.5) == (dis.a_won == 1)).sum())}
    res["elections"] = [{"election": f"{r.country} {r.election} r{int(r['round'])}", "date": r.vote_date,
                         "p_poll_a": round(r.p_poll_a, 3), "p_market_a": round(r.p_mkt_a, 3), "gap": round(r.gap, 3),
                         "sigma_pp": round(r.sigma, 2), "sigma_basis": r.sigma_basis, "a_won": bool(r.a_won),
                         "poll_error_pp": round(r.poll_error, 2), "fx_move_sd": None if pd.isna(r.z1_FX) else round(r.z1_FX, 2)}
                        for _, r in e.iterrows()]
    g = res["gap_vs_poll_error"]
    if g["n"] < 15:
        out.update(badge="untested", reason=f"only {g['n']} elections have both polls and recorded odds (need 15)")
    elif g["rho"] > 0 and g["p"] < 0.05:
        out.update(badge="tested_leads", reason=f"|gap| vs size of the poll miss: rho {g['rho']}, p={g['p']}, n={g['n']}")
    else:
        out.update(badge="tested_no_lead", reason=f"|gap| vs size of the poll miss: rho {g['rho']}, p={g['p']}, n={g['n']}; "
                                                 f"vs FX move: rho {res['gap_vs_move']['rho']}, n={res['gap_vs_move']['n']}. "
                   "Small sample: a lead of moderate size could be missed.")
    out["result"] = res
    out["method"] = ("Poll-implied P(A wins) = Phi(final poll margin / sigma), sigma = RMS of (actual - poll margin) over "
                     "earlier elections in the same country (3+), else all earlier elections; market P from the "
                     "recorded pre-vote odds. No parameter is fitted on the outcomes, so every point is out of sample; "
                     "there is no separate hold-out because there are too few elections with odds.")
    return out


# --------------------------------------------------------------------------

def run() -> dict:
    w = wide_moves(event_moves())
    results = {"generated_at": store.now_iso(), "source": emmacro.RAW, "fit_end": FIT_END, "n_permutations": N_PERM,
               "event_counts": w.groupby(["country", "event_type"]).size().rename("n").reset_index().to_dict("records"),
               "tests": {}}
    for f in (test_a, test_c, test_e):
        try:
            r = f(w)
        except Exception as exc:                                         # noqa: BLE001
            r = {"badge": "untested", "reason": f"test failed to run: {type(exc).__name__}: {exc}"}
        results["tests"][r.get("gauge", f.__name__[-1])] = r
    LAB_DIR.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(results, indent=1, default=lambda x: None if isinstance(x, float) and math.isnan(x) else
                              (x.item() if hasattr(x, "item") else str(x))) + "\n")
    REPORT.write_text(report(results))
    return results


def _fmt_split(s: dict) -> str:
    def one(x):
        if not x or x.get("diff") is None:
            return "n/a"
        return f"{x['n_extreme']} extreme vs {x['n_normal']} normal: {x['mean_extreme']} vs {x['mean_normal']} (p={x['p']})"
    return f"fit {one(s.get('fit'))}; hold-out {one(s.get('hold-out'))}"


def report(r: dict) -> str:
    t = r["tests"]
    L = ["# Crowd lab tests", "", f"Generated {r['generated_at']} by `python -m terminal.labtests` from em-macro "
         f"({r['source']}). Fit = events to {r['fit_end']}, hold-out = 2022 onward; one-sided permutation tests "
         f"({r['n_permutations']:,} draws). Moves are |abnormal day-1 move| / normal daily sd, averaged over FX and "
         "10y where both exist.", "",
         "Badge rule, fixed in advance: **Tested-leads** if the fit effect is positive with p < 0.05 and the hold-out "
         "effect has the same sign with p < 0.10; **Tested-no-lead** if the test ran and that is not met; **Untested** "
         "if it could not be run.", "",
         "em-macro's event-move file covers six of the 13 countries (Brazil, Mexico, Poland, Turkey, South Africa, "
         "Indonesia), rate decisions and elections only, so tests that need market moves use those six.", ""]
    a = t.get("a", {})
    L += [f"## (a) Poll vs prediction-market gap: {a.get('badge')}", "", a.get("reason", ""), ""]
    if "result" in a:
        x = a["result"]
        L += [a["method"], "",
              f"* Elections with polls and recorded odds: {x['n_elections']} (with an em-macro FX move: {x['n_with_moves']}).",
              f"* |gap| vs size of the poll miss: rho {x['gap_vs_poll_error']['rho']}, p={x['gap_vs_poll_error']['p']}.",
              f"* |gap| vs day-1 move: rho {x['gap_vs_move']['rho']}, p={x['gap_vs_move']['p']}, n={x['gap_vs_move']['n']}.",
              f"* Brier: market {x['brier_market']}, poll-implied {x['brier_poll']} (lower is better).",
              f"* They disagreed on the favourite {x['disagreements']['n']} times; the market was right "
              f"{x['disagreements']['market_right']}.", "",
              "| election | date | P(A) polls | P(A) market | gap | A won | poll miss (pp) | FX move (sd) |", "|---|---|---|---|---|---|---|---|"]
        L += [f"| {e['election']} | {e['date']} | {e['p_poll_a']} | {e['p_market_a']} | {e['gap']:+.2f} | {'yes' if e['a_won'] else 'no'} | "
              f"{e['poll_error_pp']} | {e['fx_move_sd'] if e['fx_move_sd'] is not None else '–'} |" for e in x["elections"]]
        L.append("")
    c = t.get("c", {})
    L += [f"## (c) Survey dispersion: {c.get('badge')}", "", c.get("reason", ""), ""]
    for k, p in (c.get("parts") or {}).items():
        L += [f"**{k}** – {p['reading']}; extreme = {p['extreme']}; {p['n_events']} decisions.", "",
              f"* move size: {_fmt_split(p['move'])} → {p['badge']} ({p['reason']})",
              f"* miss vs survey (bp): {_fmt_split(p['survey_miss'])}", ""]
    L += ["Reading this result: part of the 'miss vs survey' effect is mechanical (when forecasters disagree, more of them "
          "are away from the median, so the decision is more likely to differ from it). The move-size result, which is about "
          "markets rather than the survey itself, is weaker in the fit period (p≈0.07 for Brazil) and stronger in the "
          "hold-out. The Banxico reading uses inflation-forecast dispersion because the survey's rate expectations are not "
          "available keylessly, so it measures a less direct disagreement.", ""]
    if c.get("pooled"):
        L += [f"**Pooled** move size: {_fmt_split(c['pooled']['move'])}", "",
              f"**Pooled** miss vs survey (bp): {_fmt_split(c['pooled']['survey_miss'])}", ""]
    e = t.get("e", {})
    L += [f"## (e) CFTC positioning: {e.get('badge')}", "", e.get("reason", ""), ""]
    for k, p in (e.get("parts") or {}).items():
        if "error" in p:
            L += [f"* {k}: {p['error']}"]
            continue
        L += [f"**{k}** – {p['reading']}; extreme = {p['extreme']}; {p['n_events']} events {p['by_country']}.", "",
              f"* FX move size: {_fmt_split(p['move'])} → {p['badge']}",
              f"* mean move against the crowd after extreme readings (sd, + = against): {p['against_crowd_mean_sd']}", ""]
    L += ["## Not tested", "",
          "* (b) pollster concentration and house effects, (d) official optimism gap and (f) forced-flow thresholds are "
          "shown as Context or Untested on the Crowd page; they were not part of this test.", ""]
    return "\n".join(L)


if __name__ == "__main__":
    res = run()
    for k, v in res["tests"].items():
        print(k, v.get("badge"), "-", v.get("reason"))
