# forecast-panel: macro research terminal

A macro research terminal for **France, Brazil and Mexico**, published at
**https://ethanc100.github.io/forecast-panel/**. The original forecast panel lives on under the
**Lab** link (https://ethanc100.github.io/forecast-panel/lab/).

This is **Phase 1 of 5: the data spine and the catalyst calendar.** Later phases add a paper
trading book, judgement forms and scoring, scenario pages, a crowd-error monitor and an AI brief.
Everything they need is already being stored: every price series keeps its full daily history,
its upstream source and source ID, and fetch timestamps.

## The site

Mobile-first, light and dark mode, bottom navigation:

| tab | what it shows |
|---|---|
| **Today** | The next three catalysts with countdowns. Instrument tiles for USD/BRL, USD/MXN, Brazil DI Jan-27/29/31, the Brazil 10-year proxy, the France OAT-Bund spread, US 10-year and Mexico 10-year (context), each with level, 1-week and 1-month change, and a z-score of the level against the past year. |
| **Calendar** | Next 2 weeks, 3 months and 12 months. Each row: date, country, type, importance 1-3, confirmed or estimated, source, and a market-attention score with an under-attended flag. |
| **Record** | Phase 2: the paper book (Portfolio), scored calls (Judgements) and the Journal. See below. |
| **Scenarios, Crowd** | Placeholders for later phases, listing the data already stored for them. |

Also: a page per country (header links **FR / BR / MX**) and a **Status** page.

Every number carries its **source** (linked, with the source ID), an **as-of** time, a
**freshness dot** (green under 1 day old, amber under 1 week, red older) and an **evidence badge**:

| badge | meaning |
|---|---|
| Tested-leads | tested in one of the research repos and found to lead its target |
| Tested-no-lead | tested, and no lead was found (or it failed out of sample) |
| Untested | not tested as a signal yet |
| Context | background, not meant as a signal |

Badges come from `data/terminal/inputs/evidence.yaml`, with the reason and the test behind each
one (em-macro's hold-out and repricing sections, tension-index's validation). Hover a badge for its
reason.

**Country pages** show market charts (1 year and 5 years), the **fiscal optimism gap** (the
official target against independent estimates, from an editable table), **expectations and
positioning** (survey median, its dispersion as a percentile of 10 years of readings at the same
horizon, and CFTC net positioning as a percentile of 3 years), France's credit ratings, and the
most traded prediction markets.

## Phase 2: paper book, judgements and scoring

### From a phone

**Open a trade.** On a country page or a calendar event, tap **Open trade**, or tap **Open trade** on
Record > Portfolio. GitHub opens the form with the instrument, the linked catalyst and the horizon
filled in. Choose long or short and the size, either as a notional or as "risk amount to stop". Then
enter the stop, the target, a one-line thesis and what would make you close early, and tap **Submit
new issue**. You never type an entry price. The trade fills at the **first close published after you
submit**. A workflow checks the form, records it, comments a summary and closes the issue within a
minute or two. The comment includes a warning if the loss to your stop would exceed 2% of equity.

**Close a trade.** On Record > Portfolio, tap **Close** next to the position. The trade ID is filled
in. Write the two-line post-mortem: what happened against the thesis, and what you would do
differently. The exit is the first close after you submit. Stops and targets close trades on their
own, at the first close that reaches them. Positions past their horizon date are flagged.

**Review.** Record > **Portfolio** shows open positions with P&L split into price, carry and costs,
the equity curve, worst drawdown, risk at stake to your stops, hit rate, and average win and loss.
It also shows em-macro's systematic strategy (its latest positions and paper P&L) and buy-and-hold of
every instrument. Record > **Judgements** shows your calls and their scores. Record > **Journal**
lists every trade, fill, post-mortem, exit, call, update and resolution in date order.

**Make a call.** Tap **Make a call** on a calendar event or a prediction market (country page), or
**Full call** on Record > Judgements. Base rates are pre-filled where the terminal has them: for
Copom and Banxico decisions, how often the last 24 meetings changed the rate. Scenario probabilities
must total 100. Prediction-market prices on country pages stay hidden until you tap **reveal**. The
market-implied probability, and Claude's probability for forecast-panel questions, are recorded when
you submit and shown only in the comment and on the site afterwards. Use **Quick update** to move
your probability in 5% steps, and **Resolve** for questions that cannot resolve automatically.

### Rules

* **Nothing is edited after submission.** Each form becomes one write-once file under
  `data/trades/` or `data/judgements/`, and the code refuses to overwrite one. Editing an issue
  after submitting changes nothing. An invalid form is recorded as rejected, with its errors, and
  closed as "not planned"; submit a new one. Only the repository owner's issues are processed.
* Trade records: `T00012-open.json`, `-fill.json`, `-closereq.json` (with the post-mortem) and
  `-exit.json`. Judgement records: `J00015-call.json`, `U00021-update.json`, `R00030-resolve.json`.
  Derived files, rebuilt each run: `data/book/state.json`, `judgements.json` and `journal.json`.
* The daily data run fills pending trades once their next close exists, marks open positions, applies
  stops and targets, and flags passed horizons.

### Assumptions (`data/book/config.yaml`, editable)

* Starting capital is US$100,000, from 2026-10-29.
* **FX** (USD/BRL, USD/MXN): long means long USD. P&L is N × (S_t − S_0) / S_t in USD. **Carry**
  accrues daily, actual/360, at the policy-rate differential: Selic or the Banxico target against
  US fed funds. A long USD/BRL position pays the Selic.
* **Bonds, DI and the spread**: P&L is −direction × notional × duration × change in yield. Long
  means long the bond, which gains when the yield falls. For OAT-Bund, long means long OAT against
  Bund, which gains when the spread narrows. Bond and spread positions earn no carry or roll-down.
* **Duration** is 8 years for the US 10-year and the France-Germany spread, and 5.5 years for
  Brazil's and Mexico's 10-year positions. Brazil's NTN-F and Mexico's Mbonos pay coupons near
  10-13% and yield 9-15%, so their modified duration is about 5-6 years, not the 8 of a low-coupon US
  or euro bond; using 8 would overstate their P&L by about 45%. DI proxies are zero-coupon: duration
  is years to maturity / (1 + yield), fixed at entry.
* **Costs** are a full round trip charged at entry, so open P&L is liquidation value. FX costs
  0.075% (range 0.05-0.10%). Bonds cost 2 bp, the US 10-year 1 bp and the Mexico 10-year 3 bp.
* **Fills**: each instrument has the time its daily value is published (`close_utc`). Entry and exit
  are the first close whose date plus that time is after the submission. Mexico 10-year is low
  frequency (auction yields about monthly), so its fills and stops can lag by weeks. While Webstat is
  not configured, the France spread falls back to the ECB monthly series and the fill carries a
  warning; once Webstat succeeds, new trades fill on the daily series and open trades keep the series
  they were filled on.
* **DI Jan-27/29/31 are proxies** until B3 is reachable. They use Tesouro's zero-coupon Tesouro
  Prefixado (LTN) bonds maturing on the same January dates, labelled "proxy". These are retail quotes:
  the mid of the morning buy and sell rates, not the end-of-day DI settlement. LTN usually yields a
  few bp to about 20 bp above DI, and the maturity is 1 January rather than the first business day.
  Changes track DI closely; levels do not.

### Scoring

Each resolved question is scored on its last forecast before resolution. The **Brier** score is
(p − outcome)², where lower is better. The **log score** is ln of the probability given to what
happened, clipped at 1%, where higher is better. Both are compared with the market-implied
probability recorded at the same submission. The **calibration chart** appears after 30 resolved
questions. Questions linked to q1-q5, a Polymarket market (`pm:<id>`) or a Kalshi market
(`ks:<ticker>`) resolve automatically; the rest use the Resolve form.

## Daily flow

```
weekdays 22:15 UTC (after the New York close)    terminal-data.yml: every source, then the calendar + GDELT attention
release days                                      terminal-data.yml: just that source
   Mon 12:20 UTC  BCB Focus survey                   Fri 20:40 UTC  CFTC Commitments of Traders
   1st-3rd 19:10 UTC  Banxico survey                 8th-12th 12:30 UTC  IPCA inflation
daily 06:17 UTC                                   panel.yml: the Lab's forecast snapshot (unchanged)
          │
          ▼
python -m terminal.run fetch      -> data/terminal/series/<id>.json, data/terminal/status.json
python -m terminal.run calendar   -> data/terminal/calendar.json, data/terminal/attention.json
python -m terminal.run summary    -> data/terminal/summary.json
          │  commit to main
          ▼
pages.yml copies data/terminal into site/data and deploys site/ to GitHub Pages
```

Both data workflows share one concurrency group, so they never push at the same time, and both
end by calling `pages.yml`. A push that changes `site/` also redeploys.

**Failure handling.** Each source runs on its own. If a source fails, or its secret is missing,
it is skipped and marked red on the Status page with the error, and everything else keeps
working. Tiles whose source failed say so and link to Status. A fallback only runs when its
primary did not succeed.

**Degraded data.** Until the `BANXICO_TOKEN`, `FRED_API_KEY` and `WEBSTAT_CLIENT_ID` secrets are
added, the keyless backups run instead (Banxico's public chart endpoint, FRED's graph CSV, the ECB's
monthly French and German yields), and B3's DI curve is proxied by Tesouro LTN bonds. Every number
built on a substitute carries an amber **degraded** chip, and the Status page lists what is
degraded, why and how to fix it (`terminal/degraded.py`). Every feature lists its series best-first,
so when a secret is added the next data run writes the better series and tiles, charts, the book,
scenario calculators and crowd gauges switch to it with no edits. Add a secret under Settings >
Secrets and variables > Actions > New repository secret.

## Sources

| key | source | what | needs | tested from the build sandbox |
|---|---|---|---|---|
| `bcb_sgs` | BCB SGS | Selic target (432), PTAX USD/BRL (1), IPCA m/m (433) and 12m (13522) | | yes |
| `bcb_focus` | BCB Olinda Focus | annual expectations for IPCA, Selic, BRL, GDP, primary balance and net debt: median, mean, sd, min, max, respondents, every reference year | | yes |
| `tesouro` | Tesouro Direto daily CSV | longest fixed-rate bond (10-year proxy) and longest IPCA+ bond; the bond used each day is stored | | yes |
| `b3_di` | B3 reference rates (DI x pré) | DI1 Jan-27, Jan-29, Jan-31, interpolated on B3's daily curve; backfills 40 days per run to 2024 | | **no**: B3 times out from the sandbox; first verified on Actions |
| `banxico_api` | Banxico SIE API | FIX USD/MXN, target rate, TIIE 28d, 10-year auction yield, private-sector survey (inflation, GDP, year-end peso, public balance: median and sd) | `BANXICO_TOKEN` | written to the documented API, **untested** (no token here) |
| `banxico_public` | Banxico SIE public chart data | same series, keyless; runs only when the API did not | | yes |
| `webstat` | Banque de France Webstat | daily OAT and Bund 10-year, and the daily spread | `WEBSTAT_CLIENT_ID` | **untested**: Webstat is unreachable from the sandbox and the series keys need confirming |
| `ecb_monthly` | ECB Data Portal | France and Germany monthly 10-year yields and spread (the fallback for the spread tile) | | yes |
| `bundesbank` | Bundesbank | daily Bund 10-year | | yes |
| `aft_ratings` | Agence France Trésor | France credit ratings table | | **no**: AFT answers 403; the site shows `inputs/france_ratings.yaml` instead |
| `fred_api` | FRED API | US 10-year (DGS10), broad dollar (DTWEXBGS), Mexico monthly 10-year | `FRED_API_KEY` | untested (no key here) |
| `fred_public` | FRED graph CSV | same series, keyless fallback | | yes |
| `cftc` | CFTC Commitments of Traders | BRL (102741) and MXN (095741) futures: leveraged funds, asset managers, dealers, non-commercial net, open interest | | yes |
| `polymarket` | Polymarket | open markets tagged france, brazil, mexico (snapshot), plus full daily history for the top 15 per country | | yes |
| `kalshi` | Kalshi | open politics, elections, economics, financials and world markets mentioning the three countries, plus daily history | | yes (history rate-limited from the sandbox) |
| `calendar` | events.yaml, Fed, ECB, em-macro, GDELT | catalyst calendar and attention | | Fed, ECB and em-macro yes; GDELT partly (rate-limited) |

Add the secrets under the repository's Settings > Secrets and variables > Actions. Until then
those sources show red on the Status page and the keyless fallbacks carry the data.

## Catalyst calendar

* **Fiscal figures** in `data/terminal/inputs/fiscal_gap.yaml` are each checked against the official
  document (budget law, LDO/PLDO, Paquete Económico, PLF). A "verified" chip and a note on what was
  checked appear only where the document itself confirmed the number; otherwise the note says why not.
* **Hand-sourced events** in `data/terminal/inputs/events.yaml`, each with a source URL and marked
  **confirmed** (published by the institution or fixed in law) or **estimated** (from a rule or a
  past pattern). These cover France (S&P review 27 Nov 2026, the Article 47 budget deadline, the
  2027 presidential election), Brazil (Copom 2026-2027, the budget vote, the inauguration, the
  2028 budget guidelines) and Mexico (Banxico 2026 confirmed and 2027 estimated, USMCA rounds,
  consultation and the 1 Jul 2027 annual review, candidate registration, campaigns, the 6 Jun 2027
  midterms).
* **FOMC and ECB meetings** are scraped daily from federalreserve.gov and ecb.europa.eu.
* **Recurring releases** are generated by rule: Focus every Monday, the Banxico survey on the first
  business day of each month, and Brazil's bimonthly revenue and spending reports (by the 22nd).
* **Past events**: Brazil and Mexico rate decisions and elections imported from EthanC100/em-macro.

**Inauguration date.** Brazil's presidential inauguration is entered as **5 January 2027**, not 1
January. Constitutional Amendment 111/2021 moved it, starting with the president elected in 2026.

**Attention score.** For each event, the share of all GDELT-monitored articles matching its
keywords over the last 30 days, divided by the same share over the past 12 months. 1.0 means normal
coverage for those keywords, and 0.5 means half of normal. Each query is compared with its own
history, not with other queries. A first version compared queries with each other, which mostly
measured how broad their wording was, and it flagged every FOMC meeting. An event is
**under-attended** when its importance is 3, its score is below 0.5 and it is 30 or more days away.
For recurring meetings the 12-month normal includes past decision weeks, so scores sit below 1
between meetings. One 12-month GDELT call per query gives both shares, and daily results are kept
in `attention.json`.

## Editable tables

| file | what |
|---|---|
| `data/terminal/inputs/events.yaml` | catalysts, with source and confirmed or estimated |
| `data/terminal/inputs/fiscal_gap.yaml` | fiscal optimism gap: official target and independent estimates; survey medians fill in automatically |
| `data/terminal/inputs/evidence.yaml` | evidence badge and reason for each series |
| `data/terminal/inputs/france_ratings.yaml` | France ratings when the AFT table cannot be fetched |

Values marked `verified: false` show a "to verify" chip until you check them against their source.

## Running locally

```
pip install -e .[test]
python -m terminal.run all          # fetch every source, build the calendar and the summary
python -m terminal.run site         # copy data/terminal into site/data
cd site && python -m http.server    # open http://localhost:8000
pytest
```

Set `BANXICO_TOKEN`, `WEBSTAT_CLIENT_ID` and `FRED_API_KEY` in the environment to use those APIs.
`python -m terminal.run fetch --only bcb_sgs,cftc` runs selected sources.

## Data layout

```
data/terminal/series/<id>.json   metadata (source, source_id, source_url, unit, frequency, fetched_at,
                                 updated_at) and the full history, one observation per line.
                                 Histories are merged, never truncated.
data/terminal/markets/           Polymarket and Kalshi snapshots
data/terminal/status.json        every source: state, last attempt, last success, error, series written
data/terminal/calendar.json      upcoming events and imported past events
data/terminal/attention.json     GDELT share per query per day
data/terminal/summary.json       what the site reads first
data/book/config.yaml            paper book: capital, instruments, costs, durations, close times
data/book/state.json             positions, marks, equity curve, stats, benchmarks, systematic (rebuilt)
data/book/judgements.json        calls, updates, resolutions and scores (rebuilt)
data/book/journal.json           every record in date order (rebuilt)
data/trades/, data/judgements/   write-once form records
.github/ISSUE_TEMPLATE/          the five forms; .github/workflows/forms.yml processes them
terminal/                        the package: store, sources/, calendar, summary, book, forms, judgement, run
site/                            index.html, terminal.js, terminal.css (and lab/)
```

---

# Lab: the forecast panel

An aggregator of public forecasts on a fixed set of five geopolitical questions, logged daily,
combined with a track-record-weighted and extremized aggregate, and scored against outcomes and
against Polymarket.

### The questions

`data/tension_questions.yaml` is copied verbatim from
[EthanC100/gold-events](https://github.com/EthanC100/gold-events) (`data/tension_questions.yaml`)
and is the single source of the questions, their ids (`q1`-`q5`), their Polymarket markets and,
when they resolve, their outcomes. Keep it in sync with gold-events; do not edit it here.

| id | question | Polymarket market |
|---|---|---|
| q1 | US-Iran ceasefire still in effect on 31 December 2026? | US x Iran ceasefire continues through December 31? |
| q2 | Official Russia-Ukraine ceasefire agreed by 31 December 2026? | Russia x Ukraine ceasefire agreement by December 31, 2026? |
| q3 | Official Russia-Ukraine ceasefire agreed by 30 June 2027? | Russia x Ukraine ceasefire agreement by June 30, 2027? |
| q4 | Sudan ceasefire agreed by 31 December 2026? | Sudan civil war ceasefire by December 31, 2026? |
| q5 | US or Israeli strikes on Iranian territory resume by 31 March 2027? | Israel x Iran ceasefire continues through December 31? (inverted; no live market matches) |

### Sources

`data/source_map.yaml` maps each question to the non-Polymarket sources and records every wording
mismatch; the snapshot copies those notes into the log.

| source | what is logged | how | status |
|---|---|---|---|
| `polymarket` | P(Yes) of the market in the question file (`1 - P(Yes)` for `invert: true`) | gamma-api.polymarket.com | live |
| `metaculus` | recency-weighted community forecast of the matched binary question | `www.metaculus.com/api/posts/` (v2) | **untested**: the API answers HTTP 403 to anonymous calls ("only available to authenticated users"). The fetcher follows the documented API; set `METACULUS_TOKEN` (repo secret) and fill `post_id` per question in `source_map.yaml`. Until then the column is NaN with that reason in notes. When `post_id` is null and a token is present the fetcher auto-matches the top search hit and flags it `AUTO-MATCHED` for review. |
| `swift_centre` | the Swift Centre's published forecast where one covers the question | parsed from their Substack posts (`swiftcentre.substack.com/api/v1/posts/<slug>`, "Swift Centre Forecast: NN%") | live for q2 (22% on a 2026 Russia-Ukraine ceasefire, made January 2026, carried forward). No published number covers q1, q3, q4 or q5. Newer posts whose titles match a question's keywords are flagged in notes so the mapping can be updated. |
| `gjopen` | Good Judgment Open crowd forecast | parsed from the public question page's consensus table | live for q5 via GJO 5487 (IDF strike on Iran before 11 Dec 2026, a lower bound on our question). No GJO question covers q1-q4 as of 2026-10-28. |
| `my_prob` | the human forecast entered weekly in gold-events (`my_prob_<id>` in `data/forward_log.csv`) | read from a gold-events checkout (`GOLD_EVENTS_DIR`) or `GOLD_EVENTS_FORWARD_LOG`; carried forward until updated | live; blank so far in gold-events |
| `claude_prob` | `claude_prob_<id>` from the same file | same | the column does not exist in gold-events yet; logged as NaN with that note until it appears |

Every fetch failure is a NaN with the reason in the `notes` column, so one dead source never stops
the snapshot.

### Dashboard

A static, mobile-friendly site built from this repo, gold-events, tension-index and em-macro:
**https://ethanc100.github.io/forecast-panel/lab/** (GitHub Pages, redeployed by the daily workflow).

Pages:

* **This week**: one card per open question with the Polymarket probability over time (CLOB price
  history), every panel source's latest number, Claude's number, your past entries, and context (the
  tension index for conflict questions; poll average and odds for election questions, configured in
  `site/config.yaml`).
* **Blind mode** (toggle in the header, on by default): hides every other forecaster's number and the
  market chart on a question until you press "I've answered this week". The mark is stored in your
  browser (`localStorage`) for the current ISO week, so each Monday the cards are blind again.
* **Scorecard**: points per resolved question = 100 × (market Brier − your Brier), scored on the same
  Monday snapshots as `reports/scorecard.md`; running total over time; calibration chart; the same for
  Claude and the panel aggregate.
* **Countries** (Brazil, Mexico, France): 10-year yield, spread (over US Treasuries for Brazil and
  Mexico from em-macro's daily panel; over Germany for France from the ECB's monthly long-term rates,
  with the daily Bund yield from the Bundesbank), currency for Brazil and Mexico, upcoming events
  (`site/events.yaml`, hand-maintained with sources), recent rate decisions, and the em-macro risk
  model's fair value, factor breakdown and most similar past cases once em-macro publishes
  `results/risk_model/{fair_value,factors,similar_cases}.csv` (until then: "model not yet built").
* **Indicators**: tension index (last 90 days) and the gold model's weekly expected move.

#### How to open it

* On the web: https://ethanc100.github.io/forecast-panel/lab/ (light/dark follows your device; the
  header button overrides it).
* Locally: `python build_site.py` writes `site/lab/data.js`, then open `site/lab/index.html` in a browser
  (no server needed). Set `GOLD_EVENTS_DIR`, `TENSION_INDEX_DIR`, `EM_MACRO_DIR` to read sibling
  checkouts instead of GitHub.

#### How your entries flow in

1. Each Monday gold-events appends a row to `data/forward_log.csv`. Fill in `my_prob_q1`..`my_prob_q5`
   (and `my_tension_score`) on that row and push; Claude's `claude_prob_*` columns sit beside them.
2. The daily workflow here (06:17 UTC) reads that file, carries the last non-blank value forward,
   logs it in `data/panel_log.csv` as `my_prob` / `claude_prob`, rebuilds `site/data.js`, commits, and
   deploys `site/` to GitHub Pages. A push to `main` also redeploys.
3. On Mondays the run also rebuilds the aggregate log and scorecard, which is what the dashboard's
   Scorecard page shows once questions resolve (outcomes come from `data/tension_questions.yaml`).

The site has no backend and no dependencies: `site/lab/index.html`, `site/lab/app.js` (hash routing, SVG
charts with crosshair tooltips and data tables) and `site/style.css`.

### Files

```
data/tension_questions.yaml   the questions (copied from gold-events; single source of ids and outcomes)
data/source_map.yaml          per-question mapping to Metaculus / Swift Centre / GJ Open, with mismatch notes
data/method.yaml              aggregation parameters (extremizing a, Brier floor, ...)
data/panel_log.csv            one row per (date, question_id, source): prob, as_of, ref, notes
data/aggregate_log.csv        plain and extremized aggregate per (date, question), with the weights used
data/validation_summary.json  machine-readable result of validate.py
reports/panel_latest.md       the latest snapshot as a table, with all notes
reports/scorecard.md          Brier of every source and the aggregates on resolved questions (Monday runs)
reports/validation.md         does extremizing improve Brier on resolved historical questions?
reports/method.md             the aggregation rule, with references to the Good Judgment Project findings
site/                         the dashboard (index.html, app.js, style.css, config.yaml, events.yaml, data.js built daily)
forecast_panel/               the package: sources.py, panel.py, aggregate.py, scoring.py, validate.py, site_build.py
snapshot.py / score.py / validate.py / build_site.py   entry points
.github/workflows/panel.yml   daily snapshot, Monday scoring, site build, commit, GitHub Pages deploy
```

### Running

```
pip install -e .[test]
GOLD_EVENTS_DIR=../gold-events python snapshot.py     # today's row for every source and question
python score.py                                        # rebuild data/aggregate_log.csv and reports/scorecard.md
python validate.py                                     # reports/validation.md (Metaculus API with METACULUS_TOKEN, else Autocast)
pytest
```

### Schedule

`.github/workflows/panel.yml` runs daily at 06:17 UTC: it checks out gold-events (public; the
`GOLD_EVENTS_TOKEN` secret is only needed if it goes private), snapshots every source, on Mondays (or
a manual dispatch) rebuilds the aggregate log and scorecard, builds `site/data.js`, commits, and
deploys the site to GitHub Pages. Add `METACULUS_TOKEN` as a secret to turn the Metaculus column on.

The human columns are entered weekly in gold-events and carried forward until updated. **Scoring uses
the Monday snapshot**, so every forecaster is compared on the same day; a week whose Monday run
failed uses its first available day and the scorecard says so.

### Aggregation

Track-record-weighted mean with the GJP extremizing transform (`reports/method.md`):

* weights start equal; once questions resolve each source is weighted by `1 / Brier` over the
  resolved questions (unscored sources are weighted as if their Brier were 0.25, the score of a flat
  50%; Brier floored at 0.01);
* the weighted mean `p` is extremized to `p^a / (p^a + (1-p)^a)`, i.e. its log-odds are multiplied
  by `a = 1.5`; both the plain and the extremized aggregate are logged and scored.

#### Validation on history (`reports/validation.md`)

Before applying the rule live it was checked on resolved binary geopolitical questions with their
community forecast histories, read at 25%, 50%, 75% of each question's life and at close, with `a`
chosen on half the questions and scored on the other half.

The Metaculus API refused anonymous calls, so the run used the Metaculus and Good Judgment Open
subsets of the Autocast dataset (Zou et al. 2022; 2015-2022; tagged geopolitics, politics, conflict
or elections). With `METACULUS_TOKEN` set, `validate.py` pulls resolved geopolitics questions from
the API instead (documented, untested path).

| panel | questions | Brier a=1 | Brier a=1.5 | best a | held-out change |
|---|---:|---:|---:|---:|---:|
| Metaculus community forecast | 416 | 0.1239 | 0.1192 | 1.5 | -0.0048 (bootstrap 95% interval -0.0084 to -0.0008) |
| Good Judgment Open crowd | 606 | 0.0959 | 0.1008 | 1.0 | 0 (any a > 1 hurts; +0.0050 at a = 1.5) |

So extremizing the Metaculus community forecast helps, consistently across the life of a question
and in both cross-validation folds, and the calibration table shows why: the community is
under-confident (forecasts of 0.2-0.3 resolve Yes 11% of the time, 0.7-0.8 resolve Yes 82%). The
GJO crowd is already slightly over-confident at the extremes and extremizing it hurts. That is why
the live `a` is the low end of the GJP range and the plain aggregate is always reported alongside.

### Scorecard

`reports/scorecard.md` compares every source and both aggregates on resolved questions by Brier,
with a head-to-head against Polymarket on the same (week, question) pairs for sources that cover
only some questions. No question has resolved yet, so it currently shows coverage, the equal
weights in force and the latest aggregate.

### Known gaps

* Metaculus: no token in this environment, so the column is empty and the fetcher and the API
  validation path are untested. The source map has `search` strings but no `post_id`s; match the
  questions by hand once a token is available and record the wording differences in `note`.
* Swift Centre and GJ Open cover one question each; the others are logged as NaN with the reason.
* `claude_prob` is read from gold-events but that column does not exist there yet.
* France has no free daily 10-year yield source reachable from the build (stooq and the AFT site are
  blocked), so the France yield and the spread over Germany are the ECB's monthly series; the Bund is
  daily. Upcoming events in `site/events.yaml` marked `confirmed: false` need checking against the
  official calendars.
