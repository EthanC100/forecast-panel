"""Judgements: full calls, quick updates and resolutions (write-once records in data/judgements/),
market-implied and AI probabilities recorded at entry, Brier and log scores, and the journal.

    J00015-call.json      Full call (issue #15)
    U00021-update.json    Quick update (issue #21) to a call or a question id
    R00030-resolve.json   Resolution (issue #30) of a call or question id

Question ids understood for market and AI lookups and automatic resolution:
    q1..q5            forecast-panel questions (Polymarket price from data/panel_log.csv,
                      Claude's probability from gold-events, outcome from tension_questions.yaml)
    pm:<market id>    a Polymarket market (price and, once closed, outcome from the Gamma API)
    ks:<ticker>       a Kalshi market (last price and, once settled, result)
"""

from __future__ import annotations

import datetime as dt
import json
import logging
import math
from pathlib import Path

from terminal import store
from terminal.book import BOOK_DIR, TRADES_DIR, load_records
from terminal.http import get

log = logging.getLogger(__name__)

JUDGE_DIR = store.ROOT / "data" / "judgements"
STATE_PATH = BOOK_DIR / "judgements.json"
JOURNAL_PATH = BOOK_DIR / "journal.json"
CALIBRATION_MIN = 30
LOG_CLIP = 0.01


# --------------------------------------------------------------------------
# Market and AI probabilities
# --------------------------------------------------------------------------


def market_probability(qid: str | None) -> dict | None:
    """Market-implied P(yes) for a question id right now, or None."""
    if not qid:
        return None
    try:
        if qid.lower().startswith("q"):
            from forecast_panel.panel import load_panel_log
            p = load_panel_log()
            g = p[(p["question_id"] == qid.lower()) & (p["source"] == "polymarket")].dropna(subset=["prob"])
            if g.empty:
                return None
            r = g.sort_values("date").iloc[-1]
            return {"prob": float(r["prob"]), "source": "Polymarket (forecast-panel log)", "as_of": r["date"]}
        if qid.startswith("sc:"):
            from terminal import scenarios
            return scenarios.market_yes(qid[3:])
        if qid.startswith("pm:"):
            m = get(f"https://gamma-api.polymarket.com/markets/{qid[3:]}", timeout=30).json()
            prices = json.loads(m["outcomePrices"]) if isinstance(m.get("outcomePrices"), str) else m.get("outcomePrices")
            return {"prob": float(prices[0]), "source": f"Polymarket market {qid[3:]}", "as_of": store.now_iso(),
                    "question": m.get("question")}
        if qid.startswith("ks:"):
            m = get(f"https://api.elections.kalshi.com/trade-api/v2/markets/{qid[3:]}", timeout=30).json()["market"]
            p = m.get("last_price_dollars") or (m.get("last_price") / 100 if m.get("last_price") is not None else None)
            return {"prob": float(p), "source": f"Kalshi {qid[3:]}", "as_of": store.now_iso(), "question": m.get("title")} if p is not None else None
    except Exception as exc:  # noqa: BLE001
        log.warning("market probability for %s: %s", qid, exc)
    return None


def ai_probability(qid: str | None) -> dict | None:
    """Claude's probability from gold-events' forward log, for forecast-panel questions only."""
    if not qid or not qid.lower().startswith("q"):
        return None
    try:
        from forecast_panel.sources import human_column, load_forward_log
        df, why = load_forward_log()
        r = human_column(df, why, f"claude_prob_{qid.lower()}", store.today())
        if r.prob == r.prob:
            return {"prob": r.prob, "source": "Claude (gold-events forward log)", "as_of": r.as_of}
    except Exception as exc:  # noqa: BLE001
        log.warning("AI probability for %s: %s", qid, exc)
    return None


def auto_outcome(qid: str | None) -> dict | None:
    if not qid:
        return None
    try:
        if qid.lower().startswith("q"):
            from forecast_panel.questions import load_questions
            for q in load_questions():
                if q["id"] == qid.lower() and q.get("resolved") and q.get("outcome") in (0, 1):
                    return {"outcome": int(q["outcome"]), "source": "data/tension_questions.yaml",
                            "date": str(q.get("resolved_on") or q.get("resolution_date"))[:10]}
        if qid.startswith("pm:"):
            m = get(f"https://gamma-api.polymarket.com/markets/{qid[3:]}", timeout=30).json()
            prices = json.loads(m["outcomePrices"]) if isinstance(m.get("outcomePrices"), str) else m.get("outcomePrices")
            if m.get("closed") and prices and prices[0] in ("1", "0", 1, 0):
                return {"outcome": int(float(prices[0])), "source": f"Polymarket market {qid[3:]} settled",
                        "date": (m.get("closedTime") or m.get("endDate") or "")[:10]}
        if qid.startswith("ks:"):
            m = get(f"https://api.elections.kalshi.com/trade-api/v2/markets/{qid[3:]}", timeout=30).json()["market"]
            if m.get("result") in ("yes", "no"):
                return {"outcome": 1 if m["result"] == "yes" else 0, "source": f"Kalshi {qid[3:]} settled",
                        "date": (m.get("settlement_ts") or m.get("close_time") or "")[:10]}
    except Exception as exc:  # noqa: BLE001
        log.warning("auto outcome for %s: %s", qid, exc)
    return None


# --------------------------------------------------------------------------
# Scores
# --------------------------------------------------------------------------


def brier(p: float, y: int) -> float:
    return (p - y) ** 2


def log_score(p: float, y: int) -> float:
    """Natural log of the probability given to what happened, clipped at 1% / 99% (0 is best)."""
    p = min(max(p, LOG_CLIP), 1 - LOG_CLIP)
    return math.log(p if y == 1 else 1 - p)


def load_judgements() -> list[dict]:
    if not JUDGE_DIR.exists():
        return []
    return [json.loads(p.read_text()) for p in sorted(JUDGE_DIR.glob("*.json"))]


def build(resolve_online: bool = True) -> dict:
    recs = load_judgements()
    calls = {r["id"]: r for r in recs if r["type"] == "call" and not r.get("rejected")}
    updates = [r for r in recs if r["type"] == "update" and not r.get("rejected")]
    resolutions = [r for r in recs if r["type"] == "resolve" and not r.get("rejected")]
    # Each question: a call (J id) or a bare question id that updates refer to.
    questions: dict[str, dict] = {}
    for c in calls.values():
        questions[c["id"]] = {"key": c["id"], "question": c["question"], "question_id": c.get("question_id"),
                              "resolution_date": c["resolution_date"], "call": c, "forecasts": []}
        questions[c["id"]]["forecasts"].append({"record": c["id"], "kind": "call", "submitted_at": c["submitted_at"],
                                                "prob": c["probability"], "market": c.get("market_at_entry"), "ai": c.get("ai_at_entry")})
    for u in sorted(updates, key=lambda u: u["submitted_at"]):
        key = u["target"]
        if key not in questions:
            # an update to a question id with no call: find a call with that question id, else stand alone
            key = next((k for k, q in questions.items() if q.get("question_id") == u["target"]), u["target"])
            questions.setdefault(key, {"key": key, "question": u.get("question_text") or key, "question_id": u["target"],
                                       "resolution_date": None, "call": None, "forecasts": []})
        questions[key]["forecasts"].append({"record": u["id"], "kind": "update", "submitted_at": u["submitted_at"],
                                            "prob": u["probability"], "market": u.get("market_at_entry"), "ai": u.get("ai_at_entry"),
                                            "direction": u.get("direction"), "what_changed": u.get("what_changed")})
    manual = {}
    for r in sorted(resolutions, key=lambda r: r["submitted_at"]):
        manual.setdefault(r["target"], r)
    resolved = []
    for key, q in questions.items():
        res = manual.get(key) or (manual.get(q["question_id"]) if q.get("question_id") else None)
        if res:
            q["resolution"] = {"outcome": res["outcome"], "source": res.get("source"), "record": res["id"], "date": res["submitted_at"][:10]}
        elif resolve_online and q.get("question_id"):
            auto = auto_outcome(q["question_id"])
            if auto:
                q["resolution"] = auto
        if q.get("resolution"):
            y = q["resolution"]["outcome"]
            for f in q["forecasts"]:
                f["brier"] = round(brier(f["prob"], y), 4)
                f["log"] = round(log_score(f["prob"], y), 4)
                m = (f.get("market") or {}).get("prob")
                if m is not None:
                    f["market_brier"] = round(brier(m, y), 4)
                    f["market_log"] = round(log_score(m, y), 4)
            q["final"] = q["forecasts"][-1]
            resolved.append(q)
    finals = [q["final"] for q in resolved]
    paired = [f for f in finals if "market_brier" in f]
    summary = {"n_questions": len(questions), "n_resolved": len(resolved),
               "brier_mine": round(sum(f["brier"] for f in finals) / len(finals), 4) if finals else None,
               "log_mine": round(sum(f["log"] for f in finals) / len(finals), 4) if finals else None,
               "n_with_market": len(paired),
               "brier_mine_vs_market": [round(sum(f["brier"] for f in paired) / len(paired), 4),
                                        round(sum(f["market_brier"] for f in paired) / len(paired), 4)] if paired else None,
               "log_mine_vs_market": [round(sum(f["log"] for f in paired) / len(paired), 4),
                                      round(sum(f["market_log"] for f in paired) / len(paired), 4)] if paired else None,
               "calibration_min": CALIBRATION_MIN}
    if len(resolved) >= CALIBRATION_MIN:
        bins = []
        for lo in range(0, 100, 10):
            sel = [(q["final"]["prob"], q["resolution"]["outcome"]) for q in resolved
                   if lo / 100 <= q["final"]["prob"] < (lo + 10) / 100 or (lo == 90 and q["final"]["prob"] == 1.0)]
            if sel:
                bins.append({"bin": f"{lo}-{lo + 10}%", "n": len(sel), "mean_forecast": round(sum(p for p, _ in sel) / len(sel), 3),
                             "observed": round(sum(y for _, y in sel) / len(sel), 3)})
        summary["calibration"] = bins
    state = {"generated_at": store.now_iso(), "summary": summary,
             "questions": sorted(questions.values(), key=lambda q: q["forecasts"][0]["submitted_at"] if q["forecasts"] else ""),
             "rejected": [r for r in recs if r.get("rejected")]}
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=1) + "\n")
    build_journal(recs)
    return state


def build_journal(recs: list[dict] | None = None) -> list[dict]:
    """Every trade record, judgement, update, resolution and post-mortem in date order."""
    recs = recs if recs is not None else load_judgements()
    items = []
    for tid, t in load_records().items():
        op = t.get("open", {})
        if op:
            items.append({"at": op["submitted_at"], "kind": "trade-open", "id": tid, "issue": op.get("issue"),
                          "rejected": op.get("rejected", False), "errors": op.get("errors"),
                          "text": f"{op.get('direction', '?')} {op.get('instrument', '?')} · stop {op.get('stop')} · target {op.get('target')} · horizon {op.get('horizon')}",
                          "detail": op.get("thesis"), "close_early": op.get("close_early"), "link": op.get("link")})
        if f := t.get("fill"):
            items.append({"at": f["entry_close_utc"], "kind": "trade-fill", "id": tid,
                          "text": f"filled at {f['entry_value']} on {f['entry_date']} · notional ${f['notional_usd']:,.0f} · risk to stop ${f['risk_to_stop_usd']:,.0f}",
                          "detail": "; ".join(f.get("warnings") or [])})
        if c := t.get("close_request"):
            items.append({"at": c["submitted_at"], "kind": "trade-close-request", "id": tid, "issue": c.get("issue"),
                          "text": "close requested; post-mortem:", "detail": "\n".join(c.get("postmortem") or [])})
        if e := t.get("exit"):
            items.append({"at": e["exit_date"] + "T23:00:00Z", "kind": "trade-exit", "id": tid,
                          "text": f"exit at {e['exit_value']} on {e['exit_date']} ({e['reason']}) · P&L ${e['pnl']['total']:,.0f}"})
    for r in recs:
        if r["type"] == "call":
            items.append({"at": r["submitted_at"], "kind": "call", "id": r["id"], "issue": r.get("issue"), "rejected": r.get("rejected", False),
                          "errors": r.get("errors"), "text": f"{r.get('question')} · my probability {pct(r.get('probability'))} · resolves {r.get('resolution_date')}",
                          "detail": r.get("premortem"), "market": r.get("market_at_entry"), "ai": r.get("ai_at_entry")})
        elif r["type"] == "update":
            items.append({"at": r["submitted_at"], "kind": "update", "id": r["id"], "issue": r.get("issue"), "rejected": r.get("rejected", False),
                          "errors": r.get("errors"), "text": f"{r.get('target')} → {pct(r.get('probability'))} ({r.get('direction')})",
                          "detail": r.get("what_changed"), "market": r.get("market_at_entry"), "ai": r.get("ai_at_entry")})
        elif r["type"] not in ("call", "update", "resolve"):
            items.append({"at": r["submitted_at"], "kind": r["type"], "id": r["id"], "issue": r.get("issue"), "rejected": True,
                          "errors": r.get("errors"), "text": f"rejected submission for {r.get('trade_id') or r['id']}",
                          "detail": "\n".join(r.get("postmortem") or [])})
        elif r["type"] == "resolve":
            items.append({"at": r["submitted_at"], "kind": "resolve", "id": r["id"], "issue": r.get("issue"), "rejected": r.get("rejected", False),
                          "errors": r.get("errors"), "text": f"{r.get('target')} resolved {'YES' if r.get('outcome') == 1 else 'NO'}",
                          "detail": r.get("source")})
    items.sort(key=lambda x: x["at"])
    JOURNAL_PATH.parent.mkdir(parents=True, exist_ok=True)
    JOURNAL_PATH.write_text(json.dumps({"generated_at": store.now_iso(), "items": items}, ensure_ascii=False, indent=1) + "\n")
    return items


def pct(p):
    return "–" if p is None else f"{round(100 * p)}%"
