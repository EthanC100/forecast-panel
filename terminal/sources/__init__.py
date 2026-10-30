"""Source registry. Each entry: key, display name, function, the secret it needs (if any), and
the source it stands in for (a fallback runs only when that source did not succeed this run)."""

from terminal.sources import brazil, france, global_, gold_, mexico
# terminal/sources/history.py (the policy playbook's long histories) is no longer registered: the playbook was stopped.

SOURCES = [
    # key, name, country, function, secret, fallback_for, release note
    ("bcb_sgs", "BCB SGS (Selic, PTAX, IPCA)", "BR", brazil.sgs, None, None, "daily; IPCA ~10th of the month"),
    ("bcb_focus", "BCB Focus survey (Olinda)", "BR", brazil.focus, None, None, "Mondays ~08:25 BRT"),
    ("tesouro", "Tesouro Direto daily CSV", "BR", brazil.tesouro, None, None, "daily, evening"),
    ("b3_di", "B3 DI x pré reference rates", "BR", brazil.b3_di, None, None, "daily after B3 close"),
    ("banxico_api", "Banxico SIE API", "MX", mexico.banxico_api, "BANXICO_TOKEN", None, "FIX daily ~12:00 CDMX; survey 1st business day"),
    ("banxico_public", "Banxico SIE public chart data (fallback)", "MX", mexico.banxico_public, None, "banxico_api", "as above"),
    ("webstat", "Banque de France Webstat (OAT, Bund)", "FR", france.webstat, "WEBSTAT_CLIENT_ID", None, "daily, next morning"),
    ("ecb_monthly", "ECB monthly long-term rates (FR, DE, IT, ES)", "FR", france.ecb_monthly, None, None, "monthly"),
    ("bundesbank", "Bundesbank daily Bund 10y", "DE", france.bundesbank, None, None, "daily"),
    ("aft_ratings", "AFT France credit ratings table", "FR", france.aft_ratings, None, None, "on rating actions"),
    ("fr_forecasts", "IMF, OECD and European Commission forecasts for France", "FR", france.fr_forecasts, None, None,
     "IMF April/October, OECD June/December, Commission spring/autumn"),
    ("fred_api", "FRED API (US rates, real yield, dollar, EUR/USD, VIX, Brent, iron ore, soy, Fed/ECB rates)", "US", global_.fred_api, "FRED_API_KEY", None, "daily"),
    ("fred_public", "FRED public graph CSV (fallback)", "US", global_.fred_public, None, "fred_api", "daily"),
    ("gold_yahoo", "Yahoo Finance chart data (gold and silver COMEX front-month futures, GC=F and SI=F)", "GLOBAL", gold_.yahoo, None, None, "daily"),
    ("gold_stooq", "Stooq daily CSV (gold and silver spot, fallback)", "GLOBAL", gold_.stooq, None, "gold_yahoo", "daily"),
    ("gold_lbma", "LBMA gold and silver benchmark prices (fallback)", "GLOBAL", gold_.lbma, None, "gold_stooq", "daily, after the London price auctions"),
    ("worldbank_pink", "World Bank Pink Sheet (gold and silver, monthly since 1960)", "GLOBAL", gold_.worldbank, None, None, "early each month"),
    ("fomc", "Federal Reserve FOMC meeting calendar", "US", gold_.fomc, None, None, "published a year or more ahead"),
    ("gpr", "Geopolitical Risk index (Caldara and Iacoviello, daily)", "GLOBAL", gold_.gpr, None, None, "updated weekly"),
    ("imf_gold", "IMF IRFCL official gold holdings (central-bank buying)", "GLOBAL", gold_.imf_cbgold, None, None, "monthly, about 2 months' lag"),
    ("cftc", "CFTC Commitments of Traders (BRL, MXN, ZAR)", "GLOBAL", global_.cftc, None, None, "Fridays 15:30 ET"),
    ("polymarket", "Polymarket (tags france, brazil, mexico)", "GLOBAL", global_.polymarket, None, None, "continuous"),
    ("kalshi", "Kalshi (titles matching FR/BR/MX)", "GLOBAL", global_.kalshi, None, None, "continuous"),
]
