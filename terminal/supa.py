"""A small PostgREST client for Horizons' Supabase project (schema: supabase/schema.sql).

Workflows use the project's secret key (SUPABASE_SERVICE_ROLE_KEY). New-style secret keys
(sb_secret_...) go only in the `apikey` header; a legacy service_role JWT (eyJ...) also goes in
`Authorization: Bearer`. The secret key bypasses row-level security, so these jobs can fill trades,
write marks and score decisions. Without SUPABASE_URL or the key every call is skipped with a warning
and `configured()` is False, so a workflow still succeeds.
"""

from __future__ import annotations

import logging
import os

import requests

log = logging.getLogger(__name__)
UA = "forecast-panel-horizons/1.0 (+https://github.com/EthanC100/forecast-panel)"


class TablesMissing(RuntimeError):
    """The project is reachable but supabase/schema.sql has not been run yet."""


class NotConfigured(RuntimeError):
    pass


class Client:
    def __init__(self, url: str | None = None, key: str | None = None, session=None):
        self.url = (url if url is not None else os.environ.get("SUPABASE_URL", "")).rstrip("/")
        self.key = key if key is not None else os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
        self.http = session or requests.Session()

    def configured(self) -> bool:
        return bool(self.url and self.key)

    def headers(self, extra: dict | None = None) -> dict:
        if not self.configured():
            raise NotConfigured("SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY are not set")
        h = {"apikey": self.key, "User-Agent": UA, "Content-Type": "application/json"}
        if self.key.startswith("eyJ"):          # legacy service_role JWT
            h["Authorization"] = "Bearer " + self.key
        h.update(extra or {})
        return h

    def _req(self, method: str, table: str, params: dict | None = None, json=None, prefer: str | None = None):
        r = self.http.request(method, f"{self.url}/rest/v1/{table}", params=params or {}, json=json,
                              headers=self.headers({"Prefer": prefer} if prefer else None), timeout=60)
        if r.status_code >= 400:
            if r.status_code == 404 and "PGRST205" in r.text:
                raise TablesMissing(f"Supabase table {table} does not exist yet: run supabase/schema.sql in the SQL editor")
            raise RuntimeError(f"Supabase {method} {table}: HTTP {r.status_code}: {r.text[:300]}")
        return r.json() if r.text else None

    def select(self, table: str, **filters) -> list[dict]:
        """select('trades', status='in.(pending,open)', order='created_at') — values are PostgREST filters."""
        params = {"select": filters.pop("select", "*")}
        params.update({k: v for k, v in filters.items()})
        return self._req("GET", table, params) or []

    def insert(self, table: str, rows) -> list[dict]:
        return self._req("POST", table, json=rows, prefer="return=representation") or []

    def patch(self, table: str, match: dict, values: dict) -> list[dict]:
        params = {k: f"eq.{v}" for k, v in match.items()}
        return self._req("PATCH", table, params, json=values, prefer="return=representation") or []
