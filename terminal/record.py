"""Track record (Phase 5): data/book/record.json, rebuilt after every book and judgement run.

Questions, scored exactly as mine are (Brier, and log score clipped at 1%), on each resolved question:
    me          my last forecast before resolution
    AI          the AI's blind probability recorded with that forecast (the AI never sees my calls);
                on scenario questions I never called, its last judgement before resolution
    market      the market-implied probability recorded at the same moment
    no-change   my first forecast on the question, held unchanged: do my updates add anything?
Every statistic carries its count. Groups under 10 items read "insufficient data"; everything is
labelled "noisy" while fewer than 100 questions have resolved.

Skill: the Brier score split into calibration (reliability: lower is better) and discrimination
(resolution: higher is better) over ten probability bins, plus the area under the ROC curve.
Groups: catalyst type (election, budget, rating, central bank, trade, other), my stated
confidence, and lead time (forecast made 90+, 30-90 or under 30 days before resolution).
Blend: a 50/50 average of me and the AI, shown once 20 shared questions have resolved.

Horizons' view: its weekly leans scored like any forecaster (terminal/horizons.py), and against my
calls on the same hz: questions.

Trades: P&L per unit of risk (R = P&L / risk to the stop at entry, after costs), split into price,
carry and cost; the book against em-macro's systematic strategy and buy-and-hold over the same
period; hit rate and average win and loss by instrument and by thesis type.
"""

from __future__ import annotations

import datetime as dt
import json
import math
import re
from pathlib import Path

from terminal import store
from terminal.judgement import LOG_CLIP, brier, load_judgements, log_score

BOOK = store.ROOT / "data" / "book"
OUT = BOOK / "record.json"
MIN_GROUP = 10
MIN_OVERALL = 100
MIN_BLEND = 20
TYPES = ["election", "budget", "rating", "central bank", "trade", "other"]
CAL_TYPE = {"politics": "election", "election": "election", "elections": "election", "fiscal": "budget", "budget": "budget",
            "rating": "rating", "ratings": "rating", "rates": "central bank", "trade": "trade"}
KEYWORDS = [("election", r"elect|vote|presiden|midterm|ballot|run-off|congress seats|supermajorit"),
            ("rating", r"rating|downgrade|upgrade|s&p|moody|fitch|kbra|outlook"),
            ("central bank", r"copom|selic|banxico|fomc|ecb|policy rate|rate decision|central bank|rate cut|rate hike|cuts? rates|hikes? rates"),
            ("budget", r"budget|fiscal|deficit|primary|ploa|plf|paquete|spending|tax|pension|loi de finances"),
            ("trade", r"usmca|tariff|trade|t-mec")]


def _read(path: Path, default=None):
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return default


def catalyst_type(qid: str | None, text: str, cal: dict, scen: dict) -> str:
    qid = qid or ""
    if qid.startswith("sc:") and qid[3:] in scen:
        ev = cal.get((scen[qid[3:]].get("event") or {}).get("id") or "")
        if ev and CAL_TYPE.get(ev.get("type")):
            return CAL_TYPE[ev["type"]]
        text = scen[qid[3:]].get("question", "") + " " + text
    for key in (qid, qid[3:] if qid.startswith("ev:") else ""):
        if key in cal and CAL_TYPE.get(cal[key].get("type")):
            return CAL_TYPE[cal[key]["type"]]
    if qid.startswith("fc:"):
        var = qid.split(".")[1] if "." in qid else ""
        return "central bank" if "rate" in var else "budget" if var in ("balance", "primary", "nominal") else "other"
    t = text.lower()
    for name, pat in KEYWORDS:
        if re.search(pat, t):
            return name
    return "other"


def _lead_bucket(submitted: str, resolves: str | None) -> str | None:
    if not resolves:
        return None
    days = (dt.date.fromisoformat(resolves[:10]) - dt.date.fromisoformat(submitted[:10])).days
    return "90+ days" if days >= 90 else "30-90 days" if days >= 30 else "under 30 days"


def _mean(xs):
    return round(sum(xs) / len(xs), 4) if xs else None


def score_block(items: list[dict], who: str) -> dict:
    ps = [(i[who], i["y"]) for i in items if i.get(who) is not None]
    return {"n": len(ps), "brier": _mean([brier(p, y) for p, y in ps]), "log": _mean([log_score(p, y) for p, y in ps])}


def decomposition(pairs: list[tuple[float, int]]) -> dict:
    """Murphy decomposition of the Brier score over ten bins, and the ROC AUC."""
    n = len(pairs)
    if not n:
        return {"n": 0}
    base = sum(y for _, y in pairs) / n
    rel = res = 0.0
    for b in range(10):
        sel = [(p, y) for p, y in pairs if (b / 10 <= p < (b + 1) / 10) or (b == 9 and p == 1.0)]
        if not sel:
            continue
        pk, ok = sum(p for p, _ in sel) / len(sel), sum(y for _, y in sel) / len(sel)
        rel += len(sel) * (pk - ok) ** 2
        res += len(sel) * (ok - base) ** 2
    pos = [p for p, y in pairs if y == 1]
    neg = [p for p, y in pairs if y == 0]
    auc = None
    if pos and neg:
        auc = sum((1.0 if a > b else 0.5 if a == b else 0.0) for a in pos for b in neg) / (len(pos) * len(neg))
    return {"n": n, "calibration_error": round(rel / n, 4), "discrimination": round(res / n, 4),
            "uncertainty": round(base * (1 - base), 4), "auc": round(auc, 3) if auc is not None else None}


def _ai_history() -> dict[str, list[tuple[str, float]]]:
    """Every AI judgement in the brief archive: question id -> [(date, p_yes)]."""
    out: dict[str, list[tuple[str, float]]] = {}
    for p in sorted((store.DATA / "brief" / "briefs").glob("*.json")):
        b = _read(p, {})
        j = b.get("judgement") or {}
        if not j.get("ran"):
            continue
        for q in j.get("questions", []):
            if q.get("p_yes") is not None:
                out.setdefault(q["question_id"], []).append((j.get("date") or b.get("date"), q["p_yes"] / 100))
    return out


def question_items() -> tuple[list[dict], list[dict]]:
    """(items scored for everyone, AI-only items on questions I never called)."""
    state = _read(BOOK / "judgements.json", {"questions": []})
    cal = {e["id"]: e for e in (_read(store.DATA / "calendar.json", {}) or {}).get("events", []) + (_read(store.DATA / "calendar.json", {}) or {}).get("past_events", [])}
    scen = {s["id"]: s for s in (_read(store.DATA / "scenarios.json", {}) or {}).get("scenarios", [])}
    calls = {r["id"]: r for r in load_judgements() if r.get("type") == "call" and not r.get("rejected")}
    ai_hist = _ai_history()
    items, called = [], set()
    for q in state.get("questions", []):
        called.add(q.get("question_id"))
        if not q.get("resolution") or not q.get("forecasts"):
            continue
        final, first = q["forecasts"][-1], q["forecasts"][0]
        y = int(q["resolution"]["outcome"])
        call = q.get("call") or calls.get(q["key"]) or {}
        ai = (final.get("ai") or {}).get("prob")
        if ai is None and q.get("question_id") in ai_hist:
            prior = [p for d, p in ai_hist[q["question_id"]] if d <= final["submitted_at"][:10]]
            ai = prior[-1] if prior else None          # the AI's latest judgement before my forecast: still blind
        resolves = q.get("resolution_date") or q["resolution"].get("date")
        items.append({"key": q["key"], "question": q["question"], "question_id": q.get("question_id"), "y": y,
                      "resolved_on": q["resolution"].get("date"), "me": final["prob"], "ai": ai,
                      "market": (final.get("market") or {}).get("prob"), "no_change": first["prob"],
                      "type": catalyst_type(q.get("question_id"), q["question"], cal, scen),
                      "confidence": (call.get("confidence") or "unstated") or "unstated",
                      "lead": _lead_bucket(final["submitted_at"], resolves), "submitted_at": final["submitted_at"],
                      "premortem": call.get("premortem")})
    # AI judgements on resolved scenario questions I never called (resolved with the Resolve form)
    res = {r["target"]: r for r in load_judgements() if r.get("type") == "resolve" and not r.get("rejected")}
    ai_only = []
    for qid, hist in ai_hist.items():
        if qid in called or qid not in res:
            continue
        r = res[qid]
        prior = [p for d, p in hist if d <= r["submitted_at"][:10]]
        if prior:
            ai_only.append({"key": qid, "question_id": qid, "question": (scen.get(qid[3:]) or {}).get("question", qid), "y": int(r["outcome"]),
                            "resolved_on": r["submitted_at"][:10], "ai": prior[-1],
                            "type": catalyst_type(qid, "", cal, scen)})
    return items, ai_only


def group_table(items: list[dict], field: str, order: list[str]) -> list[dict]:
    rows = []
    for g in order:
        sel = [i for i in items if i.get(field) == g]
        row = {"group": g, "n": len(sel)}
        if len(sel) < MIN_GROUP:
            row["insufficient"] = True
        for who in ("me", "ai", "market"):
            row[who] = score_block(sel, who)
        rows.append(row)
    return rows


def questions_record() -> dict:
    items, ai_only = question_items()
    n = len(items)
    side = {who: score_block(items, who) for who in ("me", "ai", "market", "no_change")}
    side["ai_all"] = score_block(items + ai_only, "ai")       # the AI on every resolved question it judged
    shared_all = [i for i in items if all(i.get(w) is not None for w in ("me", "ai", "market"))]
    side_shared = {who: score_block(shared_all, who) for who in ("me", "ai", "market", "no_change")}
    skill = {who: decomposition([(i[who], i["y"]) for i in items + (ai_only if who == "ai" else []) if i.get(who) is not None])
             for who in ("me", "ai", "market")}
    blend_items = [i for i in items if i.get("ai") is not None]
    blend = {"n_shared": len(blend_items), "min": MIN_BLEND, "ready": len(blend_items) >= MIN_BLEND}
    if blend["ready"]:
        for i in blend_items:
            i["blend"] = (i["me"] + i["ai"]) / 2
        blend.update({who: score_block(blend_items, who) for who in ("me", "ai", "blend")})
        b = blend["blend"]["brier"]
        blend["verdict"] = ("the 50/50 blend beat both" if b < blend["me"]["brier"] and b < blend["ai"]["brier"] else
                            "the blend beat me but not the AI" if b < blend["me"]["brier"] else
                            "the blend beat the AI but not me" if b < blend["ai"]["brier"] else "the blend beat neither")
    conf = ["high", "medium", "low", "unstated"]
    return {"n_resolved": n, "n_ai_only": len(ai_only), "noisy": n < MIN_OVERALL, "min_group": MIN_GROUP, "min_overall": MIN_OVERALL,
            "side_by_side": side, "shared": {"n": len(shared_all), "scores": side_shared}, "skill": skill,
            "by_type": group_table(items, "type", TYPES), "by_confidence": group_table(items, "confidence", conf),
            "by_lead": group_table(items, "lead", ["90+ days", "30-90 days", "under 30 days"]), "blend": blend,
            "items": items, "ai_only": ai_only,
            "definitions": {"me": "my last forecast before resolution", "ai": "the AI's blind probability recorded with that forecast",
                            "market": "the market-implied probability recorded at the same moment",
                            "no_change": "my first forecast on the question, never updated",
                            "log": f"ln(probability given to the outcome), clipped at {LOG_CLIP:.0%}; higher is better",
                            "brier": "(probability - outcome)^2; lower is better"}}


# --------------------------------------------------------------------------
# Trades
# --------------------------------------------------------------------------

THESIS_TYPES = ["catalyst", "carry", "valuation", "momentum", "relative value", "hedge", "other", "unspecified"]


def _trade_rows(state: dict) -> list[dict]:
    from terminal.book import load_records
    recs = load_records()
    rows = []
    for v in state.get("trades", []):
        if v["status"] not in ("closed", "open") or not v.get("fill"):
            continue
        risk = v["fill"].get("risk_to_stop_usd") or 0
        p = v.get("pnl") or {}
        op = (recs.get(v["trade_id"]) or {}).get("open") or v["open"]
        rows.append({"trade_id": v["trade_id"], "status": v["status"], "instrument": v["open"]["instrument"],
                     "thesis_type": (op.get("thesis_type") or "unspecified").lower(), "thesis": op.get("thesis"),
                     "risk_usd": risk, "pnl": p, "win": (p.get("total") or 0) > 0,
                     "r": {k: round(p[k] / risk, 3) if risk and p.get(k) is not None else None for k in ("total", "price", "carry", "cost")},
                     "entry_date": v["fill"]["entry_date"], "exit_date": (v.get("exit") or {}).get("exit_date"),
                     "postmortem": (v.get("close_request") or {}).get("postmortem")})
    return rows


def _hit(rows: list[dict]) -> dict:
    wins = [r["pnl"]["total"] for r in rows if r["win"]]
    losses = [r["pnl"]["total"] for r in rows if not r["win"]]
    rs = [r["r"]["total"] for r in rows if r["r"]["total"] is not None]
    return {"n": len(rows), "insufficient": len(rows) < MIN_GROUP, "hit_rate_pct": round(100 * len(wins) / len(rows), 1) if rows else None,
            "avg_win_usd": _mean(wins), "avg_loss_usd": _mean(losses), "avg_r": _mean(rs), "total_r": round(sum(rs), 3) if rs else None}


def trades_record() -> dict:
    state = _read(BOOK / "state.json", {})
    rows = _trade_rows(state)
    closed = [r for r in rows if r["status"] == "closed"]
    open_ = [r for r in rows if r["status"] == "open"]

    def split(rs):
        out = {"n": len(rs)}
        for k in ("total", "price", "carry", "cost"):
            xs = [r["r"][k] for r in rs if r["r"][k] is not None]
            out[k + "_r"] = round(sum(xs), 3) if xs else None
            out[k + "_usd"] = round(sum(r["pnl"].get(k) or 0 for r in rs), 2) if rs else None
        out["per_trade_r"] = round(out["total_r"] / len(rs), 3) if rs and out["total_r"] is not None else None
        return out
    eq = state.get("equity", {})
    sy = state.get("systematic", {})
    sys_ret = None
    if sy.get("available") and sy.get("since_start"):
        sys_ret = {"return_pct": round(100 * (sy["since_start"][-1][1] / state["starting_capital_usd"] - 1), 2),
                   "to": sy["since_start"][-1][0], "n_months": len(sy["since_start"])}
    bh = [{"code": b["code"], "name": b["name"], "description": b["description"], **(b.get("since_start") or {})} for b in state.get("benchmarks", [])]
    bh_valid = [b["return_pct"] for b in bh if b.get("return_pct") is not None]
    instruments = sorted({r["instrument"] for r in closed})
    return {"start_date": state.get("start_date"), "as_of": state.get("as_of"),
            "closed": split(closed), "open": split(open_),
            "versus": {"book": {"return_pct": eq.get("return_pct"), "pnl_usd": eq.get("pnl_usd"), "n_trades": len(closed) + len(open_),
                                "total_r": split(closed + open_)["total_r"]},
                       "systematic": sys_ret or {"note": sy.get("message") or "no month since the start date yet"},
                       "buy_and_hold": {"equal_weight_return_pct": _mean(bh_valid), "n_instruments": len(bh_valid), "rows": bh},
                       "note": "Same period: from the book's start date. The systematic strategy is monthly and runs at its own risk "
                               "level; buy-and-hold is $100,000 long each instrument with no costs. Compare direction more than size."},
            "by_instrument": [{"group": i, **_hit([r for r in closed if r["instrument"] == i])} for i in instruments],
            "by_thesis": [{"group": t, **_hit([r for r in closed if r["thesis_type"] == t])} for t in THESIS_TYPES
                          if any(r["thesis_type"] == t for r in closed)],
            "overall": _hit(closed), "rows": rows, "min_group": MIN_GROUP}


def build() -> dict:
    from terminal import brief, horizons
    rec = {"generated_at": store.now_iso(), "questions": questions_record(), "trades": trades_record()}
    if not brief.views_on():          # Horizons' AI views are stopped: no horizons block
        OUT.parent.mkdir(parents=True, exist_ok=True)
        OUT.write_text(json.dumps(rec, ensure_ascii=False, indent=1, default=str) + "\n")
        return rec
    try:
        st = horizons.load()
        if st.get("history"):
            horizons.PATH.write_text(json.dumps(horizons.resolve(st), ensure_ascii=False, indent=1) + "\n")
        rec["horizons"] = horizons.score(_read(BOOK / "judgements.json", {"questions": []}).get("questions", []))
    except Exception as exc:  # noqa: BLE001
        rec["horizons"] = {"error": str(exc)}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(rec, ensure_ascii=False, indent=1, default=str) + "\n")
    return rec
