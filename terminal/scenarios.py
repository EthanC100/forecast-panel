"""Build data/terminal/scenarios.json from inputs/scenarios.yaml.

For each scenario: the linked calendar event and days to it; a base-rate box computed from
em-macro's event history (or the reason it cannot be); each branch's expected moves resolved from
em-macro's what-if table, its event study or an analog on this terminal's stored series; linked
prediction markets mapped to branches; my probability (latest Full call / Quick update with
question id "sc:<id>"); the calculator defaults; and the asymmetry flag.

Calculator: P(good) = (current - bad level) / (good level - bad level). Default levels are today's
level plus the good and bad branches' expected moves; with those, the result only restates the move
estimates, so the page asks you for your own outcome levels and recomputes everything with them.

Asymmetry flag, all three needed:
  |my P(YES) - market P(YES)| >= 15 points (market = the linked prediction market, or the calculator
      once you have entered your own levels)
  reward:risk >= 2 for a position toward my view: distance from the current level to the level of
      the outcome I favour, over the distance to the other one (the move if right over the move if
      wrong)
  the event is 14 to 183 days away
"""

from __future__ import annotations

import datetime as dt
import json
import logging
import math
import statistics

import yaml

from terminal import book, degraded, emmacro, store
from terminal.http import get

log = logging.getLogger("terminal")
OUT = store.DATA / "scenarios.json"
INPUT = store.INPUTS / "scenarios.yaml"
UNITS = {"fx": "%", "bond": "bp", "spread_bp": "bp", "di": "bp"}
ASYM = {"gap_pp": 15, "reward_risk": 2.0, "min_days": 14, "max_days": 183}


# --------------------------------------------------------------------------
# em-macro inputs
# --------------------------------------------------------------------------

def _what_if():
    try:
        return emmacro.frame("results/risk_model/what_if.csv")
    except Exception as exc:                                             # noqa: BLE001
        log.warning("what_if: %s", exc)
        return None


def _event_moves():
    try:
        import pandas as pd
        return pd.concat([emmacro.frame("results/fit/event_moves.csv"), emmacro.frame("results/test/event_moves.csv")])
    except Exception as exc:                                             # noqa: BLE001
        log.warning("event_moves: %s", exc)
        return None


def instrument_unit(code: str, cfg: dict) -> str:
    return "%" if cfg["instruments"][code]["kind"] == "fx" else "bp"


def resolve_move(m: dict, cfg: dict, wi, em) -> dict:
    """One expected move: value (and interval where em-macro gives one) in the instrument's unit."""
    code = m["instrument"]
    out = {"instrument": code, "unit": instrument_unit(code, cfg), "basis": m.get("basis"),
           "assumption": bool(m.get("assumption")), "value": None, "lo": None, "hi": None}
    try:
        if "value" in m:
            out.update(value=float(m["value"]), source="judgement", assumption=True)
        elif "what_if" in m:
            q = m["what_if"]
            if wi is None:
                raise RuntimeError("em-macro what_if.csv not reachable")
            r = wi[(wi.country == q["country"]) & (wi.asset == q["asset"]) & (wi.scenario == q["scenario"])]
            if r.empty:
                raise RuntimeError(f"no what-if row {q}")
            r = r.iloc[-1]
            k = float(q.get("scale", 1))
            lo, hi = sorted((float(r.lo90) * k, float(r.hi90) * k))
            out.update(value=round(float(r.estimate) * k, 2), lo=round(lo, 2), hi=round(hi, 2), interval="90%",
                       source=f"em-macro what-if {q['country']} {q['asset']} {q['scenario']} (as of {r.date})" + (f" x {k:g}" if k != 1 else ""),
                       source_url=emmacro.url("results/risk_model/what_if.csv"))
        elif "event_study" in m:
            q = m["event_study"]
            if em is None:
                raise RuntimeError("em-macro event_moves.csv not reachable")
            d = em[(em.country == q["country"]) & (em.asset == q["asset"])]
            if q.get("event_ids"):
                d = d[d.event_id.isin(q["event_ids"])]
            else:
                d = d[(d.event_type == q["event_type"]) & d.subtype.isin(q["subtypes"])]
            col = f"ab_{q.get('h', 1)}"
            vals = [float(x) for x in d[col].dropna()]
            if not vals:
                raise RuntimeError(f"no event-study rows {q}")
            sign = -1 if q["asset"] == "FX" else 1                     # em-macro FX = local currency value
            mean = sign * statistics.fmean(vals)
            out.update(value=round(mean, 2), n=len(vals), events=sorted(set(d.event_id)),
                       lo=round(sign * min(vals), 2) if len(vals) > 1 else None, hi=round(sign * max(vals), 2) if len(vals) > 1 else None,
                       interval="range of events" if len(vals) > 1 else None,
                       source=f"em-macro event study, {col} abnormal move, {len(vals)} event(s)",
                       source_url=emmacro.url("results/test/event_moves.csv"))
            if out["lo"] is not None:
                out["lo"], out["hi"] = sorted((out["lo"], out["hi"]))
        elif "analog" in m:
            q = m["analog"]
            s = store.load_series(q["series"])
            obs = [(r[0], r[1]) for r in (s or {}).get("history", []) if isinstance(r[1], (int, float))]
            a = [v for d, v in obs if d <= str(q["from"])]
            b = [v for d, v in obs if d <= str(q["to"])]
            if not a or not b:
                raise RuntimeError(f"{q['series']} has no data for {q['from']}..{q['to']}")
            a, b = a[-1], b[-1]
            v = 100 * (b / a - 1) if out["unit"] == "%" else (b - a) * (100 if s.get("unit", "").startswith("%") else 1)
            out.update(value=round(v, 2), source=f"analog on {q['series']}: {q['from']} {a:g} to {q['to']} {b:g}",
                       from_level=a, to_level=b)
    except Exception as exc:                                             # noqa: BLE001
        out["error"] = str(exc)
    return out


# --------------------------------------------------------------------------
# base rates
# --------------------------------------------------------------------------

def base_rate(spec: dict) -> dict:
    kind = spec.get("kind")
    out = {"kind": kind, "reference_class": spec.get("reference_class"), "context": spec.get("context", [])}
    try:
        if kind == "rating_review":
            out.update(rating_review(spec))
        elif kind == "budget_cycles":
            out.update(budget_cycles(spec))
        elif kind == "election_polls":
            out.update(election_polls(spec))
        else:
            out.update({"computed": False, "reason": spec.get("reason", "no reference class")})
        if spec.get("event_study"):
            out["event_study"] = event_study_rows(spec["event_study"])
    except Exception as exc:                                             # noqa: BLE001
        out.update({"computed": False, "reason": f"could not compute: {type(exc).__name__}: {exc}"})
    return out


def rating_review(spec: dict) -> dict:
    df = emmacro.frame(spec["file"])
    d = df[(df.agency == spec["agency"]) & (df.date >= str(spec["since"])) & (df.action != "initial_state")]
    d = d[d.outlook_before == spec["outlook_before"]]
    def cat(r):
        if r.action == "downgrade":
            return "downgrade"
        if r.action == "upgrade":
            return "upgrade"
        if r.action in ("outlook_change", "watch_on") and ("neg" in str(r.outlook_after) or "down" in str(r.outlook_after)):
            return "outlook or watch to negative"
        if r.action in ("outlook_change", "watch_on"):
            return "outlook to positive"
        return "affirmed"
    counts = d.apply(cat, axis=1).value_counts().to_dict() if len(d) else {}
    n, dn = len(d), counts.get("downgrade", 0)
    first = str(spec["since"])[:4]
    years = dt.date.today().year - int(first) + 1
    n_countries = df.iso3.nunique()
    # affirmations are under-recorded, so a second denominator assumes two scheduled reviews a year
    # per sovereign; the outlook going in was not always stable, so this lower bound is generous
    n_sched = 2 * years * n_countries
    rows = d.sort_values("date").tail(12)[["iso3", "date", "action", "rating_before", "outlook_before", "rating_after", "outlook_after"]]
    return {"computed": True, "n": n, "counts": counts,
            "p_yes": round(dn / n, 3) if n else None,
            "p_yes_low": round(dn / n_sched, 3),
            "headline": f"{dn} downgrades in {n} recorded {spec['agency']} actions on a stable outlook ({100 * dn / n:.0f}%)" if n else "no recorded actions",
            "range_note": f"Recorded affirmations are incomplete. Assuming two scheduled reviews a year for each of the {n_countries} "
                          f"sovereigns since {first} ({n_sched} reviews) gives {100 * dn / n_sched:.0f}% as a lower bound. Both counts "
                          "include unscheduled actions; em-macro does not mark which were scheduled.",
            "recent": rows.to_dict("records"), "source_url": emmacro.url(spec["file"])}


def budget_cycles(spec: dict) -> dict:
    c = emmacro.frame("data/events/calendar_13.csv")
    b = c[(c.iso3 == spec["iso3"]) & (c.event_type == "budget")]
    filed = b[b.subtype == "plf_presented"].sort_values("date")
    rows = []
    for _, f in filed.iterrows():
        year = int(f.date[:4])
        nxt = b[(b.date > f.date) & (b.date < f"{year + 1}-06-30")]
        prom = nxt[nxt.subtype == "budget_promulgated"]
        special = nxt[nxt.subtype == "loi_speciale_promulgated"]
        final = nxt[nxt.subtype == "budget_final_approval"]
        if prom.empty and special.empty:
            continue                                                    # cycle still open
        pdate = prom.date.iloc[0] if len(prom) else None
        rows.append({"budget_year": year + 1, "filed": f.date, "promulgated": pdate,
                     "by_31_dec": bool(pdate and pdate <= f"{year}-12-31"), "special_law": not special.empty,
                     "art_49_3": bool(len(final) and "49.3" in str(final.outcome.iloc[0]))})
    n = len(rows)
    on_time = sum(r["by_31_dec"] for r in rows)
    recent = [r for r in rows if r["filed"] >= "2022-07-01"]
    return {"computed": True, "n": n, "p_yes": round(on_time / n, 3) if n else None,
            "headline": f"{on_time} of {n} budgets promulgated by 31 December",
            "subset": {"label": "since the government lost its majority (June 2022)", "n": len(recent),
                       "on_time": sum(r["by_31_dec"] for r in recent), "special_law": sum(r["special_law"] for r in recent),
                       "art_49_3": sum(r["art_49_3"] for r in recent),
                       "p_yes": round(sum(r["by_31_dec"] for r in recent) / len(recent), 3) if recent else None},
            "rows": rows, "source_url": emmacro.url("data/events/calendar_13.csv")}


def election_polls(spec: dict) -> dict:
    e = emmacro.frame("data/events/elections.csv")
    c = emmacro.frame("data/events/calendar_13.csv")
    sub = c[c.event_type == "election"][["iso3", "date", "subtype"]].rename(columns={"date": "vote_date"})
    e = e.merge(sub, on=["iso3", "vote_date"], how="left").dropna(subset=["poll_margin_pp", "actual_margin_pp"])
    e["leader_won"] = (e.poll_margin_pp > 0) == (e.actual_margin_pp > 0)
    e["err"] = e.actual_margin_pp - e.poll_margin_pp

    def summ(d):
        return {"n": int(len(d)), "leader_won": int(d.leader_won.sum()),
                "rms_error_pp": round(math.sqrt((d.err ** 2).mean()), 2) if len(d) else None,
                "mean_abs_error_pp": round(float(d.err.abs().mean()), 2) if len(d) else None}
    own = e[(e.iso3 == spec["iso3"]) & e.subtype.isin(spec["subtypes"])]
    out = {"computed": True, "own": summ(own),
           "rows": own[["election", "vote_date", "cand_a", "cand_b", "poll_margin_pp", "actual_margin_pp", "winner"]].to_dict("records"),
           "source_url": emmacro.url("data/events/elections.csv")}
    if spec.get("pooled_subtypes"):
        out["pooled"] = summ(e[e.subtype.isin(spec["pooled_subtypes"])])
    o = out["own"]
    out["headline"] = (f"final-poll leader won {o['leader_won']} of {o['n']}; RMS poll error {o['rms_error_pp']} pp" if o["n"] else "no rows")
    return out


def event_study_rows(q: dict) -> dict:
    em = _event_moves()
    if em is None:
        return {"error": "em-macro event_moves.csv not reachable"}
    d = em[(em.country == q["country"]) & (em.event_type == q["event_type"]) & em.subtype.isin(q["subtypes"])]
    rows = []
    for eid, g in d.groupby("event_id"):
        r = {"event": eid, "date": g.event_date.iloc[0], "subtype": g.subtype.iloc[0]}
        for _, x in g.iterrows():
            v = x.ab_1
            if x.asset == "FX" and v == v:
                r["usd_fx_pct"] = round(-float(v), 2)                   # flip to USD/xxx
            elif x.asset == "Y10" and v == v:
                r["y10_bp"] = round(float(v), 1)
        rows.append(r)
    return {"label": q.get("label"), "rows": sorted(rows, key=lambda r: r["date"]), "source_url": emmacro.url("results/test/event_moves.csv")}


# --------------------------------------------------------------------------
# markets
# --------------------------------------------------------------------------

def market_prices() -> tuple[dict, dict]:
    pm, ks = {}, {}
    p = store.DATA / "markets" / "polymarket.json"
    if p.exists():
        snap = json.loads(p.read_text())
        pm = {m["id"]: {**m, "as_of": snap["fetched_at"]} for m in snap["events"]}
    k = store.DATA / "markets" / "kalshi.json"
    if k.exists():
        snap = json.loads(k.read_text())
        ks = {m["ticker"]: {**m, "as_of": snap["fetched_at"]} for m in snap["markets"]}
    return pm, ks


def _live_pm(mid: str) -> dict | None:
    try:
        m = get(f"https://gamma-api.polymarket.com/markets/{mid}", timeout=30).json()
        prices = json.loads(m["outcomePrices"]) if isinstance(m.get("outcomePrices"), str) else m.get("outcomePrices")
        return {"id": mid, "question": m.get("question"), "yes": float(prices[0]), "volume": float(m.get("volume") or 0),
                "event_slug": (m.get("events") or [{}])[0].get("slug", ""), "as_of": store.now_iso()}
    except Exception as exc:                                             # noqa: BLE001
        log.warning("polymarket %s: %s", mid, exc)
        return None


def markets_for(sc: dict, pm: dict, ks: dict, live: bool) -> dict:
    rows = []
    for m in sc.get("markets", []):
        if m["venue"] == "polymarket":
            x = pm.get(m["id"]) or (_live_pm(m["id"]) if live else None)
            row = {"venue": "Polymarket", "id": m["id"], "prob": x and x.get("yes"), "question": x and x.get("question"),
                   "volume": x and x.get("volume"), "as_of": x and x.get("as_of"),
                   "url": f"https://polymarket.com/event/{x['event_slug']}" if x and x.get("event_slug") else None}
        else:
            x = ks.get(m["ticker"])
            row = {"venue": "Kalshi", "id": m["ticker"], "prob": x and x.get("last_price"), "question": x and f"{x['event']}: {x['title']}",
                   "volume": x and x.get("volume"), "as_of": x and x.get("as_of"),
                   "url": f"https://kalshi.com/markets/{(x.get('series_ticker') or '').lower()}" if x else None}
        row.update({"note": m.get("note"), "related": bool(m.get("related")),
                    "branches": m.get("yes_branches") or m.get("branches") or []})
        rows.append(row)
    # P(YES): the first direct market, unless several markets are slices of one multi-outcome event
    # (the presidential winner market): then sum the slices mapped to the YES branches, normalised
    # by the sum over all slices listed for the scenario.
    yes_set = set(sc["yes_branches"])
    direct = [r for r in rows if not r["related"] and r["prob"] is not None]
    by_branch = {b["id"]: 0.0 for b in sc["branches"]}
    market_yes, how = None, None
    if len(direct) > 3:
        tot = sum(r["prob"] for r in direct)
        for r in direct:
            for b in r["branches"]:
                by_branch[b] += r["prob"] / tot / len(r["branches"])
        market_yes = round(sum(by_branch[b] for b in yes_set), 4)
        how = f"sum of {len(direct)} candidate markets, normalised to 100%; {round(100 * (1 - sum(by_branch.values())), 1)}% on unlisted outcomes"
        by_branch = {k: round(v, 4) for k, v in by_branch.items()}
    elif direct:
        r = direct[0]
        market_yes, how = float(r["prob"]), f"{r['venue']} {r['id']}"
        by_branch = None
    else:
        by_branch = None
    return {"rows": rows, "yes": market_yes, "how": how, "by_branch": by_branch}


# --------------------------------------------------------------------------
# my probability
# --------------------------------------------------------------------------

def my_forecast(sid: str) -> dict | None:
    from terminal.judgement import load_judgements
    qid = f"sc:{sid}"
    recs = [r for r in load_judgements() if not r.get("rejected")]
    calls = [r for r in recs if r["type"] == "call" and (r.get("question_id") or "").lower() == qid]
    call_ids = {c["id"] for c in calls}
    ups = [r for r in recs if r["type"] == "update" and (r.get("target") in call_ids or (r.get("target") or "").lower() == qid)]
    allf = sorted(calls + ups, key=lambda r: r["submitted_at"])
    if not allf:
        return None
    last = allf[-1]
    out = {"prob": last["probability"], "record": last["id"], "submitted_at": last["submitted_at"], "kind": last["type"],
           "issue_url": last.get("issue_url")}
    if calls:
        c = sorted(calls, key=lambda r: r["submitted_at"])[-1]
        out["branches_from"] = c["id"]
        out["branch_pcts"] = [{"scenario": s["scenario"], "pct": s["pct"]} for s in c.get("scenarios", [])]
    return out


def match_branches(sc: dict, mine: dict | None) -> dict:
    if not mine or not mine.get("branch_pcts"):
        return {}
    out = {}
    for b in sc["branches"]:
        lab, bid = b["label"].lower(), b["id"].lower()
        for s in mine["branch_pcts"]:
            t = s["scenario"].lower().strip()
            if t == bid or t == lab or lab.startswith(t) or t.startswith(lab[:20]):
                out[b["id"]] = s["pct"] / 100
                break
    return out


# --------------------------------------------------------------------------
# calculator and asymmetry
# --------------------------------------------------------------------------

def to_level(current: float, move: float, kind: str, unit: str | None) -> float:
    if kind == "fx":
        return current * (1 + move / 100)
    if (unit or "").startswith("%"):
        return current + move / 100                                     # yields stored in % p.a., moves in bp
    return current + move                                               # the OAT-Bund spread is stored in bp


def calculator(sc: dict, cfg: dict, branches: list[dict]) -> dict:
    """Defaults: good level = today + the good branch's expected move, bad level = today + the bad
    branch's. With these defaults the implied probability only restates the move estimates (it is
    the probability that makes the expected move zero), so the page asks for real outcome levels
    before it uses the calculator as a market probability."""
    spec = sc["calculator"]
    code = spec["instrument"]
    icfg = cfg["instruments"][code]
    inst = book.Instrument(code, icfg)
    last = inst.latest()
    if not last:
        return {"instrument": code, "error": "no data"}
    s = inst.series or {}
    by_id = {b["id"]: b for b in branches}

    def branch_move(side: str, override: str | None):
        cands = [by_id[override]] if override else [b for b in branches if b["side"] == side]
        for b in cands:
            for m in b["moves"]:
                if m["instrument"] == code and m.get("value") is not None:
                    return b["id"], m
        return None, None
    gid, gm = branch_move("good", spec.get("good_branch"))
    bid, bm = branch_move("bad", spec.get("bad_branch"))
    one_year = (dt.date.fromisoformat(last[0]) - dt.timedelta(days=365)).isoformat()
    year = [v for d, v in inst.obs if d >= one_year]
    out = {"instrument": code, "name": icfg["name"], "kind": icfg["kind"], "series": inst.series_id, "current": last[1], "as_of": last[0],
           "unit": s.get("unit"), "good_branch": gid, "bad_branch": bid,
           "good_move": gm and gm["value"], "bad_move": bm and bm["value"], "move_unit": gm and gm["unit"],
           "range_12m": [min(year), max(year)] if year else None, "proxy": bool(s.get("proxy")), "frequency": s.get("frequency"),
           "source": s.get("source"), "source_url": s.get("source_url"), "levels_are_defaults": True,
           "degraded": degraded.for_series(inst.series_id, degraded.active()),
           "default_basis": "today's level plus the expected move of the good and bad branches"}
    if gm and bm:
        out["good_level"] = round(to_level(last[1], gm["value"], icfg["kind"], s.get("unit")), 4)
        out["bad_level"] = round(to_level(last[1], bm["value"], icfg["kind"], s.get("unit")), 4)
    return out


def implied_good(c: dict) -> float | None:
    g, b, x = c.get("good_level"), c.get("bad_level"), c.get("current")
    if None in (g, b, x) or g == b:
        return None
    return (x - b) / (g - b)


def yes_is_good(sc: dict) -> bool:
    sides = {b["side"] for b in sc["branches"] if b["id"] in sc["yes_branches"]}
    return "good" in sides


def asymmetry(sc: dict, calc: dict, market_yes: float | None, mine: dict | None, days: int | None) -> dict:
    """Server-side flag with the default calculator levels. The calculator's probability counts as
    the market's only once you enter your own levels on the page (it recomputes there)."""
    yes_good = yes_is_good(sc)
    out = {"yes_is_good": yes_good, "market_yes": market_yes, "market_source": "prediction market" if market_yes is not None else None,
           "days": days, "rules": ASYM}
    checks = {}
    if mine and market_yes is not None:
        gap = 100 * (mine["prob"] - market_yes)
        checks["gap"] = {"value": round(gap, 1), "ok": abs(gap) >= ASYM["gap_pp"]}
        favour_good = (mine["prob"] > market_yes) == yes_good
        g, b, x = calc.get("good_level"), calc.get("bad_level"), calc.get("current")
        if None not in (g, b, x):
            target, other = (g, b) if favour_good else (b, g)
            reward, risk = abs(target - x), abs(x - other)
            rr = reward / risk if risk else None
            checks["reward_risk"] = {"value": round(rr, 2) if rr is not None else None, "ok": rr is not None and rr >= ASYM["reward_risk"],
                                     "favours": "good" if favour_good else "bad", "target": target, "stop": other}
        else:
            checks["reward_risk"] = {"value": None, "ok": False, "why": "no calculator levels"}
    else:
        checks["gap"] = {"value": None, "ok": False,
                         "why": "no call yet" if not mine else "no prediction market: enter outcome levels in the calculator"}
        checks["reward_risk"] = {"value": None, "ok": False, "why": "needs the gap first"}
    checks["timing"] = {"value": days, "ok": days is not None and ASYM["min_days"] <= days <= ASYM["max_days"]}
    out["checks"] = checks
    out["flag"] = all(c.get("ok") for c in checks.values())
    return out


# --------------------------------------------------------------------------

def find_event(spec: dict, cal: dict) -> dict | None:
    for e in cal.get("events", []):
        if e["country"] == spec["country"] and spec["title"].lower() in e["title"].lower():
            return e
    return None


def indicators(sc: dict) -> list[dict]:
    out = []
    for q in sc.get("indicators", []):
        s = store.load_series(q["series"])
        if not s:
            continue
        fi = s["fields"].index(q["field"]) + 2
        rows = [r for r in s["history"] if r[1] == q["ref"] and r[fi] is not None]
        if not rows:
            continue
        cutoff = (dt.date.fromisoformat(rows[-1][0]) - dt.timedelta(days=91)).isoformat()
        prev = [r for r in rows if r[0] <= cutoff]
        out.append({"label": q["label"], "value": rows[-1][fi], "as_of": rows[-1][0], "target": q.get("target"),
                    "three_months_ago": prev[-1][fi] if prev else None, "series": q["series"],
                    "source": s.get("source"), "source_url": s.get("source_url")})
    return out


def build(live: bool = True) -> dict:
    spec = yaml.safe_load(INPUT.read_text())
    cfg = book.load_config()
    cal = json.loads((store.DATA / "calendar.json").read_text()) if (store.DATA / "calendar.json").exists() else {"events": []}
    wi, em = _what_if(), _event_moves()
    pm, ks = market_prices()
    today = dt.date.today()
    out = []
    for sc in spec["scenarios"]:
        ev = find_event(sc["event"], cal)
        days = (dt.date.fromisoformat(ev["date"]) - today).days if ev else None
        branches = []
        for b in sc["branches"]:
            branches.append({**{k: b[k] for k in ("id", "label", "side")}, "signposts": b.get("signposts", []),
                             "moves": [resolve_move(m, cfg, wi, em) for m in b.get("moves", [])]})
        mk = markets_for(sc, pm, ks, live)
        mine = my_forecast(sc["id"])
        calc = calculator(sc, cfg, branches)
        asym = asymmetry(sc, calc, mk["yes"], mine, days)
        my_branch = match_branches(sc, mine)
        for b in branches:
            b["p_mine"] = my_branch.get(b["id"])
            b["p_market"] = (mk["by_branch"] or {}).get(b["id"]) if mk["by_branch"] else None
            b["p_ai"] = None
        out.append({"id": sc["id"], "title": sc["title"], "country": sc["country"], "question": sc["question"],
                    "resolution": sc["resolution"], "resolution_date": str(sc["resolution_date"]), "question_id": f"sc:{sc['id']}",
                    "yes_branches": sc["yes_branches"], "instruments": sc["instruments"],
                    "event": ev and {k: ev.get(k) for k in ("id", "date", "title", "status", "source", "importance")}, "days_to_event": days,
                    "base_rate": base_rate(sc.get("base_rate", {})), "branches": branches, "markets": mk, "mine": mine,
                    "ai": {"available": False, "note": "No AI judgement yet for this question."},
                    "calculator": calc, "asymmetry": asym, "indicators": indicators(sc)})
    from terminal import brief
    brief.apply_ai(out)
    res = {"generated_at": store.now_iso(), "asymmetry_rules": ASYM, "scenarios": out,
           "em_macro": emmacro.RAW, "notes": ["Moves marked assumption are judgements or rescalings, not em-macro estimates.",
                                             "Market probabilities are hidden until you reveal them, as elsewhere on the site."]}
    OUT.write_text(json.dumps(res, ensure_ascii=False, indent=1, default=_json_default) + "\n")
    return res


def _json_default(x):
    if isinstance(x, float) and math.isnan(x):
        return None
    if hasattr(x, "item"):
        return x.item()
    return str(x)


def market_yes(sid: str) -> dict | None:
    """Market P(YES) for question id sc:<id>, from the last build (used by judgement scoring)."""
    if not OUT.exists():
        return None
    for s in json.loads(OUT.read_text())["scenarios"]:
        if s["id"] == sid:
            a = s["asymmetry"]
            if a.get("market_yes") is None:
                return None
            return {"prob": a["market_yes"], "source": f"scenario {sid}: {a['market_source']}" +
                    (f" ({s['markets']['how']})" if s["markets"].get("how") else ""), "as_of": s.get("calculator", {}).get("as_of")}
    return None
