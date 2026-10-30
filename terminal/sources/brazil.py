"""Brazil: BCB SGS, BCB Olinda Focus survey, Tesouro Direto, B3 DI reference rates."""

from __future__ import annotations

import datetime as dt
import io
import re
import time
from urllib.parse import quote

import pandas as pd

from terminal import store
from terminal.http import get

# --------------------------------------------------------------------------
# BCB SGS
# --------------------------------------------------------------------------

SGS_URL = "https://api.bcb.gov.br/dados/serie/bcdata.sgs.{code}/dados"
SGS = [
    # id, code, name, unit, frequency, first year
    ("br.selic.target", 432, "Selic target rate (Copom)", "% p.a.", "daily", 1999),
    ("br.usdbrl.ptax", 1, "USD/BRL PTAX (sell)", "BRL per USD", "daily", 1984),
    ("br.ipca.mom", 433, "IPCA inflation, month on month", "%", "monthly", 1980),
    ("br.ipca.yoy", 13522, "IPCA inflation, 12 months", "%", "monthly", 1980),
]


def _br_date(s: str) -> str:
    d, m, y = s.split("/")
    return f"{y}-{m}-{d}"


def _sgs_range(code: int, start: dt.date, end: dt.date) -> list[list]:
    """The BCB gateway intermittently answers with an HTML error page and HTTP 200, so a
    non-JSON body is retried with back-off."""
    for attempt in range(6):
        r = get(SGS_URL.format(code=code), params={"formato": "json", "dataInicial": start.strftime("%d/%m/%Y"),
                                                  "dataFinal": end.strftime("%d/%m/%Y")}, timeout=90)
        if r.text.lstrip().startswith("["):
            break
        time.sleep(3 * (attempt + 1))
    else:
        raise RuntimeError(f"SGS {code} {start}..{end}: gateway kept returning a non-JSON page")
    out = []
    for row in r.json():
        try:
            out.append([_br_date(row["data"]), float(str(row["valor"]).replace(",", "."))])
        except (ValueError, KeyError):
            continue
    return out


def sgs() -> list[str]:
    """Daily series are fetched in windows of under 10 years (the API refuses longer ones).
    Rows dated after today are dropped: series 432 is pre-filled up to the next Copom meeting."""
    today = dt.date.today()
    written = []
    for sid, code, name, unit, freq, first_year in SGS:
        last = store.last_key(sid)
        start = (dt.date.fromisoformat(last) - dt.timedelta(days=20)) if last else dt.date(first_year, 1, 1)
        rows = []
        while start <= today:
            end = min(today, dt.date(start.year + 9, 12, 31))
            rows += _sgs_range(code, start, end)
            start = end + dt.timedelta(days=1)
        rows = [r for r in rows if r[0] <= today.isoformat()]
        store.save_series({"id": sid, "name": name, "country": "BR", "unit": unit, "frequency": freq,
                           "source": "BCB SGS", "source_id": f"SGS {code}",
                           "source_url": SGS_URL.format(code=code) + "?formato=json"}, rows)
        written.append(sid)
    return written


# --------------------------------------------------------------------------
# BCB Focus survey (Olinda)
# --------------------------------------------------------------------------

FOCUS_URL = "https://olinda.bcb.gov.br/olinda/servico/Expectativas/versao/v1/odata/ExpectativasMercadoAnuais"
FOCUS = [
    ("br.focus.ipca", "IPCA", "Focus: IPCA inflation, calendar year", "%"),
    ("br.focus.selic", "Selic", "Focus: Selic at year end", "% p.a."),
    ("br.focus.brl", "Câmbio", "Focus: USD/BRL at year end", "BRL per USD"),
    ("br.focus.gdp", "PIB Total", "Focus: real GDP growth", "%"),
    ("br.focus.primary", "Resultado primário", "Focus: primary balance", "% of GDP"),
    ("br.focus.nominal", "Resultado nominal", "Focus: nominal (overall) balance", "% of GDP"),
    ("br.focus.net_debt", "Dívida líquida do setor público", "Focus: net public sector debt", "% of GDP"),
]
FOCUS_FIELDS = ["median", "mean", "sd", "min", "max", "respondents"]


def focus() -> list[str]:
    """Annual Focus expectations, all reference years, baseCalculo 0 (the published 30-day basis).
    Key = (survey date, reference year); fields = median, mean, sd, min, max, respondents."""
    written = []
    for sid, indicator, name, unit in FOCUS:
        last = store.last_key(sid)
        flt = f"Indicador eq '{indicator}' and baseCalculo eq 0"
        if last:
            since = (dt.date.fromisoformat(last) - dt.timedelta(days=14)).isoformat()
            flt += f" and Data ge '{since}'"
        rows, skip = [], 0
        while True:
            # Olinda rejects '+' for spaces, so the query string is built with %20 by hand.
            qs = "&".join(k + "=" + quote(str(v), safe="',") for k, v in {
                "$filter": flt, "$format": "json", "$top": 10000, "$skip": skip, "$orderby": "Data asc",
                "$select": "Data,DataReferencia,Media,Mediana,DesvioPadrao,Minimo,Maximo,numeroRespondentes"}.items())
            r = get(f"{FOCUS_URL}?{qs}", timeout=180)
            vals = r.json().get("value", [])
            for v in vals:
                rows.append([v["Data"][:10], str(v["DataReferencia"]), v.get("Mediana"), v.get("Media"),
                             v.get("DesvioPadrao"), v.get("Minimo"), v.get("Maximo"), v.get("numeroRespondentes")])
            if len(vals) < 10000:
                break
            skip += 10000
        store.save_series({"id": sid, "name": name, "country": "BR", "unit": unit, "frequency": "daily (business days)",
                           "source": "BCB Focus (Olinda)", "source_id": f"ExpectativasMercadoAnuais/{indicator}/baseCalculo=0",
                           "source_url": FOCUS_URL, "fields": FOCUS_FIELDS, "key": ["date", "ref"]}, rows, key_len=2)
        written.append(sid)
    written.append(focus_meetings())
    return written


FOCUS_SELIC_URL = "https://olinda.bcb.gov.br/olinda/servico/Expectativas/versao/v1/odata/ExpectativasMercadoSelic"


def focus_meetings() -> str:
    """Focus Selic expectation for each Copom meeting ("R5/2026" = fifth meeting of 2026), from 2004.
    Key = (survey date, meeting); fields as the annual table. Dispersion before a meeting feeds the
    Crowd page's survey-dispersion gauge and its lab test."""
    sid = "br.focus.selic_meeting"
    last = store.last_key(sid)
    flt = "baseCalculo eq 0"
    if last:
        flt += f" and Data ge '{(dt.date.fromisoformat(last) - dt.timedelta(days=14)).isoformat()}'"
    rows, skip = [], 0
    while True:
        qs = "&".join(k + "=" + quote(str(v), safe="',") for k, v in {
            "$filter": flt, "$format": "json", "$top": 10000, "$skip": skip, "$orderby": "Data asc",
            "$select": "Data,Reuniao,Media,Mediana,DesvioPadrao,Minimo,Maximo,numeroRespondentes"}.items())
        vals = get(f"{FOCUS_SELIC_URL}?{qs}", timeout=180).json().get("value", [])
        for v in vals:
            rows.append([v["Data"][:10], v["Reuniao"], v.get("Mediana"), v.get("Media"), v.get("DesvioPadrao"),
                         v.get("Minimo"), v.get("Maximo"), v.get("numeroRespondentes")])
        if len(vals) < 10000:
            break
        skip += 10000
    store.save_series({"id": sid, "name": "Focus: Selic expected at each Copom meeting", "country": "BR", "unit": "% p.a.",
                       "frequency": "daily (business days)", "source": "BCB Focus (Olinda)",
                       "source_id": "ExpectativasMercadoSelic/baseCalculo=0", "source_url": FOCUS_SELIC_URL,
                       "fields": FOCUS_FIELDS, "key": ["date", "meeting"]}, rows, key_len=2)
    return sid


# --------------------------------------------------------------------------
# Tesouro Direto
# --------------------------------------------------------------------------

TESOURO_URL = ("https://www.tesourotransparente.gov.br/ckan/dataset/df56aa42-484a-4a59-8184-7676580c81e3/"
               "resource/796d2059-14e9-44e3-80c9-2d9e30b405c1/download/PrecoTaxaTesouroDireto.csv")
TD_GROUPS = {
    "br.td.pre_longest": (["Tesouro Prefixado", "Tesouro Prefixado com Juros Semestrais"],
                          "Brazil 10y proxy: longest fixed-rate Tesouro bond (Prefixado / NTN-F)"),
    "br.td.ipca_longest": (["Tesouro IPCA+", "Tesouro IPCA+ com Juros Semestrais"],
                           "Brazil real-rate proxy: longest IPCA+ Tesouro bond (NTN-B Principal / NTN-B)"),
}


# DI proxies: zero-coupon Tesouro Prefixado (LTN) bonds maturing on the same January dates as
# the DI1 contracts. Labelled "proxy" everywhere; see PROXY_NOTE for how they differ from DI1.
DI_PROXIES = {"br.di.f27.proxy": ("Jan-27", "2027-01-01"), "br.di.f29.proxy": ("Jan-29", "2029-01-01"),
              "br.di.f31.proxy": ("Jan-31", "2031-01-01")}
PROXY_NOTE = ("Proxy, not DI1: Tesouro Direto retail quotes for the zero-coupon Tesouro Prefixado (LTN) maturing "
              "1 January (DI1 matures on the first business day of January, 1-3 days later). Mid of the morning buy and "
              "sell rates (~09:30 BRT), not the end-of-day DI settlement; LTN yields usually sit a few to ~20 bp above "
              "DI for the same date (term and liquidity premium), and the retail buy/sell spread is ~12 bp. Same "
              "252-business-day compounding as DI1, so changes track DI closely; levels do not.")


def tesouro() -> list[str]:
    """Daily rate of the longest-maturity bond in each group, mid of the morning buy and sell
    rates (or whichever is quoted). The bond used each day is kept in the `bond`/`maturity` fields,
    so a jump when a new longer bond is listed is visible, not hidden."""
    r = get(TESOURO_URL, timeout=600)
    df = pd.read_csv(io.StringIO(r.content.decode("latin-1")), sep=";", decimal=",")
    df["date"] = pd.to_datetime(df["Data Base"], format="%d/%m/%Y").dt.strftime("%Y-%m-%d")
    df["mat"] = pd.to_datetime(df["Data Vencimento"], format="%d/%m/%Y").dt.strftime("%Y-%m-%d")
    buy = pd.to_numeric(df["Taxa Compra Manha"], errors="coerce").where(lambda s: s > 0)
    sell = pd.to_numeric(df["Taxa Venda Manha"], errors="coerce").where(lambda s: s > 0)
    df["rate"] = pd.concat([buy, sell], axis=1).mean(axis=1)
    written = []
    for sid, (types, name) in TD_GROUPS.items():
        g = df[df["Tipo Titulo"].isin(types) & df["rate"].notna()]
        g = g.sort_values(["date", "mat"]).groupby("date").tail(1)
        rows = [[d, float(v), m, t] for d, v, m, t in zip(g["date"], g["rate"], g["mat"], g["Tipo Titulo"])]
        store.save_series({"id": sid, "name": name, "country": "BR", "unit": "% p.a.", "frequency": "daily",
                           "source": "Tesouro Direto (Tesouro Transparente)", "source_id": "PrecoTaxaTesouroDireto.csv: "
                           + " / ".join(types) + ", longest maturity, mid of Taxa Compra/Venda Manha",
                           "source_url": TESOURO_URL, "fields": ["value", "maturity", "bond"]}, rows)
        written.append(sid)
    ltn = df[(df["Tipo Titulo"] == "Tesouro Prefixado") & df["rate"].notna()]
    for sid, (label, mat) in DI_PROXIES.items():
        g = ltn[ltn["mat"] == mat].sort_values("date")
        rows = [[d, float(v)] for d, v in zip(g["date"], g["rate"])]
        store.save_series({"id": sid, "name": f"DI {label} proxy (Tesouro LTN {mat[:4]})", "country": "BR", "unit": "% p.a. (252)",
                           "frequency": "daily", "proxy": True, "proxy_note": PROXY_NOTE, "maturity": mat,
                           "source": "Tesouro Direto (Tesouro Transparente)",
                           "source_id": f"PrecoTaxaTesouroDireto.csv: Tesouro Prefixado {mat}, mid of Taxa Compra/Venda Manha",
                           "source_url": TESOURO_URL}, rows)
        written.append(sid)
    return written


# --------------------------------------------------------------------------
# B3 DI x pré reference rates
# --------------------------------------------------------------------------

# The "lumis" page is a wrapper that loads the table from boletim1/TxRef1.asp in an iframe, so the
# inner page is tried first and the wrapper second.
B3_REF_URLS = ["https://www2.bmf.com.br/pages/portal/bmfbovespa/boletim1/TxRef1.asp",
               "https://www2.bmf.com.br/pages/portal/bmfbovespa/lumis/lum-taxas-referenciais-bmf-ptBR.asp"]
B3_REF_URL = B3_REF_URLS[0]
# DI1 futures mature on the first business day of the contract month.
DI_CONTRACTS = {"br.di.f27": ("Jan-27", "2027-01-04"), "br.di.f29": ("Jan-29", "2029-01-02"),
                "br.di.f31": ("Jan-31", "2031-01-02")}
DI_BACKFILL_START = dt.date(2024, 1, 1)
DI_BACKFILL_PER_RUN = 40


def parse_b3_curve(html: str) -> list[tuple[int, float]]:
    """(calendar days, DI x pré 252 rate %) pairs from the B3 reference-rates page."""
    out = []
    for row in re.findall(r"<tr[^>]*>(.*?)</tr>", html, flags=re.S | re.I):
        cells = [re.sub(r"<[^>]+>", "", c).strip() for c in re.findall(r"<td[^>]*>(.*?)</td>", row, flags=re.S | re.I)]
        if len(cells) >= 2 and cells[0].isdigit():
            try:
                out.append((int(cells[0]), float(cells[1].replace(".", "").replace(",", "."))))
            except ValueError:
                continue
    return sorted(out)


def interpolate(curve: list[tuple[int, float]], days: int) -> float | None:
    if not curve or days < curve[0][0] or days > curve[-1][0]:
        return None
    for (d0, r0), (d1, r1) in zip(curve, curve[1:]):
        if d0 <= days <= d1:
            return r0 if d1 == d0 else r0 + (r1 - r0) * (days - d0) / (d1 - d0)
    return curve[-1][1]


def _weekdays(start: dt.date, end: dt.date):
    d = start
    while d <= end:
        if d.weekday() < 5:
            yield d
        d += dt.timedelta(days=1)


def b3_di() -> list[str]:
    """DI1 Jan-27/Jan-29/Jan-31 rates, interpolated linearly in calendar days on B3's daily
    DI x pré reference curve. Each run fetches the last week plus up to 40 older missing weekdays
    back to 2024-01-01, so history fills in over the first few weeks. Days with no curve
    (holidays) are remembered in `no_data_dates` and not retried."""
    today = dt.date.today()
    existing = store.load_series("br.di.f27") or {}
    have = {r[0] for r in existing.get("history", [])} | set(existing.get("no_data_dates", []))
    recent = [d for d in _weekdays(today - dt.timedelta(days=7), today)]
    older = [d for d in _weekdays(DI_BACKFILL_START, today - dt.timedelta(days=8)) if d.isoformat() not in have]
    todo = recent + sorted(older, reverse=True)[:DI_BACKFILL_PER_RUN]
    rows = {sid: [] for sid in DI_CONTRACTS}
    empty, errors, diag = [], 0, ""
    for d in todo:
        curve = []
        for url in B3_REF_URLS:
            try:
                r = get(url, params={"Data": d.strftime("%d/%m/%Y"), "Data1": d.strftime("%Y%m%d"), "slcTaxa": "PRE"},
                        timeout=45, retries=0)
            except Exception as exc:  # noqa: BLE001
                errors += 1
                diag = diag or f"{url.split('/')[-1]}: {exc}"[:200]
                continue
            curve = parse_b3_curve(r.content.decode("latin-1", errors="replace"))
            if curve:
                break
            if not diag:
                text = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", r.content.decode("latin-1", errors="replace"))).strip()
                diag = f"{url.split('/')[-1]} HTTP {r.status_code}, {len(r.content)} bytes, no curve; text starts: {text[:160]!r}"
        if errors >= 6 and not any(rows.values()):
            raise RuntimeError(f"B3 unreachable ({diag})")
        if not curve:
            if d < today - dt.timedelta(days=3):
                empty.append(d.isoformat())
            continue
        for sid, (_, mat) in DI_CONTRACTS.items():
            v = interpolate(curve, (dt.date.fromisoformat(mat) - d).days)
            if v is not None:
                rows[sid].append([d.isoformat(), v])
    if not any(rows.values()):
        raise RuntimeError(f"B3 returned no DI curve for {len(todo)} dates tried. First response: {diag}")
    written = []
    for sid, (label, mat) in DI_CONTRACTS.items():
        meta = {"id": sid, "name": f"DI1 {label} (DI x pré, interpolated)", "country": "BR", "unit": "% p.a. (252)",
                "frequency": "daily", "source": "B3 reference rates (Taxas Referenciais, DI x pré)",
                "source_id": f"slcTaxa=PRE, interpolated at {mat}", "source_url": B3_REF_URL, "maturity": mat}
        old = store.load_series(sid) or {}
        meta["no_data_dates"] = sorted(set(old.get("no_data_dates", [])) | set(empty))
        store.save_series(meta, rows[sid])
        written.append(sid)
    return written
