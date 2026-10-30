"""France: Banque de France Webstat daily OAT and Bund 10y (WEBSTAT_CLIENT_ID), ECB monthly
long-term rates (fallback), Bundesbank daily Bund, AFT credit ratings table, and the IMF, OECD and
European Commission forecasts for France."""

from __future__ import annotations

import csv
import datetime as dt
import email.utils
import html as html_lib
import io
import re
import time
import zipfile

from terminal import store
from terminal.http import get
from terminal.sources.mexico import MissingSecret

# Webstat series keys (dataset FM, provider FR2). Unverified from the build sandbox, which cannot
# reach Webstat; if the status page shows "no observations", correct the keys here.
WEBSTAT_KEYS = {
    "fr.oat10y": ("FM.D.FR.EUR.FR2.BB.FR10YT_RR.YLD", "France 10-year OAT yield (TEC10)"),
    "de.bund10y.webstat": ("FM.D.DE.EUR.FR2.BB.DE10YT_RR.YLD", "Germany 10-year Bund yield (Webstat)"),
}
WEBSTAT_NEW = "https://webstat.banque-france.fr/api/explore/v2.1/catalog/datasets/observations/exports/csv"
WEBSTAT_OLD = "https://api.webstat.banque-france.fr/webstat-fr/v1/data/{dataset}/{key}"

ECB_IRS = "https://data-api.ecb.europa.eu/service/data/IRS/M.FR+DE+IT+ES.L.L40.CI.0000.EUR.N.Z"
BUNDESBANK = ("https://api.statistiken.bundesbank.de/rest/download/BBSIS/"
              "D.I.ZAR.ZI.EUR.S1311.B.A604.R10XX.R.A.A._Z._Z.A")
AFT_URLS = ["https://www.aft.gouv.fr/en/frances-credit-ratings", "https://www.aft.gouv.fr/fr/notations-souveraines"]


def _parse_date_value_csv(text: str) -> list[list]:
    rows = []
    for line in text.splitlines():
        parts = line.split(";") if ";" in line else line.split(",")   # ';' files use decimal commas
        if len(parts) < 2:
            continue
        d = next((p.strip().strip('"') for p in parts if re.fullmatch(r'"?\d{4}-\d{2}-\d{2}"?', p.strip())), None)
        if not d:
            continue
        for p in reversed(parts):
            try:
                rows.append([d[:10], float(p.strip().strip('"').replace(",", "."))])
                break
            except ValueError:
                continue
    return rows


def _webstat_fetch(key: str, client_id: str) -> tuple[list[list], str]:
    errors = []
    try:  # current Webstat (Opendatasoft explore API)
        r = get(WEBSTAT_NEW, params={"where": f'series_key="{key}"', "select": "time_period_start,obs_value",
                                     "order_by": "time_period_start"},
                headers={"Authorization": f"Apikey {client_id}"}, timeout=120, retries=1)
        rows = _parse_date_value_csv(r.text)
        if rows:
            return rows, WEBSTAT_NEW
        errors.append("explore API: no observations")
    except Exception as exc:  # noqa: BLE001
        errors.append(f"explore API: {exc}")
    dataset, rest = key.split(".", 1)
    try:  # legacy IBM API Connect gateway
        r = get(WEBSTAT_OLD.format(dataset=dataset, key=rest), params={"format": "csv", "client_id": client_id},
                headers={"X-IBM-Client-Id": client_id, "accept": "text/csv"}, timeout=120, retries=1)
        rows = _parse_date_value_csv(r.text)
        if rows:
            return rows, WEBSTAT_OLD.format(dataset=dataset, key=rest)
        errors.append("legacy API: no observations")
    except Exception as exc:  # noqa: BLE001
        errors.append(f"legacy API: {exc}")
    raise RuntimeError(f"{key}: " + " | ".join(errors))


def webstat() -> list[str]:
    client_id = store.secret("WEBSTAT_CLIENT_ID")
    if not client_id:
        raise MissingSecret("WEBSTAT_CLIENT_ID")
    written, data = [], {}
    for sid, (key, name) in WEBSTAT_KEYS.items():
        rows, url = _webstat_fetch(key, client_id)
        data[sid] = dict(rows)
        store.save_series({"id": sid, "name": name, "country": "FR" if sid.startswith("fr") else "DE", "unit": "%",
                           "frequency": "daily", "source": "Banque de France Webstat", "source_id": key, "source_url": url}, rows)
        written.append(sid)
    oat, bund = data["fr.oat10y"], data["de.bund10y.webstat"]
    spread = [[d, round(100 * (oat[d] - bund[d]), 2)] for d in sorted(oat) if d in bund]
    store.save_series({"id": "fr.spread.oat_bund", "name": "France OAT-Bund 10-year spread", "country": "FR", "unit": "bp",
                       "frequency": "daily", "source": "Banque de France Webstat (derived)",
                       "source_id": f"{WEBSTAT_KEYS['fr.oat10y'][0]} minus {WEBSTAT_KEYS['de.bund10y.webstat'][0]}",
                       "source_url": WEBSTAT_NEW}, spread)
    return written + ["fr.spread.oat_bund"]


def ecb_monthly() -> list[str]:
    r = get(ECB_IRS, params={"format": "csvdata"}, timeout=120)
    by = {"FR": {}, "DE": {}, "IT": {}, "ES": {}}
    for row in csv.DictReader(io.StringIO(r.text)):
        if row.get("REF_AREA") in by and row.get("OBS_VALUE"):
            by[row["REF_AREA"]][row["TIME_PERIOD"] + "-01"] = float(row["OBS_VALUE"])
    meta = {"unit": "%", "frequency": "monthly", "source": "ECB Data Portal (IRS)", "source_url": ECB_IRS}
    store.save_series({**meta, "id": "fr.oat10y.ecb_m", "name": "France 10-year yield (ECB, monthly average)", "country": "FR",
                       "source_id": "IRS.M.FR.L.L40.CI.0000.EUR.N.Z"}, sorted(by["FR"].items()))
    store.save_series({**meta, "id": "de.bund10y.ecb_m", "name": "Germany 10-year yield (ECB, monthly average)", "country": "DE",
                       "source_id": "IRS.M.DE.L.L40.CI.0000.EUR.N.Z"}, sorted(by["DE"].items()))
    spread = [[d, round(100 * (v - by["DE"][d]), 2)] for d, v in sorted(by["FR"].items()) if d in by["DE"]]
    store.save_series({**meta, "id": "fr.spread.oat_bund.ecb_m", "name": "France-Germany 10-year spread (ECB, monthly)",
                       "country": "FR", "unit": "bp", "source": "ECB Data Portal (IRS, derived)",
                       "source_id": "IRS.M.FR minus IRS.M.DE (L40.CI.0000.EUR.N.Z)"}, spread)
    # Italy and Spain over Bunds: external drivers for the France spread (monthly, same source)
    for cc, sid, name in (("IT", "it.spread.btp_bund.ecb_m", "Italy-Germany 10-year spread (ECB, monthly)"),
                          ("ES", "es.spread.bono_bund.ecb_m", "Spain-Germany 10-year spread (ECB, monthly)")):
        rows = [[d, round(100 * (v - by["DE"][d]), 2)] for d, v in sorted(by[cc].items()) if d in by["DE"]]
        store.save_series({**meta, "id": sid, "name": name, "country": cc, "unit": "bp", "source": "ECB Data Portal (IRS, derived)",
                           "source_id": f"IRS.M.{cc} minus IRS.M.DE (L40.CI.0000.EUR.N.Z)"}, rows)
    return ["fr.oat10y.ecb_m", "de.bund10y.ecb_m", "fr.spread.oat_bund.ecb_m", "it.spread.btp_bund.ecb_m", "es.spread.bono_bund.ecb_m"]


def bundesbank() -> list[str]:
    r = get(BUNDESBANK, params={"format": "csv", "lang": "en"}, timeout=120)
    rows = []
    for line in r.text.splitlines():
        p = line.split(",")
        if len(p) >= 2 and re.fullmatch(r"\d{4}-\d{2}-\d{2}", p[0]):
            try:
                rows.append([p[0], float(p[1])])
            except ValueError:
                pass
    store.save_series({"id": "de.bund10y", "name": "Germany 10-year Bund yield", "country": "DE", "unit": "%",
                       "frequency": "daily", "source": "Deutsche Bundesbank",
                       "source_id": "BBSIS.D.I.ZAR.ZI.EUR.S1311.B.A604.R10XX.R.A.A._Z._Z.A", "source_url": BUNDESBANK}, rows)
    return ["de.bund10y"]


AGENCIES = ["S&P", "Standard & Poor", "Moody", "Fitch", "DBRS", "Scope", "KBRA"]


def parse_aft_ratings(html: str) -> list[dict]:
    """Rows of the AFT ratings table: agency, rating, outlook and dates where the table has them."""
    out = []
    for row in re.findall(r"<tr[^>]*>(.*?)</tr>", html, flags=re.S | re.I):
        cells = [html_lib.unescape(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", c))).strip()
                 for c in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", row, flags=re.S | re.I)]
        if not cells or not any(a.lower() in cells[0].lower() for a in AGENCIES):
            continue
        dates = re.findall(r"\d{1,2}/\d{1,2}/\d{4}|\d{4}-\d{2}-\d{2}|\d{1,2} \w+ \d{4}", " ".join(cells[1:]))
        out.append({"agency": cells[0], "cells": cells[1:], "dates": dates})
    return out


def aft_ratings() -> list[str]:
    errors = []
    for url in AFT_URLS:
        try:
            r = get(url, timeout=60, retries=1, headers={"Accept": "text/html"})
            rows = parse_aft_ratings(r.text)
            if rows:
                today = store.today()
                store.save_series({"id": "fr.ratings.aft", "name": "France credit ratings (AFT table)", "country": "FR",
                                   "unit": "rating", "frequency": "on change", "source": "Agence France Trésor",
                                   "source_id": "AFT credit ratings table", "source_url": url,
                                   "fields": ["cells", "dates"], "key": ["date", "ref"]},
                                  [[today, x["agency"], x["cells"], x["dates"]] for x in rows], key_len=2)
                return ["fr.ratings.aft"]
            errors.append(f"{url}: no ratings table found")
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{url}: {exc}")
    raise RuntimeError(" | ".join(errors) + " (the site shows the hand-maintained table in data/terminal/inputs/france_ratings.yaml)")


# --------------------------------------------------------------------------
# Official forecasts for France: IMF WEO, OECD Economic Outlook, European Commission (AMECO)
# --------------------------------------------------------------------------

IMF_DM = "https://www.imf.org/external/datamapper/api/v1"
OECD_EO = ("https://sdmx.oecd.org/public/rest/data/OECD.ECO.MAD,DSD_EO@DF_EO,/FRA.CPIH_YTYPCT+GDPV_ANNPCT+NLGQ+IRS.A"
           "?startPeriod={y0}&format=csvfilewithlabels")
AMECO_ZIP = "https://ec.europa.eu/economy_finance/db_indicators/ameco/documents/ameco{n}.zip"
FC_VARS = {"inflation": "Inflation (HICP or CPI, % a year)", "gdp": "Real GDP growth (%)",
           "balance": "General government balance (% of GDP)", "rate": "Short-term interest rate (3-month, euro area, %)"}
MONTHS_EN = {m: i for i, m in enumerate(["January", "February", "March", "April", "May", "June", "July", "August",
                                          "September", "October", "November", "December"], 1)}


def _fc_save(inst: str, label: str, edition: str, edition_date: str, url: str, values: dict) -> list[str]:
    out = []
    for var, by_year in values.items():
        rows = [[edition_date, str(y), round(v, 3)] for y, v in sorted(by_year.items()) if v is not None]
        if not rows:
            continue
        sid = f"fr.fc.{inst}.{var}"
        store.save_series({"id": sid, "name": f"{label}: {FC_VARS[var]}", "country": "FR", "unit": "%",
                           "frequency": "per forecast edition", "source": label, "source_id": edition, "source_url": url,
                           "edition": edition, "edition_date": edition_date, "key": ["date", "ref"], "fields": ["value"]},
                          rows, key_len=2)
        out.append(sid)
    return out


def _imf() -> list[str]:
    meta = get(f"{IMF_DM}/indicators", timeout=60).json()["indicators"]
    edition = meta["PCPIPCH"].get("source") or "World Economic Outlook"          # "World Economic Outlook (October 2026)"
    m = re.search(r"\((\w+) (\d{4})\)", edition)
    ed_date = f"{m.group(2)}-{MONTHS_EN[m.group(1)]:02d}-01" if m else store.today()
    vals = {}
    for var, code in (("inflation", "PCPIPCH"), ("gdp", "NGDP_RPCH"), ("balance", "GGXCNL_NGDP")):
        for _ in range(3):  # the endpoint sometimes answers with its country list instead of values
            j = get(f"{IMF_DM}/{code}/FRA", timeout=90).json()
            if "values" in j:
                break
            time.sleep(5)
        d = j["values"][code]["FRA"]
        vals[var] = {int(y): float(v) for y, v in d.items() if v is not None}
    return _fc_save("imf", "IMF World Economic Outlook", edition, ed_date, "https://www.imf.org/external/datamapper/profile/FRA", vals)


def _oecd() -> list[str]:
    y0 = dt.date.today().year - 1
    r = get(OECD_EO.format(y0=y0), timeout=120)
    vals, edition = {"inflation": {}, "gdp": {}, "balance": {}, "rate": {}}, None
    var = {"CPIH_YTYPCT": "inflation", "GDPV_ANNPCT": "gdp", "NLGQ": "balance", "IRS": "rate"}
    for row in csv.DictReader(io.StringIO(r.text)):
        if row.get("MEASURE") in var and row.get("OBS_VALUE"):
            vals[var[row["MEASURE"]]][int(row["TIME_PERIOD"])] = float(row["OBS_VALUE"])
            edition = row.get("STRUCTURE_NAME") or edition                               # "Economic Outlook 119"
    n = int(re.search(r"(\d+)", edition or "0").group(1))
    # Economic Outlook 117 = June 2025, 118 = December 2025, then every six months
    ed_date = f"{2025 + (n - 117) // 2}-06-01" if n % 2 else f"{2025 + (n - 118) // 2}-12-01"
    return _fc_save("oecd", "OECD Economic Outlook", f"OECD {edition}", ed_date,
                    "https://www.oecd.org/en/topics/sub-issues/economic-outlook.html", vals)


def _ameco_table(n: int) -> tuple[list[list[str]], str]:
    r = get(AMECO_ZIP.format(n=n), timeout=180)
    z = zipfile.ZipFile(io.BytesIO(r.content))
    text = z.read(z.namelist()[0]).decode("utf-8", "replace")
    return [line.split(";") for line in text.splitlines()], r.headers.get("Last-Modified", "")


def _ec() -> list[str]:
    vals = {"inflation": {}, "gdp": {}, "balance": {}}
    modified = ""
    for n, code, var, kind in ((2, "FRA.1.0.0.0.ZCPIH", "inflation", "index"), (6, "FRA.1.1.0.0.OVGD", "gdp", "index"),
                               (16, "FRA.1.0.319.0.UBLGE", "balance", "level")):
        rows, mod = _ameco_table(n)
        modified = modified or mod
        head = rows[0]
        years = {i: int(h) for i, h in enumerate(head) if h.strip().isdigit()}
        line = next((r for r in rows if r and r[0] == code), None)
        if not line:
            continue
        series = {years[i]: float(v) for i, v in enumerate(line) if i in years and v not in ("NA", "")}
        if kind == "index":
            vals[var] = {y: 100 * (series[y] / series[y - 1] - 1) for y in series if y - 1 in series}
        else:
            vals[var] = series
    try:
        md = email.utils.parsedate_to_datetime(modified).date()
    except (TypeError, ValueError):
        md = dt.date.today()
    season = "Spring" if 3 <= md.month <= 8 else "Autumn"
    year = md.year if md.month >= 3 else md.year - 1
    edition = f"European Commission {season} {year} Economic Forecast (AMECO, updated {md.isoformat()})"
    return _fc_save("ec", "European Commission economic forecast", edition, md.isoformat(),
                    "https://economy-finance.ec.europa.eu/economic-forecast-and-surveys/economic-forecasts_en", vals)


def fr_forecasts() -> list[str]:
    written, errors = [], []
    for f in (_imf, _oecd, _ec):
        try:
            written += f()
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{f.__name__[1:]}: {type(exc).__name__}: {exc}"[:200])
    if not written:
        raise RuntimeError("; ".join(errors))
    return written
