"""Horizons' paper book on Supabase (tables in supabase/schema.sql), run daily after the data job.

1. Pending trades fill at the first end-of-day close strictly after they were requested (each
   instrument's close time from data/book/config.yaml, as in the GitHub-issue book). Size is set by
   risk: risk_usd = risk_pct% of the account's equity (US$100,000 plus realised and unrealised P&L),
   notional = risk_usd / loss per US$1 of notional between the fill and the stop. A stop on the wrong
   side of the fill, an unknown instrument or one with no prices rejects the trade.
2. Open trades are marked to market at every close since entry: marks = [[date, value, price, carry,
   cost, total], ...], with the full round-trip cost charged at entry as the book does. A close at or
   through the stop or the target closes the trade at that close; so does a close request (trade_closes)
   at the first close after it was made. Closed trades are not touched again.
3. Buy and Sell decisions with a probability and a horizon are scored once a close on or after the
   horizon exists: outcome 1 if the decided direction would have gained on price from the close on the
   decision date to that close, Brier = (probability − outcome)².

It writes only to Supabase; nothing is committed to the repository.
"""

from __future__ import annotations

import logging

from terminal import book, store
from terminal.supa import Client

log = logging.getLogger(__name__)
START_CAPITAL = 100000.0


def _instrument(cfg: dict, code: str, series_id: str | None = None):
    icfg = cfg["instruments"].get(code)
    if not icfg:
        return None
    inst = book.Instrument(code, icfg, series_id)
    return inst if inst.obs else None


def equity(trades: list[dict]) -> float:
    return START_CAPITAL + sum(float(t.get("pnl_total") or 0) for t in trades if t.get("status") in ("open", "closed"))


def _fill_dict(inst, t: dict) -> dict:
    n, dur = float(t["notional_usd"]), t.get("duration")
    dur = float(dur) if dur is not None else None
    return {"direction_sign": 1 if t["direction"] == "long" else -1, "notional_usd": n, "entry_value": float(t["entry_value"]),
            "entry_date": t["entry_date"], "duration": dur, "cost_usd": inst.cost(n, dur)}


def fill(cfg: dict, t: dict, eq: float, today: str) -> dict | None:
    """The update for a pending trade: a fill, a rejection, or None if no close is due yet."""
    inst = _instrument(cfg, t["instrument"])
    if inst is None:
        why = "unknown instrument" if t["instrument"] not in cfg["instruments"] else "no prices stored for this instrument"
        return {"status": "rejected", "reject_reason": why, "exit_reason": "rejected"}
    c = inst.first_close_after(book.parse_ts(t["requested_at"]))
    if not c or c[0] > today:
        return None
    date, v0 = c
    sign = 1 if t["direction"] == "long" else -1
    stop = float(t["stop_level"])
    if sign * inst.favourable * (v0 - stop) <= 0:
        return {"status": "rejected", "exit_reason": "rejected",
                "reject_reason": f"stop {stop:g} is on the wrong side of the fill {v0:g} on {date} for a {t['direction']} position"}
    dur = inst.duration(date, v0)
    unit = inst.unit_loss_to(v0, stop, dur)
    if unit <= 0:
        return {"status": "rejected", "exit_reason": "rejected", "reject_reason": "stop equals the fill; cannot size by risk"}
    risk = float(t["risk_pct"]) / 100.0 * eq
    return {"status": "open", "entry_date": date, "entry_value": v0, "notional_usd": round(risk / unit, 2), "risk_usd": round(risk, 2),
            "duration": dur, "series_used": inst.series_id}


def mark(cfg: dict, t: dict, closes: list[dict], today: str, rates: dict) -> dict:
    """Marks from entry to the latest close, and the exit if a stop, target or close request is due."""
    inst = _instrument(cfg, t["instrument"], t.get("series_used"))
    if inst is None:
        return {}
    f = _fill_dict(inst, t)
    stop = float(t["stop_level"])
    target = float(t["target_level"]) if t.get("target_level") is not None else None
    reqs = sorted((r for r in closes if r["trade_id"] == t["id"] and not r.get("processed_at")), key=lambda r: r["requested_at"])
    req = reqs[0] if reqs else None
    req_ts = book.parse_ts(req["requested_at"]) if req else None
    p0 = book.pnl(inst, f, f["entry_value"], f["entry_date"], rates)
    marks = [[f["entry_date"], f["entry_value"], p0["price"], p0["carry"], p0["cost"], p0["total"]]]
    out = {}
    last = (f["entry_date"], f["entry_value"], p0)
    reason = book.hit(inst, f["direction_sign"], f["entry_value"], stop, target)   # already through the stop at the entry close
    if not reason:
        for d, v in inst.closes_after(f["entry_date"]):
            if d > today:
                break
            p = book.pnl(inst, f, v, d, rates)
            marks.append([d, v, p["price"], p["carry"], p["cost"], p["total"]])
            last = (d, v, p)
            reason = book.hit(inst, f["direction_sign"], v, stop, target)
            if not reason and req_ts and inst.close_dt(d) > req_ts:
                reason = "closed"
            if reason:
                break
    d, v, p = last
    out.update({"marks": marks, "last_date": d, "last_value": v, "pnl_price": p["price"], "pnl_carry": p["carry"],
                "pnl_cost": p["cost"], "pnl_total": p["total"]})
    if reason:
        out.update({"status": "closed", "exit_date": d, "exit_value": v, "exit_reason": reason})
        if reason == "closed":
            out["_close_request"] = req["id"]
    return out


def score(cfg: dict, dcs: list[dict], today: str) -> list[tuple[str, dict]]:
    out = []
    for x in dcs:
        if x.get("scored_at") or x.get("action") not in ("Buy", "Sell") or x.get("probability") is None or not x.get("horizon"):
            continue
        inst = _instrument(cfg, x["instrument"])
        if inst is None:
            continue
        start = inst.value_on(str(x["decision_date"]))
        end = next(((d, v) for d, v in inst.obs if d >= str(x["horizon"])), None)
        if not start or not end or end[0] > today:
            continue
        sign = 1 if x["action"] == "Buy" else -1
        gained = sign * inst.favourable * (end[1] - start[1]) > 0
        p, y = float(x["probability"]), 1 if gained else 0
        out.append((x["id"], {"outcome": y, "brier": round((p - y) ** 2, 4), "scored_at": store.now_iso(),
                              "score_note": f"{inst.cfg['name']}: {start[1]:g} on {start[0]} to {end[1]:g} on {end[0]}; "
                                            f"{'moved' if gained else 'did not move'} the decided way"}))
    return out


def run(client: Client | None = None, today: str | None = None) -> dict:
    client = client or Client()
    if not client.configured():
        log.warning("hzbook: Supabase is not configured (SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY); nothing done")
        return {"configured": False}
    today = today or store.today()
    cfg = book.load_config()
    trades = client.select("trades", order="requested_at.asc")
    closes = client.select("trade_closes", processed_at="is.null")
    eq = equity(trades)
    rates: dict = {}
    res = {"configured": True, "filled": [], "rejected": [], "marked": [], "closed": [], "scored": [], "equity_before": round(eq, 2)}
    for t in trades:
        if t["status"] != "pending":
            continue
        u = fill(cfg, t, eq, today)
        if u is None:
            continue
        u["updated_at"] = store.now_iso()
        client.patch("trades", {"id": t["id"]}, u)
        t.update(u)
        res["rejected" if u["status"] == "rejected" else "filled"].append(t["id"])
    for t in trades:
        if t["status"] != "open":
            continue
        u = mark(cfg, t, closes, today, rates)
        if not u:
            continue
        req = u.pop("_close_request", None)
        u["updated_at"] = store.now_iso()
        client.patch("trades", {"id": t["id"]}, u)
        res["marked"].append(t["id"])
        if u.get("status") == "closed":
            res["closed"].append(t["id"])
        if req:
            client.patch("trade_closes", {"id": req}, {"processed_at": store.now_iso()})
    for did, u in score(cfg, client.select("decisions", scored_at="is.null"), today):
        client.patch("decisions", {"id": did}, u)
        res["scored"].append(did)
    log.info("hzbook: %d filled, %d rejected, %d marked, %d closed, %d decisions scored", *(len(res[k]) for k in ("filled", "rejected", "marked", "closed", "scored")))
    return res
