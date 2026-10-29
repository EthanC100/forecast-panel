# Crowd lab tests

Generated 2026-10-29T15:54:17Z by `python -m terminal.labtests` from em-macro (https://raw.githubusercontent.com/EthanC100/em-macro/main/). Fit = events to 2021-12-31, hold-out = 2022 onward; one-sided permutation tests (20,000 draws). Moves are |abnormal day-1 move| / normal daily sd, averaged over FX and 10y where both exist.

Badge rule, fixed in advance: **Tested-leads** if the fit effect is positive with p < 0.05 and the hold-out effect has the same sign with p < 0.10; **Tested-no-lead** if the test ran and that is not met; **Untested** if it could not be run.

em-macro's event-move file covers six of the 13 countries (Brazil, Mexico, Poland, Turkey, South Africa, Indonesia), rate decisions and elections only, so tests that need market moves use those six.

## (a) Poll vs prediction-market gap: tested_no_lead

|gap| vs size of the poll miss: rho -0.141, p=0.7152, n=18; vs FX move: rho 0.238, n=8. Small sample: a lead of moderate size could be missed.

Poll-implied P(A wins) = Phi(final poll margin / sigma), sigma = RMS of (actual - poll margin) over earlier elections in the same country (3+), else all earlier elections; market P from the recorded pre-vote odds. No parameter is fitted on the outcomes, so every point is out of sample; there is no separate hold-out because there are too few elections with odds.

* Elections with polls and recorded odds: 18 (with an em-macro FX move: 8).
* |gap| vs size of the poll miss: rho -0.141, p=0.7152.
* |gap| vs day-1 move: rho 0.238, p=0.3016, n=8.
* Brier: market 0.187, poll-implied 0.178 (lower is better).
* They disagreed on the favourite 1 times; the market was right 1.

| election | date | P(A) polls | P(A) market | gap | A won | poll miss (pp) | FX move (sd) |
|---|---|---|---|---|---|---|---|
| Chile 2005 presidential election r1 | 2005-12-11 | 0.968 | 0.642 | -0.33 | yes | 0.97 | – |
| Chile 2005 presidential election r2 | 2006-01-15 | 0.779 | 0.843 | +0.07 | yes | 0.58 | – |
| United Kingdom 2014 Scottish independence referendum r1 | 2014-09-18 | 0.836 | 0.81 | -0.03 | yes | 5.7 | – |
| United Kingdom 2016 EU membership referendum r1 | 2016-06-23 | 0.773 | 0.86 | +0.09 | no | 7.78 | – |
| Italy 2016 constitutional referendum r1 | 2016-12-04 | 0.901 | 0.746 | -0.15 | yes | 12.86 | – |
| Poland 2020 presidential election r2 | 2020-07-12 | 0.517 | 0.625 | +0.11 | yes | 1.72 | 0.23 |
| France 2022 presidential election r2 | 2022-04-24 | 1.0 | 0.926 | -0.07 | yes | 6.64 | – |
| Brazil 2022 general election r2 | 2022-10-30 | 0.669 | 0.664 | -0.01 | yes | 2.2 | 2.05 |
| Turkey 2023 Turkish presidential and parliamentary elections r1 | 2023-05-14 | 0.693 | 0.61 | -0.08 | no | 8.64 | 0.22 |
| Turkey 2023 Turkish presidential election (run-off) r2 | 2023-05-28 | 0.599 | 0.851 | +0.25 | yes | 2.36 | 0.07 |
| Mexico 2024 general election r1 | 2024-06-02 | 0.869 | 0.89 | +0.02 | yes | 16.07 | 3.74 |
| Poland 2025 presidential election r2 | 2025-06-01 | 0.532 | 0.577 | +0.04 | no | 2.38 | 2.19 |
| Chile 2025 presidential election r1 | 2025-11-16 | 0.876 | 0.945 | +0.07 | yes | 5.1 | – |
| Chile 2025 presidential election r2 | 2025-12-14 | 0.996 | 0.985 | -0.01 | yes | 1.59 | – |
| Colombia 2026 presidential election r1 | 2026-05-31 | 0.765 | 0.757 | -0.01 | no | 11.46 | – |
| Colombia 2026 presidential election r2 | 2026-06-21 | 0.707 | 0.864 | +0.16 | yes | 5.49 | – |
| Brazil 2026 general election r1 | 2026-10-04 | 0.543 | 0.367 | -0.18 | no | 2.81 | 3.96 |
| Brazil 2026 general election r2 | 2026-10-25 | 0.506 | 0.804 | +0.30 | no | 3.7 | – |

## (c) Survey dispersion: tested_leads

BR: tested_leads - move size: tested_no_lead (fit effect not significant (fit diff +0.26 sd, p=0.0669; hold-out diff +0.40 sd, p=0.0127)); miss vs survey median: tested_leads (fit p=0.0003, hold-out p=0.0071); MX: tested_no_lead - move size: tested_no_lead (fit effect not significant (fit diff +0.08 sd, p=0.2819; hold-out diff +0.19 sd, p=0.1307)); miss vs survey median: untested (only 1 extreme readings in the fit period (need 8))

**BR** – Focus sd of the Selic expected for that meeting, percentile vs the previous 40 meetings; extreme = percentile >= 80; 149 decisions.

* move size: fit 23 extreme vs 88 normal: 1.071 vs 0.809 (p=0.0669); hold-out 8 extreme vs 30 normal: 1.038 vs 0.634 (p=0.0127) → tested_leads (move size: tested_no_lead (fit effect not significant (fit diff +0.26 sd, p=0.0669; hold-out diff +0.40 sd, p=0.0127)); miss vs survey median: tested_leads (fit p=0.0003, hold-out p=0.0071))
* miss vs survey (bp): fit 23 extreme vs 88 normal: 15.217 vs 3.977 (p=0.0003); hold-out 8 extreme vs 30 normal: 9.375 vs 0.0 (p=0.0071)

**MX** – Banxico survey sd of current-year inflation, percentile vs the same month +/-1 over 10 years; extreme = percentile >= 80; 187 decisions.

* move size: fit 22 extreme vs 127 normal: 0.876 vs 0.8 (p=0.2819); hold-out 13 extreme vs 25 normal: 0.913 vs 0.721 (p=0.1307) → tested_no_lead (move size: tested_no_lead (fit effect not significant (fit diff +0.08 sd, p=0.2819; hold-out diff +0.19 sd, p=0.1307)); miss vs survey median: untested (only 1 extreme readings in the fit period (need 8)))
* miss vs survey (bp): fit 1 extreme vs 17 normal: 25.0 vs 4.412 (p=0.1638); hold-out 4 extreme vs 8 normal: 6.25 vs 6.25 (p=0.743)

Reading this result: part of the 'miss vs survey' effect is mechanical (when forecasters disagree, more of them are away from the median, so the decision is more likely to differ from it). The move-size result, which is about markets rather than the survey itself, is weaker in the fit period (p≈0.07 for Brazil) and stronger in the hold-out. The Banxico reading uses inflation-forecast dispersion because the survey's rate expectations are not available keylessly, so it measures a less direct disagreement.

**Pooled** move size: fit 45 extreme vs 215 normal: 0.976 vs 0.804 (p=0.0621); hold-out 21 extreme vs 55 normal: 0.961 vs 0.673 (p=0.0076)

**Pooled** miss vs survey (bp): fit 24 extreme vs 105 normal: 15.625 vs 4.048 (p=0.0002); hold-out 12 extreme vs 38 normal: 8.333 vs 1.316 (p=0.0253)

## (e) CFTC positioning: tested_no_lead

leveraged funds (the gauge as shown): fit effect not significant (fit diff +0.16 sd, p=0.0942; hold-out diff +0.05 sd, p=0.3659). Legacy non-commercial (robustness): fit effect not significant (fit diff +0.04 sd, p=0.2861; hold-out diff +0.09 sd, p=0.2975)

**lev_money_net** – lev_money_net / open interest, percentile vs the previous 156 weekly reports (released Friday, used only for events after release); extreme = percentile <= 10 or >= 90; 350 events {'BR': 115, 'MX': 176, 'ZA': 59}.

* FX move size: fit 52 extreme vs 186 normal: 0.98 vs 0.819 (p=0.0942); hold-out 28 extreme vs 84 normal: 0.799 vs 0.748 (p=0.3659) → tested_no_lead
* mean move against the crowd after extreme readings (sd, + = against): {'fit': 0.059, 'hold-out': -0.244}

**noncomm_net** – noncomm_net / open interest, percentile vs the previous 156 weekly reports (released Friday, used only for events after release); extreme = percentile <= 10 or >= 90; 533 events {'BR': 188, 'MX': 206, 'ZA': 139}.

* FX move size: fit 145 extreme vs 276 normal: 0.847 vs 0.803 (p=0.2861); hold-out 27 extreme vs 85 normal: 0.826 vs 0.74 (p=0.2975) → tested_no_lead
* mean move against the crowd after extreme readings (sd, + = against): {'fit': -0.065, 'hold-out': -0.144}

## Not tested

* (b) pollster concentration and house effects, (d) official optimism gap and (f) forced-flow thresholds are shown as Context or Untested on the Crowd page; they were not part of this test.
