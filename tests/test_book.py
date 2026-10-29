import datetime as dt
import json

import pytest

from terminal import book, forms, judgement, store


@pytest.fixture()
def env(tmp_path, monkeypatch):
    """Temporary store with synthetic series and a small book config."""
    for mod, attr, sub in ((store, "DATA", "terminal"), (store, "SERIES_DIR", "terminal/series"),
                           (book, "TRADES_DIR", "trades"), (book, "BOOK_DIR", "book"), (book, "STATE_PATH", "book/state.json"),
                           (forms, "TRADES_DIR", "trades"), (judgement, "JUDGE_DIR", "judgements"), (forms, "JUDGE_DIR", "judgements"),
                           (judgement, "STATE_PATH", "book/judgements.json"), (judgement, "JOURNAL_PATH", "book/journal.json")):
        monkeypatch.setattr(mod, attr, tmp_path / sub)
    cfg = {"repo": "x/y", "starting_capital_usd": 100000, "start_date": "2026-10-01", "risk_warning_pct_of_equity": 2.0,
           "instruments": {
               "USDBRL": {"name": "USD/BRL", "kind": "fx", "series": ["t.fx"], "close_utc": "16:30", "rate_usd": "t.rusd",
                          "rate_local": "t.rloc", "cost_round_trip_pct": 0.1},
               "US10Y": {"name": "US 10y", "kind": "yield", "series": ["t.y"], "close_utc": "21:00", "duration": 8, "cost_round_trip_bp": 1},
               "OATBUND": {"name": "spread", "kind": "spread_bp", "series": ["t.s"], "close_utc": "17:30", "duration": 8, "cost_round_trip_bp": 2}}}
    monkeypatch.setattr(book, "load_config", lambda: cfg)
    monkeypatch.setattr(forms, "load_config", lambda: cfg)
    days = [(dt.date(2026, 10, 1) + dt.timedelta(days=i)).isoformat() for i in range(10)]
    fx = [5.00, 5.00, 5.10, 5.20, 4.90, 4.80, 5.30, 5.30, 5.30, 5.30]
    y = [4.00, 4.00, 3.90, 3.80, 4.20, 4.30, 4.30, 4.30, 4.30, 4.30]
    sp = [80, 80, 75, 70, 90, 95, 95, 95, 95, 95]
    before = ["2026-09-28", "2026-09-29", "2026-09-30"]          # history before the first submission
    for sid, vals in (("t.fx", fx), ("t.y", y), ("t.s", sp)):
        store.save_series({"id": sid, "name": sid}, [[d, vals[0]] for d in before] + [[d, v] for d, v in zip(days, vals)])
    store.save_series({"id": "t.rusd", "name": "usd"}, [["2026-09-01", 4.0]])
    store.save_series({"id": "t.rloc", "name": "loc"}, [["2026-09-01", 14.0]])
    return cfg, days


def issue(n, title, body, created="2026-10-01T10:00:00Z", login="me", assoc="OWNER"):
    return {"repository": {"owner": {"login": "me"}},
            "issue": {"number": n, "title": title, "body": body, "created_at": created, "html_url": f"https://x/{n}",
                      "user": {"login": login}, "author_association": assoc, "labels": []}}


def body(pairs):
    return "\n\n".join(f"### {k}\n\n{v}" for k, v in pairs)


OPEN = lambda instr, dirn, size_type, size, stop, target, horizon="2026-12-31": body([
    ("Instrument", instr), ("Direction", dirn), ("Size is", size_type), ("Size (USD)", size), ("Stop level", stop),
    ("Target level", target), ("Horizon date", horizon), ("Linked catalyst or question ID", "_No response_"),
    ("Thesis (one line)", "a thesis"), ("What would make me close early", "news")])


def test_parse_body_maps_labels_to_ids():
    f = forms.parse_body(OPEN("USDBRL", "long", "Notional (USD)", "10,000", "4.5", "_No response_"), "open-trade")
    assert f["instrument"] == "USDBRL" and f["size"] == "10,000" and f["target"] is None and f["link"] is None


def test_open_trade_fill_at_next_close_and_stop_exit(env):
    cfg, days = env
    # submitted 10:00 UTC on day 0: the 16:30 close of day 0 is the first close after submission
    r = forms.handle(issue(1, "[Open trade] x", OPEN("USDBRL", "long", "Notional (USD)", "100000", "4.85", "5.50")))
    assert r["accepted"] and json.loads((book.TRADES_DIR / "T00001-open.json").read_text())["instrument"] == "USDBRL"
    # submitted 17:00 on day 0 (after the close): fills on day 1
    forms.handle(issue(2, "[Open trade] y", OPEN("USDBRL", "short", "Notional (USD)", "100000", "5.25", "_No response_"),
                       created="2026-10-01T17:00:00Z"))
    st = book.build(today=days[-1])
    t1 = next(t for t in st["trades"] if t["trade_id"] == "T00001")
    t2 = next(t for t in st["trades"] if t["trade_id"] == "T00002")
    assert t1["fill"]["entry_date"] == days[0] and t2["fill"]["entry_date"] == days[1]
    # T1 long from 5.00, stop 4.85: day 5 closes at 4.80 -> stopped there
    assert t1["status"] == "closed" and t1["exit"]["exit_date"] == days[5] and t1["exit"]["reason"] == "stop"
    price = 100000 * (4.80 - 5.00) / 4.80
    carry = 100000 * (4.0 - 14.0) / 100 / 360 * 5          # long USD pays the local rate for 5 nights
    assert t1["exit"]["pnl"]["price"] == pytest.approx(price, abs=0.01)
    assert t1["exit"]["pnl"]["carry"] == pytest.approx(carry, abs=0.01)
    assert t1["exit"]["pnl"]["cost"] == pytest.approx(-100.0)
    # T2 short from 5.00, stop 5.25: day 6 closes at 5.30 -> stopped
    assert t2["exit"]["exit_date"] == days[6] and t2["exit"]["pnl"]["carry"] > 0
    assert st["stats"]["n_closed"] == 2 and st["stats"]["hit_rate_pct"] is not None
    assert st["equity"]["worst_drawdown"]["pct"] < 0


def test_risk_sizing_bond_sign_and_manual_close(env):
    cfg, days = env
    # long US10Y (gains when the yield falls), size by $1,000 risk to a stop 25bp away: notional = 1000 / (8 * 0.0025)
    forms.handle(issue(3, "[Open trade] z", OPEN("US10Y", "long", "Risk amount to stop (USD)", "1000", "4.25", "3.70")))
    st = book.build(today=days[3])
    t = st["trades"][0]
    assert t["fill"]["notional_usd"] == pytest.approx(1000 / (8 * 0.25 / 100))
    assert t["status"] == "open" and t["pnl"]["price"] > 0           # yield 4.00 -> 3.80
    r = forms.handle(issue(4, "[Close trade] z", body([("Trade ID", "T3"), ("Post-mortem (two lines)", "line one\nline two")]),
                           created=f"{days[3]}T22:00:00Z"))
    assert r["accepted"]
    st = book.build(today=days[-1])
    t = st["trades"][0]
    assert t["exit"]["exit_date"] == days[4] and t["exit"]["reason"] == "closed on request"
    assert t["exit"]["pnl"]["price"] < 0                              # 4.00 -> 4.20 on a long bond


def test_validation_rejections_and_warning(env):
    r = forms.handle(issue(5, "[Open trade] w", OPEN("USDBRL", "long", "Notional (USD)", "100000", "5.40", "_No response_")))
    assert not r["accepted"] and "losing side" in r["comment"]
    assert json.loads((book.TRADES_DIR / "T00005-open.json").read_text())["rejected"]
    r = forms.handle(issue(6, "[Open trade] v", OPEN("OATBUND", "long", "Notional (USD)", "1000000", "100", "60")))
    assert r["accepted"] and "above the 2.0% guideline" in r["comment"]   # 1m x 8 x 20bp = $16k > 2%
    r = forms.handle(issue(7, "[Close trade] u", body([("Trade ID", "T00006"), ("Post-mortem (two lines)", "only one line")])))
    assert not r["accepted"] and "exactly two lines" in r["comment"]
    r = forms.handle(issue(8, "[Open trade] t", OPEN("USDBRL", "long", "Notional (USD)", "1", "4.8", "_No response_"), login="stranger", assoc="NONE"))
    assert not r["accepted"] and "only processed for the repository owner" in r["comment"]


def test_write_once(env):
    forms.handle(issue(9, "[Open trade] s", OPEN("USDBRL", "long", "Notional (USD)", "1000", "4.8", "_No response_")))
    with pytest.raises(book.WriteOnceError):
        forms.handle(issue(9, "[Open trade] s", OPEN("USDBRL", "long", "Notional (USD)", "1000", "4.8", "_No response_")))


CALL = lambda scen, p="60%": body([
    ("Question", "Will Copom cut in December?"), ("Question ID (optional)", "_No response_"), ("Resolution date", "2026-12-09"),
    ("Base rate", "17 of 24"), ("Factor 1", "inflation easing"), ("Factor 1: direction", "Raises the probability"),
    ("Factor 1: size", "Medium"), ("Factor 2", "_No response_"), ("Factor 2: direction", "_No response_"), ("Factor 2: size", "_No response_"),
    ("Factor 3", "_No response_"), ("Factor 3: direction", "_No response_"), ("Factor 3: size", "_No response_"),
    ("Scenarios and probabilities (must total 100)", scen), ("My probability that the question resolves YES", p),
    ("Linked trade (optional)", "_No response_"), ("What would change my mind, with dates", "IPCA on 2026-11-10 above 0.5%"),
    ("Pre-mortem (one line): if this call is wrong, why?", "BCB stays hawkish"), ("Confidence in my information", "Medium")])


def test_full_call_update_resolve_and_scores(env):
    r = forms.handle(issue(10, "[Full call] c", CALL("Cut: 60\nHold: 30")))
    assert not r["accepted"] and "total 90" in r["comment"]
    r = forms.handle(issue(11, "[Full call] c", CALL("Cut 25bp: 55\nCut 50bp: 5\nHold: 40")))
    assert r["accepted"] and "Market-implied at submission: none" in r["comment"]
    r = forms.handle(issue(12, "[Quick update] u", body([("Call or question ID", "J11"), ("New probability", "70%"),
                                                         ("Direction of the change", "Down"), ("What changed", "IPCA soft")])))
    assert r["accepted"] and "moved up" in r["comment"]
    r = forms.handle(issue(13, "[Resolve] r", body([("Call or question ID", "J00011"), ("Outcome", "Yes"), ("Source (link)", "https://bcb.gov.br")])))
    assert r["accepted"]
    js = judgement.build(resolve_online=False)
    q = js["questions"][0]
    assert q["resolution"]["outcome"] == 1 and q["final"]["prob"] == 0.7
    assert q["final"]["brier"] == pytest.approx(0.09) and q["final"]["log"] == pytest.approx(-0.3567, abs=1e-4)
    assert js["summary"]["n_resolved"] == 1 and "calibration" not in js["summary"]      # needs 30
    kinds = [i["kind"] for i in json.loads(judgement.JOURNAL_PATH.read_text())["items"]]
    assert kinds.count("call") == 2 and "update" in kinds and "resolve" in kinds


def test_scores():
    assert judgement.brier(0.7, 1) == pytest.approx(0.09)
    assert judgement.log_score(0.0, 1) == pytest.approx(-4.6052, abs=1e-4)     # clipped at 1%
    assert judgement.log_score(1.0, 1) == pytest.approx(-0.01005, abs=1e-4)
