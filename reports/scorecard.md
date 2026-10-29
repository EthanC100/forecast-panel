# Scorecard (regenerated 2026-10-29)

Brier score (mean squared error, lower is better; 0.25 is a flat 50%) of every source and of the
track-record-weighted aggregate on the questions that have resolved. Each forecaster is scored on
the Monday snapshot of every week before the question's resolution date, so all of them are
compared on the same days. See reports/method.md for the aggregation rule.

- Weekly scoring snapshots logged: 1 (2026-10-28 to 2026-10-28) (weeks without a Monday snapshot use their first day: 2026-10-28)
- Questions resolved: 0 of 5

## Brier by forecaster

`n` counts scored (Monday, question) pairs. The head-to-head columns re-score the forecaster and
Polymarket on the pairs where both have a value, so a thinly covered source is not flattered or
punished by the questions it skipped.

| forecaster | n | Brier | n (vs Polymarket) | Brier | Polymarket Brier |
|---|---:|---:|---:|---:|---:|
| polymarket | 0 |  | 0 |  |  |
| metaculus | 0 |  | 0 |  |  |
| swift_centre | 0 |  | 0 |  |  |
| gjopen | 0 |  | 0 |  |  |
| my_prob | 0 |  | 0 |  |  |
| claude_prob | 0 |  | 0 |  |  |
| aggregate_plain | 0 |  | 0 |  |  |
| aggregate_extremized | 0 |  | 0 |  |  |

## Weights in force

Inverse Brier over resolved questions, floored at 0.01; a source with no resolved
track record is weighted as if its Brier were 0.25 (equal weights until anything
resolves). Extremizing exponent a = 1.5. Weights are renormalised over the sources
that have a value on the day.

| source | track-record Brier | weight (normalised over all six) |
|---|---:|---:|
| polymarket |  | 0.167 |
| metaculus |  | 0.167 |
| swift_centre |  | 0.167 |
| gjopen |  | 0.167 |
| my_prob |  | 0.167 |
| claude_prob |  | 0.167 |

## Latest aggregate (2026-10-29)

| id | question | plain | extremized | sources | weights used |
|---|---|---:|---:|---:|---|
| q1 | US-Iran ceasefire still in effect on 31 December 2026? | 0.2925 | 0.2100 | 2 | `{"claude_prob": 0.5, "polymarket": 0.5}` |
| q2 | Official Russia-Ukraine ceasefire agreed by 31 December 2026? | 0.1650 | 0.0807 | 3 | `{"claude_prob": 0.3333, "polymarket": 0.3333, "swift_centre": 0.3333}` |
| q3 | Official Russia-Ukraine ceasefire agreed by 30 June 2027? | 0.4975 | 0.4963 | 2 | `{"claude_prob": 0.5, "polymarket": 0.5}` |
| q4 | Sudan ceasefire agreed by 31 December 2026? | 0.0875 | 0.0288 | 2 | `{"claude_prob": 0.5, "polymarket": 0.5}` |
| q5 | US or Israeli strikes on Iranian territory resume by 31 March 2027? | 0.5798 | 0.6185 | 3 | `{"claude_prob": 0.3333, "gjopen": 0.3333, "polymarket": 0.3333}` |

