"""Source registry. Each entry: key, display name, function, the secret it needs (if any), and
the source it stands in for (a fallback runs only when that source did not succeed this run)."""

from terminal.sources import brazil, france, global_, mexico

SOURCES = [
    # key, name, country, function, secret, fallback_for, release note
    ("bcb_sgs", "BCB SGS (Selic, PTAX, IPCA)", "BR", brazil.sgs, None, None, "daily; IPCA ~10th of the month"),
    ("bcb_focus", "BCB Focus survey (Olinda)", "BR", brazil.focus, None, None, "Mondays ~08:25 BRT"),
    ("tesouro", "Tesouro Direto daily CSV", "BR", brazil.tesouro, None, None, "daily, evening"),
    ("b3_di", "B3 DI x pré reference rates", "BR", brazil.b3_di, None, None, "daily after B3 close"),
    ("banxico_api", "Banxico SIE API", "MX", mexico.banxico_api, "BANXICO_TOKEN", None, "FIX daily ~12:00 CDMX; survey 1st business day"),
    ("banxico_public", "Banxico SIE public chart data (fallback)", "MX", mexico.banxico_public, None, "banxico_api", "as above"),
    ("webstat", "Banque de France Webstat (OAT, Bund)", "FR", france.webstat, "WEBSTAT_CLIENT_ID", None, "daily, next morning"),
    ("ecb_monthly", "ECB monthly long-term rates (FR, DE)", "FR", france.ecb_monthly, None, None, "monthly"),
    ("bundesbank", "Bundesbank daily Bund 10y", "DE", france.bundesbank, None, None, "daily"),
    ("aft_ratings", "AFT France credit ratings table", "FR", france.aft_ratings, None, None, "on rating actions"),
    ("fred_api", "FRED API (US 10y, dollar, Mexico 10y)", "US", global_.fred_api, "FRED_API_KEY", None, "daily"),
    ("fred_public", "FRED public graph CSV (fallback)", "US", global_.fred_public, None, "fred_api", "daily"),
    ("cftc", "CFTC Commitments of Traders (BRL, MXN, ZAR)", "GLOBAL", global_.cftc, None, None, "Fridays 15:30 ET"),
    ("polymarket", "Polymarket (tags france, brazil, mexico)", "GLOBAL", global_.polymarket, None, None, "continuous"),
    ("kalshi", "Kalshi (titles matching FR/BR/MX)", "GLOBAL", global_.kalshi, None, None, "continuous"),
]
