# Validation of the extremizing rule on history

_Generated 2026-10-28._

Autocast dataset (Metaculus API refused anonymous calls): resolved true/false questions tagged geopolitics/politics/conflict/elections, community forecast time series as shipped by Zou et al. 2022.

For every resolved question the community forecast is read at 25%, 50%, 75% of its open period and
at close. Each point is extremized by multiplying its log-odds by `a` and scored by Brier against the
outcome. `a = 1` is the untouched community forecast. The cross-validated row picks `a` on half of the
questions (split by a hash of the question id) and scores it on the other half, both ways round.

## autocast_metaculus

- questions: 416 (closing 2016-2022), base rate of Yes 0.35, sampled points: 1658

Brier by extremizing exponent `a` (columns) and point in the question's life (rows):

| point | n | a=1 | a=1.25 | a=1.5 | a=1.75 | a=2 | a=2.5 | a=3 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 25% of life | 412 | 0.1575 | **0.1559** | 0.1566 | 0.1585 | 0.1610 | 0.1668 | 0.1725 |
| 50% of life | 414 | 0.1322 | 0.1283 | **0.1269** | 0.1269 | 0.1278 | 0.1307 | 0.1340 |
| 75% of life | 416 | 0.1170 | 0.1126 | 0.1108 | **0.1105** | 0.1111 | 0.1135 | 0.1164 |
| close | 416 | 0.0894 | 0.0850 | 0.0829 | 0.0821 | **0.0820** | 0.0831 | 0.0846 |
| all points | 1658 | 0.1239 | 0.1203 | **0.1192** | 0.1194 | 0.1204 | 0.1234 | 0.1267 |

- best `a` over all points: **1.5**; Brier change vs raw: -0.0046 (95% bootstrap interval over questions -0.0084 to -0.0008)
- `a = 1.5`: Brier change vs raw -0.0046 (-0.0084 to -0.0008)
- cross-validated: `a` chosen per fold = {0: 1.5, 1: 1.5}; held-out Brier raw 0.1239 vs extremized 0.1192 (-0.0048)

Calibration of the raw community forecast (observed frequency beyond the bin on both ends is
under-confidence, which is what extremizing corrects):

| forecast bin | n | mean forecast | observed |
|---|---:|---:|---:|
| 0.0-0.1 | 262 | 0.038 | 0.008 |
| 0.1-0.2 | 212 | 0.133 | 0.061 |
| 0.2-0.3 | 207 | 0.234 | 0.106 |
| 0.3-0.4 | 198 | 0.335 | 0.167 |
| 0.4-0.5 | 153 | 0.433 | 0.320 |
| 0.5-0.6 | 140 | 0.536 | 0.493 |
| 0.6-0.7 | 121 | 0.637 | 0.545 |
| 0.7-0.8 | 115 | 0.733 | 0.817 |
| 0.8-0.9 | 110 | 0.832 | 0.882 |
| 0.9-1.0 | 140 | 0.947 | 0.993 |

## autocast_gjopen

- questions: 606 (closing 2015-2022), base rate of Yes 0.20, sampled points: 2424

Brier by extremizing exponent `a` (columns) and point in the question's life (rows):

| point | n | a=1 | a=1.25 | a=1.5 | a=1.75 | a=2 | a=2.5 | a=3 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 25% of life | 606 | **0.1222** | 0.1250 | 0.1284 | 0.1318 | 0.1348 | 0.1399 | 0.1438 |
| 50% of life | 606 | **0.1038** | 0.1065 | 0.1096 | 0.1125 | 0.1151 | 0.1195 | 0.1229 |
| 75% of life | 606 | **0.0893** | 0.0911 | 0.0933 | 0.0952 | 0.0970 | 0.1000 | 0.1025 |
| close | 606 | **0.0683** | 0.0700 | 0.0717 | 0.0733 | 0.0746 | 0.0767 | 0.0783 |
| all points | 2424 | **0.0959** | 0.0982 | 0.1008 | 0.1032 | 0.1054 | 0.1090 | 0.1119 |

- best `a` over all points: **1**; Brier change vs raw: -0.0000 (95% bootstrap interval over questions -0.0000 to +0.0000)
- `a = 1.5`: Brier change vs raw +0.0050 (+0.0025 to +0.0077)
- cross-validated: `a` chosen per fold = {0: 1.0, 1: 1.0}; held-out Brier raw 0.0959 vs extremized 0.0959 (-0.0000)

Calibration of the raw community forecast (observed frequency beyond the bin on both ends is
under-confidence, which is what extremizing corrects):

| forecast bin | n | mean forecast | observed |
|---|---:|---:|---:|
| 0.0-0.1 | 1424 | 0.026 | 0.051 |
| 0.1-0.2 | 309 | 0.126 | 0.091 |
| 0.2-0.3 | 117 | 0.226 | 0.265 |
| 0.3-0.4 | 82 | 0.335 | 0.256 |
| 0.4-0.5 | 60 | 0.436 | 0.517 |
| 0.5-0.6 | 52 | 0.527 | 0.500 |
| 0.6-0.7 | 63 | 0.641 | 0.429 |
| 0.7-0.8 | 74 | 0.744 | 0.568 |
| 0.8-0.9 | 77 | 0.837 | 0.792 |
| 0.9-1.0 | 166 | 0.958 | 0.867 |

