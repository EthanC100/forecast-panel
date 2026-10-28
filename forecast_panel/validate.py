"""Does extremizing the community forecast improve the Brier score on resolved geopolitical questions?

The live aggregate (forecast_panel/aggregate.py) multiplies the log-odds of the weighted mean by
``a``. Before applying that live, this module checks the rule on history: several hundred resolved
binary geopolitical questions with their community forecast at a few points in each question's life.

Data, in order of preference:

1. The Metaculus API (``METACULUS_TOKEN`` set): resolved binary questions in the geopolitics
   category with their recency-weighted community forecast history. Written to the documented v2
   endpoints (``/api/posts/`` with ``with_cp=true``); the API refuses anonymous calls, so this path
   is UNTESTED here. See README.
2. Otherwise the Autocast dataset (Zou et al. 2022, "Forecasting Future World Events with Neural
   Networks"), which ships 1,086 resolved true/false Metaculus questions and 907 Good Judgment
   Open questions (2015-2022) with their community/crowd forecast time series, tagged by topic.
   The geopolitics subset is selected by tag. Download: https://people.eecs.berkeley.edu/~hendrycks/autocast.tar.gz

Evaluation: for each question the community forecast is read at 25%, 50%, 75% of the question's
open period and at close; the Brier score of ``extremize(p, a)`` is compared across a grid of a.
To avoid picking a on the data it is judged on, a is also chosen on one half of the questions and
scored on the other half (two folds, split by question id), and a paired bootstrap over questions
gives an interval for the improvement over a = 1.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import logging
import os
import tarfile
from pathlib import Path

import numpy as np
import pandas as pd
import requests

from forecast_panel import DATA_DIR, REPORTS_DIR
from forecast_panel.aggregate import brier, extremize

log = logging.getLogger(__name__)

HTTP_TIMEOUT = 60
METACULUS_API = "https://www.metaculus.com/api"
AUTOCAST_URL = "https://people.eecs.berkeley.edu/~hendrycks/autocast.tar.gz"
FRACS = (0.25, 0.5, 0.75, 1.0)
A_GRID = (1.0, 1.25, 1.5, 1.75, 2.0, 2.5, 3.0)
GEO_TAG_WORDS = ("geopolit", "politics", "election", "armed conflict", "conflict", "ukraine", "russia",
                 "china", "military", "war", "terror", "nuclear", "diplomac", "international", "sanction",
                 "nato", "middle east", "iran", "israel", "north korea", "security", "government", "coup")

# A question record: {"id", "title", "source", "open", "close", "outcome", "crowd": [(iso timestamp, p)], "tags"}


# --------------------------------------------------------------------------
# Metaculus API (untested here: anonymous calls get HTTP 403)
# --------------------------------------------------------------------------


def _ts(x) -> str:
    """ISO timestamp from a unix number or an ISO string."""
    if isinstance(x, (int, float)):
        return dt.datetime.fromtimestamp(float(x), tz=dt.timezone.utc).isoformat()
    return str(x)


def metaculus_history(post: dict) -> list[tuple[str, float]]:
    q = post.get("question") or {}
    hist = ((q.get("aggregations") or {}).get("recency_weighted") or {}).get("history") or []
    out = []
    for h in hist:
        p = (h.get("centers") or h.get("means") or [None])[0]
        if p is None and h.get("forecast_values") and len(h["forecast_values"]) == 2:
            p = h["forecast_values"][1]
        if p is not None and h.get("start_time") is not None:
            out.append((_ts(h["start_time"]), float(p)))
    return out


def fetch_metaculus_resolved(n: int = 400, categories: str = "geopolitics", token: str | None = None) -> list[dict]:
    """Resolved binary questions with community forecast histories, via the v2 posts API.

    ``GET /api/posts/?statuses=resolved&forecast_type=binary&categories=<slug>&with_cp=true&limit=100&offset=..``
    Each result's ``question`` carries ``resolution`` ("yes"/"no"/"ambiguous"/"annulled"), ``open_time``,
    ``scheduled_close_time``/``actual_close_time`` and ``aggregations.recency_weighted.history``. When the
    list endpoint returns a thinned history, ``GET /api/posts/<id>/?with_cp=true`` returns the full one.
    """
    token = token or os.environ.get("METACULUS_TOKEN", "")
    headers = {"Authorization": f"Token {token}"}
    out, offset = [], 0
    while len(out) < n:
        resp = requests.get(f"{METACULUS_API}/posts/", headers=headers, timeout=HTTP_TIMEOUT,
                            params={"statuses": "resolved", "forecast_type": "binary", "categories": categories,
                                    "with_cp": "true", "limit": 100, "offset": offset, "order_by": "-published_at"})
        resp.raise_for_status()
        results = resp.json().get("results") or []
        if not results:
            break
        for post in results:
            q = post.get("question") or {}
            if q.get("resolution") not in ("yes", "no"):
                continue
            crowd = metaculus_history(post)
            if len(crowd) < 5:
                r2 = requests.get(f"{METACULUS_API}/posts/{post['id']}/", headers=headers,
                                  params={"with_cp": "true"}, timeout=HTTP_TIMEOUT)
                if r2.ok:
                    crowd = metaculus_history(r2.json())
            if len(crowd) < 2:
                continue
            out.append({"id": f"metaculus-{post['id']}", "title": post.get("title", ""), "source": "metaculus",
                        "open": _ts(q.get("open_time") or post.get("published_at")),
                        "close": _ts(q.get("actual_close_time") or q.get("scheduled_close_time")),
                        "outcome": 1 if q["resolution"] == "yes" else 0, "crowd": crowd,
                        "tags": [c.get("slug", "") for c in (post.get("projects") or {}).get("category", [])]})
        offset += 100
    return out[:n]


# --------------------------------------------------------------------------
# Autocast fallback
# --------------------------------------------------------------------------


def autocast_path(cache_dir: Path | None = None) -> Path:
    """The autocast_questions.json file, downloaded into ``cache_dir`` (AUTOCAST_DIR or data/cache) if absent."""
    cache_dir = Path(cache_dir or os.environ.get("AUTOCAST_DIR") or DATA_DIR / "cache" / "autocast")
    f = cache_dir / "autocast" / "autocast_questions.json"
    if f.exists():
        return f
    cache_dir.mkdir(parents=True, exist_ok=True)
    tgz = cache_dir / "autocast.tar.gz"
    log.info("downloading %s", AUTOCAST_URL)
    with requests.get(AUTOCAST_URL, stream=True, timeout=HTTP_TIMEOUT) as r:
        r.raise_for_status()
        with open(tgz, "wb") as fh:
            for chunk in r.iter_content(1 << 20):
                fh.write(chunk)
    with tarfile.open(tgz) as t:
        members = [m for m in t.getmembers() if m.name in ("autocast/autocast_questions.json", "autocast/README.md")]
        t.extractall(cache_dir, members=members, filter="data")
    return f


def is_geopolitical(tags: list[str]) -> bool:
    hay = " | ".join(t.lower() for t in tags)
    return any(w in hay for w in GEO_TAG_WORDS)


def load_autocast(path: Path | None = None, geopolitics_only: bool = True) -> list[dict]:
    path = path or autocast_path()
    with open(path) as f:
        raw = json.load(f)
    out = []
    for q in raw:
        if q.get("qtype") != "t/f" or q.get("status") != "Resolved" or q.get("answer") not in ("yes", "no"):
            continue
        tags = q.get("tags") or []
        if geopolitics_only and not is_geopolitical(tags):
            continue
        crowd = [(c["timestamp"], float(c["forecast"])) for c in q.get("crowd") or [] if c.get("forecast") is not None]
        if len(crowd) < 2:
            continue
        src = {"M": "metaculus", "G": "gjopen", "C": "cset"}.get(q["id"][0], "other")
        out.append({"id": q["id"], "title": q["question"], "source": src, "open": q["publish_time"],
                    "close": q["close_time"], "outcome": 1 if q["answer"] == "yes" else 0, "crowd": crowd, "tags": tags})
    return out


# --------------------------------------------------------------------------
# Evaluation
# --------------------------------------------------------------------------


def _t(s: str) -> float:
    return pd.Timestamp(s).tz_convert("UTC").timestamp() if pd.Timestamp(s).tzinfo else pd.Timestamp(s, tz="UTC").timestamp()


def sample_points(q: dict, fracs=FRACS) -> dict[float, float]:
    """Community forecast in force at open + frac * (close - open); frac 1.0 is the last value before close."""
    crowd = sorted((_t(ts), p) for ts, p in q["crowd"])
    t0, t1 = _t(q["open"]), _t(q["close"])
    t0 = min(t0, crowd[0][0])
    out = {}
    for f in fracs:
        at = t0 + f * (t1 - t0)
        before = [p for t, p in crowd if t <= at]
        if before:
            out[f] = before[-1]
    return out


def points_table(questions: list[dict], fracs=FRACS) -> pd.DataFrame:
    rows = []
    for q in questions:
        for f, p in sample_points(q, fracs).items():
            rows.append({"id": q["id"], "source": q["source"], "frac": f, "p": p, "y": q["outcome"]})
    return pd.DataFrame(rows)


def brier_grid(pts: pd.DataFrame, a_grid=A_GRID, lo: float = 0.01) -> pd.DataFrame:
    """Brier by (frac, a) over the sampled points."""
    rows = []
    for f, g in pts.groupby("frac"):
        for a in a_grid:
            rows.append({"frac": f, "a": a, "n": len(g), "brier": brier(extremize(g["p"].values, a, lo), g["y"].values)})
    for a in a_grid:
        rows.append({"frac": "all", "a": a, "n": len(pts), "brier": brier(extremize(pts["p"].values, a, lo), pts["y"].values)})
    return pd.DataFrame(rows)


def _fold(qid: str) -> int:
    return int(hashlib.md5(qid.encode()).hexdigest(), 16) % 2


def cross_validated(pts: pd.DataFrame, a_grid=A_GRID, lo: float = 0.01) -> dict:
    """Choose a on one half of the questions, score it on the other; both folds, pooled."""
    pts = pts.assign(fold=pts["id"].map(_fold))
    chosen, test_raw, test_ext = {}, [], []
    for k in (0, 1):
        train, test = pts[pts["fold"] != k], pts[pts["fold"] == k]
        if train.empty or test.empty:
            continue
        best = min(a_grid, key=lambda a: brier(extremize(train["p"].values, a, lo), train["y"].values))
        chosen[k] = best
        test_raw.append((test["p"].values, test["y"].values))
        test_ext.append((extremize(test["p"].values, best, lo), test["y"].values))
    raw = brier(np.concatenate([p for p, _ in test_raw]), np.concatenate([y for _, y in test_raw])) if test_raw else float("nan")
    ext = brier(np.concatenate([p for p, _ in test_ext]), np.concatenate([y for _, y in test_ext])) if test_ext else float("nan")
    return {"a_by_fold": chosen, "brier_raw": raw, "brier_extremized": ext, "n_points": len(pts), "n_questions": pts["id"].nunique()}


def bootstrap_diff(pts: pd.DataFrame, a: float, lo: float = 0.01, n_boot: int = 2000, seed: int = 0) -> tuple[float, float, float]:
    """Mean and 95% interval of Brier(extremized, a) - Brier(raw), resampling questions."""
    rng = np.random.default_rng(seed)
    ids = pts["id"].unique()
    per_q = pts.groupby("id").apply(lambda g: pd.Series({
        "raw": float(np.mean((g["p"].values - g["y"].values) ** 2)),
        "ext": float(np.mean((extremize(g["p"].values, a, lo) - g["y"].values) ** 2))}), include_groups=False)
    d = (per_q["ext"] - per_q["raw"]).values
    boots = np.array([np.mean(d[rng.integers(0, len(d), len(d))]) for _ in range(n_boot)])
    return float(np.mean(d)), float(np.percentile(boots, 2.5)), float(np.percentile(boots, 97.5))


def calibration(pts: pd.DataFrame, bins=(0, .1, .2, .3, .4, .5, .6, .7, .8, .9, 1.0001)) -> pd.DataFrame:
    """Observed frequency per forecast bin: under-confidence shows as observed frequencies more extreme than the bin."""
    b = pd.cut(pts["p"], bins=bins, right=False, labels=[f"{bins[i]:.1f}-{bins[i+1]:.1f}" for i in range(len(bins) - 1)])
    g = pts.groupby(b, observed=True)
    return pd.DataFrame({"n": g.size(), "mean forecast": g["p"].mean(), "observed": g["y"].mean()}).reset_index(names="bin")


def run(n: int = 400, out_path: Path = REPORTS_DIR / "validation.md", summary_path: Path = DATA_DIR / "validation_summary.json",
        autocast_file: Path | None = None) -> dict:
    token = os.environ.get("METACULUS_TOKEN", "").strip()
    panels: dict[str, list[dict]] = {}
    data_note = ""
    if token:
        try:
            panels["metaculus_api"] = fetch_metaculus_resolved(n)
            data_note = (f"Metaculus API: {len(panels['metaculus_api'])} resolved binary questions in the geopolitics "
                         "category, recency-weighted community forecast history.")
        except Exception as exc:  # noqa: BLE001
            log.warning("Metaculus API failed: %s", exc)
            data_note = f"Metaculus API failed ({exc}); "
    if "metaculus_api" not in panels:
        allq = load_autocast(autocast_file)
        panels["autocast_metaculus"] = [q for q in allq if q["source"] == "metaculus"]
        panels["autocast_gjopen"] = [q for q in allq if q["source"] == "gjopen"]
        data_note += ("Autocast dataset (Metaculus API refused anonymous calls): resolved true/false questions tagged "
                      "geopolitics/politics/conflict/elections, community forecast time series as shipped by Zou et al. 2022.")
    summary = {"generated": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d"), "data": data_note, "panels": {}}
    report = ["# Validation of the extremizing rule on history", "", f"_Generated {summary['generated']}._", "",
              data_note, "",
              "For every resolved question the community forecast is read at 25%, 50%, 75% of its open period and",
              "at close. Each point is extremized by multiplying its log-odds by `a` and scored by Brier against the",
              "outcome. `a = 1` is the untouched community forecast. The cross-validated row picks `a` on half of the",
              "questions (split by a hash of the question id) and scores it on the other half, both ways round.", ""]
    for name, qs in panels.items():
        pts = points_table(qs)
        if pts.empty:
            continue
        grid = brier_grid(pts)
        cv = cross_validated(pts)
        allrow = grid[grid["frac"] == "all"].set_index("a")["brier"]
        best_a = float(allrow.idxmin())
        mean_d, lo_d, hi_d = bootstrap_diff(pts, best_a)
        mean_15, lo_15, hi_15 = bootstrap_diff(pts, 1.5)
        years = sorted({str(q["close"])[:4] for q in qs})
        summary["panels"][name] = {"n_questions": len(qs), "n_points": int(len(pts)), "base_rate": float(pts.groupby("id")["y"].first().mean()),
                                   "years": [years[0], years[-1]] if years else [],
                                   "brier_by_a": {str(a): float(b) for a, b in allrow.items()}, "best_a": best_a,
                                   "diff_best_vs_raw": [mean_d, lo_d, hi_d], "diff_a1.5_vs_raw": [mean_15, lo_15, hi_15],
                                   "cross_validated": cv}
        report += [f"## {name}", "",
                   f"- questions: {len(qs)} (closing {years[0]}-{years[-1]}), base rate of Yes {summary['panels'][name]['base_rate']:.2f}, "
                   f"sampled points: {len(pts)}", "",
                   "Brier by extremizing exponent `a` (columns) and point in the question's life (rows):", "",
                   "| point | n | " + " | ".join(f"a={a:g}" for a in A_GRID) + " |", "|---|---:|" + "|".join(["---:"] * len(A_GRID)) + "|"]
        for f in list(FRACS) + ["all"]:
            g = grid[grid["frac"] == f].set_index("a")["brier"]
            n_f = int(grid[grid["frac"] == f]["n"].iloc[0])
            label = "close" if f == 1.0 else (f"{int(f*100)}% of life" if f != "all" else "all points")
            best = g.idxmin()
            cells = [f"**{g[a]:.4f}**" if a == best else f"{g[a]:.4f}" for a in A_GRID]
            report.append(f"| {label} | {n_f} | " + " | ".join(cells) + " |")
        report += ["", f"- best `a` over all points: **{best_a:g}**; Brier change vs raw: {mean_d:+.4f} "
                   f"(95% bootstrap interval over questions {lo_d:+.4f} to {hi_d:+.4f})",
                   f"- `a = 1.5`: Brier change vs raw {mean_15:+.4f} ({lo_15:+.4f} to {hi_15:+.4f})",
                   f"- cross-validated: `a` chosen per fold = {cv['a_by_fold']}; held-out Brier raw {cv['brier_raw']:.4f} "
                   f"vs extremized {cv['brier_extremized']:.4f} ({cv['brier_extremized'] - cv['brier_raw']:+.4f})", "",
                   "Calibration of the raw community forecast (observed frequency beyond the bin on both ends is",
                   "under-confidence, which is what extremizing corrects):", "",
                   "| forecast bin | n | mean forecast | observed |", "|---|---:|---:|---:|"]
        for r in calibration(pts).itertuples():
            report.append(f"| {r.bin} | {r.n} | {getattr(r, '_3'):.3f} | {r.observed:.3f} |")
        report.append("")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(report) + "\n")
    summary_path.write_text(json.dumps(summary, indent=2) + "\n")
    return summary
