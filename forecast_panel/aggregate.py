"""Track-record-weighted aggregation with the GJP extremizing transform. See reports/method.md.

* ``brier``      mean squared error of probabilities against 0/1 outcomes.
* ``weights``    1 / Brier per source over the questions resolved so far; equal weights until
                 anything has resolved (every unscored source is treated as if its Brier were
                 ``unscored_brier``, the score of a flat 50%).
* ``extremize``  p -> p^a / (p^a + (1-p)^a), i.e. multiply the log-odds by ``a`` (Satopaa et al.
                 2014; Baron et al. 2014). a = 1 leaves the forecast alone.
* ``aggregate``  weighted mean of the available sources, plain and extremized.
"""

from __future__ import annotations

import math

import numpy as np


def brier(p, y) -> float:
    p = np.asarray(p, dtype=float)
    y = np.asarray(y, dtype=float)
    if p.size == 0:
        return float("nan")
    return float(np.mean((p - y) ** 2))


def clip(p, lo: float = 0.01):
    return np.clip(np.asarray(p, dtype=float), lo, 1.0 - lo)


def extremize(p, a: float, lo: float = 0.01):
    """Logit extremizing: multiply the log-odds of p by a (a > 1 pushes away from 0.5)."""
    p = clip(p, lo)
    num = p ** a
    out = num / (num + (1.0 - p) ** a)
    return float(out) if np.ndim(out) == 0 else out


def weights(track: dict[str, float], floor: float = 0.01, unscored_brier: float = 0.25) -> dict[str, float]:
    """Inverse-Brier weights. ``track`` maps source -> Brier over resolved questions (NaN if none)."""
    out = {}
    for s, b in track.items():
        if b is None or (isinstance(b, float) and math.isnan(b)):
            b = unscored_brier
        out[s] = 1.0 / max(float(b), floor)
    return out


def aggregate(probs: dict[str, float], w: dict[str, float], a: float, lo: float = 0.01,
              min_sources: int = 1) -> tuple[float, float, dict[str, float]]:
    """(plain weighted mean, extremized, normalised weights used) over sources with a value."""
    avail = {s: p for s, p in probs.items() if p is not None and not math.isnan(p)}
    if len(avail) < max(1, min_sources):
        return float("nan"), float("nan"), {}
    ws = {s: w.get(s, 1.0 / 0.25) for s in avail}
    tot = sum(ws.values())
    ws = {s: v / tot for s, v in ws.items()}
    plain = sum(ws[s] * avail[s] for s in avail)
    return float(plain), float(extremize(plain, a, lo)), ws
