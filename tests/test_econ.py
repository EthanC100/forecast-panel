"""Economists and policy: consensus rows, the policy tracker's citations, consensus-gap flags and the
assessment validator."""

import datetime as dt
import json

import pytest
import yaml

from terminal import assessments, consensus, store


@pytest.fixture
def series_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "SERIES_DIR", tmp_path)
    monkeypatch.setattr(store, "series_path", lambda sid: tmp_path / f"{sid}.json")
    return tmp_path


def _survey(sid, rows, fields):
    store.save_series({"id": sid, "name": sid, "country": "BR", "unit": "%", "source": "test", "fields": fields, "key": ["date", "ref"]},
                      rows, key_len=2)


def test_survey_rows_three_month_move(series_dir):
    y = dt.date.today().year
    _survey("br.focus.ipca", [[f"{y}-01-05", str(y), 4.0, 4.1, 0.2, 3.5, 4.6, 100],
                              [f"{y}-06-05", str(y), 4.5, 4.4, 0.3, 3.9, 5.2, 110]], ["median", "mean", "sd", "min", "max", "respondents"])
    rows = [r for r in consensus.survey_rows("BR", y) if r["var"] == "inflation"]
    assert rows and rows[0]["id"] == f"fc:BR.inflation.{y}"
    assert rows[0]["median"] == 4.5 and rows[0]["min"] == 3.9 and rows[0]["max"] == 5.2 and rows[0]["dispersion"] == 0.3
    assert rows[0]["change_3m"] == pytest.approx(0.5)


def test_every_policy_is_cited():
    spec = yaml.safe_load(consensus.POLICIES.read_text())["policies"]
    assert {p["country"] for p in spec} == {"FR", "BR", "MX"}
    for p in spec:
        for side in ("claim", "assessment"):
            s = p[side]["source"]
            assert s["url"].startswith("http") and s["date"], (p["id"], side)
        assert set(p["effects"]) == {"deficit", "inflation", "growth"}
        assert p["view"]["question"] and p["view"]["resolution_date"]
        assert p["next"].get("event") or p["next"].get("date")


def test_policy_events_exist_in_calendar_inputs():
    from terminal.calendar import ev
    spec = yaml.safe_load(consensus.POLICIES.read_text())["policies"]
    manual = yaml.safe_load((store.INPUTS / "events.yaml").read_text())
    ids = {ev(e["date"], e["country"], e["type"], e["title"], e["importance"], e["status"], e.get("source", ""), e.get("query", ""))["id"]
           for e in manual.get("events", [])}
    for p in spec:
        e = p["next"].get("event")
        if e:
            assert e in ids, (p["id"], e)


def test_gap_flags(monkeypatch):
    rows = {"fc:BR.primary.2027": {"id": "fc:BR.primary.2027", "country": "BR", "label": "Primary balance", "year": 2027, "median": -0.3,
                                   "dispersion": 0.29, "unit": "% of GDP", "source": "BCB Focus"}}
    pols = [{"question_id": "pol:br-fiscal-framework", "name": "Fiscal framework", "country": "BR", "consensus": {"ref": "fc:BR.primary.2027"}}]
    calls = {"pol:br-fiscal-framework": {"id": "J00001", "submitted_at": "2026-10-30T10:00:00Z", "point": 0.2, "probability": 0.3},
             "fc:BR.primary.2027": {"id": "J00002", "submitted_at": "2026-10-30T11:00:00Z", "point": None, "probability": 0.5}}
    monkeypatch.setattr(consensus, "_calls", lambda: calls)
    g = {x["question_id"]: x for x in consensus.gaps(rows, pols)}
    assert g["pol:br-fiscal-framework"]["flagged"] and g["pol:br-fiscal-framework"]["gap_in_sd"] == pytest.approx(1.72, abs=0.01)
    assert not g["fc:BR.primary.2027"]["flagged"]
    calls["fc:BR.primary.2027"]["probability"] = 0.9
    g = {x["question_id"]: x for x in consensus.gaps(rows, pols)}
    assert g["fc:BR.primary.2027"]["flagged"]


def test_source_values_both_decimal_conventions():
    vals = assessments.source_values("déficit de R$ 86,1 bilhões (0,6% do PIB); despesas de R$ 1.239,2 bilhões; 5,4 % du PIB; 3.9% of GDP")
    for v in (86.1, 0.6, 1239.2, 5.4, 3.9):
        assert v in vals


def test_assessment_validation():
    text = "Avis du 1 octobre 2026. Le Gouvernement retient une croissance de 1,0 % en 2027 et un déficit de 5,4 % du PIB en 2026."
    ok = {"summary": "The HCFP judges 1.0% growth in 2027 optimistic; the 2026 deficit of 5.4% of GDP is plausible.",
          "key_number": {"value": "1.0%", "what": "growth"}, "date": "2026-10-01", "stance": "more cautious than the government"}
    assert assessments.validate(ok, text, None) == []
    bad = {**ok, "summary": "The deficit will reach 6.1% of GDP.", "date": "2025-10-01"}
    p = assessments.validate(bad, text, None)
    assert any("6.1" in x for x in p) and any("date" in x for x in p)


def test_full_call_point_field(monkeypatch):
    from terminal import forms
    f = {k: None for k in ("question", "question_id", "resolution_date", "base_rate", "factor1", "factor1_direction", "factor1_size",
                           "factor2", "factor2_direction", "factor2_size", "factor3", "factor3_direction", "factor3_size", "scenarios",
                           "probability", "point", "linked_trade", "change_mind", "premortem", "confidence")}
    f.update({"question": "Primary balance 2027 above the median?", "question_id": "fc:BR.primary.2027", "resolution_date": "2028-03-31",
              "base_rate": "median -0.3", "factor1": "x", "factor1_direction": "Raises the probability", "factor1_size": "Small",
              "scenarios": "Above: 30\nBelow: 70", "probability": "30%", "point": "-0.6", "change_mind": "2027-03-31 report",
              "premortem": "the survey was right", "confidence": "Low"})
    issue = {"number": 7, "user": {"login": "EthanC100"}, "created_at": "2026-10-30T10:00:00Z", "html_url": "https://x", "title": "[Full call] t"}
    monkeypatch.setattr(forms, "market_probability", lambda q: None)
    monkeypatch.setattr(forms, "ai_probability", lambda q: None)
    path, rec, lines, ok = forms.full_call(issue, f)
    assert ok and rec["point"] == -0.6
