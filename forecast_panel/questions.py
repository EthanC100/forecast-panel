"""The fixed question list (copied from EthanC100/gold-events) and the per-source mapping."""

from __future__ import annotations

from pathlib import Path

import yaml

from forecast_panel import METHOD_PATH, QUESTIONS_PATH, SOURCE_MAP_PATH


def load_questions(path: Path = QUESTIONS_PATH) -> list[dict]:
    with open(path) as f:
        qs = yaml.safe_load(f)["questions"]
    ids = [q["id"] for q in qs]
    if len(set(ids)) != len(ids):
        raise ValueError(f"duplicate question ids in {path}")
    return qs


def load_source_map(path: Path = SOURCE_MAP_PATH) -> dict[str, dict]:
    with open(path) as f:
        return yaml.safe_load(f)["questions"] or {}


def source_map_date(path: Path = SOURCE_MAP_PATH) -> str:
    """The day the source mapping was last reviewed (``matched_on``); newer posts get flagged."""
    with open(path) as f:
        return str(yaml.safe_load(f).get("matched_on") or "2026-01-01")[:10]


def load_method(path: Path = METHOD_PATH) -> dict:
    with open(path) as f:
        return yaml.safe_load(f)


def resolved_outcomes(questions: list[dict]) -> dict[str, int]:
    """id -> 0/1 outcome for questions marked resolved with a numeric outcome."""
    out = {}
    for q in questions:
        if q.get("resolved") and q.get("outcome") in (0, 1):
            out[q["id"]] = int(q["outcome"])
    return out


def resolution_dates(questions: list[dict]) -> dict[str, str]:
    """id -> ISO date from which a question counts as known.

    ``resolved_on`` (optional, the day the outcome became known) wins over ``resolution_date``
    (the question's deadline). Snapshots on or after this date are not scored.
    """
    out = {}
    for q in questions:
        d = q.get("resolved_on") or q.get("resolution_date")
        if d is not None:
            out[q["id"]] = str(d)[:10]
    return out
