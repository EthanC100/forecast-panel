"""AI brief (Phase 4): a daily snapshot, a cheap extraction of what changed, a weekly judgement,
and a validator that refuses to trust either without checking.

    snapshot    data/terminal/brief/snapshot.json   every item has an id the model must cite:
                s:<series>      latest data point, previous observation, one-week change
                ev:<event>      calendar events in the next 90 days
                sc:<scenario>   scenario pages (base rate, branches, signposts, moves, markets),
                                without your own probabilities
                pm:/ks:<id>     prediction-market odds
                cot:<series>    CFTC positioning      disp:<n>   survey dispersion
                h:<hash>        headlines (GDELT and official press pages), each with its URL
                em:<n>          em-macro findings     badge:<g>  evidence badges
                primer:<cc>     country primers
    extraction  daily, cheapest model: what changed since the last brief, every fact citing ids
    judgement   weekly (and within 3 days of an importance-3 catalyst), mid-tier model: one
                request per open scenario question sharing a cached prefix; never sees your calls
    validation  every number must match a snapshot value within rounding and every id must exist.
                Facts without a source move to the judgement side; anything else that fails is
                published as it is under a red "unverified" banner.
    spend       data/terminal/brief/spend.json; above the monthly cap only extraction runs.

Batch API first (half price); if a batch has not ended within the configured time it is
cancelled and the remaining requests go through the standard API.
"""

from __future__ import annotations

import datetime as dt
import json
import logging
import math
import re
import time
from pathlib import Path

import yaml

from terminal import emmacro, store

log = logging.getLogger(__name__)

CONF_PATH = store.INPUTS / "brief.yaml"
PRIMERS_PATH = store.INPUTS / "primers.yaml"
EVIDENCE_PATH = store.INPUTS / "evidence.yaml"
DIR = store.DATA / "brief"
SNAPSHOT = DIR / "snapshot.json"
PREV_SNAPSHOT = DIR / "snapshot_prev.json"
ARCHIVE = DIR / "briefs"
INDEX = DIR / "index.json"
LATEST = DIR / "latest.json"
JUDGEMENT = DIR / "judgement_latest.json"
SPEND = DIR / "spend.json"
SITE = "https://ethanc100.github.io/forecast-panel/"
GRID = list(range(0, 101, 5))
# withheld from the model: anything that carries your own probabilities or calls
PRIVATE_KEYS = {"mine", "p_mine", "asymmetry", "calculator", "p_ai", "ai"}


def conf() -> dict:
    return yaml.safe_load(CONF_PATH.read_text())


def _read(path: Path, default=None):
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return default


def _write(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=1, default=str) + "\n")


def _r(x, n=4):
    if x is None or (isinstance(x, float) and math.isnan(x)):
        return None
    return round(float(x), n)


# --------------------------------------------------------------------------
# Snapshot
# --------------------------------------------------------------------------

def _series_ids(summary: dict) -> list[str]:
    ids = []
    for t in summary.get("tiles", []):
        for c in t.get("series_candidates", []):
            if store.series_path(c).exists():
                ids.append(c)
                break
    for c in summary.get("countries", {}).values():
        ids += [ch["series"] for ch in c.get("charts", [])]
    ids += ["us.ust10y", "us.usd.broad", "us.fedfunds", "de.bund10y"]
    seen, out = set(), []
    for i in ids:
        if i not in seen and store.series_path(i).exists():
            seen.add(i)
            out.append(i)
    return out


def _rate_unit(unit: str) -> bool:
    return unit.strip().startswith("%") or unit.startswith("% p.a.")


def series_item(sid: str, degraded: dict[str, str]) -> dict | None:
    s = store.load_series(sid)
    if not s or s.get("key") not in (None, ["date"]) and len(s.get("key") or []) > 1:
        return None
    hist = [(r[0], r[1]) for r in s.get("history", []) if isinstance(r[1], (int, float))]
    if not hist:
        return None
    d, v = hist[-1]
    unit = s.get("unit") or ""
    it = {"id": f"s:{sid}", "kind": "data", "country": s.get("country"), "name": s.get("name"), "unit": unit,
          "date": d, "value": v, "frequency": s.get("frequency"), "source": s.get("source"), "url": s.get("source_url")}
    if len(hist) > 1:
        pd, pv = hist[-2]
        it.update({"prev_date": pd, "prev_value": pv})
        _changes(it, v, pv, unit, "")
    week = (dt.date.fromisoformat(d) - dt.timedelta(days=7)).isoformat()
    older = [x for x in hist if x[0] <= week]
    if older and s.get("frequency") in ("daily", None) and older[-1][0] >= (dt.date.fromisoformat(week) - dt.timedelta(days=5)).isoformat():
        it.update({"week_ago_date": older[-1][0], "week_ago_value": older[-1][1]})
        _changes(it, v, older[-1][1], unit, "_1w")
    for prefix, note in degraded.items():
        if sid.startswith(prefix):
            it["degraded"] = note
    return it


def _changes(it: dict, v: float, pv: float, unit: str, suffix: str) -> None:
    ch = v - pv
    it["change" + suffix] = _r(ch, 4)
    if _rate_unit(unit):
        it["change_bp" + suffix] = _r(ch * 100, 1)
    elif unit != "bp" and pv:
        it["change_pct" + suffix] = _r(ch / abs(pv) * 100, 2)


def calendar_items(days: int) -> list[dict]:
    cal = _read(store.DATA / "calendar.json", {"events": []})
    today = dt.date.today()
    end = (today + dt.timedelta(days=days)).isoformat()
    out = []
    for e in cal.get("events", []):
        if today.isoformat() <= e["date"] <= end:
            out.append({"id": f"ev:{e['id']}", "kind": "event", "country": e.get("country"), "date": e["date"],
                        "days_to": (dt.date.fromisoformat(e["date"]) - today).days, "title": e.get("title"),
                        "type": e.get("type"), "importance": e.get("importance"), "status": e.get("status"),
                        "note": e.get("note") or None, "url": e.get("source")})
    return out


def _strip_private(x):
    if isinstance(x, dict):
        return {k: _strip_private(v) for k, v in x.items() if k not in PRIVATE_KEYS}
    if isinstance(x, list):
        return [_strip_private(v) for v in x]
    return x


def scenario_items() -> list[dict]:
    sc = _read(store.DATA / "scenarios.json", {"scenarios": []})
    today = dt.date.today().isoformat()
    out = []
    for s in sc.get("scenarios", []):
        if str(s.get("resolution_date")) < today:
            continue
        br = s.get("base_rate") or {}
        base = {k: br.get(k) for k in ("kind", "reference_class", "headline", "n", "counts", "range_note", "reason", "context")
                if br.get(k) not in (None, [], "")}
        for k in ("p_yes", "p_yes_low", "p_yes_high"):
            if br.get(k) is not None:
                base[k.replace("p_", "pct_")] = _r(br[k] * 100, 1)
        rows = []
        for m in (s.get("markets") or {}).get("rows", []):
            if m.get("prob") is None:
                continue
            rows.append({"venue": m.get("venue"), "market_id": m.get("id"), "question": m.get("question"),
                         "yes_pct": _r(m["prob"] * 100, 1), "volume": _r(m.get("volume"), 0), "branches": m.get("branches"),
                         "related_only": m.get("related"), "note": m.get("note"), "url": m.get("url")})
        branches = [{"id": b["id"], "label": b["label"], "side": b.get("side"), "signposts": b.get("signposts", []),
                     "moves": [{k: mv.get(k) for k in ("instrument", "unit", "value", "lo", "hi", "source", "basis") if mv.get(k) is not None}
                               for mv in b.get("moves", [])]} for b in s.get("branches", [])]
        out.append(_strip_private({
            "id": f"sc:{s['id']}", "kind": "scenario", "country": s.get("country"), "title": s.get("title"),
            "question": s.get("question"), "resolution": s.get("resolution"), "resolution_date": s.get("resolution_date"),
            "yes_branches": s.get("yes_branches"), "event": s.get("event") and f"ev:{s['event']['id']}",
            "event_date": s.get("event") and s["event"].get("date"), "days_to_event": s.get("days_to_event"),
            "base_rate": base, "branches": branches, "markets": rows, "url": f"{SITE}#scenarios/{s['id']}"}))
    return out


def market_items(summary: dict) -> list[dict]:
    out = []
    for cc, c in summary.get("countries", {}).items():
        for m in c.get("markets", []):
            sid = (m.get("meta") or {}).get("source_id", "")
            mid = sid.replace("market ", "") if sid.startswith("market ") else sid
            prefix = "pm" if m.get("venue") == "Polymarket" else "ks"
            if m.get("prob") is None or not mid:
                continue
            out.append({"id": f"{prefix}:{mid}", "kind": "market", "country": cc, "venue": m.get("venue"),
                        "question": m.get("question"), "yes_pct": _r(m["prob"] * 100, 1), "volume": _r(m.get("volume"), 0),
                        "end_date": m.get("end_date"), "as_of": (m.get("meta") or {}).get("as_of"), "url": m.get("url")})
    return out


def crowd_items() -> tuple[list[dict], list[dict]]:
    cr = _read(store.DATA / "crowd.json", {"gauges": []})
    g = {x["id"]: x for x in cr.get("gauges", [])}
    cot, disp = [], []
    for r in (g.get("e") or {}).get("readings", []):
        meta = r.get("meta") or {}
        cot.append({"id": f"cot:{meta.get('series') or r['country'].lower()}", "kind": "positioning", "country": r.get("country"),
                    "label": r.get("label"), "as_of": r.get("as_of"), "net_contracts": r.get("net"), "net_pct_oi": r.get("net_pct_oi"),
                    "percentile": r.get("percentile"), "crowded": r.get("crowded"), "extreme": r.get("extreme"),
                    "evidence_badge": ((meta.get("evidence") or {}).get("badge")), "source": meta.get("source"), "url": meta.get("source_url")})
    for i, r in enumerate((g.get("c") or {}).get("readings", []), 1):
        meta = r.get("meta") or {}
        disp.append({"id": f"disp:{i}", "kind": "survey_dispersion", "country": r.get("country"), "label": r.get("label"),
                     "as_of": r.get("as_of"), "sd": r.get("value"), "unit": r.get("unit"), "median": r.get("median"),
                     "respondents": r.get("respondents"), "percentile": r.get("percentile"), "percentile_basis": r.get("percentile_basis"),
                     "extreme": r.get("extreme"), "event": (r.get("event") or {}).get("title"),
                     "evidence_badge": (r.get("evidence") or {}).get("badge"), "source": meta.get("source"), "url": meta.get("source_url")})
    return cot, disp


def badge_items() -> list[dict]:
    cr = _read(store.DATA / "crowd.json", {"gauges": []})
    out = [{"id": f"badge:{x['id']}", "kind": "evidence_badge", "gauge": x.get("title"), "badge": (x.get("evidence") or {}).get("badge"),
            "reason": (x.get("evidence") or {}).get("reason"), "url": SITE + "#crowd"} for x in cr.get("gauges", [])]
    ev = yaml.safe_load(EVIDENCE_PATH.read_text()) if EVIDENCE_PATH.exists() else {}
    out.append({"id": "badge:series", "kind": "evidence_badge", "gauge": "Badges on data series",
                "series": {k: v.get("badge") for k, v in (ev.get("series") or {}).items()},
                "legend": "tested_leads: tested and leads its target; tested_no_lead: tested, no lead or did not hold out of sample; "
                          "untested: not tested; context: background only", "url": SITE + "#status"})
    return out


EM_SECTIONS = [("em:5", "## 5. Findings"), ("em:6", "## 6. Hold-out"), ("em:9", "### One-time test, 2020 onward")]


def em_items() -> list[dict]:
    try:
        text = emmacro.text("README.md")
    except Exception as exc:  # noqa: BLE001
        log.warning("em-macro README: %s", exc)
        return []
    out = []
    for iid, head in EM_SECTIONS:
        i = text.find(head)
        if i < 0:
            continue
        rest = text[i + len(head):]
        m = re.search(r"\n#{2,3} ", rest)
        body = (head.lstrip("# ") + rest[: m.start() if m else len(rest)]).strip()
        body = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", body)
        out.append({"id": iid, "kind": "research", "title": "em-macro: " + head.lstrip("# "), "text": body,
                    "url": "https://github.com/EthanC100/em-macro#readme"})
    return out


def primer_items() -> list[dict]:
    p = yaml.safe_load(PRIMERS_PATH.read_text())
    return [{"id": f"primer:{cc}", "kind": "primer", "country": cc, **v} for cc, v in p.items()]


def build_snapshot(fetch_headlines: bool = True) -> dict:
    cfg = conf()["snapshot"]
    summary = _read(store.DATA / "summary.json", {})
    degraded = {}
    for d in summary.get("degraded", []):
        if d.get("id") == "webstat":
            degraded["fr.spread"] = degraded["fr.oat10y"] = d.get("effect")
        if d.get("id") == "b3":
            degraded["br.di"] = d.get("effect")
    prev = _read(SNAPSHOT)
    items = [x for x in (series_item(s, degraded) for s in _series_ids(summary)) if x]
    items += calendar_items(cfg["calendar_days"]) + scenario_items() + market_items(summary)
    cot, disp = crowd_items()
    items += cot + disp
    heads, head_status = [], []
    if fetch_headlines:
        from terminal import headlines
        heads, head_status = headlines.collect(cfg["headlines_min"], cfg["headlines_max"])
        heads = [{**h, "kind": "headline"} for h in heads]
    elif prev:
        heads = [x for x in prev["items"] if x["kind"] == "headline"]
    items += heads + em_items() + badge_items() + primer_items()
    notes = []
    if fetch_headlines and len(heads) < cfg["headlines_min"]:
        notes.append(f"Only {len(heads)} headlines today (target {cfg['headlines_min']}-{cfg['headlines_max']}); sources that failed are listed.")
    # what is new since the last snapshot
    if prev and prev.get("date") != store.today():
        old = {x["id"]: x for x in prev.get("items", [])}
        for it in items:
            o = old.get(it["id"])
            if o is None:
                it["new_since_last_brief"] = True
            elif it["kind"] in ("data", "market", "positioning", "survey_dispersion"):
                key = {"data": "value", "market": "yes_pct", "positioning": "net_contracts", "survey_dispersion": "sd"}[it["kind"]]
                if o.get(key) is not None and it.get(key) is not None and o.get(key) != it.get(key):
                    it["last_brief_value"] = o.get(key)
                    it["last_brief_date"] = o.get("date") or o.get("as_of") or prev.get("date")
                    if it["kind"] == "market":
                        it["change_pp_since_last_brief"] = _r(it["yes_pct"] - o["yes_pct"], 1)
    snap = {"date": store.today(), "generated_at": store.now_iso(), "prev_date": prev and prev.get("date"),
            "items": items, "headline_sources": head_status, "notes": notes,
            "counts": {k: sum(1 for x in items if x["kind"] == k) for k in sorted({x["kind"] for x in items})}}
    if prev and prev.get("date") != store.today():
        _write(PREV_SNAPSHOT, prev)
    _write(SNAPSHOT, snap)
    return snap


# --------------------------------------------------------------------------
# Number and id validation
# --------------------------------------------------------------------------

MONTHS = r"(?:jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\.?"
NUM = re.compile(r"(?<![\w.])[-+−]?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?")


def _scrub(text: str) -> str:
    """Remove dates, years and ids so only quantities are checked."""
    t = re.sub(r"\b(?:s|ev|sc|pm|ks|cot|disp|h|em|badge|primer):[\w.\-]+", " ", text)
    t = re.sub(r"\b\d{4}-\d{2}(?:-\d{2})?\b", " ", t)
    t = re.sub(rf"\b\d{{1,2}}(?:st|nd|rd|th)?(?:\s*[-–]\s*\d{{1,2}})?\s+{MONTHS}", " ", t, flags=re.I)
    t = re.sub(rf"\b{MONTHS}\s+\d{{1,2}}(?:st|nd|rd|th)?\b", " ", t, flags=re.I)
    t = re.sub(r"(?<![\d.,])(?:19|20)\d{2}(?:/\d{2,4})?(?![\d.,%])", " ", t)
    return t


def numbers_in(text: str) -> list[str]:
    return [m.group(0) for m in NUM.finditer(_scrub(text or ""))]


def _walk_numbers(x, out: set) -> None:
    if isinstance(x, bool) or x is None:
        return
    if isinstance(x, (int, float)):
        out.add(float(x))
    elif isinstance(x, str):
        for n in numbers_in(x):
            out.add(_to_float(n))
        for n in NUM.findall(x):  # numbers inside dates and ids in the snapshot count as snapshot values too
            out.add(_to_float(n))
    elif isinstance(x, dict):
        for v in x.values():
            _walk_numbers(v, out)
    elif isinstance(x, list):
        for v in x:
            _walk_numbers(v, out)


def _to_float(s: str) -> float:
    return float(s.replace(",", "").replace("−", "-").lstrip("+"))


def values_of(items) -> set[float]:
    out: set[float] = set()
    _walk_numbers(items, out)
    return out


def matches(token: str, values: set[float]) -> bool:
    x = _to_float(token)
    dec = len(token.split(".")[1]) if "." in token else 0
    tol = 0.5 * 10 ** -dec + 1e-9
    return any(abs(x - v) <= tol or abs(abs(x) - abs(v)) <= tol for v in values)


def check_text(text: str, values: set[float]) -> list[str]:
    return [f"number {n} is not a snapshot value" for n in numbers_in(text) if not matches(n, values)]


def validate_facts(facts: list[dict], index: dict[str, dict]) -> tuple[list[dict], list[dict], list[str]]:
    """Returns (facts, moved_to_judgement, problems). Facts keep their text exactly as written."""
    kept, moved, problems = [], [], []
    for f in facts:
        ids = [i.strip() for i in f.get("source_ids") or [] if i.strip()]
        if not ids:
            moved.append({"text": f.get("text", ""), "why": "no source cited, so it is a claim, not a fact"})
            continue
        probs = [f"unknown source id {i}" for i in ids if i not in index]
        vals = values_of([index[i] for i in ids if i in index])
        probs += check_text(f.get("text", ""), vals)
        kept.append({**f, "source_ids": ids, "ok": not probs, "problems": probs})
        problems += [f"Fact {len(kept)}: {p}" for p in probs]
    return kept, moved, problems


def validate_judgement(j: dict, sc: dict, index: dict[str, dict], all_values: set[float]) -> list[str]:
    probs = []
    own = {float(j.get("p_yes", -1))} | {float(b.get("p", -1)) for b in j.get("branches", [])}
    vals = all_values | own
    if j.get("p_yes") not in GRID:
        probs.append(f"P(yes) {j.get('p_yes')} is not on the 5% grid")
    ids = [b["id"] for b in sc["branches"]]
    got = {b.get("id"): b.get("p") for b in j.get("branches", [])}
    if sorted(got) != sorted(ids):
        probs.append(f"branches {sorted(got)} do not match the page's {sorted(ids)}")
    elif any(p not in GRID for p in got.values()):
        probs.append("a branch probability is not on the 5% grid")
    elif sum(got.values()) != 100:
        probs.append(f"branch probabilities sum to {sum(got.values())}, not 100")
    elif sum(got[b] for b in sc["yes_branches"]) != j.get("p_yes"):
        probs.append(f"YES branches sum to {sum(got[b] for b in sc['yes_branches'])}, not P(yes) {j.get('p_yes')}")
    if len(j.get("factors", [])) > 3:
        probs.append(f"{len(j['factors'])} factors (at most 3)")
    for i in [i for f in j.get("factors", []) for i in f.get("source_ids", [])] + list(j.get("source_ids", [])):
        if i not in index:
            probs.append(f"unknown source id {i}")
    texts = [j.get("base_rate_used", ""), j.get("what_would_change_view", ""), j.get("most_likely_wrong", "")]
    texts += [f.get("text", "") for f in j.get("factors", [])]
    for t in texts:
        probs += check_text(t, vals)
    return probs


# --------------------------------------------------------------------------
# Prompts
# --------------------------------------------------------------------------

def _compact(items: list[dict], drop=("url", "frequency")) -> str:
    return "\n".join(json.dumps({k: v for k, v in x.items() if k not in drop and v not in (None, [], "")},
                                ensure_ascii=False, separators=(",", ":"), sort_keys=True) for x in items)


EXTRACTION_SYSTEM = """You write the factual half of a daily research brief on France, Brazil and Mexico sovereign debt and currencies.

You get today's snapshot: one JSON object per line, each with an "id". Report what changed since the last brief (the snapshot says when that was). Changes include: data points with a new observation (compare value with prev_value, or with last_brief_value when present), new or moved calendar events in the next two weeks, market odds that moved, new positioning or survey readings, and new headlines from official press pages and news.

Rules:
- Use only the snapshot. Every fact cites the id or ids it comes from in source_ids.
- Every number you write must be copied from the cited items (value, prev_value, change, change_pct, change_bp, yes_pct, change_pp_since_last_brief, percentile, and so on), rounded if you like. Do not compute new numbers. Dates are fine.
- One fact per item or tight group of items, one sentence each, plain words, no adjectives about importance, no forecasts, no opinions.
- A headline is a fact only about what was said or published, never about whether it is true.
- Order by importance for sovereign risk and currencies: official decisions and data first, then markets, then news.
- Between 6 and 15 facts. If little changed, say so with fewer facts rather than padding.
- Items marked "degraded" come from a fallback source; mention that when you use them."""

EXTRACTION_SCHEMA = {
    "type": "object", "additionalProperties": False, "required": ["facts"],
    "properties": {"facts": {"type": "array", "items": {
        "type": "object", "additionalProperties": False, "required": ["text", "source_ids", "country", "kind"],
        "properties": {"text": {"type": "string"}, "source_ids": {"type": "array", "items": {"type": "string"}},
                       "country": {"type": "string", "enum": ["FR", "BR", "MX", "US", "GLOBAL"]},
                       "kind": {"type": "string", "enum": ["data", "event", "market", "positioning", "survey", "headline", "scenario"]}}}}}}

JUDGEMENT_ROLE = """You are a sceptical EM sovereign strategist looking for where consensus shares an error.

You give probabilities on open questions about France, Brazil and Mexico. Method, every time:
1. Start from the stated base rate on the question's scenario page (base_rate). If the page has no computed base rate, say so and name the starting point you use instead (the reference class you think fits, or the market price as a last resort).
2. Move from there only for reasons in the snapshot or the facts list. Up to three factors, each citing the ids it rests on.
3. Ask where the crowd (markets, surveys, positioning, consensus headlines) might be making the same mistake, and whether the evidence badges say a signal is worth anything. Untested or tested_no_lead signals deserve little weight.
4. Probabilities in 5% steps. Branch probabilities sum to 100 and the YES branches sum to P(yes).
5. Say what would change your view, how confident you are, and the single most likely way you are wrong.

Every number you write in text must be a value from the snapshot or the facts list (or your own probabilities). Do not write adjustment sizes such as "+10pp"; the structured fields carry your probabilities. Dates are fine. Prefer plain words to jargon."""

JUDGEMENT_SCHEMA = {
    "type": "object", "additionalProperties": False,
    "required": ["question_id", "base_rate_used", "p_yes", "branches", "factors", "what_would_change_view", "confidence",
                 "most_likely_wrong", "source_ids"],
    "properties": {
        "question_id": {"type": "string"},
        "base_rate_used": {"type": "string"},
        "p_yes": {"type": "integer", "enum": GRID},
        "branches": {"type": "array", "items": {"type": "object", "additionalProperties": False, "required": ["id", "p"],
                                                 "properties": {"id": {"type": "string"}, "p": {"type": "integer", "enum": GRID}}}},
        "factors": {"type": "array", "items": {"type": "object", "additionalProperties": False, "required": ["text", "effect", "source_ids"],
                                                "properties": {"text": {"type": "string"},
                                                               "effect": {"type": "string", "enum": ["raises", "lowers"]},
                                                               "source_ids": {"type": "array", "items": {"type": "string"}}}}},
        "what_would_change_view": {"type": "string"},
        "confidence": {"type": "string", "enum": ["low", "medium", "high"]},
        "most_likely_wrong": {"type": "string"},
        "source_ids": {"type": "array", "items": {"type": "string"}}}}


def extraction_params(cfg: dict, snap: dict) -> dict:
    body = [x for x in snap["items"] if x["kind"] not in ("research", "evidence_badge", "primer")]
    user = (f"Today is {snap['date']}. The last brief was on {snap.get('prev_date') or 'no earlier date (first brief)'}.\n\n"
            f"Snapshot items:\n{_compact(body)}")
    return {"model": cfg["models"]["extraction"], "max_tokens": cfg["max_tokens"]["extraction"],
            "system": EXTRACTION_SYSTEM, "messages": [{"role": "user", "content": user}],
            "output_config": {"effort": cfg["effort"]["extraction"], "format": {"type": "json_schema", "schema": EXTRACTION_SCHEMA}}}


def judgement_system(snap: dict) -> str:
    ctx = [x for x in snap["items"] if x["kind"] in ("primer", "research", "evidence_badge")]
    return JUDGEMENT_ROLE + "\n\nBackground (cite by id):\n" + _compact(ctx, drop=())


def judgement_params(cfg: dict, snap: dict, facts: list[dict], sc_item: dict) -> dict:
    ttl = cfg["judgement"].get("cache_ttl", "5m")
    shared = [x for x in snap["items"] if x["kind"] not in ("primer", "research", "evidence_badge")]
    facts_txt = "\n".join(f"- {f['text']} [{', '.join(f['source_ids'])}]" for f in facts) or "- (none)"
    shared_txt = (f"Today is {snap['date']}.\n\nFacts that changed since the last brief (validated):\n{facts_txt}\n\n"
                  f"Snapshot items:\n{_compact(shared)}")
    q = (f"Question {sc_item['id']}: {sc_item['question']}\nResolves {sc_item['resolution_date']}: {sc_item['resolution']}\n"
         f"Branches: {', '.join(b['id'] + ' (' + b['label'] + ')' for b in sc_item['branches'])}. YES branches: {', '.join(sc_item['yes_branches'])}.\n"
         f"Give your judgement with question_id {sc_item['id']}.")
    cc = {"type": "ephemeral", "ttl": ttl}
    return {"model": cfg["models"]["judgement"], "max_tokens": cfg["max_tokens"]["judgement"],
            "system": [{"type": "text", "text": judgement_system(snap), "cache_control": cc}],
            "messages": [{"role": "user", "content": [{"type": "text", "text": shared_txt, "cache_control": cc},
                                                       {"type": "text", "text": q}]}],
            "output_config": {"effort": cfg["effort"]["judgement"], "format": {"type": "json_schema", "schema": JUDGEMENT_SCHEMA}}}


# --------------------------------------------------------------------------
# Spend
# --------------------------------------------------------------------------

def load_spend() -> dict:
    return _read(SPEND, {"currency": "USD", "months": {}, "log": []})


def month_spend(sp: dict, month: str | None = None) -> float:
    return float(sp["months"].get(month or store.today()[:7], {}).get("usd", 0.0))


def cost_of(usage, role: str, batch: bool, cfg: dict) -> dict:
    p = cfg["prices"][role]
    cc = getattr(usage, "cache_creation", None)
    w1h = getattr(cc, "ephemeral_1h_input_tokens", 0) or 0 if cc else 0
    w5m = getattr(cc, "ephemeral_5m_input_tokens", 0) or 0 if cc else 0
    write = usage.cache_creation_input_tokens or 0
    if not cc:
        w5m = write
    tok = {"input": usage.input_tokens or 0, "cache_write_5m": w5m, "cache_write_1h": w1h,
           "cache_read": usage.cache_read_input_tokens or 0, "output": usage.output_tokens or 0}
    prompt = tok["input"] + w5m + w1h + tok["cache_read"]
    mult = (cfg.get("long_prompt") or {}).get(role, {}).get("multiplier", 1) if prompt > (cfg.get("long_prompt") or {}).get(role, {}).get("threshold", 1e12) else 1
    usd = sum(tok[k] * p[k] for k in tok) / 1e6 * mult * (cfg["batch_discount"] if batch else 1.0)
    return {**tok, "usd": round(usd, 6)}


def record_spend(sp: dict, role: str, mode: str, c: dict) -> None:
    m = sp["months"].setdefault(store.today()[:7], {"usd": 0.0, "calls": 0, "by_role": {}})
    m["usd"] = round(m["usd"] + c["usd"], 6)
    m["calls"] += 1
    m["by_role"][role] = round(m["by_role"].get(role, 0.0) + c["usd"], 6)
    sp["log"] = (sp["log"] + [{"at": store.now_iso(), "role": role, "mode": mode, **c}])[-500:]


# --------------------------------------------------------------------------
# Calling the API: Batch first, standard API as the fallback
# --------------------------------------------------------------------------

def _client():
    import anthropic
    return anthropic.Anthropic()


def _parse(msg) -> tuple[dict | None, str | None]:
    if msg.stop_reason == "refusal":
        cat = getattr(getattr(msg, "stop_details", None), "category", None)
        return None, f"the model declined ({cat or 'no category'})"
    if msg.stop_reason == "max_tokens":
        return None, "the answer was cut off at max_tokens"
    text = next((b.text for b in msg.content if b.type == "text"), None)
    if not text:
        return None, "no text in the answer"
    try:
        return json.loads(text), None
    except ValueError as exc:
        return None, f"the answer was not valid JSON ({exc})"


def call_all(reqs: list[tuple[str, str, dict]], cfg: dict, sp: dict, use_batch: bool = True) -> dict[str, tuple[dict | None, str | None]]:
    """reqs: (custom_id, role, params). Returns custom_id -> (parsed JSON or None, error or None)."""
    import anthropic
    client = _client()
    out: dict[str, tuple[dict | None, str | None]] = {}
    pending = {cid: (role, params) for cid, role, params in reqs}
    if use_batch and pending:
        try:
            b = client.messages.batches.create(requests=[{"custom_id": cid, "params": params} for cid, (role, params) in pending.items()])
            log.info("batch %s submitted (%d requests)", b.id, len(pending))
            deadline = time.monotonic() + cfg["batch"]["timeout_minutes"] * 60
            while b.processing_status != "ended" and time.monotonic() < deadline:
                time.sleep(cfg["batch"]["poll_seconds"])
                b = client.messages.batches.retrieve(b.id)
            if b.processing_status != "ended":
                log.warning("batch %s still %s after %d min: cancelling", b.id, b.processing_status, cfg["batch"]["timeout_minutes"])
                client.messages.batches.cancel(b.id)
                for _ in range(20):
                    time.sleep(15)
                    b = client.messages.batches.retrieve(b.id)
                    if b.processing_status == "ended":
                        break
            if b.processing_status == "ended":
                for r in client.messages.batches.results(b.id):
                    if r.result.type == "succeeded" and r.custom_id in pending:
                        role, _ = pending.pop(r.custom_id)
                        record_spend(sp, role, "batch", cost_of(r.result.message.usage, role, True, cfg))
                        out[r.custom_id] = _parse(r.result.message)
                    else:
                        log.warning("batch request %s: %s", r.custom_id, r.result.type)
        except anthropic.APIError as exc:
            log.warning("batch API failed (%s); using the standard API", exc)
    for cid, (role, params) in pending.items():
        try:
            msg = client.messages.create(**params)
            record_spend(sp, role, "standard", cost_of(msg.usage, role, False, cfg))
            out[cid] = _parse(msg)
        except anthropic.APIError as exc:
            out[cid] = (None, f"API error: {type(exc).__name__}: {str(exc)[:200]}")
    return out


# --------------------------------------------------------------------------
# The brief
# --------------------------------------------------------------------------

def judgement_due(snap: dict, cfg: dict, force: bool = False) -> tuple[bool, str]:
    j = cfg["judgement"]
    if force:
        return True, "run on request"
    if not JUDGEMENT.exists():
        return True, "first judgement"
    if dt.date.today().weekday() == j["weekday"]:
        return True, "weekly judgement"
    near = [x for x in snap["items"] if x["kind"] == "event" and x.get("importance", 0) >= j["catalyst_importance"]
            and 0 <= x["days_to"] <= j["catalyst_window_days"]]
    if near:
        return True, f"within {j['catalyst_window_days']} days of {near[0]['title']} ({near[0]['date']})"
    last = _read(JUDGEMENT, {}).get("date")
    return False, f"not due (weekly on {['Monday','Tuesday','Wednesday','Thursday','Friday','Saturday','Sunday'][j['weekday']]} " \
                  f"or near an importance-{j['catalyst_importance']} catalyst); showing the judgement from {last}"


def estimate_judgement_usd(snap: dict, cfg: dict, n: int) -> float:
    """Rough upper bound before spending: prefix written once at the 1-hour rate, read n-1 times, plus
    output, at batch prices (4 characters per token)."""
    p = cfg["prices"]["judgement"]
    prefix = len(judgement_system(snap)) / 4 + len(_compact(snap["items"])) / 4
    toks = prefix * p["cache_write_1h"] + prefix * (n - 1) * p["cache_read"] + n * 300 * p["input"] + n * 3000 * p["output"]
    return toks / 1e6 * cfg["batch_discount"]


def sources_for(ids: set[str], index: dict[str, dict]) -> dict:
    out = {}
    for i in sorted(ids):
        x = index.get(i)
        if not x:
            continue
        label = x.get("title") or x.get("name") or x.get("question") or x.get("label") or x.get("gauge") or i
        out[i] = {"label": label, "url": x.get("url"), "kind": x["kind"], "country": x.get("country"),
                  "date": x.get("date") or x.get("as_of"), "source": x.get("source") or x.get("venue")}
    return out


def run(force_judgement: bool = False, no_ai: bool = False, fetch_headlines: bool = True, use_batch: bool = True) -> dict:
    cfg = conf()
    snap = build_snapshot(fetch_headlines)
    index = {x["id"]: x for x in snap["items"]}
    all_values = values_of(snap["items"])
    sp = load_spend()
    month = month_spend(sp)
    cap = float(cfg["monthly_cap_usd"])
    brief = {"date": snap["date"], "generated_at": store.now_iso(), "snapshot": {"items": len(snap["items"]), "counts": snap["counts"],
             "headline_sources": snap["headline_sources"], "notes": snap["notes"], "prev_date": snap.get("prev_date")}}
    if no_ai or not store.secret("ANTHROPIC_API_KEY"):
        brief.update({"status": "no_ai", "verified": None, "problems": [], "facts": [], "moved_to_judgement": [],
                      "judgement": {"ran": False, "why": "ANTHROPIC_API_KEY is not set" if not no_ai else "run without AI"}})
        return _publish(brief, sp, cfg, index)
    # 1. extraction
    res = call_all([("extraction", "extraction", extraction_params(cfg, snap))], cfg, sp, use_batch)
    data, err = res.get("extraction", (None, "no result"))
    problems = []
    if err:
        problems.append(f"Extraction failed: {err}")
        facts, moved = [], []
    else:
        facts, moved, p = validate_facts(data.get("facts", []), index)
        problems += p
    # 2. judgement
    open_sc = [x for x in snap["items"] if x["kind"] == "scenario"]
    due, why = judgement_due(snap, cfg, force_judgement)
    mode = "full"
    if due and month >= cap:
        due, why, mode = False, f"extraction only: ${month:.2f} spent this month, at or above the ${cap:.2f} cap", "extraction_only"
    elif due and month + estimate_judgement_usd(snap, cfg, len(open_sc)) > cap:
        due, why, mode = False, f"extraction only: this judgement would take the month past the ${cap:.2f} cap", "extraction_only"
    judgement = {"ran": False, "why": why}
    if due and open_sc:
        good_facts = [f for f in facts if f["ok"]]
        reqs = [(f"j-{x['id'][3:]}", "judgement", judgement_params(cfg, snap, good_facts, x)) for x in open_sc]
        res = call_all(reqs, cfg, sp, use_batch)
        qs = []
        for x in open_sc:
            j, err = res.get(f"j-{x['id'][3:]}", (None, "no result"))
            if err:
                qs.append({"question_id": x["id"], "scenario_id": x["id"][3:], "title": x["title"], "ok": False, "problems": [err]})
                problems.append(f"Judgement {x['id']}: {err}")
                continue
            p = validate_judgement(j, x, index, all_values)
            j["question_id"] = x["id"]
            qs.append({**j, "scenario_id": x["id"][3:], "title": x["title"], "country": x.get("country"), "ok": not p, "problems": p})
            problems += [f"Judgement {x['id']}: {q}" for q in p]
        judgement = {"ran": True, "why": why, "date": snap["date"], "questions": qs}
        _write(JUDGEMENT, {"date": snap["date"], "generated_at": store.now_iso(), "why": why,
                           "verified": all(q["ok"] for q in qs), "questions": qs})
    elif JUDGEMENT.exists():
        last = _read(JUDGEMENT)
        judgement.update({"carried": True, "date": last.get("date"), "verified": last.get("verified"), "questions": last.get("questions", [])})
    cited = {i for f in facts for i in f["source_ids"]}
    for q in judgement.get("questions", []):
        cited |= set(q.get("source_ids", [])) | {i for f in q.get("factors", []) for i in f.get("source_ids", [])} | {q["question_id"]}
    brief.update({"status": "ok" if not err else "failed", "mode": mode, "verified": not problems, "problems": problems,
                  "facts": facts, "moved_to_judgement": moved, "judgement": judgement, "sources": sources_for(cited, index)})
    return _publish(brief, sp, cfg, index)


def _publish(brief: dict, sp: dict, cfg: dict, index: dict) -> dict:
    today = store.today()
    m = sp["months"].get(today[:7], {"usd": 0.0})
    run_usd = sum(e["usd"] for e in sp["log"] if e["at"][:10] == today)
    brief["cost"] = {"today_usd": round(run_usd, 4), "month_usd": round(m["usd"], 4), "cap_usd": cfg["monthly_cap_usd"],
                     "month": today[:7]}
    sp["cap_usd"] = cfg["monthly_cap_usd"]
    _write(SPEND, sp)
    _write(ARCHIVE / f"{today}.json", brief)
    _write(LATEST, brief)
    idx = [e for e in _read(INDEX, []) if e["date"] != today]
    idx.append({"date": today, "verified": brief.get("verified"), "status": brief.get("status"), "n_facts": len(brief.get("facts", [])),
                "judgement": bool(brief.get("judgement", {}).get("ran")), "mode": brief.get("mode")})
    _write(INDEX, sorted(idx, key=lambda e: e["date"], reverse=True))
    apply_to_scenarios()
    return brief


def apply_ai(scenarios: list[dict]) -> None:
    """Put the latest judgement's probabilities on the scenario pages (the site shows them only
    after you have made a call on that question)."""
    j = _read(JUDGEMENT)
    by = {q["scenario_id"]: q for q in (j or {}).get("questions", []) if q.get("p_yes") is not None}
    for s in scenarios:
        q = by.get(s["id"])
        if not q:
            s["ai"] = {"available": False, "note": "No AI judgement yet for this question."}
            continue
        bp = {b["id"]: b["p"] / 100 for b in q.get("branches", [])}
        for b in s.get("branches", []):
            b["p_ai"] = bp.get(b["id"])
        s["ai"] = {"available": True, "p_yes": q["p_yes"] / 100, "date": j["date"], "confidence": q.get("confidence"),
                   "verified": q.get("ok"), "problems": q.get("problems", []), "base_rate_used": q.get("base_rate_used"),
                   "factors": q.get("factors", []), "what_would_change_view": q.get("what_would_change_view"),
                   "most_likely_wrong": q.get("most_likely_wrong"), "brief": f"#brief/{j['date']}"}


def apply_to_scenarios() -> None:
    path = store.DATA / "scenarios.json"
    sc = _read(path)
    if not sc:
        return
    apply_ai(sc["scenarios"])
    path.write_text(json.dumps(sc, ensure_ascii=False, indent=1) + "\n")


def ai_probability(qid: str) -> dict | None:
    """The latest AI judgement for sc:<id>, recorded at entry by the judgement engine."""
    j = _read(JUDGEMENT)
    for q in (j or {}).get("questions", []):
        if q.get("question_id") == qid and q.get("p_yes") is not None:
            return {"prob": q["p_yes"] / 100, "source": f"AI brief judgement ({j['date']})", "as_of": j["date"]}
    return None
