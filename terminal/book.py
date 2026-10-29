"""Paper trading book: fills at the next close, daily mark-to-market with carry and costs,
automatic stop/target exits, horizon flags, equity curve and statistics, buy-and-hold
benchmarks and em-macro's systematic strategy for comparison.

Records (data/trades/, write-once; never edited):
    T00012-open.json        the Open trade form as submitted (issue #12)
    T00012-fill.json        entry at the first close after submission (written by the daily run)
    T00012-closereq.json    the Close trade form, with the two-line post-mortem
    T00012-exit.json        exit at the first close after the close request, or at the close that hit
                            the stop or target
Derived (rebuilt every run): data/book/state.json.
"""

from __future__ import annotations

import csv
import datetime as dt
import io
import json
import logging
import os
from pathlib import Path

import yaml

from terminal import degraded, store
from terminal.http import get

log = logging.getLogger(__name__)

BOOK_DIR = store.ROOT / "data" / "book"
TRADES_DIR = store.ROOT / "data" / "trades"
CONFIG_PATH = BOOK_DIR / "config.yaml"
STATE_PATH = BOOK_DIR / "state.json"
EM_MACRO_RAW = "https://raw.githubusercontent.com/EthanC100/em-macro/main/"


class WriteOnceError(FileExistsError):
    pass


def write_once(path: Path, obj: dict) -> None:
    """Records are never edited: refuse to overwrite. Old versions live only in git history."""
    if path.exists():
        raise WriteOnceError(f"{path.name} already exists; records are write-once")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=1) + "\n")


def load_config() -> dict:
    return yaml.safe_load(CONFIG_PATH.read_text())


def parse_ts(s: str) -> dt.datetime:
    s = str(s).replace("Z", "+00:00")
    d = dt.datetime.fromisoformat(s)
    return d if d.tzinfo else d.replace(tzinfo=dt.timezone.utc)


# --------------------------------------------------------------------------
# Instruments and pricing
# --------------------------------------------------------------------------


class Instrument:
    def __init__(self, code: str, cfg: dict, series_id: str | None = None):
        self.code, self.cfg = code, cfg
        self.kind = cfg["kind"]
        ids = [series_id] if series_id else cfg["series"]
        self.series = None
        for sid in ids:
            s = store.load_series(sid)
            if s and s.get("history"):
                self.series = s
                break
        self.series_id = self.series["id"] if self.series else (ids[0] if ids else None)
        rows = self.series["history"] if self.series else []
        self.obs = [(r[0], float(r[1])) for r in rows if isinstance(r[1], (int, float))]
        self.extra = {r[0]: r[2:] for r in rows}
        hh, mm = (int(x) for x in cfg.get("close_utc", "21:00").split(":"))
        self.close_time = dt.time(hh, mm, tzinfo=dt.timezone.utc)
        self.scale = {"yield": 100.0, "spread_bp": 10000.0}.get(self.kind)
        self.favourable = 1 if self.kind == "fx" else -1   # +1: long gains when the value rises

    def close_dt(self, date: str) -> dt.datetime:
        return dt.datetime.combine(dt.date.fromisoformat(date), self.close_time)

    def first_close_after(self, ts: dt.datetime, after_date: str | None = None):
        for d, v in self.obs:
            if self.close_dt(d) > ts and (after_date is None or d > after_date):
                return d, v
        return None

    def closes_after(self, date: str):
        return [(d, v) for d, v in self.obs if d > date]

    def value_on(self, date: str):
        last = None
        for d, v in self.obs:
            if d > date:
                break
            last = (d, v)
        return last

    def latest(self, before: dt.datetime | None = None):
        """Latest close, or the latest one published at or before `before`."""
        if before is None:
            return self.obs[-1] if self.obs else None
        prior = [(d, v) for d, v in self.obs if self.close_dt(d) <= before]
        return prior[-1] if prior else None

    def duration(self, entry_date: str, entry_value: float) -> float | None:
        dur = self.cfg.get("duration")
        if self.kind == "fx":
            return None
        if dur == "zero_coupon":
            years = (dt.date.fromisoformat(self.cfg["maturity"]) - dt.date.fromisoformat(entry_date)).days / 365.25
            return round(max(years, 0.0) / (1 + entry_value / 100.0), 4)
        return float(dur)

    def unit_loss_to(self, entry: float, level: float, duration: float | None) -> float:
        """Loss per 1 USD of notional if the value moves from entry to `level` (absolute)."""
        if self.kind == "fx":
            return abs(level - entry) / level
        return duration * abs(level - entry) / self.scale

    def cost(self, notional: float, duration: float | None) -> float:
        if self.kind == "fx":
            return notional * self.cfg.get("cost_round_trip_pct", 0.075) / 100.0
        return notional * duration * self.cfg.get("cost_round_trip_bp", 2) / 10000.0


def _rate_lookup(sid: str | None):
    s = store.load_series(sid) if sid else None
    obs = [(r[0], r[1]) for r in (s or {}).get("history", []) if isinstance(r[1], (int, float))]
    return obs


def _rate_on(obs, date: str):
    lo, hi, ans = 0, len(obs) - 1, None
    while lo <= hi:
        mid = (lo + hi) // 2
        if obs[mid][0] <= date:
            ans = obs[mid][1]
            lo = mid + 1
        else:
            hi = mid - 1
    return ans


def carry(inst: Instrument, direction: int, notional: float, start: str, end: str, rates_cache: dict) -> float:
    """FX carry, actual/360 on calendar days in (start, end], at the previous day's rate differential."""
    if inst.kind != "fx" or end <= start:
        return 0.0
    usd = rates_cache.setdefault(inst.cfg["rate_usd"], _rate_lookup(inst.cfg["rate_usd"]))
    loc = rates_cache.setdefault(inst.cfg["rate_local"], _rate_lookup(inst.cfg["rate_local"]))
    total, d = 0.0, dt.date.fromisoformat(start)
    stop = dt.date.fromisoformat(end)
    while d < stop:
        ru, rl = _rate_on(usd, d.isoformat()), _rate_on(loc, d.isoformat())
        if ru is not None and rl is not None:
            total += (ru - rl) / 100.0 / 360.0
        d += dt.timedelta(days=1)
    return direction * notional * total


def pnl(inst: Instrument, fill: dict, value: float, date: str, rates_cache: dict) -> dict:
    d, n, v0, dur = fill["direction_sign"], fill["notional_usd"], fill["entry_value"], fill.get("duration")
    if inst.kind == "fx":
        price = d * n * (value - v0) / value
    else:
        price = -d * n * dur * (value - v0) / inst.scale
    c = carry(inst, d, n, fill["entry_date"], date, rates_cache)
    cost = fill["cost_usd"]
    return {"price": round(price, 2), "carry": round(c, 2), "cost": round(-cost, 2), "total": round(price + c - cost, 2)}


def hit(inst: Instrument, direction: int, value: float, stop: float | None, target: float | None) -> str | None:
    g = direction * inst.favourable
    if stop is not None and g * (value - stop) <= 0:
        return "stop"
    if target is not None and g * (value - target) >= 0:
        return "target"
    return None


def validate_levels(inst: Instrument, direction: int, ref: float, stop: float, target: float | None) -> list[str]:
    g = direction * inst.favourable
    errs = []
    if g * (ref - stop) <= 0:
        errs.append(f"stop {stop} is not on the losing side of the latest close {ref} for a "
                    f"{'long' if direction > 0 else 'short'} {inst.code}")
    if target is not None and g * (target - ref) <= 0:
        errs.append(f"target {target} is not on the winning side of the latest close {ref}")
    return errs


# --------------------------------------------------------------------------
# Records
# --------------------------------------------------------------------------


def load_records() -> dict[str, dict]:
    trades: dict[str, dict] = {}
    if not TRADES_DIR.exists():
        return trades
    for p in sorted(TRADES_DIR.glob("T*.json")):
        rec = json.loads(p.read_text())
        tid, kind = p.stem.split("-", 1)
        trades.setdefault(tid, {})[{"open": "open", "fill": "fill", "closereq": "close_request", "exit": "exit"}[kind]] = rec
    return trades


def _equity_hint() -> float:
    if STATE_PATH.exists():
        try:
            return float(json.loads(STATE_PATH.read_text())["equity"]["current"])
        except Exception:  # noqa: BLE001
            pass
    return float(load_config()["starting_capital_usd"])


def make_fill(cfg: dict, op: dict, inst: Instrument, close: tuple[str, float], equity: float) -> dict:
    date, v0 = close
    sign = 1 if op["direction"] == "long" else -1
    dur = inst.duration(date, v0)
    unit = inst.unit_loss_to(v0, op["stop"], dur)
    warnings = []
    if op["size_type"] == "risk":
        if unit <= 0:
            raise ValueError("stop equals the entry close; cannot size by risk")
        notional = op["size"] / unit
    else:
        notional = op["size"]
    cost = inst.cost(notional, dur)
    risk = notional * unit + cost
    pct = 100 * risk / equity if equity else None
    if pct is not None and pct > cfg["risk_warning_pct_of_equity"]:
        warnings.append(f"risk to stop ${risk:,.0f} is {pct:.1f}% of equity (above {cfg['risk_warning_pct_of_equity']}%)")
    if inst.cfg.get("low_frequency"):
        warnings.append("low-frequency instrument: marks, stops and exits can lag by weeks")
    if inst.series and inst.series.get("proxy"):
        warnings.append("marked on a proxy series: " + inst.series["name"])
    if inst.series and inst.series.get("frequency") == "monthly" and not inst.cfg.get("low_frequency"):
        warnings.append(f"marked on monthly data ({inst.series['name']}) because the daily source is unavailable; "
                        "stops and targets are checked once a month for this trade")
    return {"type": "fill", "trade_id": op["trade_id"], "instrument": op["instrument"], "direction_sign": sign,
            "entry_date": date, "entry_value": v0, "entry_close_utc": inst.close_dt(date).isoformat(),
            "series_used": inst.series_id, "duration": dur, "notional_usd": round(notional, 2),
            "cost_usd": round(cost, 2), "risk_to_stop_usd": round(risk, 2), "risk_pct_of_equity": round(pct, 2) if pct else None,
            "equity_reference_usd": round(equity, 2), "warnings": warnings,
            "bond_at_entry": (inst.extra.get(date) or [None, None])[1] if inst.code == "BR10Y" else None,
            "written_at": store.now_iso()}


def process(cfg: dict, trades: dict, today: str, rates_cache: dict) -> list[str]:
    """Write any fills and exits that are now due. Returns the files written."""
    written = []
    equity = _equity_hint()
    for tid, t in sorted(trades.items()):
        op = t.get("open")
        if not op or op.get("rejected"):
            continue
        icfg = cfg["instruments"][op["instrument"]]
        if "fill" not in t:
            inst = Instrument(op["instrument"], icfg)
            c = inst.first_close_after(parse_ts(op["submitted_at"]))
            if not c or c[0] > today:
                continue
            fill = make_fill(cfg, op, inst, c, equity)
            write_once(TRADES_DIR / f"{tid}-fill.json", fill)
            t["fill"] = fill
            written.append(f"{tid}-fill.json")
            h = hit(inst, fill["direction_sign"], c[1], op["stop"], op.get("target"))
            if h:
                ex = {"type": "exit", "trade_id": tid, "reason": f"{h} already reached at the entry close", "exit_date": c[0],
                      "exit_value": c[1], "pnl": pnl(inst, fill, c[1], c[0], rates_cache), "written_at": store.now_iso()}
                write_once(TRADES_DIR / f"{tid}-exit.json", ex)
                t["exit"] = ex
                written.append(f"{tid}-exit.json")
                continue
        if "exit" in t:
            continue
        fill = t["fill"]
        inst = Instrument(op["instrument"], icfg, fill["series_used"])
        req = t.get("close_request")
        req_ts = parse_ts(req["submitted_at"]) if req else None
        for d, v in inst.closes_after(fill["entry_date"]):
            if d > today:
                break
            reason = hit(inst, fill["direction_sign"], v, op["stop"], op.get("target"))
            if not reason and req_ts and inst.close_dt(d) > req_ts:
                reason = "closed on request"
            if reason:
                ex = {"type": "exit", "trade_id": tid, "reason": reason, "exit_date": d, "exit_value": v,
                      "pnl": pnl(inst, fill, v, d, rates_cache), "written_at": store.now_iso()}
                write_once(TRADES_DIR / f"{tid}-exit.json", ex)
                t["exit"] = ex
                written.append(f"{tid}-exit.json")
                break
    return written


# --------------------------------------------------------------------------
# State: marks, equity, statistics, benchmarks, systematic
# --------------------------------------------------------------------------


def weekdays(start: str, end: str):
    d, e = dt.date.fromisoformat(start), dt.date.fromisoformat(end)
    while d <= e:
        if d.weekday() < 5:
            yield d.isoformat()
        d += dt.timedelta(days=1)


def trade_view(cfg: dict, tid: str, t: dict, today: str, rates_cache: dict) -> dict:
    op = t["open"]
    v = {"trade_id": tid, "open": op, "fill": t.get("fill"), "close_request": t.get("close_request"), "exit": t.get("exit"),
         "flags": []}
    if op.get("rejected"):
        v["status"] = "rejected"
        return v
    if not t.get("fill"):
        v["status"] = "pending"
        return v
    inst = Instrument(op["instrument"], cfg["instruments"][op["instrument"]], t["fill"]["series_used"])
    if t.get("exit"):
        v["status"] = "closed"
        v["pnl"] = t["exit"]["pnl"]
        return v
    v["status"] = "open"
    last = inst.value_on(today)
    mark = pnl(inst, t["fill"], last[1], today, rates_cache)
    at_stop = pnl(inst, t["fill"], op["stop"], today, rates_cache)
    v.update({"mark": {"date": last[0], "value": last[1], "series": inst.series_id}, "pnl": mark,
              "risk_to_stop_now": round(max(0.0, mark["total"] - at_stop["total"]), 2)})
    if op.get("horizon") and today > op["horizon"]:
        v["flags"].append(f"horizon {op['horizon']} has passed")
    if req := t.get("close_request"):
        v["flags"].append(f"close requested {req['submitted_at'][:16].replace('T', ' ')}; exits at the next close")
    if inst.code == "BR10Y" and t["fill"].get("bond_at_entry"):
        now_bond = (inst.extra.get(last[0]) or [None, None])[1]
        if now_bond and now_bond != t["fill"]["bond_at_entry"]:
            v["flags"].append(f"proxy switched bond: entry {t['fill']['bond_at_entry']}, now {now_bond}")
    if (dt.date.fromisoformat(today) - dt.date.fromisoformat(last[0])).days > 7:
        v["flags"].append(f"last mark {last[0]} is more than a week old")
    return v


def equity_curve(cfg: dict, trades: dict, today: str, rates_cache: dict) -> list[list]:
    cap = float(cfg["starting_capital_usd"])
    insts = {}
    out = []
    for day in weekdays(str(cfg["start_date"]), today):
        eq = cap
        for tid, t in trades.items():
            f = t.get("fill")
            if not f or f["entry_date"] > day:
                continue
            ex = t.get("exit")
            if ex and ex["exit_date"] <= day:
                eq += ex["pnl"]["total"]
                continue
            key = (t["open"]["instrument"], f["series_used"])
            inst = insts.setdefault(key, Instrument(key[0], cfg["instruments"][key[0]], key[1]))
            last = inst.value_on(day)
            if last:
                eq += pnl(inst, f, last[1], day, rates_cache)["total"]
        out.append([day, round(eq, 2)])
    return out


def drawdown(curve: list[list]) -> dict:
    peak, peak_d, worst = None, None, {"pct": 0.0, "from": None, "to": None}
    for d, v in curve:
        if peak is None or v > peak:
            peak, peak_d = v, d
        dd = 100 * (v / peak - 1) if peak else 0.0
        if dd < worst["pct"]:
            worst = {"pct": round(dd, 2), "from": peak_d, "to": d}
    return worst


def buy_and_hold(cfg: dict, today: str, rates_cache: dict) -> list[dict]:
    out = []
    one_year = (dt.date.fromisoformat(today) - dt.timedelta(days=365)).isoformat()
    for code, icfg in cfg["instruments"].items():
        inst = Instrument(code, icfg)
        row = {"code": code, "name": icfg["name"], "series": inst.series_id, "proxy": bool(inst.series and inst.series.get("proxy")),
               "description": "long USD" if inst.kind == "fx" else ("long OAT vs Bund" if inst.kind == "spread_bp" else "long the bond")}
        last = inst.latest()
        for label, start in (("since_start", str(cfg["start_date"])), ("last_12m", one_year)):
            c = next(((d, v) for d, v in inst.obs if d >= start), None)
            if not c or not last or last[0] <= c[0]:
                row[label] = None
                continue
            fill = {"direction_sign": 1, "notional_usd": 100000.0, "entry_value": c[1], "entry_date": c[0],
                    "duration": inst.duration(c[0], c[1]), "cost_usd": 0.0}
            row[label] = {"from": c[0], "to": last[0], "pnl_usd": pnl(inst, fill, last[1], last[0], rates_cache)["total"]}
            row[label]["return_pct"] = round(row[label]["pnl_usd"] / 1000.0, 2)
        out.append(row)
    return out


def _em_macro_text(path: str) -> str | None:
    local = os.environ.get("EM_MACRO_DIR")
    if local and (Path(local) / path).exists():
        return (Path(local) / path).read_text()
    try:
        return get(EM_MACRO_RAW + path, timeout=60).text
    except Exception as exc:  # noqa: BLE001
        log.warning("em-macro %s: %s", path, exc)
        return None


RELEVANT_SYSTEMATIC = {"BRL", "MXN", "BR10Y", "MX10Y", "FR-DE", "US10Y", "DE10Y"}


def systematic(cfg: dict) -> dict:
    pos_t, pnl_t = _em_macro_text("results/systematic/positions.csv"), _em_macro_text("results/systematic/paper_pnl.csv")
    if not pos_t or not pnl_t:
        return {"available": False, "message": "em-macro results/systematic not reachable"}
    pos = list(csv.DictReader(io.StringIO(pos_t)))
    rows = list(csv.DictReader(io.StringIO(pnl_t)))
    start_m = str(cfg["start_date"])[:7]
    cap = float(cfg["starting_capital_usd"])
    since, eq = [], cap
    for r in rows:
        if r["month"] >= start_m:
            eq *= 1 + float(r["net"])
            since.append([r["month"], round(eq, 2)])
    full = [[r["month"], float(r["cumulative_net"]), r["sample"]] for r in rows]
    return {"available": True, "source": EM_MACRO_RAW + "results/systematic/",
            "as_of": pos[0]["as_of"] if pos else None, "effective_from": pos[0]["effective_from"] if pos else None,
            "positions": [{**p, "relevant": p["instrument"] in RELEVANT_SYSTEMATIC} for p in pos],
            "since_start": since, "full_history": full, "latest_sample": rows[-1]["sample"] if rows else None,
            "note": "Monthly paper P&L of em-macro's frozen systematic strategy (carry, trend, value across 10 currencies and "
                    "13 bond positions), scaled to the book's starting capital from the book's first month. Its positions "
                    "cover more countries than this book."}


def build(today: str | None = None) -> dict:
    cfg = load_config()
    today = today or store.today()
    rates_cache: dict = {}
    trades = load_records()
    written = process(cfg, trades, today, rates_cache)
    views = [trade_view(cfg, tid, t, today, rates_cache) for tid, t in sorted(trades.items())]
    curve = equity_curve(cfg, trades, today, rates_cache)
    cap = float(cfg["starting_capital_usd"])
    current = curve[-1][1] if curve else cap
    closed = [v for v in views if v["status"] == "closed"]
    wins = [v["pnl"]["total"] for v in closed if v["pnl"]["total"] > 0]
    losses = [v["pnl"]["total"] for v in closed if v["pnl"]["total"] <= 0]
    open_ = [v for v in views if v["status"] == "open"]
    risk = sum(v.get("risk_to_stop_now", 0) for v in open_)
    latest = {}
    deg_rules = degraded.active()
    for code, icfg in cfg["instruments"].items():
        inst = Instrument(code, icfg)
        last = inst.latest()
        latest[code] = {"name": icfg["name"], "kind": icfg["kind"], "country": icfg.get("country"), "series": inst.series_id,
                        "proxy": bool(inst.series and inst.series.get("proxy")), "value": last[1] if last else None,
                        "date": last[0] if last else None, "close_utc": icfg.get("close_utc"),
                        "low_frequency": bool(icfg.get("low_frequency")), "note": icfg.get("note"),
                        "degraded": degraded.for_series(inst.series_id, deg_rules),
                        # what the site's trade-sizing calculator needs to reproduce pnl() and cost()
                        "scale": inst.scale, "favourable": inst.favourable, "rate_usd": icfg.get("rate_usd"), "rate_local": icfg.get("rate_local"),
                        "maturity": icfg.get("maturity"), "unit": (inst.series or {}).get("unit"),
                        "duration": icfg.get("duration"), "cost": icfg.get("cost_round_trip_pct", icfg.get("cost_round_trip_bp")),
                        "cost_unit": "% of notional" if icfg["kind"] == "fx" else "bp of yield"}
    state = {
        "generated_at": store.now_iso(), "as_of": today, "repo": cfg.get("repo"),
        "starting_capital_usd": cap, "start_date": str(cfg["start_date"]), "assumptions": cfg.get("assumptions", []),
        "risk_warning_pct_of_equity": cfg["risk_warning_pct_of_equity"], "instruments": latest,
        "equity": {"current": current, "pnl_usd": round(current - cap, 2), "return_pct": round(100 * (current / cap - 1), 3),
                   "curve": curve, "worst_drawdown": drawdown(curve)},
        "risk_at_stake_usd": round(risk, 2), "risk_at_stake_pct": round(100 * risk / current, 2) if current else None,
        "stats": {"n_closed": len(closed), "n_open": len(open_), "n_pending": sum(v["status"] == "pending" for v in views),
                  "hit_rate_pct": round(100 * len(wins) / len(closed), 1) if closed else None,
                  "avg_win_usd": round(sum(wins) / len(wins), 2) if wins else None,
                  "avg_loss_usd": round(sum(losses) / len(losses), 2) if losses else None,
                  "realised_pnl_usd": round(sum(v["pnl"]["total"] for v in closed), 2)},
        "trades": views, "written_this_run": written,
        "benchmarks": buy_and_hold(cfg, today, rates_cache), "systematic": systematic(cfg),
    }
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=1) + "\n")
    return state
