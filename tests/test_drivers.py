"""External drivers: regression helpers, plain-English labels, attribution readings, trade exposure,
and the EUR/USD book convention."""

import numpy as np
import pandas as pd
import pytest

from terminal import drivers as D


def test_ols_uni_recovers_beta():
    rng = np.random.default_rng(0)
    x = rng.normal(size=300)
    y = 0.8 * x + rng.normal(scale=0.2, size=300)
    r = D.ols_uni(y, x)
    assert r["beta"] == pytest.approx(0.8, abs=0.05) and 0 < r["se"] < 0.05 and r["r2"] > 0.8


def test_ols_multi_covariance_shape():
    rng = np.random.default_rng(1)
    X = rng.normal(size=(200, 3))
    y = X @ np.array([1.0, -0.5, 0.0]) + rng.normal(scale=0.1, size=200)
    m = D.ols_multi(y, X)
    assert m["beta"][0] == pytest.approx(1.0, abs=0.05) and m["beta"][1] == pytest.approx(-0.5, abs=0.05)
    assert len(m["cov"]) == 3 and all(len(r) == 3 for r in m["cov"]) and m["resid_sd"] > 0


def test_changes_weekly_pct_and_bp():
    idx = pd.date_range("2026-01-01", periods=30, freq="D")
    s = pd.Series(np.linspace(100, 103, 30), index=idx)
    w = D.changes(s, "pct", "W")
    assert (w > 0).all()
    b = D.changes(pd.Series(np.linspace(400, 430, 30), index=idx), "bp", "W")
    assert b.iloc[-1] == pytest.approx(7, abs=1.5)


def test_sentence_peso():
    inst = D.INSTRUMENTS["USDMXN"]
    s = D.sentence(inst, D.DRIVERS["usd"], 0.8)
    assert s == "When the dollar (broad index) rises 1%, USD/MXN usually rises 0.80% (the peso weakens about 0.80%)."
    s = D.sentence(D.INSTRUMENTS["OATBUND"], D.DRIVERS["eur"], -1.0)
    assert "narrows 1.0bp" in s


def test_reading_dollar_led():
    parts = [{"driver": "usd", "contrib": 0.9}, {"driver": "vix", "contrib": 0.1}]
    r = D.reading(1.2, parts, 0.2, "USD/MXN", "peso", "Mexico", "%", "week")
    assert r == "Most of this week's peso fall (USD/MXN +1.20%) came from the dollar (broad index), not Mexico."
    r = D.reading(1.2, [{"driver": "usd", "contrib": 0.1}], 1.1, "USD/MXN", "peso", "Mexico", "%", "week")
    assert "local to Mexico" in r


def test_eurusd_book_convention():
    from terminal.book import Instrument, carry, pnl
    import yaml
    from terminal import store
    cfg = yaml.safe_load((store.ROOT / "data" / "book" / "config.yaml").read_text())
    inst = Instrument("EURUSD", cfg["instruments"]["EURUSD"])
    assert inst.inverse and inst.favourable == 1
    fill = {"direction_sign": 1, "notional_usd": 100000, "entry_value": 1.10, "entry_date": "2026-10-01", "cost_usd": 20.0}
    p = pnl(inst, fill, 1.21, "2026-10-01", {})
    assert p["price"] == pytest.approx(10000.0)          # long EUR, EUR/USD +10% -> +10% of notional
    assert inst.unit_loss_to(1.10, 1.045, None) == pytest.approx(0.05)
