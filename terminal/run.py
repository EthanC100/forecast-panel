"""Command line for the terminal's daily flow.

    python -m terminal.run fetch [--only key1,key2]   fetch sources, write series + status
    python -m terminal.run calendar [--no-attention]  rebuild the catalyst calendar (+ GDELT attention)
    python -m terminal.run summary                    rebuild data/terminal/summary.json for the site
    python -m terminal.run book                       fills, exits, marks -> data/book/state.json
    python -m terminal.run judge                      scores and journal -> data/book/judgements.json, journal.json
    python -m terminal.run all                        fetch, calendar, summary, book, judge
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
            st.update({"state": "error", "error": f"{type(exc).__name__}: {exc}"[:600], "note": None})
            log.warning("%s: failed: %s", key, exc)
            log.debug(traceback.format_exc())
        store.save_status(status)
    store.save_status(status)
    if ran and not ok_now:
        log.error("every selected source failed")
    return status


def copy_site(dest=store.ROOT / "site" / "data") -> None:
    """What pages.yml does at deploy: terminal data at site/data, book data at site/data/book."""
    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(store.DATA, dest, ignore=shutil.ignore_patterns("inputs"))
    book = store.ROOT / "data" / "book"
    if book.exists():
        shutil.copytree(book, dest / "book")


def main(argv=None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["fetch", "calendar", "summary", "book", "judge", "all", "site", "lab", "brief", "snapshot"])
    ap.add_argument("--only", default="", help="comma-separated source keys for fetch")
    ap.add_argument("--no-attention", action="store_true", help="calendar: skip the GDELT attention refresh")
    ap.add_argument("--force-judgement", action="store_true", help="brief: run the judgement even if it is not due")
    ap.add_argument("--no-ai", action="store_true", help="brief: build the snapshot and archive entry without calling the API")
    ap.add_argument("--no-headlines", action="store_true", help="brief/snapshot: reuse the last headlines instead of fetching")
    ap.add_argument("--no-batch", action="store_true", help="brief: use the standard API instead of the Batch API")
    a = ap.parse_args(argv)
    only = {s.strip() for s in a.only.split(",") if s.strip()} or None
    if a.cmd in ("fetch", "all"):
        st = fetch(only)
        if only and not any(st["sources"].get(k, {}).get("state") == "ok" for k in only):
            log.error("none of %s succeeded", sorted(only))
    if a.cmd in ("calendar", "all"):
        from terminal import calendar
        calendar.build(attention=not a.no_attention)
    if a.cmd == "lab":
        from terminal import labtests
        for k, v in labtests.run()["tests"].items():
            log.info("lab test %s: %s", k, v.get("badge"))
    if a.cmd in ("book", "all"):
        from terminal import book
        st = book.build()
        log.info("book: equity %.2f, %d open, %d pending; wrote %s", st["equity"]["current"], st["stats"]["n_open"],
                 st["stats"]["n_pending"], st["written_this_run"] or "nothing")
    if a.cmd in ("judge", "all"):
        from terminal import judgement
        js = judgement.build()
        log.info("judgements: %d questions, %d resolved", js["summary"]["n_questions"], js["summary"]["n_resolved"])
    if a.cmd in ("summary", "all"):
        # after book and judge, so scenario pages see the latest calls
        from terminal import crowd, scenarios, summary, teach
        summary.build()
        scenarios.build()
        crowd.build()
        teach.build()
    if a.cmd == "snapshot":
        from terminal import brief
        log.info("snapshot: %s", brief.build_snapshot(fetch_headlines=not a.no_headlines)["counts"])
    if a.cmd == "brief":
        from terminal import brief
        b = brief.run(force_judgement=a.force_judgement, no_ai=a.no_ai, fetch_headlines=not a.no_headlines, use_batch=not a.no_batch)
        log.info("brief %s: %s, verified=%s, %d facts, judgement %s; today $%.4f, month $%.4f of $%.2f", b["date"], b["status"],
                 b.get("verified"), len(b.get("facts", [])), "ran" if b["judgement"].get("ran") else "not run (" + b["judgement"]["why"] + ")",
                 b["cost"]["today_usd"], b["cost"]["month_usd"], b["cost"]["cap_usd"])
        for p in b.get("problems", []):
            log.warning("unverified: %s", p)
    if a.cmd == "site":
        copy_site()
    return 0


if __name__ == "__main__":
    sys.exit(main())
