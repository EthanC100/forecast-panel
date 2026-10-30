"""Gold: source parsers (Stooq, LBMA, GPR, IMF, World Bank, FOMC), gold.json assembly, and the paper
book's metal instruments (kind "price")."""

import datetime as dt
import json

import pandas as pd
import pytest

from terminal import book, forms, gold, store
from terminal.sources import gold_


@pytest.fixture
def series_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "SERIES_DIR", tmp_path / "series")
    monkeypatch.setattr(store, "DATA", tmp_path)
    monkeypatch.setattr(gold, "OUT", tmp_path / "gold.json")
    return tmp_path


# ---------------- parsers ----------------

def test_parse_stooq_and_rejects_html():
    rows = gold_.parse_stooq("Date,Open,High,Low,Close\n2026-10-27,4100,4150,4090,4120.5\n2026-10-28,4120,4130,4080,4101\n")
    assert rows == [["2026-10-27", 4120.5], ["2026-10-28", 4101.0]]
    with pytest.raises(RuntimeError):
        gold_.parse_stooq("<!DOCTYPE html><html>bot check</html>")


def test_parse_lbma_usd_column():
    rows = gold_.parse_lbma([{"d": "2026-10-27", "v": [4105.3, 3100.1, 3500.2]}, {"d": "2026-10-28", "v": [0, 0, 0]}])
    assert rows == [["2026-10-27", 4105.3]]
    with pytest.raises(RuntimeError):
        gold_.parse_lbma([])


def test_parse_gpr_rows():
    rows = gold_.parse_gpr([{"DAY": 20261026, "GPRD": 165.25}, {"DAY": 20261027.0, "GPRD": float("nan")}, {"DAY": "x", "GPRD": 1}])
    assert rows == [["2026-10-26", 165.25]]


IMF_XML = """<data><Series COUNTRY="USA" FREQ="M"><Obs TIME_PERIOD="2026-M01" OBS_VALUE="261498926"/>
<Obs TIME_PERIOD="2026-M02" OBS_VALUE="261498926"/></Series>
<Series COUNTRY="POL" FREQ="M"><Obs TIME_PERIOD="2026-M01" OBS_VALUE="15000000"/><Obs TIME_PERIOD="2026-M02" OBS_VALUE="15321507.466"/></Series>
<Series COUNTRY="BAD" FREQ="M"><Obs TIME_PERIOD="2026-M01" OBS_VALUE="1"/><Obs TIME_PERIOD="2026-M02" OBS_VALUE="999999999999"/></Series>
<Series COUNTRY="G163" FREQ="M"><Obs TIME_PERIOD="2026-M01" OBS_VALUE="1"/><Obs TIME_PERIOD="2026-M02" OBS_VALUE="5"/></Series></data>"""


def test_parse_imf_gold_sums_changes_and_drops_breaks():
    rows, bad = gold_.parse_imf_gold(IMF_XML)
    assert bad == ["BAD"]
    assert rows == [["2026-02-28", pytest.approx(10.0, abs=0.01), 2]]       # Poland +321,507 oz = 10 t; US flat


def test_parse_pink_sheet():
    df = pd.DataFrame([["World Bank", None, None], [None, "Gold", "Silver"], [None, "($/troy oz)", "($/troy oz)"],
                       ["2026M08", 4411.0, 60.1], ["2026M09", 4319.0, 64.6], ["note", None, None]])
    out = gold_.parse_pink_sheet(df)
    assert out["Gold"] == [["2026-08-31", 4411.0], ["2026-09-30", 4319.0]] and out["Silver"][-1] == ["2026-09-30", 64.6]


FOMC_HTML = """<h4>2026 FOMC Meetings</h4>
<div class="fomc-meeting__month"><strong>October</strong></div><div class="fomc-meeting__date">27-28</div>
<div class="fomc-meeting__month"><strong>December</strong></div><div class="fomc-meeting__date">8-9*</div>
<h4>2027 FOMC Meetings</h4>
<div class="fomc-meeting__month"><strong>Jan/Feb</strong></div><div class="fomc-meeting__date">31-1</div>
<div class="fomc-meeting__month"><strong>March</strong></div><div class="fomc-meeting__date">16-17*</div>"""


def test_parse_fomc():
    rows = gold_.parse_fomc(FOMC_HTML)
    assert ["2026-12-09", "2026-12-08", 1, "December 8-9*"] in rows
    assert rows[0] == ["2026-10-28", "2026-10-27", 0, "October 27-28"]
    assert [r[0] for r in rows] == ["2026-10-28", "2026-12-09", "2027-03-17"]     # "Jan/Feb" is not a month name: skipped


def test_parse_fomc_two_month_meeting():
    html = FOMC_HTML.replace("Jan/Feb", "January/February")
    rows = gold_.parse_fomc(html)
    assert ["2027-02-01", "2027-01-31", 0, "January/February 31-1"] in rows


# ---------------- gold.json ----------------

def _daily(sid, start, values, unit="USD per troy ounce", freq="daily"):
    d0 = dt.date.fromisoformat(start)
    store.save_series({"id": sid, "name": sid, "unit": unit, "frequency": freq, "source": "test", "source_url": "https://x"},
                      [[(d0 + dt.timedelta(days=i)).isoformat(), v] for i, v in enumerate(values)])


FWD = ("log_date,model_version,data_as_of,pred_gold_5d,pred_silver_5d,realised_gold_5d,realised_silver_5d,gpr_level,note\n"
       "2026-10-21,v2-rolling,2026-10-20,0.01,-0.02,0.005,0.01,150,\n"
       "2026-10-28,v2-rolling,2026-10-27,0.0027423,-0.0071061,,,165.25,prediction uses last week's changes\n")
MID = ("# Gold and silver around US midterm elections\n## Gold\n| Group | n | raw 1d | net 1d | raw 5d | net 5d | raw 20d | net 20d |\n"
       "|---|---:|---:|---:|---:|---:|---:|---:|\n| All midterms | 6 | -0.83% | -0.75% | +1.10% | +0.87% | +2.26% | +1.79% |\n## Silver\n")


def test_gold_json_assembly(series_dir):
    n = 800
    _daily("gl.gold", "2024-08-01", [2400 + i for i in range(n)])
    _daily("gl.silver", "2024-08-01", [28 + i / 100 for i in range(n)])
    _daily("us.tips10", "2024-08-01", [2.0 + (i % 50) / 100 for i in range(n)], unit="%")
    _daily("us.usd.broad", "2024-08-01", [120 + (i % 30) / 10 for i in range(n)], unit="index")
    _daily("gl.gpr", "2016-01-01", [100 + (i % 200) for i in range(3950)], unit="index")
    store.save_series({"id": "gl.cbgold", "name": "cb", "frequency": "monthly", "fields": ["value", "reporters"], "source_url": "https://imf"},
                      [[f"2025-{m:02d}-28", 20.0, 30] for m in range(1, 13)] + [[f"2026-{m:02d}-28", 25.0, 30] for m in range(1, 10)])
    store.save_series({"id": "us.fomc.meetings", "name": "FOMC", "fields": ["first_day", "projections", "label"], "source_url": "https://fed"},
                      [["2026-12-09", "2026-12-08", 1, "December 8-9*"], ["2027-06-09", "2027-06-08", 1, "June 8-9*"]])
    fake = {"data/forward_log.csv": FWD, "reports/midterms.md": MID}
    g = gold.build(today="2026-10-30", fetch=lambda p: fake[p])
    p = g["prices"]["gold"]
    assert p["value"] == 2400 + n - 1 and p["chg_1w_pct"] == pytest.approx(100 * (3199 / 3192 - 1), abs=0.01) and p["degraded"] is None
    assert g["prices"]["ratio"]["value"] == pytest.approx(3199 / 35.99, abs=0.1)
    assert {d["id"] for d in g["drivers"]} == {"real_yield", "dollar", "gpr", "cb_buying"}
    assert all(d["reading"] and d["url"] for d in g["drivers"])
    m = g["model"]
    assert m["available"] and m["pred_gold_5d_pct"] == pytest.approx(0.27, abs=0.01) and m["pred_silver_5d_pct"] == pytest.approx(-0.71, abs=0.01)
    assert m["n_scored"] == 1 and m["direction_hits"] == 1
    up = {u["title"]: u for u in g["upcoming"]}
    assert "US midterm elections" in up and up["US midterm elections"]["study"]["raw_20d"] == pytest.approx(2.26)
    assert "FOMC rate decision and projections" in up and all(u["date"] <= "2027-02-27" for u in g["upcoming"])
    ep = {e["id"]: e for e in g["episodes"]}
    assert ep["us-election-2024"]["basis"] == "daily" and ep["us-election-2024"]["moves"]["gold_pct_1m"] is not None
    assert ep["gfc-2008"]["moves"]["gold_pct_6m"] is None          # no stored history that far back
    assert json.loads(gold.OUT.read_text())["model"]["log_date"] == "2026-10-28"


def test_gold_falls_back_to_monthly_and_model_unreachable(series_dir):
    _daily("gl.gold.wb_m", "2026-01-31", [4000, 4100], freq="monthly")
    g = gold.build(today="2026-10-30", fetch=lambda p: (_ for _ in ()).throw(OSError("offline")))
    assert g["prices"]["gold"]["degraded"] and g["prices"]["gold"]["chg_1w_pct"] is None
    assert g["prices"]["silver"] is None and g["prices"]["ratio"] is None
    assert not g["model"]["available"] and "offline" in g["model"]["note"]


# ---------------- paper book: metals ----------------

def test_metal_trade_pnl_carry_and_sizing(tmp_path, monkeypatch):
    for mod, attr, sub in ((store, "DATA", "terminal"), (store, "SERIES_DIR", "terminal/series"), (book, "TRADES_DIR", "trades"),
                           (book, "BOOK_DIR", "book"), (book, "STATE_PATH", "book/state.json"), (forms, "TRADES_DIR", "trades")):
        monkeypatch.setattr(mod, attr, tmp_path / sub)
    cfg = {"repo": "x/y", "starting_capital_usd": 100000, "start_date": "2026-10-01", "risk_warning_pct_of_equity": 2.0,
           "instruments": {"XAUUSD": {"name": "Gold (XAU/USD)", "kind": "price", "series": ["t.gold"], "close_utc": "21:00",
                                      "rate_usd": "t.fed", "cost_round_trip_pct": 0.1}}}
    monkeypatch.setattr(book, "load_config", lambda: cfg)
    monkeypatch.setattr(forms, "load_config", lambda: cfg)
    days = [(dt.date(2026, 10, 1) + dt.timedelta(days=i)).isoformat() for i in range(6)]
    store.save_series({"id": "t.gold", "name": "gold"}, [["2026-09-30", 4000.0]] + [[d, v] for d, v in zip(days, [4000, 4040, 4080, 3900, 3800, 3800])])
    store.save_series({"id": "t.fed", "name": "fed"}, [["2026-09-01", 3.6]])
    inst = book.Instrument("XAUUSD", cfg["instruments"]["XAUUSD"])
    assert inst.favourable == 1 and inst.duration(days[0], 4000) is None
    assert inst.unit_loss_to(4000, 3900, None) == pytest.approx(0.025)
    assert inst.cost(100000, None) == pytest.approx(100.0)
    fill = {"direction_sign": 1, "notional_usd": 100000.0, "entry_value": 4000.0, "entry_date": days[0], "duration": None, "cost_usd": 100.0}
    p = book.pnl(inst, fill, 4080.0, days[2], {})
    assert p["price"] == pytest.approx(2000.0)                       # +2% of $100k
    assert p["carry"] == pytest.approx(-100000 * 3.6 / 100 / 360 * 2, abs=0.01)   # a long pays USD funding
    short = book.pnl(inst, {**fill, "direction_sign": -1}, 4080.0, days[2], {})
    assert short["price"] == pytest.approx(-2000.0) and short["carry"] > 0
    assert book.hit(inst, 1, 3890.0, 3900.0, None) == "stop" and book.hit(inst, -1, 3890.0, None, 3900.0) == "target"
    assert not book.validate_levels(inst, 1, 4000.0, 3900.0, 4200.0)
    # through the form: alias "gold", sized by risk to the stop
    from tests.test_book import OPEN, issue
    r = forms.handle(issue(1, "[Open trade] g", OPEN("gold", "long", "Risk amount to stop (USD)", "1000", "3900", "4300")))
    assert r["accepted"]
    st = book.build(today=days[-1])
    t = st["trades"][0]
    assert t["open"]["instrument"] == "XAUUSD"
    assert t["fill"]["notional_usd"] == pytest.approx(1000 / 0.025) and t["status"] == "closed" and t["exit"]["reason"] == "stop"
    assert st["instruments"]["XAUUSD"]["cost_unit"] == "% of notional"
    assert next(b for b in st["benchmarks"] if b["code"] == "XAUUSD")["description"] == "long gold"


def test_gold_degraded_rule_clears_when_either_daily_source_works():
    from terminal import degraded
    assert "gold" in [r["id"] for r in degraded.active({"sources": {"gold_stooq": {"state": "error"}}})]
    assert "gold" not in [r["id"] for r in degraded.active({"sources": {"gold_stooq": {"state": "error"}, "gold_lbma": {"state": "ok"}}})]
    r = next(r for r in degraded.active({"sources": {}}) if r["id"] == "gold")
    assert "Stooq and LBMA" in r["upgrade"] and degraded.for_series("gl.gold.wb_m", [r])["id"] == "gold"
