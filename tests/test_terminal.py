import datetime as dt
import json

import pytest

from terminal import calendar, store, summary
from terminal.sources import brazil, france, global_


@pytest.fixture()
def tmp_store(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "DATA", tmp_path)
    monkeypatch.setattr(store, "SERIES_DIR", tmp_path / "series")
    monkeypatch.setattr(store, "STATUS_PATH", tmp_path / "status.json")
    return tmp_path


def test_save_series_merges_and_never_deletes(tmp_store):
    meta = {"id": "x.test", "name": "t", "source": "s", "source_id": "id"}
    store.save_series(meta, [["2026-01-01", 1.0], ["2026-01-02", 2.0]])
    s = store.save_series(meta, [["2026-01-02", 2.5], ["2026-01-03", 3.0]])   # overwrite one, add one, omit one
    assert s["history"] == [["2026-01-01", 1.0], ["2026-01-02", 2.5], ["2026-01-03", 3.0]]
    on_disk = json.loads((tmp_store / "series" / "x.test.json").read_text())
    assert on_disk["n"] == 3 and on_disk["first"] == "2026-01-01" and on_disk["source_id"] == "id"
    store.save_series(meta, [["2026-01-04", float("nan")]])                     # all-empty rows are ignored
    assert store.load_series("x.test")["n"] == 3


def test_save_series_two_part_key(tmp_store):
    meta = {"id": "x.survey", "name": "t", "fields": ["median", "sd"]}
    store.save_series(meta, [["2026-01-01", "2026", 4.0, 0.2], ["2026-01-01", "2027", 3.8, 0.3]], key_len=2)
    s = store.save_series(meta, [["2026-01-01", "2026", 4.1, 0.2]], key_len=2)
    assert [r[:3] for r in s["history"]] == [["2026-01-01", "2026", 4.1], ["2026-01-01", "2027", 3.8]]


def test_b3_curve_parse_and_interpolate():
    html = ("<table><tr><td class='a'>1</td><td>14,90</td><td>0,00</td></tr>"
            "<tr><td>100</td><td>14,50</td><td>1</td></tr><tr><td>300</td><td>13,50</td><td>1</td></tr></table>")
    curve = brazil.parse_b3_curve(html)
    assert curve == [(1, 14.9), (100, 14.5), (300, 13.5)]
    assert brazil.interpolate(curve, 200) == pytest.approx(14.0)
    assert brazil.interpolate(curve, 400) is None


def test_parse_fomc_and_ecb():
    fed = ('<h4>2027 FOMC Meetings</h4><div class="fomc-meeting__month"><strong>January</strong></div>'
           '<div class="fomc-meeting__date">26-27</div><div class="fomc-meeting__month"><strong>Apr/May</strong></div>'
           '<div class="fomc-meeting__date">30-1</div><div class="fomc-meeting__month"><strong>August</strong></div>'
           '<div class="fomc-meeting__date">22 (notation vote)</div>')
    assert calendar.parse_fomc(fed) == ["2027-01-27", "2027-05-01"]
    ecb = ("<dt> 16/12/2026 </dt><dd>Governing Council of the ECB: monetary policy meeting in Frankfurt (Day 1)<br></dd>"
           "<dt> 17/12/2026 </dt><dd>Governing Council of the ECB: monetary policy meeting in Frankfurt (Day 2), followed by press conference</dd>"
           "<dt> 25/11/2026 </dt><dd>Governing Council of the ECB: non-monetary policy meeting</dd>")
    assert calendar.parse_ecb(ecb) == ["2026-12-17"]


def test_recurring_rules():
    ev = calendar.recurring(dt.date(2026, 11, 1), dt.date(2026, 11, 30))
    focus = [e["date"] for e in ev if e["origin"] == "rule:focus"]
    assert focus == ["2026-11-02", "2026-11-09", "2026-11-16", "2026-11-23", "2026-11-30"]
    rardp = [e["date"] for e in ev if e["origin"] == "rule:rardp"]
    assert rardp == ["2026-11-20"]          # 22 Nov 2026 is a Sunday -> Friday 20th
    assert all(e["status"] == "estimated" for e in ev)


def test_attention_score_and_under_attended():
    far = (dt.date.today() + dt.timedelta(days=60)).isoformat()
    near = (dt.date.today() + dt.timedelta(days=10)).isoformat()
    events = [calendar.ev(far, "BR", "rates", "A", 3, "confirmed", "", "qa"),
              calendar.ev(near, "BR", "rates", "B", 3, "confirmed", "", "qb"),
              calendar.ev(far, "GLOBAL", "rates", "C", 3, "confirmed", "", "qc"),
              calendar.ev(far, "BR", "fiscal", "D", 3, "confirmed", "", "qd")]
    att = {"queries": {"qa": {"history": [["d", 1, 100, 0.002, 0.001]]},         # twice its normal
                       "qb": {"history": [["d", 1, 100, 0.0001, 0.001]]},        # a tenth of normal but near
                       "qc": {"history": [["d", 1, 100, 0.00004, 0.0001]]},      # 0.4 of normal, far: flagged
                       "qd": {"history": [["d", 1, 100, 0.01]]}}}                # old 4-field row: no score
    calendar.score_events(events, att)
    assert events[0]["attention"]["score"] == pytest.approx(2.0) and not events[0]["under_attended"]
    assert events[1]["attention"]["score"] == pytest.approx(0.1) and not events[1]["under_attended"]
    assert events[2]["attention"]["score"] == pytest.approx(0.4) and events[2]["under_attended"]
    assert events[3]["attention"] is None and not events[3]["under_attended"]


def test_stats_changes_and_z():
    hist = [[(dt.date(2026, 1, 1) + dt.timedelta(days=i)).isoformat(), 10.0 + (i % 5) * 0.1] for i in range(300)]
    hist.append(["2026-10-28", 12.0])
    s = {"history": hist}
    st = summary.stats(s, "bp")
    assert st["level"] == 12.0 and st["as_of"] == "2026-10-28"
    assert st["chg_1w"] == pytest.approx(100 * (12.0 - [v for d, v in hist if d <= "2026-10-21"][-1]), abs=0.1)
    assert st["z_1y"] > 3
    assert summary.change(5.0, ("d", 4.0), "pct") == pytest.approx(25.0)
    assert summary.change(96.7, ("d", 81.5), "diff") == pytest.approx(15.2)


def test_dispersion_percentile_same_horizon():
    rows = []
    for y in range(2016, 2027):
        for m in range(1, 13):
            d = f"{y}-{m:02d}-01"
            rows.append([d, str(y), 1.0, 1.0, 0.1 * m, 0, 0, 0])    # horizon 0: sd 0.1..1.2
            rows.append([d, str(y + 1), 1.0, 1.0, 5.0, 0, 0, 0])    # horizon 1: always 5
    s = {"history": rows, "fields": ["median", "mean", "sd", "min", "max", "respondents"], "last": "2026-12-01"}
    assert summary.dispersion_percentile(s, "sd", 0, 0.05) == 0.0
    assert summary.dispersion_percentile(s, "sd", 0, 1.25) == 100.0
    assert summary.dispersion_percentile(s, "sd", 1, 5.0) == 100.0


def test_kalshi_country_filter_and_dollars():
    assert global_._kalshi_country("Next French presidential election winner?") == "FR"
    assert global_._kalshi_country("Will Lula win?") == "BR"
    assert global_._kalshi_country("Banxico rate decision in December") == "MX"
    assert global_._kalshi_country("New Mexico governor race") is None
    assert global_._dollars("0.2100") == pytest.approx(0.21) and global_._dollars(None, 37) == pytest.approx(0.37)


def test_webstat_csv_parser_and_aft_table():
    rows = france._parse_date_value_csv('time_period_start;obs_value\n"2026-10-27";3,45\n2026-10-28;3.47\nnoise')
    assert rows == [["2026-10-27", 3.45], ["2026-10-28", 3.47]]
    html = ("<table><tr><th>Agency</th><th>Rating</th></tr><tr><td>S&amp;P Global</td><td>A+</td></tr><tr><td>Fitch Ratings</td><td>A+</td><td>Stable</td>"
            "<td>28/08/2026</td></tr><tr><td>Moody's</td><td>Aa3</td><td>Negative</td></tr></table>")
    out = france.parse_aft_ratings(html)
    assert [r["agency"] for r in out] == ["S&P Global", "Fitch Ratings", "Moody's"] and out[1]["dates"] == ["28/08/2026"]


def test_evidence_lookup_prefix():
    summary.EVIDENCE = {"default": {"badge": "untested"}, "series": {"br.di": {"badge": "untested"},
                        "mx.mbono10y.auction": {"badge": "context"}, "pm.": {"badge": "tested_no_lead"}}}
    assert summary.evidence("mx.mbono10y.auction")["badge"] == "context"
    assert summary.evidence("pm.12345")["badge"] == "tested_no_lead"
    assert summary.evidence("zz.unknown")["badge"] == "untested"
    summary.EVIDENCE = None


def test_degraded_then_upgrades_when_primary_appears(tmp_store):
    from terminal import degraded
    monthly = {"id": "fr.spread.oat_bund.ecb_m", "name": "spread (ECB monthly)", "frequency": "monthly"}
    store.save_series(monthly, [["2026-08-31", 80.0], ["2026-09-30", 82.0]])
    status = {"sources": {"webstat": {"state": "missing_secret"}, "ecb_monthly": {"state": "ok"},
                          "banxico_api": {"state": "ok"}, "fred_api": {"state": "ok"}, "b3_di": {"state": "ok"}}}
    rules = degraded.active(status)
    assert [r["id"] for r in rules] == ["webstat"] and "WEBSTAT_CLIENT_ID" in rules[0]["upgrade"]
    s, fallback = summary.first_series(["fr.spread.oat_bund", "fr.spread.oat_bund.ecb_m"])
    assert fallback and degraded.for_series(s["id"], rules)["id"] == "webstat"
    # the secret is added: Webstat succeeds and writes the daily series; nothing else changes
    store.save_series({"id": "fr.spread.oat_bund", "name": "spread (daily)", "frequency": "daily"},
                      [["2026-10-27", 79.0], ["2026-10-28", 78.5]])
    status["sources"]["webstat"]["state"] = "ok"
    rules = degraded.active(status)
    s, fallback = summary.first_series(["fr.spread.oat_bund", "fr.spread.oat_bund.ecb_m"])
    assert s["id"] == "fr.spread.oat_bund" and not fallback and rules == []
    assert degraded.for_series("mx.survey.inflation", degraded.active({"sources": {}}))["id"] == "banxico"
    assert degraded.for_series("mx.cot.mxn", degraded.active({"sources": {}})) is None


def test_rating_reviews_dedupe_by_country_agency_date():
    manual = {"date": "2026-11-27", "country": "FR", "type": "ratings", "title": "S&P Global sovereign rating review: France", "origin": "manual"}
    aft = {"date": "2026-11-27", "country": "FR", "type": "ratings", "title": "Standard & Poor's sovereign rating review: France", "origin": "aft"}
    other = {"date": "2026-12-11", "country": "FR", "type": "ratings", "title": "KBRA sovereign rating review: France", "origin": "aft"}
    copom = {"date": "2026-11-04", "country": "BR", "type": "rates", "title": "Copom decision"}
    out = calendar.dedupe_ratings([manual, copom, aft, other])
    assert aft in out and manual not in out and other in out and copom in out
    assert calendar.rating_key(manual) == calendar.rating_key(aft) == ("FR", "S&P", "2026-11-27")
