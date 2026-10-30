"""Long history for the policy playbook (Horizons country pages): what followed past episodes in
Brazil, Mexico, France and Argentina. Monthly and quarterly series from FRED (OECD and IMF data
redistributed by the St. Louis Fed), annual inflation and growth from the IMF World Economic Outlook
(DataMapper API) where no monthly or quarterly series reaches back far enough.

Stored like every other series, under hist.*. Series the terminal already stores (Brazil's IPCA,
the France and Mexico 10-year yields, the Brazil 10-year proxy) are not fetched twice.
"""

from __future__ import annotations

import csv
import datetime as dt
import io
import logging
import re
import time

from terminal import store
from terminal.http import get

FRED_API = "https://api.stlouisfed.org/fred/series/observations"
FRED_CSV = "https://fred.stlouisfed.org/graph/fredgraph.csv"
IMF_DM = "https://www.imf.org/external/datamapper/api/v1"
log = logging.getLogger(__name__)

# id, FRED code, name, country, unit, frequency
FRED_HIST = [
    ("hist.mx.cpi_yoy", "CPALTT01MXM659N", "Mexico CPI inflation, % over 12 months (OECD)", "MX", "%", "monthly"),
    ("hist.fr.cpi_yoy", "CPALTT01FRM659N", "France CPI inflation, % over 12 months (OECD)", "FR", "%", "monthly"),
    ("hist.br.gdp_q", "NGDPRSAXDCBRQ", "Brazil real GDP, seasonally adjusted (IMF IFS)", "BR", "BRL millions, constant prices", "quarterly"),
    ("hist.mx.gdp_q", "NGDPRSAXDCMXQ", "Mexico real GDP, seasonally adjusted (IMF IFS)", "MX", "MXN millions, constant prices", "quarterly"),
    ("hist.fr.gdp_q", "CLVMNACSCAB1GQFR", "France real GDP, seasonally adjusted (Eurostat)", "FR", "EUR millions, chain-linked", "quarterly"),
    ("hist.ar.gdp_q", "NGDPRSAXDCARQ", "Argentina real GDP, seasonally adjusted (IMF IFS)", "AR", "ARS millions, constant prices", "quarterly"),
    ("hist.br.fx_m", "CCUSMA02BRM618N", "Brazilian reais per US dollar, monthly average (OECD)", "BR", "BRL per USD", "monthly"),
    ("hist.mx.fx_m", "CCUSMA02MXM618N", "Mexican pesos per US dollar, monthly average (OECD)", "MX", "MXN per USD", "monthly"),
    ("hist.fr.fx_m", "CCUSMA02FRM618N", "France: national currency (euro, francs converted) per US dollar, monthly average (OECD)", "FR",
     "EUR per USD", "monthly"),
    ("hist.ar.fx_m", "ARGCCUSMA02STM", "Argentine pesos per US dollar, monthly average (OECD)", "AR", "ARS per USD", "monthly"),
    ("hist.fr.y10_m", "IRLTLT01FRM156N", "France long-term government bond yield, monthly (OECD)", "FR", "%", "monthly"),
]
# id, IMF WEO code, ISO3, name, country
IMF_HIST = [(f"hist.{cc.lower()}.{kind}_a", code, iso, f"{name}: {label}", cc)
            for cc, iso, name in (("BR", "BRA", "Brazil"), ("MX", "MEX", "Mexico"), ("FR", "FRA", "France"), ("AR", "ARG", "Argentina"))
            for kind, code, label in (("cpi", "PCPIPCH", "inflation, average consumer prices, % a year (IMF WEO)"),
                                      ("gdp", "NGDP_RPCH", "real GDP growth, % a year (IMF WEO)"))]


def _fred_rows(code: str) -> tuple[list[list], str, str]:
    key = store.secret("FRED_API_KEY")
    if key:
        r = get(FRED_API, params={"series_id": code, "api_key": key, "file_type": "json"}, timeout=90)
        rows = [[o["date"], float(o["value"])] for o in r.json()["observations"] if o["value"] not in (".", "")]
        return rows, "FRED API", f"{FRED_API}?series_id={code}"
    r = get(FRED_CSV, params={"id": code}, timeout=90)
    rows = []
    for row in csv.reader(io.StringIO(r.text)):
        if len(row) == 2 and re.fullmatch(r"\d{4}-\d{2}-\d{2}", row[0]):
            try:
                rows.append([row[0], float(row[1])])
            except ValueError:
                pass
    return rows, "FRED (public graph CSV)", f"{FRED_CSV}?id={code}"


def _imf(code: str) -> dict:
    for _ in range(3):  # the endpoint sometimes answers with its country list instead of values
        j = get(f"{IMF_DM}/{code}", timeout=120).json()
        if "values" in j:
            return j["values"][code]
        time.sleep(5)
    raise RuntimeError(f"IMF DataMapper returned no values for {code}")


def fetch() -> list[str]:
    written, errors = [], []
    for sid, code, name, country, unit, freq in FRED_HIST:
        try:
            rows, src, url = _fred_rows(code)
            if not rows:
                raise RuntimeError("no observations")
            store.save_series({"id": sid, "name": name, "country": country, "unit": unit, "frequency": freq, "source": src,
                               "source_id": f"FRED {code}", "source_url": url}, rows)
            written.append(sid)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{sid}: {exc}")
    last_full = dt.date.today().year - 1   # the WEO's current and future years are projections
    cache: dict[str, dict] = {}
    for sid, code, iso, name, country in IMF_HIST:
        try:
            vals = cache.get(code) or cache.setdefault(code, _imf(code))
            rows = [[f"{y}-12-31", float(v)] for y, v in sorted((vals.get(iso) or {}).items()) if v is not None and int(y) <= last_full]
            if not rows:
                raise RuntimeError(f"no values for {iso}")
            store.save_series({"id": sid, "name": name, "country": country, "unit": "%", "frequency": "annual",
                               "source": "IMF World Economic Outlook (DataMapper)", "source_id": f"WEO {code} {iso}",
                               "source_url": f"{IMF_DM}/{code}/{iso}",
                               "note": "Annual; the latest year may still be an IMF estimate. Future years (projections) are not stored."}, rows)
            written.append(sid)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{sid}: {exc}")
    for e in errors:
        log.warning("history: %s", e)
    if errors and not written:
        raise RuntimeError("; ".join(errors)[:500])
    return written
