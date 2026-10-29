"""France: Banque de France Webstat daily OAT and Bund 10y (WEBSTAT_CLIENT_ID), ECB monthly
long-term rates (fallback), Bundesbank daily Bund, AFT credit ratings table."""

from __future__ import annotations

import csv
import html as html_lib
import io
import re

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

ECB_IRS = "https://data-api.ecb.europa.eu/service/data/IRS/M.FR+DE.L.L40.CI.0000.EUR.N.Z"
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
    by = {"FR": {}, "DE": {}}
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
    return ["fr.oat10y.ecb_m", "de.bund10y.ecb_m", "fr.spread.oat_bund.ecb_m"]


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
