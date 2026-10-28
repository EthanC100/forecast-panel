# forecast-panel

An aggregator of public forecasts on a fixed set of five geopolitical questions, logged daily,
combined with a track-record-weighted and extremized aggregate, and scored against outcomes and
against Polymarket.

## The questions

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

## Sources

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

## Files

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
forecast_panel/               the package: sources.py, panel.py, aggregate.py, scoring.py, validate.py
snapshot.py / score.py / validate.py   entry points
.github/workflows/panel.yml   daily snapshot, Monday scoring, commits the results
```

## Running

```
pip install -e .[test]
GOLD_EVENTS_DIR=../gold-events python snapshot.py     # today's row for every source and question
python score.py                                        # rebuild data/aggregate_log.csv and reports/scorecard.md
python validate.py                                     # reports/validation.md (Metaculus API with METACULUS_TOKEN, else Autocast)
pytest
```

## Schedule

`.github/workflows/panel.yml` runs daily at 06:17 UTC: it checks out gold-events (secret
`GOLD_EVENTS_TOKEN`, a fine-grained PAT with read access to that private repo; without it the human
columns are NaN), snapshots every source, and on Mondays (or a manual dispatch) rebuilds the
aggregate log and scorecard. It commits `data/*.csv` and `reports/*.md`. Add `METACULUS_TOKEN` as a
secret to turn the Metaculus column on.

The human columns are entered weekly in gold-events and carried forward until updated. **Scoring uses
the Monday snapshot**, so every forecaster is compared on the same day; a week whose Monday run
failed uses its first available day and the scorecard says so.

## Aggregation

Track-record-weighted mean with the GJP extremizing transform (`reports/method.md`):

* weights start equal; once questions resolve each source is weighted by `1 / Brier` over the
  resolved questions (unscored sources are weighted as if their Brier were 0.25, the score of a flat
  50%; Brier floored at 0.01);
* the weighted mean `p` is extremized to `p^a / (p^a + (1-p)^a)`, i.e. its log-odds are multiplied
  by `a = 1.5`; both the plain and the extremized aggregate are logged and scored.

### Validation on history (`reports/validation.md`)

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

## Scorecard

`reports/scorecard.md` compares every source and both aggregates on resolved questions by Brier,
with a head-to-head against Polymarket on the same (week, question) pairs for sources that cover
only some questions. No question has resolved yet, so it currently shows coverage, the equal
weights in force and the latest aggregate.

## Known gaps

* Metaculus: no token in this environment, so the column is empty and the fetcher and the API
  validation path are untested. The source map has `search` strings but no `post_id`s; match the
  questions by hand once a token is available and record the wording differences in `note`.
* Swift Centre and GJ Open cover one question each; the others are logged as NaN with the reason.
* `claude_prob` is read from gold-events but that column does not exist there yet.
* gold-events is private, so the workflow needs `GOLD_EVENTS_TOKEN` to read the human columns.
