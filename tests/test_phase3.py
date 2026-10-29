import pandas as pd
import pytest

from terminal import crowd, labtests, scenarios, store


@pytest.fixture()
def tmp_store(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "DATA", tmp_path)
    monkeypatch.setattr(store, "SERIES_DIR", tmp_path / "series")
    monkeypatch.setattr(store, "STATUS_PATH", tmp_path / "status.json")
    return tmp_path


def test_permutation_tests_detect_a_shift_and_not_noise():
    big = labtests.perm_diff([3.0, 3.2, 2.9, 3.1, 3.3, 2.8, 3.0, 3.1], [1.0, 1.1, 0.9, 1.2, 1.0, 0.8, 1.1, 0.9, 1.0])
    assert big["diff"] > 1.5 and big["p"] < 0.01
    same = labtests.perm_diff([1.0, 2.0, 3.0, 4.0], [1.0, 2.0, 3.0, 4.0])
    assert same["p"] > 0.4
    rho = labtests.perm_spearman([1, 2, 3, 4, 5, 6, 7, 8], [2, 1, 4, 3, 6, 5, 8, 7])
    assert rho["rho"] > 0.8 and rho["p"] < 0.05


def test_trailing_percentile_uses_only_the_past():
    p = labtests.trailing_percentile([1, 2, 3, 4, 100, 0], window=3, min_n=3)
    assert p[:3] == [None, None, None]
    assert p[3] == 100 and p[4] == 100 and p[5] == 0           # 100 vs (2,3,4); 0 vs (3,4,100)


def test_verdict_rule():
    fit_ok = {"n_extreme": 10, "diff": 0.5, "p": 0.01}
    assert labtests.verdict(fit_ok, {"diff": 0.3, "p": 0.05})[0] == "tested_leads"
    assert labtests.verdict(fit_ok, {"diff": -0.3, "p": 0.9})[0] == "tested_no_lead"
    assert labtests.verdict({"n_extreme": 3, "diff": 1.0, "p": 0.001}, None)[0] == "untested"


def test_favourite_matching_handles_short_names():
    assert labtests._same_side("No", "No (remain in UK)")
    assert labtests._same_side("Lula", "Luiz Inácio Lula da Silva (PT)")
    assert not labtests._same_side("Flávio Bolsonaro", "Luiz Inácio Lula da Silva (PT)")


def test_poll_implied_uses_earlier_elections_only():
    e = pd.DataFrame({"iso3": ["X"] * 5, "vote_date": ["2000", "2004", "2008", "2012", "2016"],
                      "poll_margin_pp": [5, 5, 5, 5, 5], "actual_margin_pp": [9, 1, 9, 1, 5]})
    out = labtests.poll_implied(e)
    assert out["sigma"].iloc[:3].isna().all()                  # fewer than 3 earlier elections anywhere
    assert out["sigma"].iloc[3] == pytest.approx(4.0)
    assert 0.5 < out["p_poll_a"].iloc[3] < 1


SC = {"yes_branches": ["down"], "branches": [{"id": "up", "side": "good"}, {"id": "down", "side": "bad"}]}


def test_calculator_and_asymmetry():
    calc = {"current": 100.0, "good_level": 90.0, "bad_level": 120.0}
    assert scenarios.implied_good(calc) == pytest.approx(2 / 3)
    assert not scenarios.yes_is_good(SC)
    # I think the bad outcome is likelier than the market: favour bad, target 120, stop 90 -> 20/10 = 2:1
    a = scenarios.asymmetry(SC, calc, market_yes=0.2, mine={"prob": 0.4}, days=40)
    assert a["checks"]["gap"]["ok"] and a["checks"]["reward_risk"]["value"] == 2.0 and a["flag"]
    assert not scenarios.asymmetry(SC, calc, 0.2, {"prob": 0.4}, days=200)["flag"]    # too far away
    assert not scenarios.asymmetry(SC, calc, 0.3, {"prob": 0.4}, days=40)["flag"]     # gap 10 points
    assert not scenarios.asymmetry(SC, calc, None, {"prob": 0.4}, days=40)["flag"]    # no market
    assert scenarios.to_level(5.0, 2.0, "fx", None) == pytest.approx(5.1)
    assert scenarios.to_level(14.0, 30.0, "di", "% p.a.") == pytest.approx(14.3)
    assert scenarios.to_level(80.0, 12.0, "spread_bp", "bp") == 92.0


def test_resolve_moves(tmp_store):
    cfg = {"instruments": {"USDMXN": {"kind": "fx"}, "OATBUND": {"kind": "spread_bp"}}}
    wi = pd.DataFrame([{"country": "FRA", "asset": "spread_bp", "scenario": "downgrade_1", "estimate": 36.95, "lo90": 29.09,
                        "hi90": 44.81, "date": "2026-09-01"}])
    m = scenarios.resolve_move({"instrument": "OATBUND", "what_if": {"country": "FRA", "asset": "spread_bp", "scenario": "downgrade_1",
                                                                       "scale": 0.5}}, cfg, wi, None)
    assert m["value"] == pytest.approx(18.48, abs=0.01) and m["lo"] == pytest.approx(14.545, abs=0.01)
    em = pd.DataFrame([{"country": "MX", "asset": "FX", "event_id": "E1", "event_type": "election", "subtype": "legislative", "ab_1": 1.0},
                       {"country": "MX", "asset": "FX", "event_id": "E2", "event_type": "election", "subtype": "legislative", "ab_1": -3.0}])
    m = scenarios.resolve_move({"instrument": "USDMXN", "event_study": {"country": "MX", "event_type": "election", "subtypes": ["legislative"],
                                                                         "asset": "FX", "h": 1}}, cfg, None, em)
    assert m["value"] == pytest.approx(1.0)                   # local-currency value -1% on average = USD/MXN +1%
    store.save_series({"id": "mx.usdmxn.fix", "name": "x"}, [["2016-11-08", 18.5], ["2016-11-11", 21.0]])
    m = scenarios.resolve_move({"instrument": "USDMXN", "analog": {"series": "mx.usdmxn.fix", "from": "2016-11-08", "to": "2016-11-11"}}, cfg, None, None)
    assert m["value"] == pytest.approx(13.51, abs=0.01)
    assert "error" in scenarios.resolve_move({"instrument": "USDMXN", "what_if": {"country": "X", "asset": "y", "scenario": "z"}}, cfg, wi, None)


def test_rating_notches_and_middle():
    assert crowd.notch("Baa3") == crowd.notch("BBB-") == 9
    rows = [{"notch": crowd.notch(r)} for r in ("BBB", "Baa3", "BBB-")]
    assert crowd.SCALE[crowd.middle(rows)] == "BBB-"
