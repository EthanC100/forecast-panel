"""Mexico: Banxico SIE (API with BANXICO_TOKEN; public chart JSON as the keyless fallback).

The peso (FIX) is Mexico's primary instrument; the 10-year auction yield is context only.

Survey series IDs come from the SIE tables of the "Encuesta sobre las Expectativas de los
Especialistas en Economía del Sector Privado" (CR154 inflation, CR163 GDP, CR171 year-end peso,
CR175 public balance), checked against each table's row labels on 2026-10-29: in every block the
first ID is the mean, +1 the median and +6 the standard deviation.
"""

from __future__ import annotations

import datetime as dt

from terminal import store
from terminal.http import get

SIE_API = "https://www.banxico.org.mx/SieAPIRest/service/v1/series/{ids}/datos"
SIE_CHART = "https://www.banxico.org.mx/SieInternet/consultaSerieGrafica.do"

MARKET = [
    # id, SIE id, name, unit, frequency
    ("mx.usdmxn.fix", "SF43718", "USD/MXN FIX", "MXN per USD", "daily"),
    ("mx.policy.target", "SF61745", "Banxico target rate", "% p.a.", "daily"),
    ("mx.tiie28", "SF43783", "TIIE 28-day", "% p.a.", "daily"),
    ("mx.mbono10y.auction", "SF44071", "10-year Mbono auction yield (context)", "% p.a.", "per auction"),
]
SURVEY = {
    # id: (name, unit, {horizon: (median id, sd id)})
    "mx.survey.inflation": ("Banxico survey: headline inflation, year end", "%",
                            {0: ("SR14139", "SR14144"), 1: ("SR14146", "SR14151")}),
    "mx.survey.gdp": ("Banxico survey: real GDP growth", "%", {0: ("SR14448", "SR14453"), 1: ("SR14455", "SR14460")}),
    "mx.survey.usdmxn": ("Banxico survey: USD/MXN at year end", "MXN per USD",
                         {0: ("SR14770", "SR14775"), 1: ("SR14777", "SR14782")}),
    "mx.survey.balance": ("Banxico survey: public sector economic balance", "% of GDP",
                          {0: ("SR14938", "SR14943"), 1: ("SR14945", "SR14950")}),
}


def _num(x) -> float | None:
    try:
        return float(str(x).replace(",", ""))
    except ValueError:
        return None


def _api_series(ids: list[str], token: str) -> dict[str, list[list]]:
    r = get(SIE_API.format(ids=",".join(ids)), headers={"Bmx-Token": token, "Accept": "application/json"}, timeout=120)
    out = {}
    for s in r.json()["bmx"]["series"]:
        rows = []
        for d in s.get("datos") or []:
            dd, mm, yy = d["fecha"].split("/")
            v = _num(d["dato"])
            if v is not None:
                rows.append([f"{yy}-{mm}-{dd}", v])
        out[s["idSerie"]] = rows
    return out


def _chart_series(sie_id: str) -> list[list]:
    r = get(SIE_CHART, params={"s": f"{sie_id},CF300,1", "versionSerie": "LA-MAS-RECIENTE", "l": "es"}, timeout=120)
    return [[v[0][:10], float(v[1])] for v in r.json().get("valores") or [] if v[1] is not None]


def _write(fetch, source: str, how: str) -> list[str]:
    written = []
    for sid, sie_id, name, unit, freq in MARKET:
        rows = fetch([sie_id])[sie_id]
        store.save_series({"id": sid, "name": name, "country": "MX", "unit": unit, "frequency": freq,
                           "source": source, "source_id": f"SIE {sie_id}", "source_url": how.format(id=sie_id)}, rows)
        written.append(sid)
    for sid, (name, unit, horizons) in SURVEY.items():
        ids = [i for pair in horizons.values() for i in pair]
        data = fetch(ids)
        rows = {}
        for h, (med_id, sd_id) in horizons.items():
            sd = dict((d, v) for d, v in data.get(sd_id, []))
            for d, v in data.get(med_id, []):
                ref = str(int(d[:4]) + h)
                rows[(d, ref)] = [d, ref, v, sd.get(d)]
        store.save_series({"id": sid, "name": name, "country": "MX", "unit": unit, "frequency": "monthly",
                           "source": source, "source_id": "SIE " + ", ".join(ids) + " (median, sd for years t and t+1)",
                           "source_url": how.format(id=",".join(ids)), "fields": ["median", "sd"], "key": ["date", "ref"]},
                          list(rows.values()), key_len=2)
        written.append(sid)
    return written


def banxico_api() -> list[str]:
    token = store.secret("BANXICO_TOKEN")
    if not token:
        raise MissingSecret("BANXICO_TOKEN")
    return _write(lambda ids: _api_series(ids, token), "Banxico SIE API", SIE_API + "?(Bmx-Token)")


def banxico_public() -> list[str]:
    return _write(lambda ids: {i: _chart_series(i) for i in ids}, "Banxico SIE (public chart data)",
                  SIE_CHART + "?s={id},CF300,1")


class MissingSecret(RuntimeError):
    def __init__(self, name: str):
        super().__init__(f"secret {name} is not set")
        self.name = name
