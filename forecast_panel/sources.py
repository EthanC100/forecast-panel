"""Fetchers, one per source. Each returns a :class:`Reading` and never raises: a failure is a NaN
probability with the reason in ``notes``, so one dead source cannot stop the daily snapshot.

Sources
-------
polymarket    gamma-api.polymarket.com, the market in tension_questions.yaml (``invert`` honoured).
metaculus     www.metaculus.com/api/posts/ - needs METACULUS_TOKEN; the API answers 403 to anonymous
              calls ("The API is only available to authenticated users"), so this fetcher is written
              to the documented v2 API and is UNTESTED here. See README.
swift_centre  the Swift Centre's public forecasts, published as Substack posts
              (swiftcentre.substack.com). The number is parsed from the post text, which prints
              "<question label> ... Swift Centre Forecast (on <date>): NN%".
gjopen        Good Judgment Open question pages, whose public HTML carries the crowd forecast table.
my_prob /     the human columns of gold-events/data/forward_log.csv (entered weekly there, carried
claude_prob   forward until updated).
"""

from __future__ import annotations

import html as html_lib
import json
import logging
import os
import re
import time
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

import pandas as pd
import requests

log = logging.getLogger(__name__)

HTTP_TIMEOUT = 30
NAN = float("nan")

POLYMARKET_API = "https://gamma-api.polymarket.com"
METACULUS_API = "https://www.metaculus.com/api"
SWIFT_SUBSTACK = "https://swiftcentre.substack.com"
GJOPEN = "https://www.gjopen.com"
GOLD_EVENTS_RAW = "https://raw.githubusercontent.com/EthanC100/gold-events/main/data/forward_log.csv"


@dataclass
class Reading:
    prob: float = NAN
    as_of: str = ""      # the date the source's number was made/last updated, when known
    ref: str = ""        # url or identifier of the thing read
    notes: list[str] = field(default_factory=list)

    def note(self) -> str:
        return "; ".join(n for n in self.notes if n)


def _get(url: str, *, retries: int = 4, **kw) -> requests.Response:
    """GET with a short exponential back-off on 429 and 5xx (Substack rate-limits bursts)."""
    kw.setdefault("timeout", HTTP_TIMEOUT)
    delay = 2.0
    for attempt in range(retries + 1):
        resp = requests.get(url, **kw)
        if resp.status_code == 429 or resp.status_code >= 500:
            if attempt < retries:
                wait = float(resp.headers.get("Retry-After") or delay)
                time.sleep(min(wait, 30))
                delay *= 2
                continue
        resp.raise_for_status()
        return resp
    resp.raise_for_status()
    return resp


def _text(html: str) -> str:
    t = re.sub(r"<[^>]+>", " ", html)
    return html_lib.unescape(re.sub(r"\s+", " ", t)).strip()


# --------------------------------------------------------------------------
# Polymarket
# --------------------------------------------------------------------------


def polymarket(q: dict) -> Reading:
    """P(question as worded) from the market linked in the question file."""
    url = (q.get("url") or "").strip()
    r = Reading(ref=url)
    if q.get("source") != "polymarket" or not url:
        r.notes.append("no Polymarket market in tension_questions.yaml")
        return r
    slug = url.rstrip("/").split("/")[-1].split("?")[0]
    try:
        market = None
        for kind in ("markets", "events"):
            items = _get(f"{POLYMARKET_API}/{kind}", params={"slug": slug}).json()
            if items:
                market = items[0] if kind == "markets" else items[0]["markets"][0]
                break
        if market is None:
            r.notes.append(f"no Polymarket market or event with slug {slug!r}")
            return r
        prices = market.get("outcomePrices")
        prices = json.loads(prices) if isinstance(prices, str) else prices
        p = float(prices[0])
        r.prob = 1.0 - p if q.get("invert") else p
        r.ref = f"polymarket market {market.get('id')}: {market.get('question')}"
        if q.get("invert"):
            r.notes.append("logged as 1 - P(Yes) of the market (invert: true)")
        if market.get("closed"):
            r.notes.append("MARKET CLOSED: price is the settled value, not a forecast")
        mismatch = (q.get("resolution_note") or "").strip()
        if mismatch:
            r.notes.append("wording: " + re.sub(r"\s+", " ", mismatch))
    except Exception as exc:  # noqa: BLE001
        r.notes.append(f"fetch failed: {exc}")
    return r


# --------------------------------------------------------------------------
# Metaculus (documented API; untested here because anonymous calls are refused)
# --------------------------------------------------------------------------


def _metaculus_headers() -> dict:
    token = os.environ.get("METACULUS_TOKEN", "").strip()
    return {"Authorization": f"Token {token}"} if token else {}


def _metaculus_latest(post: dict) -> float:
    """Community (recency-weighted) P(Yes) of a binary question in a /api/posts/ item.

    In the v2 API the aggregate sits at question.aggregations.recency_weighted.latest with
    ``centers`` = [P(yes)] and ``forecast_values`` = [P(no), P(yes)].
    """
    question = post.get("question") or {}
    if question.get("type") not in (None, "binary"):
        raise ValueError(f"post {post.get('id')} is not binary ({question.get('type')})")
    agg = question.get("aggregations") or {}
    for key in ("recency_weighted", "unweighted", "metaculus_pred"):
        latest = (agg.get(key) or {}).get("latest") or {}
        if latest.get("centers"):
            return float(latest["centers"][0])
        if latest.get("means"):
            return float(latest["means"][0])
        fv = latest.get("forecast_values")
        if fv and len(fv) == 2:
            return float(fv[1])
    raise ValueError("no community prediction in the response")


def metaculus(q: dict, cfg: dict | None) -> Reading:
    r = Reading()
    cfg = cfg or {}
    if cfg.get("note"):
        r.notes.append(cfg["note"])
    if not _metaculus_headers():
        r.notes.append("METACULUS_TOKEN not set; the Metaculus API refuses anonymous calls (HTTP 403)")
        return r
    try:
        if cfg.get("post_id"):
            resp = requests.get(f"{METACULUS_API}/posts/{int(cfg['post_id'])}/",
                                params={"with_cp": "true"}, headers=_metaculus_headers(), timeout=HTTP_TIMEOUT)
            resp.raise_for_status()
            post = resp.json()
        elif cfg.get("search"):
            resp = requests.get(f"{METACULUS_API}/posts/",
                                params={"search": cfg["search"], "forecast_type": "binary", "statuses": "open",
                                        "limit": 5, "with_cp": "true"},
                                headers=_metaculus_headers(), timeout=HTTP_TIMEOUT)
            resp.raise_for_status()
            results = resp.json().get("results") or []
            if not results:
                r.notes.append(f"no open binary Metaculus question matches {cfg['search']!r}")
                return r
            post = results[0]
            others = "; ".join(f"{p.get('id')}: {p.get('title')}" for p in results[1:4])
            r.notes.append(f"AUTO-MATCHED by search {cfg['search']!r} (verify and set post_id); other candidates: {others}")
        else:
            r.notes.append("no Metaculus post_id or search in source_map.yaml")
            return r
        p = _metaculus_latest(post)
        r.prob = 1.0 - p if cfg.get("invert") else p
        r.ref = f"metaculus post {post.get('id')}: {post.get('title')}"
        r.as_of = str((post.get("question") or {}).get("cp_reveal_time") or "")[:10]
        if cfg.get("invert"):
            r.notes.append("logged as 1 - P(Yes) (invert: true)")
    except Exception as exc:  # noqa: BLE001
        r.notes.append(f"fetch failed: {exc}")
    return r


# --------------------------------------------------------------------------
# Swift Centre (Substack)
# --------------------------------------------------------------------------

SWIFT_FORECAST_RE = r"Swift Centre Forecast[^:%]{0,40}:\s*([0-9]+(?:\.[0-9]+)?)\s*%"


@lru_cache(maxsize=32)
def swift_post_text(slug: str) -> tuple[str, dict]:
    """(plain text, post json) of a Swift Centre Substack post; cached so several questions share one fetch."""
    post = _get(f"{SWIFT_SUBSTACK}/api/v1/posts/{slug}").json()
    return _text(post.get("body_html") or ""), post


def parse_swift_forecast(text: str, label: str) -> float | None:
    """The 'Swift Centre Forecast: NN%' that follows the question label in a post's text."""
    m = re.search(label + r".{0,300}?" + SWIFT_FORECAST_RE, text, flags=re.I | re.S)
    return float(m.group(1)) / 100.0 if m else None


def swift_archive(limit: int = 20) -> list[dict]:
    return _get(f"{SWIFT_SUBSTACK}/api/v1/archive", params={"sort": "new", "limit": limit}).json()


def _newer_posts_note(archive: list[dict], keywords: list[str], since: str, exclude_slug: str | None) -> str:
    hits = []
    for p in archive:
        date = (p.get("post_date") or "")[:10]
        if date <= since or p.get("slug") == exclude_slug:
            continue
        title = (p.get("title") or "")
        hay = (title + " " + (p.get("subtitle") or "")).lower()
        if any(k.lower() in hay for k in keywords):
            hits.append(f"{date} {title!r}")
    return ("newer Swift Centre post(s) may cover this question, check and update source_map.yaml: "
            + " | ".join(hits)) if hits else ""


def swift_centre(cfg: dict | None, note: str = "", keywords: list[str] | None = None,
                 archive: list[dict] | None = None, since: str = "2026-01-01") -> Reading:
    """``since``: posts dated after this (and after the configured post) are flagged as possibly
    relevant; pass the date the mapping was last reviewed (``matched_on`` in source_map.yaml)."""
    r = Reading()
    if note:
        r.notes.append(note)
    try:
        if archive is None:
            archive = swift_archive()
        if cfg:
            text, post = swift_post_text(cfg["post"])
            p = parse_swift_forecast(text, cfg["label"])
            r.ref = post.get("canonical_url") or f"{SWIFT_SUBSTACK}/p/{cfg['post']}"
            r.as_of = str(cfg.get("as_of") or (post.get("post_date") or "")[:10])
            if p is None:
                r.notes.append(f"label {cfg['label']!r} not found before a 'Swift Centre Forecast: NN%' in the post")
            else:
                r.prob = p
                r.notes.append(f"published forecast, carried forward from {r.as_of}")
            if cfg.get("note"):
                r.notes.append(cfg["note"])
            since = max(since, (post.get("post_date") or "")[:10])
        newer = _newer_posts_note(archive, keywords or [], since, (cfg or {}).get("post"))
        if newer:
            r.notes.append(newer)
    except Exception as exc:  # noqa: BLE001
        r.notes.append(f"fetch failed: {exc}")
    return r


# --------------------------------------------------------------------------
# Good Judgment Open
# --------------------------------------------------------------------------


def parse_gjopen_consensus(page_html: str) -> tuple[str, dict[str, float]]:
    """(question title, {answer label: crowd probability}) from a GJ Open question page."""
    title = ""
    m = re.search(r"<title>(.*?)</title>", page_html, flags=re.S)
    if m:
        title = _text(m.group(1)).split("|", 1)[-1].strip()
    i = page_html.find("consensus-table")
    if i < 0:
        raise ValueError("no consensus table on the page")
    chunk = re.sub(r"\s+", " ", page_html[i:i + 20000])
    rows = re.findall(r"<tr\s*>\s*<td>(.*?)</td>\s*<td class=\"text-right\">\s*([0-9]+(?:\.[0-9]+)?)%", chunk)
    if not rows:
        raise ValueError("consensus table has no rows")
    return title, {_text(a): float(b) / 100.0 for a, b in rows}


def gjopen(cfg: dict | None, note: str = "") -> Reading:
    r = Reading()
    if note:
        r.notes.append(note)
    if not cfg:
        return r
    qid = int(cfg["question_id"])
    r.ref = f"{GJOPEN}/questions/{qid}"
    try:
        title, table = parse_gjopen_consensus(_get(r.ref, headers={"Accept": "text/html"}).text)
        r.ref = f"gjopen {qid}: {title}"
        wanted = [a.strip().lower() for a in cfg.get("yes_answers") or ["Yes"]]
        found = {k: v for k, v in table.items() if k.strip().lower() in wanted}
        missing = [a for a in wanted if a not in {k.strip().lower() for k in found}]
        if missing:
            r.notes.append(f"answers not found on the page: {missing}; page has {list(table)}")
            return r
        r.prob = min(1.0, sum(found.values()))
        if cfg.get("note"):
            r.notes.append(cfg["note"])
        if len(found) > 1:
            r.notes.append("sum of " + " + ".join(f"{k} ({v:.3f})" for k, v in found.items()))
    except Exception as exc:  # noqa: BLE001
        r.notes.append(f"fetch failed: {exc}")
    return r


# --------------------------------------------------------------------------
# Human columns from gold-events/data/forward_log.csv
# --------------------------------------------------------------------------


def load_forward_log() -> tuple[pd.DataFrame | None, str]:
    """gold-events' forward log, from GOLD_EVENTS_FORWARD_LOG (a path or url), GOLD_EVENTS_DIR, or the
    public raw url. Returns (frame or None, where it came from / why not)."""
    cands = []
    if os.environ.get("GOLD_EVENTS_FORWARD_LOG"):
        cands.append(os.environ["GOLD_EVENTS_FORWARD_LOG"])
    if os.environ.get("GOLD_EVENTS_DIR"):
        cands.append(str(Path(os.environ["GOLD_EVENTS_DIR"]) / "data" / "forward_log.csv"))
    cands.append(GOLD_EVENTS_RAW)
    errors = []
    for c in cands:
        try:
            if c.startswith("http"):
                # gold-events is public: try without credentials first, so a stale token cannot break it.
                resp = requests.get(c, timeout=HTTP_TIMEOUT)
                tok = os.environ.get("GOLD_EVENTS_TOKEN") or os.environ.get("GITHUB_TOKEN")
                if resp.status_code in (401, 403, 404) and tok and "githubusercontent" in c:
                    resp = requests.get(c, headers={"Authorization": f"token {tok}"}, timeout=HTTP_TIMEOUT)
                resp.raise_for_status()
                from io import StringIO
                df = pd.read_csv(StringIO(resp.text))
            else:
                df = pd.read_csv(c)
            df["log_date"] = pd.to_datetime(df["log_date"]).dt.strftime("%Y-%m-%d")
            return df.sort_values("log_date"), c
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{c}: {exc}")
    return None, "forward_log.csv unavailable (" + " | ".join(errors) + ")"


def human_column(df: pd.DataFrame | None, why: str, column: str, snapshot_date: str) -> Reading:
    """Last non-blank value of ``column`` logged on or before ``snapshot_date``, carried forward."""
    r = Reading(ref=f"gold-events forward_log.csv column {column}")
    if df is None:
        r.notes.append(why)
        return r
    if column not in df.columns:
        r.notes.append(f"column {column} is not in forward_log.csv (yet)")
        return r
    rows = df[(df["log_date"] <= snapshot_date) & df[column].notna()]
    if rows.empty:
        r.notes.append(f"{column} blank in every forward_log.csv row up to {snapshot_date}")
        return r
    last = rows.iloc[-1]
    r.prob = float(last[column])
    r.as_of = str(last["log_date"])
    if r.as_of != snapshot_date:
        r.notes.append(f"carried forward from the {r.as_of} weekly entry")
    return r
