import json

import pandas as pd

from forecast_panel.site_build import _f, build_scorecard, forward_log_series, latest_by_source


def _panel():
    rows = []
    for date in ["2026-11-02", "2026-11-09"]:
        for qid, p in [("q1", 0.8), ("q2", 0.3)]:
            rows += [{"date": date, "question_id": qid, "source": "polymarket", "prob": p, "as_of": date, "ref": "", "notes": ""},
                     {"date": date, "question_id": qid, "source": "my_prob", "prob": 0.9 if qid == "q1" else 0.5, "as_of": date, "ref": "", "notes": ""},
                     {"date": date, "question_id": qid, "source": "claude_prob", "prob": float("nan"), "as_of": date, "ref": "", "notes": "blank"}]
    return pd.DataFrame(rows)


def test_scorecard_points_beat_market():
    qs = [{"id": "q1", "question": "A?", "resolution_date": "2026-11-16", "resolved": True, "outcome": 1},
          {"id": "q2", "question": "B?", "resolution_date": "2026-12-31", "resolved": False, "outcome": None}]
    agg = pd.DataFrame({"date": ["2026-11-02", "2026-11-09"], "question_id": ["q1", "q1"], "aggregate_plain": [0.85, 0.85], "aggregate_extremized": [0.9, 0.9]})
    s = build_scorecard(qs, _panel(), agg)
    me = s["forecasters"]["my_prob"]
    assert me["per_question"][0]["points"] == 100 * (0.04 - 0.01)      # market Brier 0.04, mine 0.01
    assert me["total_points"] == me["per_question"][0]["running_total"]
    assert me["open"] == {"q2": 0.5}
    assert s["forecasters"]["claude_prob"]["per_question"][0]["points"] is None
    assert s["forecasters"]["aggregate_extremized"]["per_question"][0]["points"] == round(100 * (0.04 - 0.01), 2)
    assert me["calibration"][0]["observed"] == 1.0
    json.dumps(s)  # JSON-safe


def test_helpers():
    assert _f(float("nan")) is None and _f("x") is None and _f(0.123456) == 0.12346
    fwd = pd.DataFrame({"log_date": ["2026-10-28", "2026-11-04"], "my_prob_q1": [None, 0.4]})
    assert forward_log_series(fwd, "my_prob_q1") == [["2026-11-04", 0.4]]
    assert forward_log_series(fwd, "claude_prob_q1") == []
    latest = latest_by_source(_panel(), "q1")
    assert latest["polymarket"]["date"] == "2026-11-09" and latest["claude_prob"]["prob"] is None
