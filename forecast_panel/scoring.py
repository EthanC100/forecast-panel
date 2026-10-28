"""Monday scoring: the aggregate log and the scorecard.

Every Monday the run takes the Monday snapshot of each week (so each forecaster is compared on
the same day), scores every source on the questions that have resolved, re-derives the
inverse-Brier weights, and rebuilds:

* data/aggregate_log.csv   the plain and extremized aggregate for every snapshot day, computed
                           with the weights that were in force that day (only questions already
                           resolved by that day feed the weights, so the aggregate is scored
                           honestly out of sample);
* reports/scorecard.md     Brier of every source and of the aggregates on resolved questions,
                           plus head-to-head Brier against Polymarket on the same days.
"""

from __future__ import annotations

import datetime as dt
import json
import math

import numpy as np
import pandas as pd

from forecast_panel import AGGREGATE_LOG_PATH, AGGREGATES, REPORTS_DIR, SOURCES
from forecast_panel.aggregate import aggregate, brier, weights
from forecast_panel.questions import load_method, load_questions, resolution_dates, resolved_outcomes


def _weekday(date: str) -> int:
    return dt.date.fromisoformat(date).weekday()


def _iso_week(date: str) -> str:
    y, w, _ = dt.date.fromisoformat(date).isocalendar()
    return f"{y}-W{w:02d}"


def monday_snapshots(panel: pd.DataFrame) -> pd.DataFrame:
    """The rows of each ISO week's Monday; when a week has no Monday snapshot (a missed run), its
    earliest snapshot stands in and ``scoring_day`` says so."""
    if panel.empty:
        return panel.assign(week=[], scoring_day=[])
    p = panel.copy()
    p["week"] = p["date"].map(_iso_week)
    picks = {}
    for week, g in p.groupby("week"):
        dates = sorted(g["date"].unique())
        mondays = [d for d in dates if _weekday(d) == 0]
        picks[week] = (mondays[0], "monday") if mondays else (dates[0], f"no Monday snapshot, {dates[0]} used")
    p = p[[d == picks[w][0] for d, w in zip(p["date"], p["week"])]].copy()
    p["scoring_day"] = p["week"].map(lambda w: picks[w][1])
    return p


def scorable(rows: pd.DataFrame, outcomes: dict[str, int], res_dates: dict[str, str],
             known_by: str | None = None) -> pd.DataFrame:
    """Rows on resolved questions, taken strictly before the question's resolution date (and, when
    ``known_by`` is given, only questions whose resolution date is on or before it)."""
    if rows.empty:
        return rows.assign(outcome=[])
    keep = []
    for r in rows.itertuples():
        rd = res_dates.get(r.question_id)
        ok = (r.question_id in outcomes and rd is not None and r.date < rd
              and (known_by is None or rd <= known_by))
        keep.append(ok)
    out = rows[keep].copy()
    out["outcome"] = out["question_id"].map(outcomes)
    return out


def track_record(scored: pd.DataFrame, names: list[str], column: str = "source") -> dict[str, float]:
    """Brier per forecaster over the scorable Monday rows (NaN with no rows)."""
    out = {}
    for s in names:
        g = scored[(scored[column] == s) & scored["prob"].notna()]
        out[s] = brier(g["prob"], g["outcome"]) if len(g) else float("nan")
    return out


def build_aggregate_log(panel: pd.DataFrame, questions: list[dict] | None = None,
                        method: dict | None = None) -> pd.DataFrame:
    questions = questions or load_questions()
    method = method or load_method()
    outcomes, res_dates = resolved_outcomes(questions), resolution_dates(questions)
    mondays = monday_snapshots(panel)
    rows = []
    for date, day in panel.groupby("date"):
        known = scorable(mondays[mondays["date"] < date], outcomes, res_dates, known_by=date)
        w = weights(track_record(known, SOURCES), method["brier_floor"], method["unscored_brier"])
        for qid, g in day.groupby("question_id"):
            probs = dict(zip(g["source"], g["prob"]))
            plain, ext, used = aggregate(probs, w, method["extremizing_a"], method["clip"], method["min_sources"])
            rows.append({"date": date, "question_id": qid, "aggregate_plain": plain,
                         "aggregate_extremized": ext, "n_sources": len(used),
                         "weights": json.dumps({k: round(v, 4) for k, v in used.items()}),
                         "extremizing_a": method["extremizing_a"]})
    cols = ["date", "question_id", "aggregate_plain", "aggregate_extremized", "n_sources", "weights", "extremizing_a"]
    return pd.DataFrame(rows, columns=cols)


def long_aggregates(agg: pd.DataFrame) -> pd.DataFrame:
    """aggregate_log in the panel_log shape (date, question_id, source, prob)."""
    parts = [agg[["date", "question_id", a]].rename(columns={a: "prob"}).assign(source=a) for a in AGGREGATES]
    return pd.concat(parts, ignore_index=True) if parts else pd.DataFrame(columns=["date", "question_id", "source", "prob"])


def head_to_head(scored: pd.DataFrame, s: str, ref: str = "polymarket") -> tuple[float, float, int]:
    """(Brier of s, Brier of ref, n) on the (date, question) pairs where both have a value."""
    a = scored[(scored["source"] == s) & scored["prob"].notna()][["date", "question_id", "prob", "outcome"]]
    b = scored[(scored["source"] == ref) & scored["prob"].notna()][["date", "question_id", "prob"]]
    m = a.merge(b, on=["date", "question_id"], suffixes=("", "_ref"))
    if m.empty:
        return float("nan"), float("nan"), 0
    return brier(m["prob"], m["outcome"]), brier(m["prob_ref"], m["outcome"]), len(m)


def _fmt(x) -> str:
    return "" if x is None or (isinstance(x, float) and math.isnan(x)) else f"{x:.4f}"


def scorecard(panel: pd.DataFrame, agg: pd.DataFrame, questions: list[dict] | None = None,
              method: dict | None = None, generated: str | None = None) -> str:
    questions = questions or load_questions()
    method = method or load_method()
    outcomes, res_dates = resolved_outcomes(questions), resolution_dates(questions)
    titles = {q["id"]: q["question"] for q in questions}
    names = SOURCES + AGGREGATES
    both = pd.concat([panel[["date", "question_id", "source", "prob"]], long_aggregates(agg)], ignore_index=True)
    mondays = monday_snapshots(both)
    scored = scorable(mondays, outcomes, res_dates)
    generated = generated or dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d")
    weeks = sorted(mondays["date"].unique()) if not mondays.empty else []

    L = [f"# Scorecard (regenerated {generated})", "",
         "Brier score (mean squared error, lower is better; 0.25 is a flat 50%) of every source and of the",
         "track-record-weighted aggregate on the questions that have resolved. Each forecaster is scored on",
         "the Monday snapshot of every week before the question's resolution date, so all of them are",
         "compared on the same days. See reports/method.md for the aggregation rule.", "",
         f"- Weekly scoring snapshots logged: {len(weeks)}" + (f" ({weeks[0]} to {weeks[-1]})" if weeks else "")
         + ("" if mondays.empty or (mondays["scoring_day"] == "monday").all()
            else " (weeks without a Monday snapshot use their first day: "
            + ", ".join(sorted(set(mondays.loc[mondays["scoring_day"] != "monday", "date"]))) + ")"),
         f"- Questions resolved: {len(outcomes)} of {len(questions)}", ""]
    if len(outcomes):
        L += ["## Resolved questions", "", "| id | question | outcome | resolution date |", "|---|---|---:|---|"]
        for qid, y in outcomes.items():
            L.append(f"| {qid} | {titles[qid]} | {y} | {res_dates.get(qid, '')} |")
        L.append("")

    L += ["## Brier by forecaster", "",
          "`n` counts scored (Monday, question) pairs. The head-to-head columns re-score the forecaster and",
          "Polymarket on the pairs where both have a value, so a thinly covered source is not flattered or",
          "punished by the questions it skipped.", "",
          "| forecaster | n | Brier | n (vs Polymarket) | Brier | Polymarket Brier |",
          "|---|---:|---:|---:|---:|---:|"]
    for s in names:
        g = scored[(scored["source"] == s) & scored["prob"].notna()]
        b = brier(g["prob"], g["outcome"]) if len(g) else float("nan")
        hb, pb, n = head_to_head(scored, s)
        L.append(f"| {s} | {len(g)} | {_fmt(b)} | {n} | {_fmt(hb)} | {_fmt(pb)} |")
    L.append("")

    if len(outcomes):
        L += ["## Brier by question", "", "| id | " + " | ".join(names) + " |", "|---|" + "|".join(["---:"] * len(names)) + "|"]
        for qid in outcomes:
            cells = []
            for s in names:
                g = scored[(scored["source"] == s) & (scored["question_id"] == qid) & scored["prob"].notna()]
                cells.append(_fmt(brier(g["prob"], g["outcome"])) if len(g) else "")
            L.append(f"| {qid} | " + " | ".join(cells) + " |")
        L.append("")

    # Weights now in force (what the next aggregate would use).
    track = track_record(scorable(mondays, outcomes, res_dates), SOURCES)
    w = weights(track, method["brier_floor"], method["unscored_brier"])
    tot = sum(w.values())
    L += ["## Weights in force", "",
          f"Inverse Brier over resolved questions, floored at {method['brier_floor']}; a source with no resolved",
          f"track record is weighted as if its Brier were {method['unscored_brier']} (equal weights until anything",
          f"resolves). Extremizing exponent a = {method['extremizing_a']}. Weights are renormalised over the sources",
          "that have a value on the day.", "",
          "| source | track-record Brier | weight (normalised over all six) |", "|---|---:|---:|"]
    for s in SOURCES:
        L.append(f"| {s} | {_fmt(track[s])} | {w[s] / tot:.3f} |")
    L.append("")

    if not agg.empty:
        last = agg[agg["date"] == agg["date"].max()]
        L += [f"## Latest aggregate ({last['date'].iloc[0]})", "",
              "| id | question | plain | extremized | sources | weights used |", "|---|---|---:|---:|---:|---|"]
        for r in last.itertuples():
            L.append(f"| {r.question_id} | {titles.get(r.question_id, '')} | {_fmt(r.aggregate_plain)} | "
                     f"{_fmt(r.aggregate_extremized)} | {r.n_sources} | `{r.weights}` |")
        L.append("")
    return "\n".join(L) + "\n"


def run(panel: pd.DataFrame, questions: list[dict] | None = None, method: dict | None = None,
        agg_path=AGGREGATE_LOG_PATH, report_path=REPORTS_DIR / "scorecard.md") -> pd.DataFrame:
    questions = questions or load_questions()
    method = method or load_method()
    agg = build_aggregate_log(panel, questions, method)
    agg.to_csv(agg_path, index=False, float_format="%.4f")
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(scorecard(panel, agg, questions, method))
    return agg
