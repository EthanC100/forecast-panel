#!/usr/bin/env python3
"""Daily snapshot: fetch every source for every question and append to data/panel_log.csv.

    python snapshot.py [--date YYYY-MM-DD]

Environment: METACULUS_TOKEN (Metaculus API), GOLD_EVENTS_DIR or GOLD_EVENTS_FORWARD_LOG (the
gold-events checkout or forward_log.csv path/url), GOLD_EVENTS_TOKEN (to read it from GitHub).
"""

import argparse
import logging

from forecast_panel.panel import append_log, snapshot, write_panel_report
from forecast_panel.questions import load_questions

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=None, help="snapshot date (default: today, UTC)")
    args = ap.parse_args()
    qs = load_questions()
    rows = snapshot(args.date, qs)
    append_log(rows)
    write_panel_report(rows, qs)
    print(rows[["question_id", "source", "prob", "as_of"]].to_string(index=False))
