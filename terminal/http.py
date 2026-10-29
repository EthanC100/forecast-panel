"""HTTP GET with retries and a polite back-off. Every source goes through this."""

from __future__ import annotations

import time

import requests

UA = "forecast-panel-terminal/1.0 (+https://github.com/EthanC100/forecast-panel)"


def get(url: str, *, params=None, headers=None, timeout: int = 60, retries: int = 3, backoff: float = 3.0) -> requests.Response:
    h = {"User-Agent": UA}
    h.update(headers or {})
    last = None
    for attempt in range(retries + 1):
        try:
            r = requests.get(url, params=params, headers=h, timeout=timeout)
            if r.status_code in (429, 500, 502, 503, 504, 524) and attempt < retries:
                time.sleep(min(float(r.headers.get("Retry-After") or backoff * (2 ** attempt)), 60))
                continue
            r.raise_for_status()
            return r
        except requests.RequestException as exc:
            last = exc
            if attempt < retries and not (isinstance(exc, requests.HTTPError) and exc.response is not None
                                          and exc.response.status_code in (400, 401, 403, 404, 406)):
                time.sleep(backoff * (2 ** attempt))
                continue
            raise
    raise last  # pragma: no cover
