import pandas as pd

from forecast_panel.sources import human_column, parse_gjopen_consensus, parse_swift_forecast

GJO_PAGE = """<html><head><title>
  Good Judgment&reg; Open | When will the IDF next strike Iran?
</title></head><body>
<table class="table table-striped consensus-table"><thead><tr><th>Possible Answer</th><th class="text-right">Crowd Forecast</th></tr></thead>
<tbody>
<tr ><td>Before 24 July 2026</td><td class="text-right">0.13%</td><td class="text-right recent-change-col"> +0.00% </td></tr>
<tr ><td>Between 24 July 2026 and 17 September 2026</td><td class="text-right">0.19%</td><td class="text-right"> +0.00% </td></tr>
<tr ><td>Not before 11 December 2026</td><td class="text-right">60.00%</td><td class="text-right"> -1.00% </td></tr>
</tbody></table></body></html>"""

SWIFT_TEXT = ("1. Will the USA acquire Greenland in 2026? Swift Centre Forecast: 4% Polymarket at the time: 12% "
              "2. Russia-Ukraine ceasefire in 2026? Swift Centre Forecast: 22% Polymarket at the time: 43% "
              "3. Trump out as President before 2027? Swift Centre Forecast (on 27th April) : 4.6% Polymarket on same date: 17%")


def test_parse_gjopen_consensus():
    title, table = parse_gjopen_consensus(GJO_PAGE)
    assert title == "When will the IDF next strike Iran?"
    assert table["Before 24 July 2026"] == 0.0013
    assert table["Not before 11 December 2026"] == 0.6


def test_parse_swift_forecast():
    assert parse_swift_forecast(SWIFT_TEXT, r"Russia-Ukraine ceasefire in 2026\?") == 0.22
    assert parse_swift_forecast(SWIFT_TEXT, r"Trump out as President before 2027\?") == 0.046
    assert parse_swift_forecast(SWIFT_TEXT, r"Sudan ceasefire") is None


def test_human_column_carries_forward():
    df = pd.DataFrame({"log_date": ["2026-10-05", "2026-10-12", "2026-10-19"],
                       "my_prob_q1": [0.3, None, 0.4]})
    r = human_column(df, "", "my_prob_q1", "2026-10-14")
    assert r.prob == 0.3 and r.as_of == "2026-10-05" and "carried forward" in r.note()
    r = human_column(df, "", "my_prob_q1", "2026-10-19")
    assert r.prob == 0.4 and r.note() == ""
    r = human_column(df, "", "claude_prob_q1", "2026-10-19")
    assert r.prob != r.prob and "not in forward_log.csv" in r.note()
    r = human_column(None, "unavailable", "my_prob_q1", "2026-10-19")
    assert r.prob != r.prob and r.note() == "unavailable"
