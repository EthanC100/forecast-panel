"""Final Horizons backend: the Supabase paper book (fills, rejections, marks, stops, close requests,
decision scoring), reminders read from Supabase, the Algorithm tab's data and the Yahoo gold parser."""

import datetime as dt
import json

import pytest

from terminal import algorithm, book, hzbook, reminders, store
from terminal.sources import gold_
from terminal.supa import Client


class Fake:
    """An in-memory stand-in for the PostgREST client: eq./is.null filters, patch by id."""

    def __init__(self, **tables):
        self.t = {k: [dict(r) for r in v] for k, v in tables.items()}
        self.patches = []

    def configured(self):
        return True

    def select(self, table, **f):
        f.pop("order", None)
        f.pop("select", None)
        rows = self.t.get(table, [])
        for k, v in f.items():
            if v == "is.null":
                rows = [r for r in rows if r.get(k) is None]
            elif v.startswith("eq."):
                rows = [r for r in rows if str(r.get(k)) == v[3:]]
        return [dict(r) for r in rows]

    def patch(self, table, match, values):
        self.patches.append((table, match, values))
        for r in self.t[table]:
            if all(r.get(k) == v for k, v in match.items()):
                r.update(values)
        return []


@pytest.fixture()
def env(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "DATA", tmp_path / "terminal")
    monkeypatch.setattr(store, "SERIES_DIR", tmp_path / "terminal" / "series")
    cfg = {"starting_capital_usd": 100000, "start_date": "2026-10-01",
           "instruments": {"USDBRL": {"name": "USD/BRL", "kind": "fx", "series": ["t.fx"], "close_utc": "16:30", "rate_usd": "t.rusd",
                                      "rate_local": "t.rloc", "cost_round_trip_pct": 0.1},
                           "US10Y": {"name": "US 10y", "kind": "yield", "series": ["t.y"], "close_utc": "21:00", "duration": 8, "cost_round_trip_bp": 1}}}
    monkeypatch.setattr(book, "load_config", lambda: cfg)
    days = [(dt.date(2026, 10, 1) + dt.timedelta(days=i)).isoformat() for i in range(10)]
    fx = [5.00, 5.00, 5.10, 5.20, 4.90, 4.80, 5.30, 5.30, 5.30, 5.30]
    hist = [[(dt.date(2025, 10, 1) + dt.timedelta(days=i)).isoformat(), 5.0 + 0.01 * ((i % 7) - 3)] for i in range(360)]
    store.save_series({"id": "t.fx", "name": "fx"}, hist + [[d, v] for d, v in zip(days, fx)])
    store.save_series({"id": "t.y", "name": "y"}, [[d, 4.0] for d in days])
    store.save_series({"id": "t.rusd", "name": "usd"}, [["2026-09-01", 4.0]])
    store.save_series({"id": "t.rloc", "name": "loc"}, [["2026-09-01", 14.0]])
    return cfg


def trade(i, direction, stop, requested="2026-10-01T10:00:00Z", instrument="USDBRL", **kw):
    return {"id": f"t{i}", "instrument": instrument, "direction": direction, "risk_pct": 1, "stop_level": stop, "target_level": None,
            "requested_at": requested, "status": "pending", "pnl_total": None, "series_used": None, **kw}


def test_fill_mark_stop_close_reject_and_score(env):
    c = Fake(trades=[trade(1, "long", 4.85), trade(2, "short", 5.40), trade(3, "long", 5.20), trade(4, "long", 1, instrument="XYZ"),
                     trade(5, "long", 4.5, requested="2026-10-10T20:00:00Z")],
             trade_closes=[{"id": "c1", "trade_id": "t2", "requested_at": "2026-10-03T12:00:00Z", "processed_at": None}],
             decisions=[{"id": "d1", "action": "Buy", "instrument": "USDBRL", "probability": 0.7, "decision_date": "2026-10-01", "horizon": "2026-10-07"},
                        {"id": "d2", "action": "Sell", "instrument": "USDBRL", "probability": 0.6, "decision_date": "2026-10-01", "horizon": "2026-10-07"},
                        {"id": "d3", "action": "Hold", "instrument": "USDBRL", "probability": 0.6, "decision_date": "2026-10-01", "horizon": "2026-10-07"},
                        {"id": "d4", "action": "Buy", "instrument": "USDBRL", "probability": 0.6, "decision_date": "2026-10-01", "horizon": "2026-12-31"}])
    r = hzbook.run(c, today="2026-10-10")
    T = {t["id"]: t for t in c.t["trades"]}
    # t1: filled at the first close after 10:00 UTC on 1 Oct (16:30), sized so the stop loses 1% of $100,000
    t1 = T["t1"]
    assert t1["entry_date"] == "2026-10-01" and t1["entry_value"] == 5.0 and t1["risk_usd"] == 1000.0
    assert t1["notional_usd"] == pytest.approx(1000 / (0.15 / 4.85), rel=1e-6)
    # ... marked daily and stopped at 4.80 on 6 Oct
    assert t1["status"] == "closed" and t1["exit_reason"] == "stop" and t1["exit_date"] == "2026-10-06" and t1["exit_value"] == 4.8
    assert [m[0] for m in t1["marks"]][:2] == ["2026-10-01", "2026-10-02"] and t1["marks"][-1][0] == "2026-10-06"
    assert t1["pnl_total"] == pytest.approx(t1["pnl_price"] + t1["pnl_carry"] + t1["pnl_cost"], abs=0.02) and t1["pnl_price"] < 0
    assert t1["marks"][0][4] == t1["pnl_cost"] < 0            # the round-trip cost is charged at entry
    # t2: closed on request at the first close after the request (3 Oct 16:30 > 12:00)
    assert T["t2"]["status"] == "closed" and T["t2"]["exit_reason"] == "closed" and T["t2"]["exit_date"] == "2026-10-03"
    assert c.t["trade_closes"][0]["processed_at"]
    # t3: stop above a long's fill; t4: unknown instrument; t5: no close yet after its request
    assert T["t3"]["status"] == "rejected" and "wrong side" in T["t3"]["reject_reason"]
    assert T["t4"]["status"] == "rejected" and T["t4"]["reject_reason"] == "unknown instrument"
    assert T["t5"]["status"] == "pending"
    assert set(r["filled"]) == {"t1", "t2"} and set(r["closed"]) == {"t1", "t2"}
    # decisions: Buy right (5.00 -> 5.30), Sell wrong; Hold and an unexpired horizon unscored
    D = {d["id"]: d for d in c.t["decisions"]}
    assert D["d1"]["outcome"] == 1 and D["d1"]["brier"] == pytest.approx(0.09)
    assert D["d2"]["outcome"] == 0 and D["d2"]["brier"] == pytest.approx(0.36)
    assert "outcome" not in D["d3"] and "outcome" not in D["d4"]
    # a second run touches nothing closed and keeps the pending trade pending
    n = len(c.patches)
    hzbook.run(c, today="2026-10-10")
    assert all(p[1].get("id") not in ("t1", "t2", "t3", "t4") for p in c.patches[n:])


def test_open_trade_marks_to_latest_close_and_sizes_on_equity(env):
    c = Fake(trades=[trade(1, "short", 5.60), {**trade(9, "long", 1.0), "status": "closed", "pnl_total": 5000.0}], trade_closes=[], decisions=[])
    hzbook.run(c, today="2026-10-10")
    t = c.t["trades"][0]
    assert t["status"] == "open" and t["risk_usd"] == 1050.0     # 1% of $105,000 (start + realised)
    assert t["last_date"] == "2026-10-10" and t["marks"][-1][1] == 5.3 and len(t["marks"]) == 10
    assert t["pnl_price"] < 0 and t["pnl_carry"] > 0             # short USD/BRL earns the real's carry


def test_not_configured_is_a_warning():
    assert hzbook.run(Client(url="", key=""))["configured"] is False


def test_secret_key_header_only():
    h = Client(url="https://x.supabase.co", key="sb_secret_abc").headers()
    assert h["apikey"] == "sb_secret_abc" and "Authorization" not in h
    assert Client(url="https://x.supabase.co", key="eyJabc").headers()["Authorization"] == "Bearer eyJabc"


def test_reminders_from_supabase(env):
    (store.DATA).mkdir(parents=True, exist_ok=True)
    (store.DATA / "calendar.json").write_text(json.dumps({"events": [
        {"id": "e1", "date": "2026-11-04", "country": "BR", "title": "Copom decision", "importance": 3},
        {"id": "e2", "date": "2026-11-05", "country": "MX", "title": "Banxico decision", "importance": 3},
        {"id": "e3", "date": "2026-11-04", "country": "FR", "title": "Minor", "importance": 2}]}))
    c = Fake(trades=[{"id": "t1", "instrument": "USDBRL", "direction": "long", "status": "open", "horizon": "2026-10-20",
                      "entry_date": "2026-10-01", "entry_value": 5.0, "series_used": "t.fx"}],
             decisions=[{"id": "d1", "country": "BR", "decision_date": "2026-10-20", "change_mind": "the 2026-11-03 IPCA print"},
                        {"id": "d2", "country": "FR", "decision_date": "2026-10-01", "change_mind": None}])
    keys = {r["key"] for r in reminders.active("2026-11-02", c)}
    assert "horizon:t1" in keys and "signpost:d1:2026-11-03" in keys and "stale:FR:d2" in keys
    assert "catalyst:e2" in keys and "catalyst:e1" not in keys            # Brazil has a decision in the last 14 days
    assert not any(k.startswith("stale:BR") for k in keys)
    texts = json.dumps(reminders.active("2026-11-02", c))
    assert "$" not in texts and "notional" not in texts                 # no P&L or sizes in issue text
    assert reminders.active("2026-11-02", Client(url="", key="")) is None


def test_algorithm_mapping(env):
    env["instruments"].update({"USDMXN": {"name": "USD/MXN", "kind": "fx", "series": ["t.fx"], "close_utc": "18:30", "rate_usd": "t.rusd", "rate_local": "t.rloc"},
                               "MX10Y": {"name": "MX 10y", "kind": "yield", "series": ["t.y"], "duration": 5.5}})
    pos = ("as_of,effective_from,book,instrument,description,side,size_pct_of_capital,risk_share_pct,instrument_vol_pct,carry_z,trend_z,value_z,cost_pct_per_trade\n"
           "2026-09,2026-10,fx,BRL,BRL vs USD (Brazil),long,22.58,7.7,10.3,0.411,0.775,0.148,0.1\n"
           "2026-09,2026-10,bond,MX10Y,Mexico 10y local-currency bond (excess over local policy rate),long,32.77,6.2,5.68,1.383,-0.396,-0.179,0.1\n"
           "2026-09,2026-10,fx,TRY,TRY vs USD (Turkey),long,46.17,6.3,4.13,2.658,1.133,-1.183,0.3\n")
    pnl = ("month,fx_gross,bond_gross,cost,net,gross_leverage,sample,cumulative_net,carry_basket,sp500_tr\n"
           "2026-08,0,0,0,0.01,6,test,1.01,0.02,0\n2026-09,0,0,0,-0.005,6,test,1.00495,-0.01,0\n")
    o = algorithm.build_from(pos, pnl, env)
    P = {p["instrument"]: p for p in o["positions"]}
    brl = P["BRL"]["copyable"]
    assert brl["instrument"] == "USDBRL" and brl["direction"] == "short" and brl["level"] == 5.3
    assert brl["suggested_stop"] == pytest.approx(5.3 * (1 + 2 * 10.3 / 12 ** 0.5 / 100), abs=1e-4)   # a short's stop is above
    mx = P["MX10Y"]["copyable"]
    assert mx["direction"] == "long" and mx["suggested_stop"] == pytest.approx(4.0 + 2 * 5.68 / 12 ** 0.5 / 5.5, abs=0.01)
    assert P["TRY"]["copyable"] is None and P["TRY"]["country"] == "Turkey" and P["MX10Y"]["country"] == "Mexico"
    assert o["pnl"][-1][:3] == ["2026-09", -0.005, -0.01] and o["pnl"][-1][4] == pytest.approx(1.02 * 0.99)
    assert o["this_month"]["n_copyable"] == 2 and o["this_month"]["last_12m"]["net"] == pytest.approx(1.01 * 0.995 - 1)


def test_yahoo_parser():
    obj = {"chart": {"result": [{"meta": {"gmtoffset": -14400}, "timestamp": [1761710400, 1761796800, 1761883200],
                                 "indicators": {"quote": [{"close": [4012.5, None, 4050.25]}]}}], "error": None}}
    rows = gold_.parse_yahoo(obj)
    assert rows == [["2025-10-29", 4012.5], ["2025-10-31", 4050.25]]
    with pytest.raises(RuntimeError):
        gold_.parse_yahoo({"chart": {"result": None, "error": {"code": "Not Found"}}})
