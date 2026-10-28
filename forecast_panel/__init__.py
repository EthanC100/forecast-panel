"""forecast-panel: public forecasts on a fixed set of geopolitical questions, logged daily and scored."""

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
REPORTS_DIR = ROOT / "reports"

QUESTIONS_PATH = DATA_DIR / "tension_questions.yaml"
SOURCE_MAP_PATH = DATA_DIR / "source_map.yaml"
METHOD_PATH = DATA_DIR / "method.yaml"
PANEL_LOG_PATH = DATA_DIR / "panel_log.csv"
AGGREGATE_LOG_PATH = DATA_DIR / "aggregate_log.csv"

# Order of the sources in every table. The two human columns come from gold-events.
SOURCES = ["polymarket", "metaculus", "swift_centre", "gjopen", "my_prob", "claude_prob"]
AGGREGATES = ["aggregate_plain", "aggregate_extremized"]
