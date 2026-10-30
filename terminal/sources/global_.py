"""Global: FRED (API with FRED_API_KEY; public graph CSV as fallback), CFTC Commitments of
Traders for BRL and MXN futures, Polymarket and Kalshi markets about France, Brazil, Mexico."""

from __future__ import annotations

import csv
import datetime as dt
import io
import json
import re
import time

from terminal import store
from terminal.http import get
from terminal.sources.mexico import MissingSecret

# --------------------------------------------------------------------------
# FRED
# --------------------------------------------------------------------------

FRED = [
    ("us.ust10y", "DGS10", "US 10-year Treasury yield", "US", "%", "daily"),
    ("us.usd.broad", "DTWEXBGS", "US dollar index (broad, goods and services)", "US", "index Jan-2006=100", "daily"),
    ("mx.10y.oecd_m", "IRLTLT01MXM156N", "Mexico 10-year government yield (monthly, context)", "MX", "%", "monthly"),
    ("us.fedfunds", "DFF", "US effective federal funds rate (USD leg of FX carry)", "US", "% p.a.", "daily"),
    # external drivers
    ("us.ust2y", "DGS2", "US 2-year Treasury yield", "US", "%", "daily"),
    ("us.vix", "VIXCLS", "VIX (CBOE volatility index)", "US", "index", "daily"),
    ("us.fed.upper", "DFEDTARU", "Fed funds target range, upper limit", "US", "% p.a.", "daily"),
    ("eu.eurusd", "DEXUSEU", "EUR/USD (US dollars per euro, noon New York)", "GLOBAL", "USD per EUR", "daily"),
    ("eu.ecb.dfr", "ECBDFR", "ECB deposit facility rate", "GLOBAL", "% p.a.", "daily"),
    ("gl.brent", "DCOILBRENTEU", "Brent crude oil (Europe spot)", "GLOBAL", "USD per barrel", "daily"),
    ("gl.ironore", "PIORECRUSDM", "Iron ore (China import, IMF primary commodity prices)", "GLOBAL", "USD per tonne", "monthly"),
    ("gl.soy", "PSOYBUSDM", "Soybeans (IMF primary commodity prices)", "GLOBAL", "USD per tonne", "monthly"),
]
FRED_API = "https://api.stlouisfed.org/fred/series/observations"
FRED_CSV = "https://fred.stlouisfed.org/graph/fredgraph.csv"


def _fred_write(fetch, source: str, url_fmt: str) -> list[str]:
    for sid, code, name, country, unit, freq in FRED:
        store.save_series({"id": sid, "name": name, "country": country, "unit": unit, "frequency": freq, "source": source,
                           "source_id": f"FRED {code}", "source_url": url_fmt.format(code=code)}, fetch(code))
    return [f[0] for f in FRED]


def fred_api() -> list[str]:
    key = store.secret("FRED_API_KEY")
    if not key:
        raise MissingSecret("FRED_API_KEY")

    def fetch(code):
        r = get(FRED_API, params={"series_id": code, "api_key": key, "file_type": "json"}, timeout=90)
        return [[o["date"], float(o["value"])] for o in r.json()["observations"] if o["value"] not in (".", "")]
    return _fred_write(fetch, "FRED API", FRED_API + "?series_id={code}")


def fred_public() -> list[str]:
    def fetch(code):
        r = get(FRED_CSV, params={"id": code}, timeout=90)
        rows = []
        for row in csv.reader(io.StringIO(r.text)):
            if len(row) == 2 and re.fullmatch(r"\d{4}-\d{2}-\d{2}", row[0]):
                try:
                    rows.append([row[0], float(row[1])])
                except ValueError:
                    pass
        return rows
    return _fred_write(fetch, "FRED (public graph CSV)", FRED_CSV + "?id={code}")


# --------------------------------------------------------------------------
# CFTC Commitments of Traders
# --------------------------------------------------------------------------

CFTC_TFF = "https://publicreporting.cftc.gov/resource/gpe5-46if.json"
CFTC_LEGACY = "https://publicreporting.cftc.gov/resource/6dca-aqww.json"
COT = {"br.cot.brl": ("102741", "BRL futures (CME)", "BR"), "mx.cot.mxn": ("095741", "MXN futures (CME)", "MX"),
       # ZAR is not a terminal country; it widens the Crowd positioning lab test to a third EM currency.
       "za.cot.zar": ("122741", "ZAR futures (CME)", "ZA")}
COT_FIELDS = ["lev_money_net", "asset_mgr_net", "dealer_net", "noncomm_net", "open_interest"]


def _i(x):
    try:
        return int(float(x))
    except (TypeError, ValueError):
        return None


def cftc() -> list[str]:
    """Weekly positions (contracts). Traders in Financial Futures: leveraged funds, asset managers,
    dealers (from 2006); legacy report: non-commercial net (longer history). Net = long - short."""
    written = []
    for sid, (code, name, country) in COT.items():
        tff = get(CFTC_TFF, params={"$where": f"cftc_contract_market_code='{code}'", "$limit": 50000,
                                    "$order": "report_date_as_yyyy_mm_dd"}, timeout=120).json()
        leg = get(CFTC_LEGACY, params={"$where": f"cftc_contract_market_code='{code}'", "$limit": 50000,
                                       "$order": "report_date_as_yyyy_mm_dd",
                                       "$select": "report_date_as_yyyy_mm_dd,noncomm_positions_long_all,noncomm_positions_short_all,open_interest_all"},
                  timeout=120).json()
        rows: dict[str, list] = {}
        for r in leg:
            d = r["report_date_as_yyyy_mm_dd"][:10]
            nl, ns = _i(r.get("noncomm_positions_long_all")), _i(r.get("noncomm_positions_short_all"))
            rows[d] = [d, None, None, None, (nl - ns) if None not in (nl, ns) else None, _i(r.get("open_interest_all"))]
        for r in tff:
            d = r["report_date_as_yyyy_mm_dd"][:10]
            row = rows.setdefault(d, [d, None, None, None, None, _i(r.get("open_interest_all"))])

            def net(a, b):
                x, y = _i(r.get(a)), _i(r.get(b))
                return x - y if None not in (x, y) else None
            row[1] = net("lev_money_positions_long", "lev_money_positions_short")
            row[2] = net("asset_mgr_positions_long", "asset_mgr_positions_short")
            row[3] = net("dealer_positions_long_all", "dealer_positions_short_all")
        store.save_series({"id": sid, "name": f"CFTC positioning: {name}", "country": country, "unit": "contracts (net long)",
                           "frequency": "weekly (Tuesday positions, released Friday)", "source": "CFTC Commitments of Traders",
                           "source_id": f"CFTC contract {code}: TFF gpe5-46if + legacy 6dca-aqww",
                           "source_url": CFTC_TFF, "fields": COT_FIELDS}, list(rows.values()))
        written.append(sid)
    return written


# --------------------------------------------------------------------------
# Prediction markets
# --------------------------------------------------------------------------

MARKETS_DIR = store.DATA / "markets"
PM_GAMMA = "https://gamma-api.polymarket.com/events"
PM_CLOB = "https://clob.polymarket.com/prices-history"
PM_TAGS = {"FR": "france", "BR": "brazil", "MX": "mexico"}
PM_HISTORY_PER_COUNTRY = 15          # daily price history kept for the top markets by volume
KALSHI = "https://api.elections.kalshi.com/trade-api/v2"
COUNTRY_RE = {
    "FR": re.compile(r"\b(France|French|Macron|Lecornu|Le Pen|Bardella|OAT)\b", re.I),
    "BR": re.compile(r"\b(Brazil|Brazilian|Lula|Bolsonaro|Copom|Selic|Haddad)\b", re.I),
    "MX": re.compile(r"\b(Mexico|Mexican|Sheinbaum|Banxico|USMCA)\b", re.I),
}
NOT_MX = re.compile(r"\bNew Mexico\b", re.I)
KALSHI_CATEGORIES = {"Politics", "Elections", "Economics", "Financials", "World"}   # drops sports matches like "Mexico Open"


def _dollars(x, cents=None):
    """Kalshi quotes prices as dollar strings (`*_dollars`); older payloads used integer cents."""
    v = _f(x)
    if v is not None:
        return v
    c = _f(cents)
    return c / 100.0 if c is not None else None


def _f(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def polymarket() -> list[str]:
    snapshot, written = {"fetched_at": store.now_iso(), "source": "Polymarket Gamma API", "events": []}, []
    for country, tag in PM_TAGS.items():
        events, offset = [], 0
        while True:
            batch = get(PM_GAMMA, params={"tag_slug": tag, "closed": "false", "limit": 100, "offset": offset}, timeout=60).json()
            events += batch
            if len(batch) < 100 or offset > 1000:
                break
            offset += 100
        markets = []
        for e in events:
            for m in e.get("markets") or []:
                if m.get("closed"):
                    continue
                prices = m.get("outcomePrices")
                prices = json.loads(prices) if isinstance(prices, str) else prices
                tokens = m.get("clobTokenIds")
                tokens = json.loads(tokens) if isinstance(tokens, str) else tokens
                markets.append({"country": country, "event": e.get("title"), "event_slug": e.get("slug"), "id": m.get("id"),
                                "question": m.get("question"), "slug": m.get("slug"), "yes": _f(prices[0]) if prices else None,
                                "volume": _f(m.get("volume")) or 0.0, "end_date": (m.get("endDate") or "")[:10],
                                "yes_token": tokens[0] if tokens else None})
        snapshot["events"] += markets
        for m in sorted(markets, key=lambda m: -m["volume"])[:PM_HISTORY_PER_COUNTRY]:
            if not m["yes_token"]:
                continue
            h = get(PM_CLOB, params={"market": m["yes_token"], "interval": "max", "fidelity": 1440}, timeout=60).json().get("history", [])
            by_day = {dt.datetime.fromtimestamp(int(x["t"]), tz=dt.timezone.utc).strftime("%Y-%m-%d"): float(x["p"]) for x in h}
            sid = f"pm.{m['id']}"
            store.save_series({"id": sid, "name": m["question"], "country": country, "unit": "probability (Yes)",
                               "frequency": "daily", "source": "Polymarket CLOB", "source_id": f"market {m['id']} / {m['slug']}",
                               "source_url": f"https://polymarket.com/event/{m['event_slug']}/{m['slug']}",
                               "event": m["event"], "end_date": m["end_date"]}, sorted(by_day.items()))
            written.append(sid)
    MARKETS_DIR.mkdir(parents=True, exist_ok=True)
    (MARKETS_DIR / "polymarket.json").write_text(json.dumps(snapshot, ensure_ascii=False, indent=1) + "\n")
    return written


def _kalshi_country(text: str) -> str | None:
    for c, rx in COUNTRY_RE.items():
        if rx.search(text) and not (c == "MX" and NOT_MX.search(text) and not re.search(r"\b(Mexico City|Mexican)\b", text)):
            return c
    return None


def kalshi() -> list[str]:
    snapshot, written, cursor, pages = {"fetched_at": store.now_iso(), "source": "Kalshi trade API v2", "markets": []}, [], None, 0
    while pages < 60:
        params = {"status": "open", "limit": 200, "with_nested_markets": "true"}
        if cursor:
            params["cursor"] = cursor
        d = get(f"{KALSHI}/events", params=params, timeout=60).json()
        pages += 1
        for e in d.get("events", []):
            if e.get("category") not in KALSHI_CATEGORIES:
                continue
            country = _kalshi_country(f"{e.get('title', '')} {e.get('sub_title', '')}")
            if not country:
                continue
            for m in e.get("markets") or []:
                snapshot["markets"].append({"country": country, "category": e.get("category"), "event": e.get("title"),
                                            "event_ticker": e.get("event_ticker"), "series_ticker": e.get("series_ticker"),
                                            "ticker": m.get("ticker"), "title": m.get("yes_sub_title") or m.get("title") or m.get("subtitle"),
                                            "yes_bid": _dollars(m.get("yes_bid_dollars"), m.get("yes_bid")),
                                            "yes_ask": _dollars(m.get("yes_ask_dollars"), m.get("yes_ask")),
                                            "last_price": _dollars(m.get("last_price_dollars"), m.get("last_price")),
                                            "volume": _f(m.get("volume_fp")) or _f(m.get("volume")) or 0.0,
                                            "open_interest": _f(m.get("open_interest_fp")) or _f(m.get("open_interest")),
                                            "close_time": (m.get("close_time") or "")[:10]})
        cursor = d.get("cursor")
        if not cursor:
            break
        time.sleep(0.3)
    end = int(time.time())
    for m in sorted(snapshot["markets"], key=lambda m: -(m.get("volume") or 0))[:40]:
        if not m.get("series_ticker"):
            continue
        time.sleep(1.0)
        try:
            c = get(f"{KALSHI}/series/{m['series_ticker']}/markets/{m['ticker']}/candlesticks",
                    params={"start_ts": end - 3 * 365 * 86400, "end_ts": end, "period_interval": 1440}, timeout=60, retries=2).json()
        except Exception as exc:  # noqa: BLE001
            snapshot.setdefault("history_errors", []).append(f"{m['ticker']}: {exc}"[:200])
            if "429" in str(exc):
                break
            continue
        rows = []
        for k in c.get("candlesticks", []):
            price, bid, ask = k.get("price") or {}, k.get("yes_bid") or {}, k.get("yes_ask") or {}
            close = _dollars(price.get("close_dollars"), price.get("close"))
            if close is None:
                b, a = _dollars(bid.get("close_dollars"), bid.get("close")), _dollars(ask.get("close_dollars"), ask.get("close"))
                close = (a + b) / 2 if None not in (a, b) else None
            if close is not None:
                rows.append([dt.datetime.fromtimestamp(int(k["end_period_ts"]), tz=dt.timezone.utc).strftime("%Y-%m-%d"), close])
        if rows:
            sid = f"ks.{m['ticker']}"
            store.save_series({"id": sid, "name": f"{m['event']}: {m['title']}", "country": m["country"],
                               "unit": "probability (Yes)", "frequency": "daily", "source": "Kalshi",
                               "source_id": m["ticker"], "source_url": f"https://kalshi.com/markets/{m['series_ticker']}"}, rows)
            written.append(sid)
    MARKETS_DIR.mkdir(parents=True, exist_ok=True)
    (MARKETS_DIR / "kalshi.json").write_text(json.dumps(snapshot, ensure_ascii=False, indent=1) + "\n")
    return written
