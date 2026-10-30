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
SIE_META = "https://www.banxico.org.mx/SieAPIRest/service/v1/series/{ids}"

MARKET = [
    # id, SIE id, name, unit, frequency
    ("mx.usdmxn.fix", "SF43718", "USD/MXN FIX", "MXN per USD", "daily"),
    ("mx.policy.target", "SF61745", "Banxico target rate", "% p.a.", "daily"),
    ("mx.tiie28", "SF43783", "TIIE 28-day", "% p.a.", "daily"),
    ("mx.mbono10y.auction", "SF44071", "10-year Mbono auction yield (context)", "% p.a.", "per auction"),
]
SURVEY = {
    # id: (name, unit, {horizon: median id}). Each survey answer is a block of seven consecutive SIE ids:
    # mean, median, first quartile, third quartile, minimum, maximum, standard deviation.
    "mx.survey.inflation": ("Banxico survey: headline inflation, year end", "%", {0: "SR14139", 1: "SR14146"}),
    "mx.survey.gdp": ("Banxico survey: real GDP growth", "%", {0: "SR14448", 1: "SR14455"}),
    "mx.survey.usdmxn": ("Banxico survey: USD/MXN at year end", "MXN per USD", {0: "SR14770", 1: "SR14777"}),
    "mx.survey.balance": ("Banxico survey: public sector economic balance", "% of GDP", {0: "SR14938", 1: "SR14945"}),
}
# The interbank (fondeo) rate is asked for the close of quarters relative to the survey quarter t:
# blocks for t, t+1, ..., t+7 start at these median ids (Banxico titles: "Cierre dentro de k trimestres").
# Year-end of the survey year is t+(4-q), of the next year t+(8-q), q being the survey's quarter.
POLICY_RATE = ("mx.survey.policy_rate", "Banxico survey: interbank (policy) rate, Q4 close", "% p.a.",
               [f"SR{14659 + 7 * k}" for k in range(8)])
SURVEY_FIELDS = ["median", "sd", "min", "max"]
OFFSET = {"sd": 5, "min": 3, "max": 4}      # from the median id within its block


def _sid(base: str, off: int) -> str:
    return f"SR{int(base[2:]) + off}"


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


# The chart endpoint fills days without an observation (holidays, non-auction days, survey questions
# not asked that month) with this sentinel instead of leaving them out.
NO_DATA = -989898.0


def _chart_series(sie_id: str) -> list[list]:
    r = get(SIE_CHART, params={"s": f"{sie_id},CF300,1", "versionSerie": "LA-MAS-RECIENTE", "l": "es"}, timeout=120)
    return [[v[0][:10], float(v[1])] for v in r.json().get("valores") or [] if v[1] is not None and float(v[1]) > NO_DATA + 1]


def _write(fetch, source: str, how: str, titles: dict | None = None) -> list[str]:
    written = []
    for sid, sie_id, name, unit, freq in MARKET:
        rows = fetch([sie_id])[sie_id]
        store.save_series({"id": sid, "name": name, "country": "MX", "unit": unit, "frequency": freq,
                           "source": source, "source_id": f"SIE {sie_id}", "source_url": how.format(id=sie_id)}, rows)
        written.append(sid)
    for sid, (name, unit, horizons) in SURVEY.items():
        ids = [x for med in horizons.values() for x in [med] + [_sid(med, o) for o in OFFSET.values()]]
        data = fetch(ids)
        rows = {}
        for h, med in horizons.items():
            extra = {k: dict((d, v) for d, v in data.get(_sid(med, o), [])) for k, o in OFFSET.items()}
            for d, v in data.get(med, []):
                ref = str(int(d[:4]) + h)
                rows[(d, ref)] = [d, ref, v, extra["sd"].get(d), extra["min"].get(d), extra["max"].get(d)]
        meta = {"id": sid, "name": name, "country": "MX", "unit": unit, "frequency": "monthly",
                "source": source, "source_id": "SIE " + ", ".join(ids) + " (median, sd, min, max for years t and t+1)",
                "source_url": how.format(id=",".join(ids)), "fields": SURVEY_FIELDS, "key": ["date", "ref"]}
        if titles:
            meta["titles"] = {i: titles.get(i) for i in ids}
        store.save_series(meta, list(rows.values()), key_len=2)
        written.append(sid)
    written.append(_policy_rate(fetch, source, how, titles))
    return written


def _policy_rate(fetch, source: str, how: str, titles: dict | None) -> str:
    sid, name, unit, meds = POLICY_RATE
    ids = [x for med in meds for x in [med] + [_sid(med, o) for o in OFFSET.values()]]
    data = fetch(ids)
    by = {i: dict((d, v) for d, v in data.get(i, [])) for i in ids}
    rows = []
    dates = sorted(set(by[meds[0]]) | set(by[meds[4]]))
    for d in dates:
        q = (int(d[5:7]) - 1) // 3 + 1
        for ref, k in ((int(d[:4]), 4 - q), (int(d[:4]) + 1, 8 - q)):
            med = meds[k]
            v = by[med].get(d)
            if v is None:
                continue
            rows.append([d, str(ref), v, by[_sid(med, OFFSET["sd"])].get(d), by[_sid(med, OFFSET["min"])].get(d),
                         by[_sid(med, OFFSET["max"])].get(d), f"t+{k}"])
    meta = {"id": sid, "name": name, "country": "MX", "unit": unit, "frequency": "monthly", "source": source,
            "source_id": "SIE " + ", ".join(meds) + " (+ sd, min, max): close of quarter t+k, k chosen so the quarter is Q4",
            "source_url": how.format(id=",".join(meds)), "fields": SURVEY_FIELDS + ["horizon"], "key": ["date", "ref"]}
    if titles:
        meta["titles"] = {i: titles.get(i) for i in ids}
    store.save_series(meta, rows, key_len=2)
    return sid


def banxico_api() -> list[str]:
    token = store.secret("BANXICO_TOKEN")
    if not token:
        raise MissingSecret("BANXICO_TOKEN")
    return _write(lambda ids: _api_series(ids, token), "Banxico SIE API", SIE_API.replace("{ids}", "{id}") + " (Bmx-Token header)",
                  titles=_titles(token))


def _titles(token: str) -> dict:
    """Banxico's own titles for every survey id, stored with the series so the id mapping can be checked."""
    ids = [x for _, _, h in SURVEY.values() for med in h.values() for x in [med] + [_sid(med, o) for o in OFFSET.values()]]
    ids += [x for med in POLICY_RATE[3] for x in [med] + [_sid(med, o) for o in OFFSET.values()]]
    out = {}
    try:
        for i in range(0, len(ids), 20):
            r = get(SIE_META.format(ids=",".join(ids[i:i + 20])), headers={"Bmx-Token": token, "Accept": "application/json"}, timeout=60)
            for s in r.json()["bmx"]["series"]:
                out[s["idSerie"]] = s.get("titulo")
    except Exception:  # noqa: BLE001
        pass
    return out


def banxico_public() -> list[str]:
    return _write(lambda ids: {i: _chart_series(i) for i in ids}, "Banxico SIE (public chart data)",
                  SIE_CHART + "?s={id},CF300,1")


class MissingSecret(RuntimeError):
    def __init__(self, name: str):
        super().__init__(f"secret {name} is not set")
        self.name = name
