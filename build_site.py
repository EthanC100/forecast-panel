#!/usr/bin/env python3
"""Build site/data.js for the dashboard. Set GOLD_EVENTS_DIR / TENSION_INDEX_DIR / EM_MACRO_DIR to read
local checkouts instead of GitHub."""

import logging

from forecast_panel.site_build import OUT_PATH, build

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    d = build()
    print(f"wrote {OUT_PATH} ({OUT_PATH.stat().st_size // 1024} KB); notes: {d['notes']}")
    for q in d["questions"]:
        print(q["id"], len(q["market_history"]), "market points;", {k: v["prob"] for k, v in q["latest"].items()})
    for k, c in d["countries"].items():
        print(k, len(c["yield"].get("series", [])), "yield pts", len(c["spread"].get("series", [])), "spread pts", len(c["fx"].get("series", [])), "fx pts", c["risk_model"]["status"])
