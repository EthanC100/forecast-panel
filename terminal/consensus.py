"""Economists and policy: consensus forecasts, independent fiscal assessments, the policy tracker and
the consensus-gap flags (data/terminal/consensus.json).

Consensus forecasts, this year and next:
    Brazil   BCB Focus survey (median, mean, sd, min, max, respondents; published 30-day basis)
    Mexico   Banxico survey of private-sector economists (median, sd, min, max)
    France   IMF World Economic Outlook, OECD Economic Outlook and the European Commission forecast:
             the consensus is the median of the three, with their range and standard deviation
Each row also shows how the median has moved over the last three months.

Consensus gap: a Full call with a question id `fc:<CC>.<variable>.<year>` (a forecast row) or
`pol:<policy id>` (a policy linked to a forecast row) is compared with that row. With a point
forecast, the gap is flagged when |mine - median| exceeds the row's dispersion (its standard
deviation). Without one, a forecast-row call (phrased "above the median?") is flagged when its
probability is 84% or more, or 16% or less: the probability a normal forecast distribution puts
beyond one standard deviation. That is where an edge would have to come from.
"""

from __future__ import annotations

import datetime as dt
import json
import logging
import statistics

import yaml

from terminal import store

log = logging.getLogger(__name__)

OUT = store.DATA / "consensus.json"
POLICIES = store.INPUTS / "policies.yaml"
ASSESSMENTS = store.DATA / "assessments.json"

VARS = {
    "BR": [("inflation", "br.focus.ipca", "Inflation (IPCA, Dec/Dec)"), ("policy_rate", "br.focus.selic", "Selic rate, year end"),
           ("gdp", "br.focus.gdp", "Real GDP growth"), ("primary", "br.focus.primary", "Primary balance, % of GDP"),
           ("nominal", "br.focus.nominal", "Overall (nominal) balance, % of GDP")],
    "MX": [("inflation", "mx.survey.inflation", "Inflation, year end"), ("policy_rate", "mx.survey.policy_rate", "Policy (interbank) rate, Q4 close"),
           ("gdp", "mx.survey.gdp", "Real GDP growth"), ("balance", "mx.survey.balance", "Public-sector economic balance, % of GDP")],
}
FR_VARS = [("inflation", "Inflation (HICP; IMF: CPI)"), ("rate", "Short-term rate (3-month, euro area; OECD only)"),
           ("gdp", "Real GDP growth"), ("balance", "General government balance, % of GDP")]
FR_INST = [("imf", "IMF"), ("oecd", "OECD"), ("ec", "European Commission")]
SURVEY_NAME = {"BR": "BCB Focus", "MX": "Banxico survey"}
GAP_PROB = (0.16, 0.84)


def _r(x, n=2):
    return None if x is None else round(float(x), n)


def survey_rows(cc: str, year: int) -> list[dict]:
    out = []
    for var, sid, label in VARS[cc]:
        s = store.load_series(sid)
        if not s or not s.get("history"):
            continue
        f = s["fields"]
        last = s["history"][-1][0]
        lag = 91 if cc == "BR" else 85
        cut = (dt.date.fromisoformat(last) - dt.timedelta(days=lag)).isoformat()
        for ref in (year, year + 1):
            rows = [r for r in s["history"] if r[1] == str(ref)]
            if not rows:
                continue
            cur = dict(zip(f, rows[-1][2:]))
            old = [r for r in rows if r[0] <= cut]
            prev = dict(zip(f, old[-1][2:])) if old else {}
            med = cur.get("median")
            out.append({"id": f"fc:{cc}.{var}.{ref}", "country": cc, "var": var, "label": label, "year": ref, "unit": s.get("unit"),
                        "median": _r(med), "mean": _r(cur.get("mean")), "sd": _r(cur.get("sd"), 3), "min": _r(cur.get("min")),
                        "max": _r(cur.get("max")), "respondents": cur.get("respondents"), "as_of": rows[-1][0],
                        "median_3m_ago": _r(prev.get("median")), "date_3m_ago": old[-1][0] if old else None,
                        "change_3m": _r(med - prev["median"], 3) if med is not None and prev.get("median") is not None else None,
                        "dispersion": _r(cur.get("sd"), 3), "dispersion_kind": "sd across respondents",
                        "source": SURVEY_NAME[cc], "source_id": s.get("source_id"), "source_url": s.get("source_url"),
                        "titles": (s.get("titles") or None)})
    return out


def france_rows(year: int) -> list[dict]:
    out = []
    cut = (dt.date.today() - dt.timedelta(days=91)).isoformat()
    for var, label in FR_VARS:
        for ref in (year, year + 1):
            insts, then = [], []
            for key, name in FR_INST:
                s = store.load_series(f"fr.fc.{key}.{var}")
                if not s:
                    continue
                rows = [r for r in s["history"] if r[1] == str(ref)]
                if not rows:
                    continue
                insts.append({"institution": name, "value": _r(rows[-1][2]), "edition": s.get("edition"), "edition_date": rows[-1][0],
                              "url": s.get("source_url")})
                old = [r for r in rows if r[0] <= cut]
                if old:
                    then.append(old[-1][2])
            if not insts:
                continue
            vals = [i["value"] for i in insts]
            med = statistics.median(vals)
            sd = statistics.stdev(vals) if len(vals) >= 2 else None
            prev = statistics.median(then) if len(then) == len(insts) and then else None
            out.append({"id": f"fc:FR.{var}.{ref}", "country": "FR", "var": var, "label": label, "year": ref, "unit": "%",
                        "median": _r(med), "sd": _r(sd, 3), "min": _r(min(vals)), "max": _r(max(vals)), "respondents": len(vals),
                        "as_of": max(i["edition_date"] for i in insts), "median_3m_ago": _r(prev),
                        "change_3m": _r(med - prev, 3) if prev is not None else None,
                        "change_3m_note": None if prev is not None else "no earlier edition stored for every institution yet",
                        "dispersion": _r(sd, 3), "dispersion_kind": "sd across the institutions" if sd is not None else None,
                        "source": "IMF, OECD and European Commission", "institutions": insts})
    return out


def _calendar() -> dict[str, dict]:
    cal = json.loads((store.DATA / "calendar.json").read_text()) if (store.DATA / "calendar.json").exists() else {"events": []}
    return {e["id"]: e for e in cal.get("events", [])}


def policies(rows_by_id: dict[str, dict]) -> list[dict]:
    spec = yaml.safe_load(POLICIES.read_text())["policies"]
    cal = _calendar()
    out = []
    for p in spec:
        nxt = dict(p.get("next") or {})
        ev = cal.get(nxt.get("event") or "")
        if ev:
            nxt.update({"date": ev["date"], "title": ev["title"], "status": ev.get("status"), "importance": ev.get("importance")})
        elif nxt.get("event"):
            nxt["missing_event"] = True
        cons = p.get("consensus") or None
        if cons and cons.get("ref") in rows_by_id:
            r = rows_by_id[cons["ref"]]
            cons = {**cons, "label": r["label"], "year": r["year"], "median": r["median"], "dispersion": r["dispersion"],
                    "unit": r["unit"], "source": r["source"], "as_of": r["as_of"]}
        out.append({**p, "next": nxt, "consensus": cons, "question_id": f"pol:{p['id']}"})
    return out


def _calls() -> dict[str, dict]:
    """Latest accepted Full call per fc:/pol: question id."""
    from terminal.judgement import load_judgements
    latest = {}
    for r in load_judgements():
        q = r.get("question_id") or ""
        if r.get("type") != "call" or r.get("rejected") or not (q.startswith("fc:") or q.startswith("pol:")):
            continue
        if q not in latest or r["submitted_at"] > latest[q]["submitted_at"]:
            latest[q] = r
    return latest


def gaps(rows_by_id: dict[str, dict], pols: list[dict]) -> list[dict]:
    out = []
    by_pol = {p["question_id"]: p for p in pols}
    for qid, c in _calls().items():
        if qid.startswith("pol:"):
            p = by_pol.get(qid)
            ref = ((p or {}).get("consensus") or {}).get("ref")
            row = rows_by_id.get(ref)
            label = p["name"] if p else qid
            country = p["country"] if p else None
        else:
            row, label, country = rows_by_id.get(qid), None, qid[3:5]
        if not row:
            out.append({"question_id": qid, "record": c["id"], "flagged": False, "note": "no consensus row to compare with"})
            continue
        point, prob = c.get("point"), c.get("probability")
        g = {"question_id": qid, "record": c["id"], "submitted_at": c["submitted_at"], "country": country or row["country"],
             "label": label or f"{row['label']} {row['year']}", "consensus_id": row["id"], "consensus_median": row["median"],
             "dispersion": row["dispersion"], "unit": row["unit"], "source": row["source"], "my_point": point, "my_prob": prob}
        if point is not None and row["median"] is not None:
            g["gap"] = round(point - row["median"], 3)
            if row["dispersion"]:
                g["gap_in_sd"] = round(g["gap"] / row["dispersion"], 2)
                g["flagged"] = abs(g["gap"]) > row["dispersion"]
                g["basis"] = "point forecast vs the median, in units of the consensus standard deviation"
            else:
                g["flagged"] = False
                g["basis"] = "no dispersion available for this row (one institution only)"
        elif prob is not None and qid.startswith("fc:"):
            g["flagged"] = prob <= GAP_PROB[0] or prob >= GAP_PROB[1]
            g["basis"] = "probability of coming in above the median; 84%+ or 16%- implies a view more than one sd away"
        else:
            g["flagged"] = False
            g["basis"] = "give a point forecast in the Full call to compare with the consensus"
        out.append(g)
    return sorted(out, key=lambda g: (not g.get("flagged"), -abs(g.get("gap_in_sd") or 0)))


def build() -> dict:
    year = dt.date.today().year
    rows = survey_rows("BR", year) + survey_rows("MX", year) + france_rows(year)
    by_id = {r["id"]: r for r in rows}
    pols = policies(by_id)
    gp = gaps(by_id, pols)
    flagged = {g["question_id"]: g for g in gp if g.get("flagged")}
    for r in rows:
        r["mine"] = next((g for g in gp if g.get("consensus_id") == r["id"] and g["question_id"] == r["id"]), None)
    for p in pols:
        p["mine"] = next((g for g in gp if g["question_id"] == p["question_id"]), None)
    assessments = json.loads(ASSESSMENTS.read_text()) if ASSESSMENTS.exists() else {"items": [], "note": "not yet run"}
    res = {"generated_at": store.now_iso(), "year": year,
           "forecasts": {cc: [r for r in rows if r["country"] == cc] for cc in ("FR", "BR", "MX")},
           "policies": {cc: [p for p in pols if p["country"] == cc] for cc in ("FR", "BR", "MX")},
           "assessments": assessments, "gaps": gp, "n_flagged": len(flagged),
           "gap_rule": "Flagged when my point forecast differs from the consensus median by more than the consensus standard "
                       "deviation, or (without a point) when my probability of beating the median is 84% or more, or 16% or less."}
    OUT.write_text(json.dumps(res, ensure_ascii=False, indent=1, default=str) + "\n")
    return res
