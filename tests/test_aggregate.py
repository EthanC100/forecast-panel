import math

import numpy as np

from forecast_panel.aggregate import aggregate, brier, extremize, weights


def test_brier():
    assert brier([0.5, 0.5], [0, 1]) == 0.25
    assert brier([1.0, 0.0], [1, 0]) == 0.0
    assert math.isnan(brier([], []))


def test_extremize_identity_and_symmetry():
    assert abs(extremize(0.3, 1.0) - 0.3) < 1e-12
    assert abs(extremize(0.5, 3.0) - 0.5) < 1e-12
    assert abs(extremize(0.3, 1.5) + extremize(0.7, 1.5) - 1.0) < 1e-12
    assert extremize(0.7, 1.5) > 0.7 and extremize(0.3, 1.5) < 0.3
    # log-odds are multiplied by a
    p = 0.8
    lo = math.log(p / (1 - p)) * 2.0
    assert abs(extremize(p, 2.0) - 1 / (1 + math.exp(-lo))) < 1e-12
    # clipping keeps 0 and 1 finite
    out = extremize(np.array([0.0, 1.0]), 2.0)
    assert 0 < out[0] < out[1] < 1


def test_weights_equal_until_resolution_then_inverse_brier():
    w = weights({"a": float("nan"), "b": float("nan")})
    assert w["a"] == w["b"]
    w = weights({"a": 0.1, "b": float("nan"), "c": 0.0})
    assert w["a"] == 10.0 and w["b"] == 4.0 and w["c"] == 100.0  # floor 0.01


def test_aggregate_uses_available_sources_only():
    probs = {"a": 0.2, "b": float("nan"), "c": 0.6}
    plain, ext, used = aggregate(probs, {"a": 1.0, "b": 1.0, "c": 3.0}, a=1.5)
    assert set(used) == {"a", "c"}
    assert abs(plain - (0.25 * 0.2 + 0.75 * 0.6)) < 1e-12
    assert abs(ext - extremize(plain, 1.5)) < 1e-12
    plain, ext, used = aggregate({"a": float("nan")}, {"a": 1.0}, a=1.5)
    assert math.isnan(plain) and used == {}
