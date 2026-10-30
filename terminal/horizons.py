"""Horizons' view: a weekly lean on each country's bond and currency, and on gold, written by the
brief's judgement step and checked with the brief's rules.

    views.json  data/terminal/horizons/views.json
                views     the latest view per region and asset
                history   every view issued (one per region and asset per week: a later view in the
                          same week replaces the earlier one), resolved once its horizon has passed

A view leans long, short or not at all, with p = the probability that the instrument moves the
leaned way by the horizon end (5% steps, at least 50). It is scored like any forecaster on the
question "does a long position gain?": p_long = p when leaning long, 1 - p when leaning short.
Calls I make on the same question (hz:<REGION>.<asset>.<view date>) resolve by the same rule.
"""

from __future__ import annotations

import datetime as dt
import json
import logging
import math
from pathlib import Path

from terminal import store

log = logging.getLogger(__name__)

PATH = store.DATA / "horizons" / "views.json"
LABEL = "Horizons' view, not financial advice"
GRID = list(range(0, 101, 5))
LOG_CLIP = 0.01
MIN_GROUP = 10
MIN_OVERALL = 100

# region -> asset -> (instrument code, plain name, what "long" means)
ASSETS = {
    "BR": {"bond": ("BR10Y", "Brazil 10-year government bond (longest fixed-rate Tesouro bond)",
                    "Long the bond = Brazil's 10-year yield falls (bond prices rise)."),
           "currency": ("USDBRL", "Brazilian real (USD/BRL)", "Long the currency = the real strengthens: USD/BRL falls.")},
    "MX": {"bond": ("MX10Y", "Mexico 10-year government bond (M bono)",
                    "Long the bond = Mexico's 10-year yield falls (bond prices rise). The 10-year auction yield updates every few weeks."),
           "currency": ("USDMXN", "Mexican peso (USD/MXN)", "Long the currency = the peso strengthens: USD/MXN falls.")},
    "FR": {"bond": ("OATBUND", "France 10-year OAT against the German Bund (spread)",
                    "Long the bond = French 10-year bonds beat German ones: the OAT-Bund spread narrows. The spread is used rather "
                    "than the OAT yield because it isolates French risk from moves in euro-area rates as a whole."),
           "currency": ("EURUSD", "Euro (EUR/USD)", "Long the currency = the euro strengthens: EUR/USD rises.")},
    "GOLD": {"gold": ("XAUUSD", "Gold (US dollars per troy ounce)", "Long gold = the gold price rises.")},
}
REGIONS = list(ASSETS)
LONG_IS_UP = {"BR10Y": False, "MX10Y": False, "OATBUND": False, "USDBRL": False, "USDMXN": False, "EURUSD": True, "XAUUSD": True}
FALLBACK_SERIES = {"XAUUSD": ["gl.gold"]}


def _read(path: Path, default=None):
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return default


def series_for(code: str) -> list[str]:
    try:
        from terminal.book import load_config
        ins = (load_config().get("instruments") or {}).get(code) or {}
        ids = list(ins.get("series") or [])
    except Exception:  # noqa: BLE001
        ids = []
    return ids + [s for s in FALLBACK_SERIES.get(code, []) if s not in ids]


def _obs(code: str) -> tuple[str | None, list[tuple[str, float]]]:
    for sid in series_for(code):
        s = store.load_series(sid)
        hist = [(r[0], r[1]) for r in (s or {}).get("history", []) if isinstance(r[1], (int, float))]
        if hist:
            return sid, sorted(hist)
    return None, []


def value_on(code: str, date: str) -> tuple[str | None, str | None, float | None]:
    """(series id, observation date, value): the last observation on or before ``date``."""
    sid, hist = _obs(code)
    prior = [x for x in hist if x[0] <= date]
    return (sid, prior[-1][0], prior[-1][1]) if prior else (sid, None, None)


def qid(region: str, asset: str, date: str) -> str:
    return f"hz:{region}.{asset}.{date}"


def instruments(date: str) -> dict:
    """What the model is told about each region's instruments: name, meaning, current level."""
    out = {}
    for r, assets in ASSETS.items():
        out[r] = {}
        for a, (code, name, meaning) in assets.items():
            sid, d, v = value_on(code, date)
            out[r][a] = {"instrument": code, "name": name, "meaning": meaning, "series": sid, "level": v, "level_date": d,
                         "long_is_up": LONG_IS_UP[code]}
    return out


# --------------------------------------------------------------------------
# Validation (the brief's rules plus the view's own)
# --------------------------------------------------------------------------

def validate_view(v: dict, region: str, index: dict, all_values: set[float], episode_ids: set[str], check_text) -> list[str]:
    probs = []
    asset = v.get("asset")
    if asset not in ASSETS.get(region, {}):
        return [f"asset {asset!r} is not one of {sorted(ASSETS.get(region, {}))}"]
    lean, p = v.get("lean"), v.get("p")
    if lean not in ("long", "short", "none"):
        probs.append(f"lean {lean!r} is not long, short or none")
    if lean == "none":
        if p is not None:
            probs.append("no view, so p must be empty")
    elif p not in GRID or p < 50:
        probs.append(f"p {p} must be on the 5% grid and at least 50 (the probability the leaned way wins)")
    hw = v.get("horizon_weeks")
    if not isinstance(hw, int) or not 4 <= hw <= 13:
        probs.append(f"horizon of {hw} weeks is outside 4-13")
    if v.get("confidence") not in ("low", "medium", "high"):
        probs.append(f"confidence {v.get('confidence')!r}")
    if len(v.get("reasons") or []) > 3:
        probs.append(f"{len(v['reasons'])} reasons (at most 3)")
    ids = [i for r in v.get("reasons") or [] for i in r.get("source_ids", [])] + list(v.get("source_ids") or [])
    probs += [f"unknown source id {i}" for i in ids if i not in index]
    ep = ((v.get("resembles") or {}).get("episode_id") or "").strip()
    if ep and ep not in episode_ids:
        probs.append(f"unknown episode {ep}")
    vals = all_values | ({float(p)} if isinstance(p, (int, float)) else set()) | ({float(hw)} if isinstance(hw, int) else set())
    texts = [r.get("text", "") for r in v.get("reasons") or []] + [v.get("main_risk", ""), v.get("would_change", ""),
                                                                   (v.get("resembles") or {}).get("why", "")]
    for t in texts:
        probs += check_text(t, vals)
    return probs


def finish_view(v: dict, region: str, date: str) -> dict:
    """Attach the instrument, entry level, horizon end and question id to a validated view."""
    code, name, meaning = ASSETS[region][v["asset"]]
    sid, d, val = value_on(code, date)
    hw = v.get("horizon_weeks") if isinstance(v.get("horizon_weeks"), int) else 8
    end = (dt.date.fromisoformat(date) + dt.timedelta(weeks=hw)).isoformat()
    p = v.get("p")
    p_long = None if v.get("lean") == "none" or p is None else (p / 100 if v["lean"] == "long" else 1 - p / 100)
    q = qid(region, v["asset"], date)
    word = {"long": "long", "short": "short"}.get(v.get("lean"))
    return {**v, "region": region, "date": date, "instrument": code, "name": name, "meaning": meaning, "series": sid,
            "entry_date": d, "entry_value": val, "horizon_end": end, "p_long": None if p_long is None else round(p_long, 2),
            "question_id": q, "question": f"Will a long position in the {name} gain between {date} and {end}?",
            "summary": f"Lean {word} {name}, {p}% that it wins by {end}" if word else f"No view on the {name}"}


# --------------------------------------------------------------------------
# Writing, resolving, scoring
# --------------------------------------------------------------------------

def load() -> dict:
    return _read(PATH, {"label": LABEL, "views": {}, "history": []})


def record(date: str, views: dict[str, dict[str, dict]], verified: bool | None) -> dict:
    """Store this run's views (region -> asset -> finished view). Regions not in ``views`` keep their
    latest view. A view replaces one for the same region and asset issued less than 7 days earlier."""
    st = load()
    cur = st.get("views") or {}
    hist = st.get("history") or []
    for r, assets in views.items():
        for a, v in assets.items():
            cur.setdefault(r, {})[a] = v
            if v.get("ok") is False:
                continue
            hist = [h for h in hist if not (h["region"] == r and h["asset"] == a and not h.get("resolved")
                                             and 0 <= (dt.date.fromisoformat(date) - dt.date.fromisoformat(h["date"])).days < 7)]
            hist.append({k: v.get(k) for k in ("question_id", "date", "region", "asset", "instrument", "series", "lean", "p", "p_long",
                                                "confidence", "horizon_weeks", "horizon_end", "entry_date", "entry_value", "summary")})
    st.update({"date": date, "generated_at": store.now_iso(), "verified": verified, "label": LABEL, "views": cur,
               "history": sorted(hist, key=lambda h: (h["date"], h["region"], h["asset"]))})
    resolve(st)
    PATH.parent.mkdir(parents=True, exist_ok=True)
    PATH.write_text(json.dumps(st, ensure_ascii=False, indent=1) + "\n")
    return st


def outcome(h: dict, today: str | None = None) -> dict | None:
    """Resolve one view (or an hz: question): did a long position gain by the horizon end?"""
    today = today or store.today()
    if not h.get("entry_value") and h.get("entry_value") != 0 or h["horizon_end"] >= today:
        return None
    sid, hist = _obs(h["instrument"])
    if not hist or hist[-1][0] < h["horizon_end"] and (dt.date.fromisoformat(h["horizon_end"]) - dt.date.fromisoformat(hist[-1][0])).days > 10:
        return None                      # the series has not caught up with the horizon yet
    prior = [x for x in hist if x[0] <= h["horizon_end"]]
    if not prior:
        return None
    d, v = prior[-1]
    up = v > h["entry_value"]
    gained = int(v != h["entry_value"] and up == LONG_IS_UP[h["instrument"]])
    return {"outcome": gained, "exit_date": d, "exit_value": v, "series": sid}


def _log(p: float, y: int) -> float:
    p = min(max(p, LOG_CLIP), 1 - LOG_CLIP)
    return math.log(p if y == 1 else 1 - p)


def resolve(st: dict, today: str | None = None) -> dict:
    for h in st.get("history", []):
        if h.get("resolved"):
            continue
        o = outcome(h, today)
        if not o:
            continue
        h.update({"resolved": True, **o})
        if h.get("p_long") is not None:
            h["brier"] = round((h["p_long"] - o["outcome"]) ** 2, 4)
            h["log"] = round(_log(h["p_long"], o["outcome"]), 4)
            h["hit"] = int((h["lean"] == "long") == bool(o["outcome"]))
    return st


def hz_outcome(question_id: str) -> dict | None:
    """Resolution of an hz: question, from the view it refers to."""
    st = load()
    h = next((x for x in st.get("history", []) if x.get("question_id") == question_id), None)
    if not h:
        return None
    o = h if h.get("resolved") else outcome(h)
    if not o or o.get("outcome") is None:
        return None
    return {"outcome": int(o["outcome"]), "source": f"{h['instrument']} {h['entry_value']} on {h['entry_date']} vs "
                                                    f"{o['exit_value']} on {o['exit_date']} ({h.get('series')})", "date": h["horizon_end"]}


def _block(rows: list[dict]) -> dict:
    n = len(rows)
    out = {"n": n, "insufficient": n < MIN_GROUP}
    if rows:
        out.update({"brier": round(sum(r["brier"] for r in rows) / n, 4), "log": round(sum(r["log"] for r in rows) / n, 4),
                    "hit_rate_pct": round(100 * sum(r["hit"] for r in rows) / n, 1)})
    return out


def score(questions: list[dict] | None = None) -> dict:
    """The track-record block: Horizons scored like any forecaster, and against my calls on hz: questions."""
    st = resolve(load())
    hist = st.get("history", [])
    scored = [h for h in hist if h.get("resolved") and h.get("p_long") is not None]
    out = {"label": LABEL, "n_views": len(hist), "n_open": sum(1 for h in hist if not h.get("resolved")),
           "n_no_view": sum(1 for h in hist if h.get("lean") == "none"), "n_resolved": len(scored),
           "noisy": len(scored) < MIN_OVERALL, "min_group": MIN_GROUP, "min_overall": MIN_OVERALL, "overall": _block(scored),
           "by_region": [{"group": r, **_block([h for h in scored if h["region"] == r])} for r in REGIONS],
           "by_asset": [{"group": a, **_block([h for h in scored if h["asset"] == a])} for a in ("bond", "currency", "gold")],
           "definition": "p_long = the view's probability that a long position gains by the horizon end; Brier and log "
                         "scores as for my calls; hit = the lean pointed the right way."}
    by_q = {h["question_id"]: h for h in scored}
    pairs = []
    for q in questions or []:
        h = by_q.get(q.get("question_id") or "")
        if h and q.get("resolution") and q.get("forecasts"):
            me = q["forecasts"][-1]["prob"]
            y = int(q["resolution"]["outcome"])
            pairs.append({"question_id": h["question_id"], "me": me, "horizons": h["p_long"], "y": y})
    vs = {"n": len(pairs), "insufficient": len(pairs) < MIN_GROUP}
    if pairs:
        for who in ("me", "horizons"):
            vs[who] = {"n": len(pairs), "brier": round(sum((p[who] - p["y"]) ** 2 for p in pairs) / len(pairs), 4),
                       "log": round(sum(_log(p[who], p["y"]) for p in pairs) / len(pairs), 4)}
    out["vs_me"] = vs
    out["items"] = hist[-200:]
    return out
