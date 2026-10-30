"""Which features run on a weaker substitute right now, and what turns them back to full quality.

A substitute is active only while its primary source is not `ok` in status.json. Nothing here
chooses data: every feature already lists its series best-first (TILES, chart groups, book
instrument `series`), so when a secret is added the primary source writes the better series on the
next run and each feature picks it up by itself. This module only labels what is degraded today.
"""

from __future__ import annotations

from terminal import store

RULES = [
    {"id": "banxico", "primary": "banxico_api", "fallback": "banxico_public", "secret": "BANXICO_TOKEN",
     "series": ["mx.usdmxn.fix", "mx.policy.target", "mx.tiie28", "mx.mbono10y.auction", "mx.survey."],
     "features": "USD/MXN FIX, Banxico target rate, TIIE 28d, Mbono 10y auction yield, Banxico survey (country page, "
                 "USDMXN and MX10Y in the book, Crowd survey dispersion)",
     "effect": "Same Banxico series IDs, read from the public chart endpoint that backs banxico.org.mx graphs. It is "
               "unofficial and undocumented, so it can change without notice, and it serves the latest values only "
               "as of the page cache (can lag the API by hours)."},
    {"id": "fred", "primary": "fred_api", "fallback": "fred_public", "secret": "FRED_API_KEY",
     "series": ["us.", "mx.10y.oecd_m"],
     "features": "US 10-year, broad dollar, fed funds (carry in the book), OECD Mexico 10y",
     "effect": "Same FRED series, read from the public fredgraph.csv download. Values are identical; there is no "
               "vintage/revision metadata and the endpoint is rate-limited more tightly."},
    {"id": "webstat", "primary": "webstat", "fallback": "ecb_monthly", "secret": "WEBSTAT_CLIENT_ID",
     "series": ["fr.spread.oat_bund.ecb_m", "fr.oat10y.ecb_m", "de.bund10y.ecb_m"],
     "features": "France OAT-Bund spread and OAT 10y (Today tile, France page, OATBUND in the book, scenario calculators)",
     "effect": "Monthly averages from the ECB instead of daily Banque de France yields: a daily move, a stop or a "
               "target inside the month is invisible, and the latest value is up to five weeks old. New book trades "
               "switch to the daily series automatically once Webstat succeeds; open trades keep the series they "
               "were filled on."},
    {"id": "b3", "primary": "b3_di", "fallback": "tesouro", "secret": None,
     "series": ["br.di.f27.proxy", "br.di.f29.proxy", "br.di.f31.proxy"],
     "features": "Brazil DI Jan-27/29/31 (Today tiles, Brazil page, DI trades in the book)",
     "effect": "B3 blocks automated requests, so DI rates are proxied by Tesouro's January-dated LTN yields "
               "(sovereign zero-coupon, close to but not the same as the DI swap curve)."},
    {"id": "gold", "primary": "gold_yahoo", "also_ok": ["gold_stooq", "gold_lbma"], "fallback": "worldbank_pink", "secret": None,
     "series": ["gl.gold.wb_m", "gl.silver.wb_m"],
     "features": "Gold and silver prices (Gold page, XAUUSD and XAGUSD in the book)",
     "effect": "Monthly average prices from the World Bank instead of daily spot: a daily move, a stop or a target inside "
               "the month is invisible, and the latest value is up to five weeks old.",
     "upgrade": "none to add: Yahoo, Stooq and LBMA refuse automated requests from some networks; the book and the prices "
                "switch back to daily data by themselves on the first run any of them answers"},
]


def active(status: dict | None = None) -> list[dict]:
    status = status if status is not None else store.load_status()
    srcs = status.get("sources", {})
    out = []
    for r in RULES:
        p, f = srcs.get(r["primary"], {}), srcs.get(r["fallback"], {})
        if p.get("state") == "ok" or any(srcs.get(k, {}).get("state") == "ok" for k in r.get("also_ok", [])):
            continue
        upgrade = r.get("upgrade") or (
            f"add the {r['secret']} secret under Settings > Secrets and variables > Actions; the next data run "
            "uses it and every feature switches over by itself" if r["secret"] else
            "none available from GitHub Actions (B3 blocks it); switches back automatically if B3 answers")
        out.append({**r, "primary_state": p.get("state", "not run"), "fallback_state": f.get("state", "not run"),
                    "fallback_name": f.get("name"), "upgrade": upgrade})
    return out


def for_series(sid: str | None, rules: list[dict]) -> dict | None:
    if not sid:
        return None
    for r in rules:
        if any(sid == p or (p.endswith(".") and sid.startswith(p)) or sid.startswith(p + ".") for p in r["series"]):
            return {"id": r["id"], "effect": r["effect"], "upgrade": r["upgrade"]}
    return None
