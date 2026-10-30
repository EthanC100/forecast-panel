"""Gold and its drivers: gold and silver daily closes (Yahoo's COMEX front-month futures GC=F and SI=F,
the source gold-events uses; Stooq daily spot CSV and LBMA's published benchmark prices as fallbacks;
the World Bank's monthly averages last), the daily Geopolitical Risk index (Caldara and Iacoviello), and official-sector net
gold purchases (IMF International Reserves and Foreign Currency Liquidity, as in gold-events).

US 10-year real yields (FRED DFII10) come with the other FRED series in global_.py.
"""

from __future__ import annotations

import csv
import datetime as dt
import io
import re

from terminal import store
from terminal.http import get

TROY_OZ_PER_TONNE = 32150.7466
MAX_HOLDINGS_T = 9000.0   # no reporter holds more than the US (8,133 t); larger = unit break
MAX_MONTHLY_T = 500.0     # no central bank trades this much in a month; larger = unit break

METALS = {
    "gl.gold": {"stooq": "xauusd", "lbma": "gold_pm", "yahoo": "GC=F", "name": "Gold spot", "unit": "USD per troy ounce"},
    "gl.silver": {"stooq": "xagusd", "lbma": "silver", "yahoo": "SI=F", "name": "Silver spot", "unit": "USD per troy ounce"},
}
YAHOO = "https://query1.finance.yahoo.com/v8/finance/chart/{sym}"
STOOQ = "https://stooq.com/q/d/l/"
LBMA = "https://prices.lbma.org.uk/json/{file}.json"
GPR_URL = "https://www.matteoiacoviello.com/gpr_files/data_gpr_daily_recent.xls"
GPR_PAGE = "https://www.matteoiacoviello.com/gpr.htm"
IMF_URL = "https://api.imf.org/external/sdmx/2.1/data/IMF.STA,IRFCL/.IRFCLDT1_IRFCL56V_FTO..M"


# --------------------------------------------------------------------------
# Gold and silver
# --------------------------------------------------------------------------

def parse_stooq(text: str) -> list[list]:
    """Stooq daily CSV (Date,Open,High,Low,Close[,Volume]) -> [[date, close]]."""
    if not text.lstrip().startswith("Date,"):
        # Stooq answers with an HTML page or a plain-text message when it won't serve the file
        raise RuntimeError(f"Stooq did not return CSV: {text[:80]!r}")
    rows = []
    for r in csv.DictReader(io.StringIO(text)):
        try:
            rows.append([r["Date"], float(r["Close"])])
        except (KeyError, TypeError, ValueError):
            continue
    if not rows:
        raise RuntimeError("Stooq CSV had no rows")
    return rows


def parse_lbma(obj) -> list[list]:
    """LBMA price JSON: [{"d": "2024-01-02", "v": [usd, gbp, eur]}, ...] -> [[date, usd]]."""
    rows = []
    for x in obj or []:
        try:
            v = x["v"][0]
            if v:
                rows.append([x["d"], float(v)])
        except (KeyError, IndexError, TypeError, ValueError):
            continue
    if not rows:
        raise RuntimeError("LBMA JSON had no USD prices")
    return rows


def parse_yahoo(obj) -> list[list]:
    """Yahoo chart JSON (chart.result[0].timestamp + indicators.quote[0].close) -> [[date, close]].
    Dates are the exchange's trading dates (timestamps shifted by the exchange's gmtoffset)."""
    try:
        res = obj["chart"]["result"][0]
    except (KeyError, IndexError, TypeError):
        err = (obj or {}).get("chart", {}).get("error") if isinstance(obj, dict) else None
        raise RuntimeError(f"Yahoo returned no chart result: {err!r}")
    off = int((res.get("meta") or {}).get("gmtoffset") or 0)
    ts = res.get("timestamp") or []
    closes = ((res.get("indicators") or {}).get("quote") or [{}])[0].get("close") or []
    rows = {}
    for t, c in zip(ts, closes):
        if c is None:
            continue
        d = dt.datetime.fromtimestamp(int(t) + off, dt.timezone.utc).date().isoformat()
        rows[d] = round(float(c), 4)
    if not rows:
        raise RuntimeError("Yahoo chart had no closes")
    return [[d, v] for d, v in sorted(rows.items())]


def _meta(sid: str, source: str, source_id: str, url: str, name: str | None = None) -> dict:
    m = METALS[sid]
    return {"id": sid, "name": name or m["name"], "country": "GLOBAL", "unit": m["unit"], "frequency": "daily", "source": source,
            "source_id": source_id, "source_url": url}


def yahoo() -> list[str]:
    """COMEX front-month futures closes (GC=F, SI=F) from Yahoo's public chart endpoint, the source
    gold-events uses. Requested with the library's default user agent; a refusal is recorded as a failure."""
    out = []
    for sid, m in METALS.items():
        url = YAHOO.format(sym=m["yahoo"])
        r = get(url, params={"range": "max", "interval": "1d"}, timeout=60)
        name = ("Gold" if sid == "gl.gold" else "Silver") + " (COMEX front-month futures, " + m["yahoo"] + ")"
        meta = _meta(sid, "Yahoo Finance chart data (COMEX front-month futures)", f"Yahoo {m['yahoo']}", url, name)
        meta["note"] = "Front-month futures settle close to spot but roll each contract month; not the LBMA spot benchmark."
        store.save_series(meta, parse_yahoo(r.json()))
        out.append(sid)
    return out


def stooq() -> list[str]:
    out = []
    for sid, m in METALS.items():
        r = get(STOOQ, params={"s": m["stooq"], "i": "d"}, timeout=60)
        store.save_series(_meta(sid, "Stooq (daily CSV)", f"Stooq {m['stooq']}", f"{STOOQ}?s={m['stooq']}&i=d"), parse_stooq(r.text))
        out.append(sid)
    return out


def lbma() -> list[str]:
    out = []
    for sid, m in METALS.items():
        url = LBMA.format(file=m["lbma"])
        r = get(url, timeout=60)
        label = "LBMA Gold Price PM" if m["lbma"] == "gold_pm" else "LBMA Silver Price"
        store.save_series(_meta(sid, "LBMA (published benchmark prices)", label, url), parse_lbma(r.json()))
        out.append(sid)
    return out


# --------------------------------------------------------------------------
# Geopolitical Risk index
# --------------------------------------------------------------------------

def parse_gpr(rows: list[dict]) -> list[list]:
    """Rows of the daily GPR sheet (DAY as YYYYMMDD, GPRD) -> [[date, value]]."""
    out = []
    for r in rows:
        try:
            day = str(int(float(r["DAY"])))
            v = float(r["GPRD"])
        except (KeyError, TypeError, ValueError):
            continue
        if v != v:   # NaN
            continue
        out.append([f"{day[:4]}-{day[4:6]}-{day[6:8]}", round(v, 3)])
    if not out:
        raise RuntimeError("GPR sheet had no DAY/GPRD rows")
    return out


def gpr() -> list[str]:
    import pandas as pd   # needs xlrd for .xls
    raw = get(GPR_URL, timeout=180).content
    df = pd.read_excel(io.BytesIO(raw))
    if "GPRD" not in df.columns:
        raise RuntimeError(f"GPR file has no GPRD column; columns: {list(df.columns)[:8]}")
    store.save_series({"id": "gl.gpr", "name": "Geopolitical Risk index (daily)", "country": "GLOBAL",
                       "unit": "index, 1985-2019 average = 100", "frequency": "daily",
                       "source": "Caldara and Iacoviello, Geopolitical Risk Index", "source_id": "GPRD",
                       "source_url": GPR_PAGE, "download_url": GPR_URL,
                       "note": "Share of newspaper articles about adverse geopolitical events (Caldara and Iacoviello, "
                               "American Economic Review, 2022)."},
                      parse_gpr(df.to_dict("records")))
    return ["gl.gpr"]


# --------------------------------------------------------------------------
# Central-bank gold buying (IMF IRFCL)
# --------------------------------------------------------------------------

def parse_imf_gold(text: str) -> tuple[list[list], list[str]]:
    """Monthly net change in official gold holdings, tonnes, summed over IMF IRFCL reporters.

    Holdings (fine troy ounces) are differenced per reporter; a month's figure sums the reporters
    with data in both months, so a country joining the survey does not count as buying. Aggregates
    are dropped, and so is any reporter whose level or monthly change is implausible (a unit break).
    Returns (rows [[month-end date, tonnes, reporters]], dropped reporters)."""
    series = re.findall(r"<Series ([^>]*)>(.*?)</Series>", text, flags=re.S)
    if not series:
        raise RuntimeError(f"IMF IRFCL returned no series: {text[:120]!r}")
    hold: dict[str, dict[str, float]] = {}
    for attrs, body in series:
        m = re.search(r'COUNTRY="([^"]+)"', attrs)
        if not m or not re.fullmatch(r"[A-Z]{3}", m.group(1)):
            continue
        for y, mo, v in re.findall(r'TIME_PERIOD="(\d{4})-M(\d{2})" OBS_VALUE="([^"]*)"', body):
            try:
                hold.setdefault(m.group(1), {})[f"{y}-{mo}"] = float(v) / TROY_OZ_PER_TONNE
            except ValueError:
                continue
    bad, months = [], sorted({k for h in hold.values() for k in h})
    changes: dict[str, dict[str, float]] = {}
    for c, h in hold.items():
        ch = {}
        for a, b in zip(months, months[1:]):
            if a in h and b in h:
                ch[b] = h[b] - h[a]
        if max(h.values()) > MAX_HOLDINGS_T or any(abs(x) > MAX_MONTHLY_T for x in ch.values()):
            bad.append(c)
            continue
        changes[c] = ch
    rows = []
    for mth in months[1:]:
        xs = [ch[mth] for ch in changes.values() if mth in ch]
        if xs:
            y, mo = int(mth[:4]), int(mth[5:])
            end = (dt.date(y + (mo == 12), mo % 12 + 1, 1) - dt.timedelta(days=1)).isoformat()
            rows.append([end, round(sum(xs), 2), len(xs)])
    if not rows:
        raise RuntimeError("IMF IRFCL: no reporter had two consecutive months")
    return rows, sorted(bad)


def imf_cbgold() -> list[str]:
    r = get(IMF_URL, params={"startPeriod": "1999-01"}, timeout=300)
    rows, bad = parse_imf_gold(r.text)
    store.save_series({"id": "gl.cbgold", "name": "Central banks' net gold purchases (IMF reporters)", "country": "GLOBAL",
                       "unit": "tonnes per month", "frequency": "monthly", "fields": ["value", "reporters"],
                       "source": "IMF International Reserves and Foreign Currency Liquidity (IRFCL)",
                       "source_id": "IRFCLDT1_IRFCL56V_FTO", "source_url": IMF_URL + "?startPeriod=1999-01",
                       "note": "Sum of monthly changes in official gold holdings over reporters with both months; "
                               "excludes reporters with unit breaks" + (f" ({', '.join(bad)})" if bad else "") +
                               ". Recent months are incomplete until slow reporters file, so they understate buying."},
                      rows)
    return ["gl.cbgold"]


# --------------------------------------------------------------------------
# World Bank Pink Sheet (monthly averages since 1960)
# --------------------------------------------------------------------------

WB_PAGE = "https://www.worldbank.org/en/research/commodity-markets"
WB_MONTHLY = {"Gold": ("gl.gold.wb_m", "Gold (World Bank Pink Sheet, monthly average)"),
              "Silver": ("gl.silver.wb_m", "Silver (World Bank Pink Sheet, monthly average)")}


def parse_pink_sheet(df) -> dict[str, list[list]]:
    """The 'Monthly Prices' sheet read with header=None: a row of commodity names, then rows whose first
    cell is a month such as 1960M01. Returns {name: [[month-end date, value]]} for Gold and Silver."""
    head = None
    for i in range(min(len(df), 15)):
        cells = [str(x).strip() for x in df.iloc[i].tolist()]
        if "Gold" in cells and "Silver" in cells:
            head = i
            cols = {n: cells.index(n) for n in WB_MONTHLY}
            break
    if head is None:
        raise RuntimeError("Pink Sheet: no header row with Gold and Silver")
    out: dict[str, list[list]] = {n: [] for n in WB_MONTHLY}
    for i in range(head + 1, len(df)):
        m = re.fullmatch(r"(\d{4})M(\d{2})", str(df.iat[i, 0]).strip())
        if not m:
            continue
        y, mo = int(m.group(1)), int(m.group(2))
        end = (dt.date(y + (mo == 12), mo % 12 + 1, 1) - dt.timedelta(days=1)).isoformat()
        for n, j in cols.items():
            try:
                v = float(df.iat[i, j])
            except (TypeError, ValueError):
                continue
            if v == v:
                out[n].append([end, v])
    if not out["Gold"]:
        raise RuntimeError("Pink Sheet: no gold prices")
    return out


def worldbank() -> list[str]:
    import pandas as pd   # needs openpyxl for .xlsx
    page = get(WB_PAGE, timeout=60).text
    links = sorted(set(re.findall(r'https?://[^"\'\s]+CMO-Historical-Data-Monthly\.xlsx', page)))
    if not links:
        raise RuntimeError("World Bank commodity page: no CMO-Historical-Data-Monthly.xlsx link")
    url = links[-1]
    raw = get(url, timeout=180).content
    data = parse_pink_sheet(pd.read_excel(io.BytesIO(raw), sheet_name="Monthly Prices", header=None))
    out = []
    for n, (sid, name) in WB_MONTHLY.items():
        store.save_series({"id": sid, "name": name, "country": "GLOBAL", "unit": "USD per troy ounce", "frequency": "monthly",
                           "source": "World Bank Commodity Price Data (Pink Sheet)", "source_id": f"CMO monthly: {n}",
                           "source_url": WB_PAGE, "download_url": url,
                           "note": "Monthly average price; used for long history and as a monthly stand-in when daily prices are unavailable."},
                          data[n])
        out.append(sid)
    return out


# --------------------------------------------------------------------------
# FOMC meeting calendar (federalreserve.gov)
# --------------------------------------------------------------------------

FOMC_URL = "https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm"
MONTHS = {m: i for i, m in enumerate(["January", "February", "March", "April", "May", "June", "July", "August", "September",
                                      "October", "November", "December"], 1)}


def parse_fomc(html: str) -> list[list]:
    """The Fed's FOMC calendars page -> [[decision date, first day, projections (0/1), label]].
    A meeting such as "October/November 31-1" spans two months; the decision is on the last day."""
    heads = [(m.start(), int(m.group(1))) for m in re.finditer(r"(\d{4}) FOMC Meetings", html)]
    rows = []
    for k, (pos, year) in enumerate(heads):
        end = heads[k + 1][0] if k + 1 < len(heads) else len(html)
        block = html[pos:end]
        for mon, days in re.findall(r'fomc-meeting__month[^>]*>\s*(?:<strong>)?\s*([A-Za-z/]+)\s*<.*?fomc-meeting__date[^>]*>\s*([^<]+?)\s*<',
                                    block, re.S):
            m = re.fullmatch(r"(\d{1,2})-(\d{1,2})(\*?)", days.replace(" ", "").replace("(notationvote)", ""))
            parts = mon.split("/")
            if not m or parts[0] not in MONTHS or parts[-1] not in MONTHS:
                continue
            d1, d2, star = int(m.group(1)), int(m.group(2)), m.group(3) == "*"
            first = dt.date(year, MONTHS[parts[0]], d1)
            last = dt.date(year + (MONTHS[parts[-1]] < MONTHS[parts[0]]), MONTHS[parts[-1]], d2)
            rows.append([last.isoformat(), first.isoformat(), int(star), f"{mon} {days.strip()}"])
    if not rows:
        raise RuntimeError("FOMC page: no meetings found")
    return sorted({r[0]: r for r in rows}.values())


def fomc() -> list[str]:
    rows = parse_fomc(get(FOMC_URL, timeout=60).text)
    store.save_series({"id": "us.fomc.meetings", "name": "FOMC meeting dates", "country": "US", "unit": "meeting",
                       "frequency": "event", "fields": ["first_day", "projections", "label"], "source": "Federal Reserve Board",
                       "source_id": "FOMC calendars", "source_url": FOMC_URL,
                       "note": "Date = the decision day (the meeting's last day). Projections = a Summary of Economic Projections is published."},
                      rows)
    return ["us.fomc.meetings"]
