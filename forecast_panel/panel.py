"""Daily snapshot: one row per (date, question, source) appended to data/panel_log.csv."""

from __future__ import annotations

import datetime as dt
import logging

import pandas as pd

from forecast_panel import PANEL_LOG_PATH, REPORTS_DIR, SOURCES
from forecast_panel import sources as src
from forecast_panel.questions import load_questions, load_source_map, source_map_date

log = logging.getLogger(__name__)

LOG_COLUMNS = ["date", "question_id", "source", "prob", "as_of", "ref", "notes"]


def today() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d")


def snapshot(date: str | None = None, questions: list[dict] | None = None,
             source_map: dict | None = None) -> pd.DataFrame:
    date = date or today()
    questions = questions or load_questions()
    source_map = source_map if source_map is not None else load_source_map()
    try:
        archive = src.swift_archive()
    except Exception as exc:  # noqa: BLE001
        log.warning("Swift Centre archive: %s", exc)
        archive = []
    fwd, fwd_why = src.load_forward_log()
    reviewed = source_map_date()

    rows = []
    for q in questions:
        qid = q["id"]
        m = source_map.get(qid) or {}
        readings = {
            "polymarket": src.polymarket(q),
            "metaculus": src.metaculus(q, m.get("metaculus")),
            "swift_centre": src.swift_centre(m.get("swift_centre"), m.get("swift_centre_note", ""),
                                             m.get("swift_keywords"), archive, since=reviewed),
            "gjopen": src.gjopen(m.get("gjopen"), m.get("gjopen_note", "")),
            "my_prob": src.human_column(fwd, fwd_why, f"my_prob_{qid}", date),
            "claude_prob": src.human_column(fwd, fwd_why, f"claude_prob_{qid}", date),
        }
        for s in SOURCES:
            r = readings[s]
            rows.append({"date": date, "question_id": qid, "source": s, "prob": r.prob,
                         "as_of": r.as_of or date, "ref": r.ref, "notes": r.note()})
    return pd.DataFrame(rows, columns=LOG_COLUMNS)


def load_panel_log(path=PANEL_LOG_PATH) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame(columns=LOG_COLUMNS)
    df = pd.read_csv(path, dtype={"date": str, "question_id": str, "source": str, "as_of": str,
                                  "ref": str, "notes": str})
    df["prob"] = pd.to_numeric(df["prob"], errors="coerce")
    return df


def append_log(rows: pd.DataFrame, path=PANEL_LOG_PATH) -> pd.DataFrame:
    """Add the rows, replacing any earlier rows for the same (date, question, source)."""
    old = load_panel_log(path)
    key = ["date", "question_id", "source"]
    if not old.empty:
        drop = old.set_index(key).index.isin(rows.set_index(key).index)
        old = old[~drop]
    out = pd.concat([old, rows], ignore_index=True)
    out = out.sort_values(["date", "question_id", "source"], kind="stable")
    out.to_csv(path, index=False, float_format="%.4f")
    return out


def panel_table(rows: pd.DataFrame) -> pd.DataFrame:
    """questions x sources probabilities for one snapshot."""
    t = rows.pivot(index="question_id", columns="source", values="prob")
    return t.reindex(columns=[s for s in SOURCES if s in t.columns])


def write_panel_report(rows: pd.DataFrame, questions: list[dict], path=REPORTS_DIR / "panel_latest.md") -> None:
    date = rows["date"].iloc[0]
    titles = {q["id"]: q["question"] for q in questions}
    t = panel_table(rows)
    lines = [f"# Panel snapshot {date}", "",
             "Probability of each question as worded, by source. Blank = no value (see notes).", "",
             "| id | question | " + " | ".join(t.columns) + " |",
             "|---|---|" + "|".join(["---:"] * len(t.columns)) + "|"]
    for qid in t.index:
        vals = ["" if pd.isna(v) else f"{v:.3f}" for v in t.loc[qid]]
        lines.append(f"| {qid} | {titles.get(qid, '')} | " + " | ".join(vals) + " |")
    lines += ["", "## Notes", ""]
    for r in rows.itertuples():
        if r.notes:
            lines.append(f"- **{r.question_id} / {r.source}** ({r.as_of}): {r.notes}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n")
