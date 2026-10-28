# Aggregation method

The panel's aggregate on each question is a **track-record-weighted mean** of the sources that have
a value that day, reported **plain** and **extremized**. Parameters live in `data/method.yaml`; the
code is `forecast_panel/aggregate.py` and the weights are re-derived every Monday by
`forecast_panel/scoring.py`.

## 1. Weights

Let `B_s` be source `s`'s Brier score over the resolved questions, computed on the weekly scoring
snapshots (the Monday snapshot of each week, strictly before the question's resolution date).

```
w_s = 1 / max(B_s, 0.01)                 for a source with a resolved track record
w_s = 1 / 0.25 = 4                       for a source with none yet (the Brier of a flat 50%)
p_plain = sum_s w_s p_s / sum_s w_s      over the sources with a value on the day
```

Until any question has resolved every source has `B_s` undefined, so the weights are equal. After the
first resolution a source that has been scored moves above the unscored ones if it beat a coin flip
and below them if it did not. The floor stops a lucky perfect score from taking over.

With five questions the track record will stay thin for a long time, so the weights will be noisy.
That is a known cost of inverse-Brier weighting on small samples; the Good Judgment Project (GJP)
found that weighting by past accuracy helped, but the gain over an unweighted mean of *good*
forecasters was modest compared with the gain from extremizing (Ungar et al. 2012; Mellers et al.
2014). The plain aggregate is therefore always reported next to the extremized one, and the
scorecard scores both.

## 2. Extremizing

The weighted mean is pushed away from 0.5 by multiplying its log-odds by `a`:

```
p_ext = p^a / (p^a + (1 - p)^a)          equivalently  logit(p_ext) = a * logit(p)
```

with `p` first clipped to `[0.01, 0.99]`. `a = 1` is the identity. This is the transform used by the
GJP team: Satopää et al. (2014) derive it from a logit model in which each forecaster sees only part
of the available information, so the mean of their probabilities is under-confident even when every
individual is calibrated; Baron et al. (2014) give the two reasons (partial information and
individual under-confidence) and report that `a` between about 1.5 and 3 improved the Brier score
of GJP aggregates, more for larger crowds and for forecasts further from resolution. Tetlock and
Gardner (2015, ch. 9) describe the same step in plain words.

The live value is **`a = 1.5`**, the low end of the GJP range, for two reasons:

* every input here is already an aggregate (a market price, a community median, a crowd forecast,
  a team's published number), not an individual forecaster, so the partial-information argument is
  weaker than it was for GJP's individual forecasters and some of the under-confidence has already
  been squeezed out;
* the historical check in `reports/validation.md` (`python validate.py`) found `a = 1.5` best for the
  Metaculus community forecast on 416 resolved geopolitical questions (Brier 0.1239 to 0.1192,
  held-out, bootstrap interval of the improvement excluding zero), while the Good Judgment Open crowd
  forecast on 606 questions was slightly *over*-confident and any `a > 1` made it worse. The sign of
  the effect depends on the source, so a modest `a` is the safe choice and the plain aggregate is
  always shown alongside it.

Caveat: on a day when only one source has a value (today, Polymarket alone on three of the five
questions), "extremized aggregate" means "extremized market price". The validation evidence for that
is the Metaculus panel only; the GJO panel says the opposite. Treat the extremized number as the
headline only once two or more sources contribute.

## 3. Scoring

`reports/scorecard.md` is rebuilt by every Monday run. For each forecaster (the six sources and the
two aggregates) it reports the Brier score over all scored (week, question) pairs and, because the
sources cover different questions, a head-to-head Brier against Polymarket restricted to the pairs
where both have a value. Scoring uses the Monday snapshot so every forecaster is compared on the same
day; a week whose Monday run failed uses its first available day and says so.

Outcomes come only from `resolved` / `outcome` in `data/tension_questions.yaml` (the gold-events
file). A question is scored on every weekly snapshot dated before `resolved_on` (if set) or else
`resolution_date`.

## References

* Satopää, V. A., Baron, J., Foster, D. P., Mellers, B. A., Tetlock, P. E., Ungar, L. H. (2014).
  Combining multiple probability predictions using a simple logit model. *International Journal of
  Forecasting* 30(2), 344-356.
* Baron, J., Mellers, B. A., Tetlock, P. E., Ungar, L. H. (2014). Two reasons to make aggregated
  probability forecasts more extreme. *Decision Analysis* 11(2), 133-145.
* Ungar, L., Mellers, B., Satopää, V., Tetlock, P., Baron, J. (2012). The Good Judgment Project: a
  large scale test of different methods of combining expert predictions. *AAAI Fall Symposium:
  Machine Aggregation of Human Judgment*.
* Mellers, B. et al. (2014). Psychological strategies for winning a geopolitical forecasting
  tournament. *Psychological Science* 25(5), 1106-1115.
* Tetlock, P. E., Gardner, D. (2015). *Superforecasting: The Art and Science of Prediction*. Crown.
* Zou, A., Xiao, T., Jia, R., Kwon, J., Mazeika, M., Li, R., Song, D., Steinhardt, J., Evans, O.,
  Hendrycks, D. (2022). Forecasting Future World Events with Neural Networks. *NeurIPS* (the Autocast
  dataset used by `validate.py` when the Metaculus API is not reachable).
