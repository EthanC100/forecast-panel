"""Command line for the terminal's daily flow.

    python -m terminal.run fetch [--only key1,key2]   fetch sources, write series + status
    python -m terminal.run calendar [--no-attention]  rebuild the catalyst calendar (+ GDELT attention)
    python -m terminal.run summary                    rebuild data/terminal/summary.json for the site
    python -m terminal.run all                        all three
    python -m terminal.run site                       copy data/terminal into site/data for local viewing

A source that fails, or whose secret is missing, is recorded as an error on the status page and
skipped; everything else keeps going. Exit code is 0 unless every selected source failed.
"""

from __future__ import annotations

import argparse
import logging
import shutil
import sys
import traceback

from terminal import store
from terminal.sources import SOURCES
from terminal.sources.mexico import MissingSecret

log = logging.getLogger("terminal")


def fetch(only: set[str] | None = None) -> dict:
    status = store.load_status()
    srcs = status.setdefault("sources", {})
    ok_now: set[str] = set()
    ran = 0
    for key, name, country, func, secret, fallback_for, release in SOURCES:
        if only and key not in only and not (fallback_for and fallback_for in only):
            continue
        st = srcs.setdefault(key, {})
        st.update({"name": name, "country": country, "secret": secret, "fallback_for": fallback_for, "release": release,
                   "secret_present": bool(store.secret(secret)) if secret else None})
        if fallback_for and fallback_for in ok_now:
            st.update({"state": "standby", "last_attempt": store.now_iso(), "error": None,
                       "note": f"not needed: {fallback_for} succeeded this run"})
            continue
        ran += 1
        st["last_attempt"] = store.now_iso()
        try:
            written = func()
            st.update({"state": "ok", "last_success": st["last_attempt"], "error": None, "series": written,
                       "n_series": len(written), "note": None})
            ok_now.add(key)
            log.info("%s: ok (%d series)", key, len(written))
        except MissingSecret as exc:
            st.update({"state": "missing_secret", "error": str(exc),
                       "note": "skipped; add the secret under Settings > Secrets and variables > Actions"})
            log.warning("%s: %s", key, exc)
        except Exception as exc:  # noqa: BLE001
            st.update({"state": "error", "error": f"{type(exc).__name__}: {exc}"[:600]})
            log.warning("%s: failed: %s", key, exc)
            log.debug(traceback.format_exc())
        store.save_status(status)
    store.save_status(status)
    if ran and not ok_now:
        log.error("every selected source failed")
    return status


def copy_site(dest=store.ROOT / "site" / "data") -> None:
    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(store.DATA, dest, ignore=shutil.ignore_patterns("inputs"))


def main(argv=None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["fetch", "calendar", "summary", "all", "site"])
    ap.add_argument("--only", default="", help="comma-separated source keys for fetch")
    ap.add_argument("--no-attention", action="store_true", help="calendar: skip the GDELT attention refresh")
    a = ap.parse_args(argv)
    only = {s.strip() for s in a.only.split(",") if s.strip()} or None
    if a.cmd in ("fetch", "all"):
        st = fetch(only)
        if only and not any(st["sources"].get(k, {}).get("state") == "ok" for k in only):
            log.error("none of %s succeeded", sorted(only))
    if a.cmd in ("calendar", "all"):
        from terminal import calendar
        calendar.build(attention=not a.no_attention)
    if a.cmd in ("summary", "all"):
        from terminal import summary
        summary.build()
    if a.cmd == "site":
        copy_site()
    return 0


if __name__ == "__main__":
    sys.exit(main())
