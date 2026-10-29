"""Normalised storage for the terminal.

Layout (all under data/terminal/):

series/<id>.json   one file per series: metadata + full history, never truncated.
status.json        one entry per source: last attempt, last success, error, series written.
calendar.json      catalyst calendar (built by terminal.calendar).
attention.json     GDELT attention history per query (built by terminal.calendar).
summary.json       what the site reads first (built by terminal.summary).
inputs/*.yaml      hand-edited tables: events, fiscal gap, evidence badges, ratings fallback.

Series file format
------------------
{
  "id": "br.usdbrl.ptax", "name": ..., "country": "BR", "unit": ..., "frequency": "daily",
  "source": "BCB SGS", "source_id": "SGS 1", "source_url": ...,
  "fields": ["value"]                     # names of the columns after the key
  "key": ["date"]                         # or ["date", "ref"] for survey tables
  "fetched_at": ISO time of the last successful fetch,
  "updated_at": ISO time the history last changed,
  "first": ..., "last": ..., "n": ...,
  "history": [[date, value], ...]         # one observation per line in the file
}

History is merged, never replaced: a fetch adds new keys and overwrites values for keys it
returns; keys it does not return are kept. That is the "do not delete any data" rule.
"""

from __future__ import annotations

import datetime as dt
import json
import math
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data" / "terminal"
SERIES_DIR = DATA / "series"
INPUTS = DATA / "inputs"
STATUS_PATH = DATA / "status.json"


def now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def today() -> str:
    return dt.date.today().isoformat()


def _clean(v):
    if v is None:
        return None
    if isinstance(v, float):
        if math.isnan(v) or math.isinf(v):
            return None
        return round(v, 6)
    return v


def series_path(sid: str) -> Path:
    return SERIES_DIR / f"{sid}.json"


def load_series(sid: str) -> dict | None:
    p = series_path(sid)
    if not p.exists():
        return None
    return json.loads(p.read_text())


def last_key(sid: str) -> str | None:
    s = load_series(sid)
    return s["last"] if s and s.get("history") else None


def _dump(meta: dict, history: list[list]) -> str:
    head = {k: v for k, v in meta.items() if k != "history"}
    body = json.dumps(head, ensure_ascii=False, indent=1)[:-2]  # drop the closing "\n}"
    lines = ",\n".join("  " + json.dumps(r, ensure_ascii=False, separators=(",", ":")) for r in history)
    return body + ',\n "history": [\n' + lines + "\n ]\n}\n"


def save_series(meta: dict, rows: list, key_len: int = 1) -> dict:
    """Merge ``rows`` into the stored history of ``meta['id']`` and write the file.

    ``rows`` are sequences whose first ``key_len`` items are the key (date, or date + ref).
    Values for keys already stored are overwritten; other stored keys are kept.
    """
    sid = meta["id"]
    old = load_series(sid) or {}
    merged: dict[tuple, list] = {}
    for r in old.get("history", []):
        merged[tuple(r[:key_len])] = list(r)
    changed = False
    for r in rows:
        r = [_clean(x) for x in r]
        if any(x is None for x in r[:key_len]):
            continue
        if all(x is None for x in r[key_len:]):
            continue
        k = tuple(r[:key_len])
        if merged.get(k) != r:
            merged[k] = r
            changed = True
    history = [merged[k] for k in sorted(merged)]
    now = now_iso()
    out = {**{k: v for k, v in old.items() if k != "history"}, **meta}
    out["key"] = meta.get("key") or (["date"] if key_len == 1 else ["date", "ref"])
    out.setdefault("fields", ["value"])
    out["fetched_at"] = now
    out["updated_at"] = now if (changed or not old) else old.get("updated_at", now)
    out["n"] = len(history)
    out["first"] = history[0][0] if history else None
    out["last"] = history[-1][0] if history else None
    SERIES_DIR.mkdir(parents=True, exist_ok=True)
    series_path(sid).write_text(_dump(out, history))
    out["history"] = history
    return out


# --------------------------------------------------------------------------
# Status
# --------------------------------------------------------------------------


def load_status() -> dict:
    if STATUS_PATH.exists():
        return json.loads(STATUS_PATH.read_text())
    return {"sources": {}}


def save_status(status: dict) -> None:
    status["updated_at"] = now_iso()
    STATUS_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATUS_PATH.write_text(json.dumps(status, ensure_ascii=False, indent=1, sort_keys=True) + "\n")


def secret(name: str) -> str | None:
    v = os.environ.get(name, "").strip()
    return v or None
