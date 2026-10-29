"""Build data/terminal/crowd.json: six gauges of where the crowd could be wrong together, each with
an evidence badge, and a ranked list of the most likely shared errors in the next six months.

Badges for (a), (c) and (e) come from the lab tests (data/terminal/lab/crowd_tests.json, written by
`python -m terminal.labtests`); (b), (d) and (f) have not been tested and say so.
"""

from __future__ import annotations

import datetime as dt
import json
import logging
import math
import re

import pandas as pd
import yaml

from terminal import emmacro, labtests, scenarios as scn, store, summary

log = logging.getLogger("terminal")
OUT = store.DATA / "crowd.json"
LAB = labtests.OUT
POLLS = store.INPUTS / "polls.yaml"
# which fiscal-table row speaks to which scenario
OPTIMISM = {"br-fiscal-2027": ("BR", 2027), "fr-budget-2027": ("FR", 2027)}
WEIGHT = {"tested_leads": 1.0, "untested": 0.5, "context": 0.3, "tested_no_lead": 0.25}


def lab_results() -> dict:
    return json.loads(LAB.read_text()) if LAB.exists() else {"tests": {}}


def badge(lab: dict, gauge: str, part: str | None = None) -> dict:
    t = lab.get("tests", {}).get(gauge)
    if not t:
        return {"badge": "untested", "reason": "lab test not run yet (python -m terminal.labtests)"}
    if part and t.get("parts", {}).get(part):
        p = t["parts"][part]
        return {"badge": p["badge"], "reason": p["reason"], "report": "reports/crowd_lab.md"}
    return {"badge": t.get("badge", "untested"), "reason": t.get("reason", ""), "report": "reports/crowd_lab.md"}


def _safe(fn, *a):
    try:
        return fn(*a)
    except Exception as exc:                                             # noqa: BLE001
        log.warning("crowd %s: %s", fn.__name__, exc)
        return {"error": f"{type(exc).__name__}: {exc}"}


# --------------------------------------------------------------------------
# (a) poll vs prediction-market gap
# --------------------------------------------------------------------------

def gauge_a(lab: dict, scen: list[dict]) -> dict:
    out = {"id": "a", "title": "Poll vs prediction-market gap", "evidence": badge(lab, "a"),
           "what": "Poll-implied probability = Phi(poll lead / that country's historical RMS poll error); compared with the "
                   "prediction-market price for the same outcome. A large gap means one of the two crowds is wrong.",
           "readings": []}
    e = labtests.poll_implied(emmacro.frame("data/events/elections.csv"))
    polls = (yaml.safe_load(POLLS.read_text()) or {}).get("polls", []) if POLLS.exists() else []
    by_id = {s["id"]: s for s in scen}
    for p in polls:
        prior = e[e.iso3 == p["iso3"]]
        sig = math.sqrt((prior["err"] ** 2).mean()) if len(prior) >= 3 else math.sqrt((e["err"] ** 2).mean())
        margin = float(p["a_pct"]) - float(p["b_pct"])
        p_poll = labtests._phi(margin / sig)
        s = by_id.get(p.get("scenario"))
        mkt = s and s["markets"]["by_branch"] and s["markets"]["by_branch"].get(p.get("a_branch"))
        if mkt is None and s and p.get("a_branch") in s["yes_branches"]:
            mkt = s["markets"]["yes"]
        out["readings"].append({"label": p["label"], "scenario": p.get("scenario"), "poll_margin_pp": round(margin, 1),
                                "sigma_pp": round(sig, 2), "p_poll": round(p_poll, 3), "p_market": mkt,
                                "gap": round(mkt - p_poll, 3) if mkt is not None else None, "poll_date": str(p.get("date")),
                                "source": p.get("source")})
    last = (lab.get("tests", {}).get("a", {}).get("result") or {}).get("elections") or []
    if last:
        out["latest_resolved"] = last[-1]
    if not polls:
        out["note"] = ("No current polls entered. Add the latest head-to-head poll for a scenario to "
                       "data/terminal/inputs/polls.yaml (format in the file) and this gauge computes the gap.")
    return out


# --------------------------------------------------------------------------
# (b) pollster concentration and house effects
# --------------------------------------------------------------------------

def gauge_b() -> dict:
    out = {"id": "b", "title": "Pollster concentration and house effects",
           "evidence": {"badge": "untested", "reason": "Not tested: em-macro has pollster-level polls for 8 countries' recent elections, "
                                                        "too few to test whether concentration or herding predicts the size of the miss."},
           "what": "Final 14 days before each vote: how many pollsters, the largest pollster's share of polls (HHI), each pollster's "
                   "lean against the average (house effect), and whether polls spread less than sampling error alone implies "
                   "(herding ratio < 1). The miss is actual margin minus the final-polls average.",
           "elections": []}
    el = emmacro.frame("data/events/elections.csv")
    frames = [emmacro.frame("data/events/raw/prevote_polls_br_mx.csv"), emmacro.frame("data/events/raw/prevote_polls_tr_pl_id_za.csv")]
    p = pd.concat(frames, ignore_index=True)
    p = p[p.contest.isin(["round1", "runoff", "single"])].dropna(subset=["a_pct", "b_pct"])
    p["end"] = p.field_end.fillna(p.field_start)
    for (iso, vd, contest), g in p.groupby(["iso3", "vote_date", "contest"]):
        rnd = 2 if contest == "runoff" else 1
        actual = el[(el.iso3 == iso) & (el.vote_date == vd) & (el["round"] == rnd)]
        g = g[g.end.notna() & (g.end >= (pd.Timestamp(vd) - pd.Timedelta(days=14)).strftime("%Y-%m-%d"))]
        if len(g) < 4:
            continue
        a, b = g.a_pct.astype(float), g.b_pct.astype(float)
        share = (a + b) / 100
        g = g.assign(margin=100 * (a - b) / (a + b))                    # two-candidate margin, comparable to results
        shares = g.pollster.value_counts(normalize=True)
        n_med = pd.to_numeric(g.sample_size, errors="coerce").median()
        pa = (a / (a + b)).mean()
        exp_sd = 200 * math.sqrt(pa * (1 - pa) / n_med) if n_med == n_med and n_med else None
        house = (g.groupby("pollster").margin.mean() - g.margin.mean()).round(1)
        rec = {"election": f"{iso} {vd} {contest}", "iso3": iso, "date": vd, "n_polls": int(len(g)), "n_pollsters": int(g.pollster.nunique()),
               "top_pollster": shares.index[0], "top_share": round(float(shares.iloc[0]), 2), "hhi": round(float((shares ** 2).sum()), 3),
               "mean_margin": round(float(g.margin.mean()), 2), "sd_margin": round(float(g.margin.std()), 2),
               "expected_sd": round(exp_sd, 2) if exp_sd else None,
               "herding_ratio": round(float(g.margin.std()) / exp_sd, 2) if exp_sd else None,
               "house_effects": house.sort_values().to_dict()}
        if len(actual) and actual.actual_margin_pp.notna().any():
            rec["actual_margin"] = float(actual.actual_margin_pp.iloc[0])
            rec["miss"] = round(rec["actual_margin"] - rec["mean_margin"], 2)
        out["elections"].append(rec)
    out["elections"].sort(key=lambda r: r["date"], reverse=True)
    out["upcoming"] = "No polls yet for Mexico's June 2027 midterms in em-macro; Mexico's history is shown for its pollsters."
    return out


# --------------------------------------------------------------------------
# (c) survey dispersion
# --------------------------------------------------------------------------

def _meeting_key(m: str):
    k, y = m[1:].split("/")
    return int(y), int(k)


def gauge_c(lab: dict, cal: dict) -> dict:
    out = {"id": "c", "title": "Survey dispersion percentile", "evidence": badge(lab, "c"), "readings": [],
           "what": "How much forecasters disagree before a decision, against their own history. Wide disagreement "
                   "before a Copom meeting has been followed by decisions further from the survey median and larger moves."}
    s = store.load_series("br.focus.selic_meeting")
    if s:
        h = pd.DataFrame(s["history"], columns=["date", "meeting"] + s["fields"])
        last = h.date.max()
        cur = h[h.date == last]
        nxt = min(cur.meeting, key=_meeting_key)
        row = cur[cur.meeting == nxt].iloc[0]
        past = _safe(labtests.copom_dispersion)
        pct = None
        if isinstance(past, pd.DataFrame) and len(past):
            prior = past.sd.tail(40).tolist()
            pct = round(100 * sum(x <= row["sd"] for x in prior) / len(prior), 1)
        nxt_ev = next((e for e in cal.get("events", []) if e["country"] == "BR" and "Copom" in e["title"] and e["date"] >= dt.date.today().isoformat()), None)
        out["readings"].append({"label": f"Focus: Selic for the next Copom ({nxt})", "country": "BR", "value": row["sd"], "unit": "pp (sd)",
                                "median": row["median"], "respondents": row["respondents"], "as_of": last, "percentile": pct,
                                "percentile_basis": "vs the last survey before each of the previous 40 meetings",
                                "extreme": pct is not None and pct >= 80, "event": nxt_ev and {"date": nxt_ev["date"], "title": nxt_ev["title"]},
                                "evidence": badge(lab, "c", "BR"), "meta": summary.meta_of(s, last)})
    s = store.load_series("br.focus.primary")
    if s:
        nxt_year = str(dt.date.today().year + 1)
        date, rows = summary.latest_by_ref(s)
        r = rows.get(nxt_year)
        if r:
            rec = dict(zip(s["fields"], r[2:]))
            h = int(nxt_year) - int(date[:4])
            pct = summary.dispersion_percentile(s, "sd", h, rec.get("sd"))
            out["readings"].append({"label": f"Focus: {nxt_year} primary balance", "country": "BR", "value": rec.get("sd"), "unit": "pp of GDP (sd)",
                                    "median": rec.get("median"), "respondents": rec.get("respondents"), "as_of": date, "percentile": pct,
                                    "percentile_basis": "vs readings at the same horizon over 10 years", "extreme": pct is not None and pct >= 80,
                                    "scenarios": ["br-fiscal-2027"],
                                    "evidence": {"badge": "untested", "reason": "The lab test covered dispersion before rate decisions, not fiscal surveys."},
                                    "meta": summary.meta_of(s, date)})
    s = store.load_series("mx.survey.inflation")
    if s:
        h = pd.DataFrame([r[:4] for r in s["history"]], columns=["date", "ref", "median", "sd"]).dropna(subset=["sd"])
        h = h[h.ref.astype(int) == h.date.str[:4].astype(int)]
        h["month"] = h.date.str[5:7].astype(int)
        last = h.iloc[-1]
        ref = h[(h.date < last.date) & (h.date >= str(int(last.date[:4]) - 10)) & ((h.month - last.month).abs() <= 1)]
        pct = round(100 * float((ref["sd"] <= last["sd"]).mean()), 1) if len(ref) >= 12 else None
        nxt_ev = next((e for e in cal.get("events", []) if e["country"] == "MX" and "Banxico" in e["title"] and "decision" in e["title"]
                       and e["date"] >= dt.date.today().isoformat()), None)
        out["readings"].append({"label": f"Banxico survey: {last.ref} inflation", "country": "MX", "value": last["sd"], "unit": "pp (sd)",
                                "median": last["median"], "as_of": last.date, "percentile": pct,
                                "percentile_basis": "vs the same month +/-1 over the previous 10 years",
                                "extreme": pct is not None and pct >= 80, "event": nxt_ev and {"date": nxt_ev["date"], "title": nxt_ev["title"]},
                                "evidence": badge(lab, "c", "MX"), "meta": summary.meta_of(s, last.date)})
    return out


# --------------------------------------------------------------------------
# (d) official optimism gap
# --------------------------------------------------------------------------

def gauge_d() -> dict:
    out = {"id": "d", "title": "Official optimism gap",
           "evidence": {"badge": "untested", "reason": "Not tested: em-macro has no history of official targets against independent estimates."},
           "what": "Government target minus the median independent estimate for the same year and measure (positive = government "
                   "more optimistic). From the fiscal table on each country page.", "rows": []}
    for c in ("FR", "BR", "MX"):
        for r in summary.fiscal_rows(c):
            indep = [i for i in r["independent"] if isinstance(i.get("value"), (int, float))]
            out["rows"].append({"country": c, "year": r.get("year"), "measure": r.get("metric"),
                                "official": (r.get("official") or {}).get("value"), "independent_median": round(sorted(i["value"] for i in indep)[len(indep) // 2], 2) if indep else None,
                                "n_independent": len(indep), "gap": r["gap"], "verified": (r.get("official") or {}).get("verified")})
    return out


# --------------------------------------------------------------------------
# (e) CFTC positioning
# --------------------------------------------------------------------------

def gauge_e(lab: dict, cal: dict) -> dict:
    out = {"id": "e", "title": "CFTC net positioning percentile", "evidence": badge(lab, "e"), "readings": [],
           "what": "Leveraged funds' net futures position / open interest, percentile over 3 years (BRL and MXN futures; long = "
                   "long the local currency). Shown as a flag only when a dated catalyst for that country is within 30 days."}
    today = dt.date.today()
    for c, name in (("BR", "BRL"), ("MX", "MXN")):
        try:
            d = labtests.cot_readings(c)
        except Exception as exc:                                         # noqa: BLE001
            out["readings"].append({"country": c, "error": str(exc)})
            continue
        last = d.iloc[-1]
        soon = [e for e in cal.get("events", []) if e["country"] == c and e["importance"] >= 3
                and 0 <= (dt.date.fromisoformat(e["date"]) - today).days <= 30]
        pct = None if pd.isna(last.pct) else round(float(last.pct), 1)
        extreme = pct is not None and (pct <= 10 or pct >= 90)
        out["readings"].append({"country": c, "label": f"{name} futures, leveraged funds", "as_of": last.date, "net": int(last.lev_money_net),
                                "net_pct_oi": round(100 * float(last.x), 1), "percentile": pct, "extreme": extreme,
                                "crowded": "long " + name if pct and pct >= 90 else ("short " + name if pct is not None and pct <= 10 else None),
                                "catalysts_30d": [{"date": e["date"], "title": e["title"]} for e in soon],
                                "flag": extreme and bool(soon), "meta": summary.meta_of(store.load_series(labtests.COT_SERIES[c]), last.date)})
    return out


# --------------------------------------------------------------------------
# (f) forced-flow thresholds
# --------------------------------------------------------------------------

SCALE = ["AAA", "AA+", "AA", "AA-", "A+", "A", "A-", "BBB+", "BBB", "BBB-", "BB+", "BB", "BB-", "B+", "B", "B-"]
MOODYS = {"Aaa": "AAA", "Aa1": "AA+", "Aa2": "AA", "Aa3": "AA-", "A1": "A+", "A2": "A", "A3": "A-", "Baa1": "BBB+", "Baa2": "BBB",
          "Baa3": "BBB-", "Ba1": "BB+", "Ba2": "BB", "Ba3": "BB-", "B1": "B+", "B2": "B", "B3": "B-"}


def notch(r: str) -> int | None:
    r = MOODYS.get(str(r).strip(), str(r).strip())
    return SCALE.index(r) if r in SCALE else None


def latest_ratings(iso3: str) -> list[dict]:
    rows = []
    for f in ("data/events/raw/rating_actions_eu.csv", "data/events/raw/rating_actions_em.csv"):
        d = emmacro.frame(f)
        d = d[d.iso3 == iso3].sort_values("date")
        for ag, g in d.groupby("agency"):
            x = g.iloc[-1]
            rows.append({"agency": ag, "rating": x.rating_after, "outlook": x.outlook_after, "date": x.date, "notch": notch(x.rating_after)})
    return rows


def middle(rows: list[dict]) -> int | None:
    n = sorted(r["notch"] for r in rows if r["notch"] is not None)
    return n[1] if len(n) == 3 else None


def gauge_f() -> dict:
    out = {"id": "f", "title": "Forced-flow thresholds", "evidence": {"badge": "context", "reason": "Mechanical thresholds, not forecasts; not tested."},
           "what": "Distance from today's ratings to levels that force buying or selling: index investment-grade eligibility "
                   "(middle of S&P, Moody's and Fitch), losing the last AA-category rating, ECB collateral and TPI conditions, "
                   "and auction stress.", "items": []}
    ig = SCALE.index("BBB-")
    mx = latest_ratings("MEX")
    m = middle(mx)
    cuts = sorted((ig + 1 - r["notch"], r["agency"], r["outlook"]) for r in mx if r["notch"] is not None)
    out["items"].append({"country": "MX", "threshold": "Investment-grade index eligibility (middle rating BBB- or better)", "scenarios": ["mx-midterms-2027", "usmca-2027"],
                         "ratings": mx, "middle": SCALE[m] if m is not None else None,
                         "distance": f"{cuts[0][0]} notch ({cuts[0][1]}) and {cuts[1][0]} notch ({cuts[1][1]}) cuts take the middle rating to junk",
                         "notches_to_trigger": cuts[0][0] + cuts[1][0],
                         "negative_outlooks": [r["agency"] for r in mx if "neg" in str(r["outlook"])],
                         "near": cuts[0][0] + cuts[1][0] <= 2,
                         "why": "Global aggregate and IG-only mandates sell when the middle rating drops below BBB- (index rules use the "
                                "middle of the three)."})
    br = latest_ratings("BRA")
    ups = sorted((ig - r["notch"] if r["notch"] is not None else 99, r["agency"]) for r in br if r["notch"] is not None)
    out["items"].append({"country": "BR", "threshold": "Investment-grade index eligibility (upgrade side)", "ratings": br, "scenarios": [],
                         "middle": SCALE[middle(br)] if middle(br) is not None else None,
                         "distance": f"{-ups[0][0]} notch ({ups[0][1]}) and {-ups[1][0]} notch ({ups[1][1]}) upgrades needed for an investment-grade middle rating",
                         "notches_to_trigger": -(ups[0][0] + ups[1][0]), "near": False,
                         "why": "Forced buying only on a return to investment grade; far away."})
    fr = latest_ratings("FRA")
    aa = [r for r in fr if r["notch"] is not None and r["notch"] <= SCALE.index("AA-")]
    out["items"].append({"country": "FR", "threshold": "Last AA-category rating among the big three", "ratings": fr, "scenarios": ["fr-sp-2026-11"],
                         "distance": (f"{aa[0]['agency']} at {aa[0]['rating']} ({aa[0]['outlook']}) is the last; one notch removes it"
                                      if len(aa) == 1 else f"{len(aa)} agencies in the AA category"),
                         "near": len(aa) == 1 and "neg" in str(aa[0]["outlook"]), "notches_to_trigger": 1 if len(aa) == 1 else None,
                         "why": "Some reserve-manager and insurer mandates key on the AA category; mandates differ and are not public."})
    best = min(r["notch"] for r in fr if r["notch"] is not None)
    out["items"].append({"country": "FR", "threshold": "ECB collateral eligibility (best rating BBB- or better)", "scenarios": [],
                         "distance": f"{ig - best} notches above the floor at the best agency", "near": False, "notches_to_trigger": ig - best + 1,
                         "why": "The Eurosystem's credit-quality floor; not close."})
    cal = emmacro.frame("data/events/calendar_13.csv")
    edp = cal[(cal.iso3 == "FRA") & cal.subtype.fillna("").str.startswith("edp")].sort_values("date")
    failed = edp[edp.subtype.str.contains("no_effective|non_compliance|126_8", regex=True)]
    last = edp.iloc[-1] if len(edp) else None
    out["items"].append({"country": "FR", "threshold": "ECB TPI eligibility: compliance with the EU fiscal framework", "scenarios": ["fr-budget-2027", "fr-pres-2027"],
                         "distance": ("France is under an excessive deficit procedure (since Jul 2024) with a Council recommendation "
                                      f"({last.date}); em-macro records no finding that it failed to take effective action, so this "
                                      "criterion is met today." if last is not None and failed.empty else
                                      "em-macro records a finding of no effective action: TPI eligibility in doubt."),
                         "near": not failed.empty, "notches_to_trigger": None,
                         "why": "TPI purchases need compliance with the EU fiscal framework; a Council finding of no effective action under "
                                "the EDP would remove it. Next checkpoint: the Commission's autumn package.",
                         "source_url": emmacro.url("data/events/calendar_13.csv")})
    inst = scn.book.Instrument("DI29", scn.book.load_config()["instruments"]["DI29"])
    obs = inst.obs[-780:]
    if len(obs) > 40:
        ch = [abs(obs[i][1] - obs[i - 20][1]) * 100 for i in range(20, len(obs))]
        cur = ch[-1]
        pct = round(100 * sum(x <= cur for x in ch) / len(ch), 1)
        out["items"].append({"country": "BR", "threshold": "Auction stress: Tesouro shrinks or cancels fixed-rate auctions in volatile weeks", "scenarios": ["br-fiscal-2027"],
                             "distance": f"20-day move in DI Jan-29 (proxy) is {cur:.0f} bp, percentile {pct} over 3 years",
                             "near": pct >= 90, "percentile": pct,
                             "why": "When rates gap, the Treasury cuts fixed-rate supply and leans on floating (LFT) issuance; a "
                                    "move above the 90th percentile is the zone where that has happened."})
    return out


# --------------------------------------------------------------------------
# ranked shared errors
# --------------------------------------------------------------------------

def ranked(scen: list[dict], g: dict) -> list[dict]:
    items = []
    for s in scen:
        days = s.get("days_to_event")
        if days is None or days < 0 or days > 183:
            continue
        sig = []
        br, mk = s["base_rate"], s["asymmetry"].get("market_yes")
        p_base = br.get("p_yes")
        if br.get("kind") == "budget_cycles" and br.get("subset", {}).get("p_yes") is not None:
            p_base = br["subset"]["p_yes"]
        if mk is not None and p_base is not None:
            gap = mk - p_base
            sig.append({"signal": "market vs base rate", "detail": f"market {100 * mk:.0f}% vs base rate {100 * p_base:.0f}%",
                        "strength": min(1.0, abs(gap) / 0.3), "badge": "untested", "hidden_market": True})
        for r in g["c"].get("readings", []):
            if s["id"] in r.get("scenarios", []) and r.get("percentile") is not None:
                # the lab evidence is for wide disagreement, so only the high side counts
                sig.append({"signal": "survey dispersion", "detail": f"{r['label']}: percentile {r['percentile']}",
                            "strength": max(0.0, (r["percentile"] - 50) / 50), "badge": r["evidence"]["badge"]})
        for r in g["e"].get("readings", []):
            if r.get("country") == s["country"] and r.get("percentile") is not None and days <= 30:
                sig.append({"signal": "positioning near the event", "detail": f"{r['label']}: percentile {r['percentile']}",
                            "strength": 1.0 if r["extreme"] else 0.0, "badge": g["e"]["evidence"]["badge"]})
        yr = OPTIMISM.get(s["id"])
        for r in g["d"].get("rows", []):
            if yr and (r["country"], r["year"]) == yr and r["gap"] is not None:
                sig.append({"signal": "official optimism gap", "detail": f"{r['year']} {r['measure']}: official {r['official']} vs independent {r['independent_median']}",
                            "strength": min(1.0, abs(r["gap"]) / 1.0), "badge": g["d"]["evidence"]["badge"]})
        for it in g["f"].get("items", []):
            if s["id"] in it.get("scenarios", []) and it.get("near"):
                sig.append({"signal": "forced-flow threshold", "detail": f"{it['threshold']}: {it['distance']}", "strength": 1.0,
                            "badge": g["f"]["evidence"]["badge"]})
        for r in g["a"].get("readings", []):
            if r.get("scenario") == s["id"] and r.get("gap") is not None:
                sig.append({"signal": "poll vs market gap", "detail": f"{r['label']}: polls {100 * r['p_poll']:.0f}%, market {100 * r['p_market']:.0f}%",
                            "strength": min(1.0, abs(r["gap"]) / 0.3), "badge": g["a"]["evidence"]["badge"], "hidden_market": True})
        sig = [x for x in sig if x["strength"] > 0]
        score = sum(WEIGHT.get(x["badge"], 0.3) * x["strength"] for x in sig)
        items.append({"scenario": s["id"], "title": s["title"], "question": s["question"], "date": s["event"] and s["event"]["date"],
                      "days": days, "score": round(score, 3), "signals": sig})
    items.sort(key=lambda x: -x["score"])
    return items


def build() -> dict:
    lab = lab_results()
    cal = json.loads((store.DATA / "calendar.json").read_text()) if (store.DATA / "calendar.json").exists() else {"events": []}
    sc = json.loads(scn.OUT.read_text())["scenarios"] if scn.OUT.exists() else []
    g = {"a": _safe(gauge_a, lab, sc), "b": _safe(gauge_b), "c": _safe(gauge_c, lab, cal), "d": _safe(gauge_d),
         "e": _safe(gauge_e, lab, cal), "f": _safe(gauge_f)}
    for k, v in g.items():
        v.setdefault("id", k)
    out = {"generated_at": store.now_iso(), "gauges": [g[k] for k in "abcdef"],
           "shared_errors": ranked(sc, g),
           "ranking_method": ("Heuristic, not a tested model. For each scenario due within 6 months: each signal that applies scores "
                              "0-1 for strength and is weighted by its evidence (Tested-leads 1, Untested 0.5, Context 0.3, "
                              "Tested-no-lead 0.25); the score is the sum. Market-vs-base-rate gap counts when both exist."),
           "lab": {"generated_at": lab.get("generated_at"), "report": "reports/crowd_lab.md"}}
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=1, default=scn._json_default) + "\n")
    return out
