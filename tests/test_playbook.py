"""Policy playbook (Horizons country pages): the cited YAML is complete and well formed, and the
6- and 24-month outcomes are computed correctly from stored series."""

import datetime as dt
import re

import pytest
import yaml

from terminal import playbook

SPEC = yaml.safe_load(playbook.SPEC.read_text())
KEYS = set(SPEC["sources"]) | set(SPEC["works"])


def test_sources_and_works_are_complete():
    for k, s in SPEC["sources"].items():
        assert s["url"].startswith("https://") and s["label"] and s["date"], k
    for k, w in SPEC["works"].items():
        assert w["author"] and w["title"] and 1900 < int(w["year"]) <= dt.date.today().year, k


def test_policies_cited_and_positioned():
    assert set(SPEC["countries"]) == {"BR", "MX", "FR"}
    for cc, c in SPEC["countries"].items():
        assert c["approach"]["summary"].strip()
        assert len(c["approach"]["policies"]) >= 3, cc
        for p in c["approach"]["policies"]:
            assert 0 <= p["position"] <= 100, p["name"]
            assert p["why"].strip() and p["sources"] and set(p["sources"]) <= KEYS, p["name"]


def test_every_country_has_all_five_schools_cited():
    for cc in ("BR", "MX", "FR"):
        got = [s["school"] for s in SPEC["schools"][cc]]
        assert sorted(got) == sorted(playbook.SCHOOLS), cc
        for s in SPEC["schools"][cc]:
            assert s["view"].strip() and s["applies_to"].strip(), (cc, s["school"])
            assert s["cites"] and set(s["cites"]) <= set(SPEC["works"]), (cc, s["school"])   # published writing only
            assert '"' not in s["view"] and "“" not in s["view"], (cc, s["school"])          # no quotations


def test_episodes_cited_and_cut_against_every_school():
    ids, against = set(), set()
    for e in SPEC["episodes"]:
        assert e["id"] not in ids
        ids.add(e["id"])
        assert e["country"] in playbook.SERIES
        dt.date.fromisoformat(e["start"])
        assert e["summary"].strip() and e["cites"] and set(e["cites"]) <= KEYS, e["id"]
        for a in e.get("against", []):
            assert a["school"] in playbook.SCHOOLS and a["why"].strip(), e["id"]
            against.add(a["school"])
    assert against == set(playbook.SCHOOLS)
    named = {"br-real-plan-1994", "br-lula-orthodox-2003", "br-new-economic-matrix-2011", "br-spending-cap-2016", "mx-tequila-1994",
             "ar-convertibility-1991", "ar-milei-2023", "fr-rigueur-1983"}
    assert named <= ids
    assert {e["country"] for e in SPEC["episodes"]} == {"BR", "MX", "FR", "AR"}


def test_no_numbers_without_a_source_in_summaries():
    # numbers in the hand-written text must come with at least one fetched (URL) source on the item
    for e in SPEC["episodes"]:
        if re.search(r"\d+(\.\d+)?%", e["summary"]):
            assert any(c in SPEC["sources"] for c in e["cites"]), e["id"]


def _monthly(start, values):
    d, rows = dt.date.fromisoformat(start), []
    for v in values:
        rows.append((d, v))
        d = playbook.add_months(d, 1)
    return rows


def test_outcomes_from_synthetic_series(monkeypatch):
    # 30 months from Nov 2019 (the month before the episode): inflation rises 0.1 a month, fx (local per USD) rises by 1/24 of its start a month,
    # the 10-year yield rises 10bp a month; quarterly GDP grows 1% a quarter
    infl = _monthly("2019-11-01", [3 + 0.1 * i for i in range(30)])
    fx = _monthly("2019-11-01", [5 * (1 + i / 24) for i in range(30)])
    y10 = _monthly("2019-11-01", [10 + 0.1 * i for i in range(30)])
    gdp = [(dt.date(2018 + q // 4, 3 * (q % 4) + 1, 1), 100 * 1.01 ** q) for q in range(24)]
    data = {"hist.mx.cpi_yoy": infl, "hist.mx.fx_m": fx, "mx.10y.oecd_m": y10, "hist.mx.gdp_q": gdp}
    loader = lambda sid: playbook.Series(sid, data[sid], {"source": "test"}) if sid in data else None
    oc, start, src = playbook.outcomes({"country": "MX", "start": "2019-12-10"}, today=dt.date(2026, 1, 1), loader=loader)
    m6, m24 = oc["m6"], oc["m24"]
    assert m6["date"] == "2020-06" and m24["date"] == "2021-12"
    assert start["inflation"] == pytest.approx(3.0) and m6["inflation"] == pytest.approx(3.7) and m6["inflation_chg_pp"] == pytest.approx(0.7)
    assert m24["fx_pct"] == pytest.approx(100 * (5 / (5 * (1 + 25 / 24)) - 1), abs=0.05)   # base Nov 2019 to Dec 2021: 25 months
    assert m6["y10_bp"] == 70 and m24["y10_bp"] == 250
    assert m6["growth"] == pytest.approx(100 * (1.01 ** 4 - 1), abs=0.05)
    assert src["inflation"]["m6"]["series"] == "hist.mx.cpi_yoy"


def test_null_reasons():
    loader = lambda sid: playbook.Series(sid, _monthly("2020-01-01", [1.0] * 12), {}) if sid == "hist.ar.fx_m" else None
    oc, _, src = playbook.outcomes({"country": "AR", "start": "2020-06-01"}, today=dt.date(2026, 1, 1), loader=loader)
    assert oc["m6"]["fx_pct"] == 0 and oc["m6"]["null_reasons"]["y10_bp"] == playbook.NO_FREE_DATA
    assert "after the latest data" in oc["m24"]["null_reasons"]["fx_pct"]
