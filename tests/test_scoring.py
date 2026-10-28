import json

import pandas as pd

from forecast_panel import SOURCES
from forecast_panel.scoring import build_aggregate_log, monday_snapshots, scorable, scorecard

METHOD = {"extremizing_a": 1.5, "brier_floor": 0.01, "unscored_brier": 0.25, "clip": 0.01, "min_sources": 1}
QUESTIONS = [
    {"id": "q1", "question": "A?", "resolution_date": "2026-11-16", "resolved": True, "outcome": 1},
    {"id": "q2", "question": "B?", "resolution_date": "2026-12-31", "resolved": False, "outcome": None},
]


def _panel():
    rows = []
    # Mondays 2026-11-02, 2026-11-09, 2026-11-16 (resolution day, excluded) plus a Tuesday.
    for date in ["2026-11-02", "2026-11-03", "2026-11-09", "2026-11-16", "2026-11-23"]:
        for qid in ["q1", "q2"]:
            for s in SOURCES:
                p = {"polymarket": 0.8, "metaculus": 0.6, "gjopen": float("nan")}.get(s, 0.5)
                rows.append({"date": date, "question_id": qid, "source": s, "prob": p, "as_of": date, "ref": "", "notes": ""})
    return pd.DataFrame(rows)


def test_monday_snapshots_pick_mondays():
    m = monday_snapshots(_panel())
    assert sorted(m["date"].unique()) == ["2026-11-02", "2026-11-09", "2026-11-16", "2026-11-23"]
    assert (m["scoring_day"] == "monday").all()
    # a week without a Monday falls back to its first day
    p = _panel()
    p = p[p["date"] != "2026-11-02"]
    m = monday_snapshots(p)
    assert "2026-11-03" in set(m["date"]) and "no Monday" in m[m["date"] == "2026-11-03"]["scoring_day"].iloc[0]


def test_scorable_excludes_unresolved_and_post_resolution():
    s = scorable(monday_snapshots(_panel()), {"q1": 1}, {"q1": "2026-11-16", "q2": "2026-12-31"})
    assert set(s["question_id"]) == {"q1"}
    assert sorted(s["date"].unique()) == ["2026-11-02", "2026-11-09"]
    assert (s["outcome"] == 1).all()


def test_aggregate_log_weights_switch_after_resolution():
    agg = build_aggregate_log(_panel(), QUESTIONS, METHOD)
    early = agg[(agg["date"] == "2026-11-09") & (agg["question_id"] == "q2")].iloc[0]
    late = agg[(agg["date"] == "2026-11-23") & (agg["question_id"] == "q2")].iloc[0]
    w_early, w_late = json.loads(early["weights"]), json.loads(late["weights"])
    assert "gjopen" not in w_early and len(w_early) == 5
    assert len({round(v, 6) for v in w_early.values()}) == 1          # equal weights before anything resolves
    assert w_late["polymarket"] > w_late["metaculus"] > w_late["my_prob"]  # 0.8 beat 0.6 beat 0.5 on q1
    assert early["aggregate_extremized"] > early["aggregate_plain"] > 0.5


def test_scorecard_renders():
    panel = _panel()
    agg = build_aggregate_log(panel, QUESTIONS, METHOD)
    md = scorecard(panel, agg, QUESTIONS, METHOD, generated="2026-11-23")
    assert "| polymarket | 2 | 0.0400 |" in md
    assert "aggregate_extremized" in md and "Weights in force" in md
