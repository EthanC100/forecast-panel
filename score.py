#!/usr/bin/env python3
"""Monday scoring: rebuild data/aggregate_log.csv and reports/scorecard.md from data/panel_log.csv."""

import logging

from forecast_panel.panel import load_panel_log
from forecast_panel.scoring import run

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    agg = run(load_panel_log())
    print(agg.tail(len(agg.question_id.unique()) if len(agg) else 0).to_string(index=False))
