#!/usr/bin/env python3
"""Validate the extremizing rule on resolved historical questions -> reports/validation.md.

    python validate.py [--n 400] [--autocast path/to/autocast_questions.json]

Uses the Metaculus API when METACULUS_TOKEN is set, otherwise the Autocast dataset (downloaded
into data/cache/ or AUTOCAST_DIR when absent).
"""

import argparse
import logging
from pathlib import Path

from forecast_panel.validate import run

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=400, help="questions to pull from the Metaculus API")
    ap.add_argument("--autocast", type=Path, default=None, help="path to autocast_questions.json")
    args = ap.parse_args()
    s = run(n=args.n, autocast_file=args.autocast)
    for name, p in s["panels"].items():
        print(name, p["n_questions"], "questions; best a", p["best_a"], "; Brier by a", p["brier_by_a"])
