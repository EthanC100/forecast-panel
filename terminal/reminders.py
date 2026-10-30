"""Horizons reminders as GitHub issues assigned to the repository owner, so they arrive as phone
notifications. The conditions are read from Horizons' Supabase tables (supabase/schema.sql).

Daily (.github/workflows/reminders.yml):
    horizon     an open paper trade past its horizon date
    move        an open trade whose instrument has moved more than 2 standard deviations since entry
                (sd of daily changes over the year before entry, scaled by the square root of the
                number of closes since entry)
    stale       a market whose latest decision is 14 or more days old
    signpost    a YYYY-MM-DD date in a decision's "what would change my mind", from the day before
                until six days after
    catalyst    an importance-3 catalyst within 3 days with no decision for that market in 14 days

Issue text is minimal (no P&L, no sizes) because the repository may be public. Each issue carries a
hidden key (<!-- catalyst-reminder:KEY -->), so a reminder is opened once; an open reminder whose
condition has cleared is closed with a comment. Without GITHUB_TOKEN it is a dry run; without the
Supabase settings nothing is checked and existing reminders are left as they are. The open reminders
are written to data/book/reminders.json.
"""

from __future__ import annotations

import datetime as dt
import json
import logging
import math
import os
import re

import requests

from terminal import store

log = logging.getLogger(__name__)

API = "https://api.github.com"
OUT = store.ROOT / "data" / "book" / "reminders.json"
LABEL = "reminder"
MARK = re.compile(r"<!-- catalyst-reminder:(\S+) -->")
STALE_DAYS = 14
SITE = "https://ethanc100.github.io/forecast-panel/"


def _read(path, default=None):
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return default


def _repo() -> str:
    return os.environ.get("GITHUB_REPOSITORY") or "EthanC100/forecast-panel"


def _z_move(inst_code: str, cfg: dict, fill: dict) -> tuple[float, float, int] | None:
    from terminal.book import Instrument
    inst = Instrument(inst_code, cfg["instruments"][inst_code], fill.get("series_used"))
    obs = inst.obs
    before = [v for d, v in obs if d <= fill["entry_date"]][-251:]
    after = [(d, v) for d, v in obs if d > fill["entry_date"]]
    if len(before) < 30 or not after:
        return None
    if inst.kind in ("fx", "price"):
        ch = [100 * (b / a - 1) for a, b in zip(before, before[1:])]
        move = 100 * (after[-1][1] / fill["entry_value"] - 1)
    else:
        ch = [b - a for a, b in zip(before, before[1:])]
        move = after[-1][1] - fill["entry_value"]
    m = sum(ch) / len(ch)
    sd = math.sqrt(sum((c - m) ** 2 for c in ch) / (len(ch) - 1))
    if sd <= 0:
        return None
    return move / (sd * math.sqrt(len(after))), move, len(after)


MARKETS = {"BR": "Brazil", "MX": "Mexico", "FR": "France", "GOLD": "Gold"}
APP = SITE + "horizons/"


def active(today: str | None = None, client=None) -> list[dict] | None:
    """Reminders due today, read from Horizons' Supabase tables. None when Supabase is not configured
    (so sync() leaves existing reminder issues alone). Issue text stays minimal: no P&L, no sizes."""
    from terminal.book import load_config
    from terminal.supa import Client
    client = client or Client()
    if not client.configured():
        log.warning("reminders: Supabase is not configured; no reminders computed")
        return None
    today = today or store.today()
    td = dt.date.fromisoformat(today)
    out = []
    trades = client.select("trades", status="eq.open")
    decisions = client.select("decisions", order="decision_date.desc")
    cfg = load_config()
    # open trades: past the horizon, or a move of more than 2 sd since entry
    for t in trades:
        icfg = cfg["instruments"].get(t["instrument"]) or {}
        name = icfg.get("name", t["instrument"])
        if t.get("horizon") and str(t["horizon"]) < today:
            out.append({"key": f"horizon:{t['id']}", "kind": "horizon", "title": f"Horizons: {name} trade is past its horizon ({t['horizon']})",
                        "body": f"Your {t['direction']} {name} paper trade passed its horizon date. Close it, or note why it stays open.\n\n[Portfolio]({APP}#portfolio)"})
        if not icfg or not t.get("entry_date"):
            continue
        try:
            z = _z_move(t["instrument"], cfg, {"series_used": t.get("series_used"), "entry_date": str(t["entry_date"]),
                                              "entry_value": float(t["entry_value"])})
        except Exception as exc:  # noqa: BLE001
            log.warning("move check %s: %s", t["id"], exc)
            z = None
        if z and abs(z[0]) > 2:
            way = "up" if z[0] > 0 else "down"
            out.append({"key": f"move:{t['id']}:{way}", "kind": "move", "title": f"Horizons: {name} moved {z[0]:+.1f} sd since your trade opened",
                        "body": f"{name} has moved {way} by more than two standard deviations of its usual move since your entry on {t['entry_date']}. "
                                f"Check the thesis and the stop.\n\n[Portfolio]({APP}#portfolio)"})
    # decisions: the latest per market older than 14 days, and dated signposts in "what would change my mind"
    latest = {}
    for x in decisions:
        latest.setdefault(x["country"], x)
    for c, x in latest.items():
        age = (td - dt.date.fromisoformat(str(x["decision_date"])[:10])).days
        if age >= STALE_DAYS:
            out.append({"key": f"stale:{c}:{x['id']}", "kind": "stale", "title": f"Horizons: review your {MARKETS.get(c, c)} decision (last {x['decision_date']})",
                        "body": f"Your latest {MARKETS.get(c, c)} decision is {age} days old. Review it and paste a new decision record if your view changed."
                                f"\n\n[Strategy]({APP}#strategy)"})
    for x in decisions:
        for d in sorted(set(re.findall(r"\d{4}-\d{2}-\d{2}", x.get("change_mind") or ""))):
            try:
                gap = (dt.date.fromisoformat(d) - td).days
            except ValueError:
                continue
            if -6 <= gap <= 1:
                when = "tomorrow" if gap == 1 else "today" if gap == 0 else f"{-gap} days ago"
                out.append({"key": f"signpost:{x['id']}:{d}", "kind": "signpost",
                            "title": f"Horizons: signpost {d} in your {MARKETS.get(x['country'], x['country'])} decision",
                            "body": f"A date you wrote under 'What would change my mind' is {when}. Check whether it changed your view.\n\n[Strategy]({APP}#strategy)"})
    # importance-3 catalysts within 3 days with no decision for that market in the last 14 days
    recent = {x["country"] for x in decisions if (td - dt.date.fromisoformat(str(x["decision_date"])[:10])).days <= STALE_DAYS}
    cal = _read(store.DATA / "calendar.json", {"events": []}) or {}
    gold = _read(store.DATA / "gold.json", {}) or {}
    events = [e for e in cal.get("events", []) if e.get("country") in MARKETS]
    events += [{**e, "id": "gold-" + e["date"] + "-" + re.sub(r"[^a-z0-9]+", "-", e["title"].lower()).strip("-"), "country": "GOLD"}
               for e in gold.get("upcoming", []) if (e.get("importance") or 0) >= 3]
    for e in events:
        gap = (dt.date.fromisoformat(e["date"]) - td).days
        if (e.get("importance") or 0) < 3 or not 0 <= gap <= 3 or e["country"] in recent:
            continue
        out.append({"key": f"catalyst:{e['id']}", "kind": "catalyst",
                    "title": f"Horizons: {e['title']} in {gap} day{'s' if gap != 1 else ''} ({e['date']}), no {MARKETS[e['country']]} decision yet",
                    "body": f"A major catalyst is close and you have no {MARKETS[e['country']]} decision in the last {STALE_DAYS} days.\n\n[Strategy]({APP}#strategy)"})
    return out


# --------------------------------------------------------------------------
# GitHub
# --------------------------------------------------------------------------

class GitHub:
    def __init__(self, token: str, repo: str):
        self.s = requests.Session()
        self.s.headers.update({"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json",
                               "X-GitHub-Api-Version": "2022-11-28"})
        self.repo = repo

    def req(self, method: str, path: str, **kw):
        r = self.s.request(method, f"{API}/repos/{self.repo}{path}", timeout=30, **kw)
        if r.status_code >= 400 and not (method == "POST" and path == "/labels" and r.status_code == 422):
            raise RuntimeError(f"GitHub {method} {path}: {r.status_code} {r.text[:200]}")
        return r

    def reminder_issues(self) -> list[dict]:
        out = []
        for page in range(1, 11):
            batch = self.req("GET", "/issues", params={"labels": LABEL, "state": "all", "per_page": 100, "page": page}).json()
            out += [i for i in batch if "pull_request" not in i]
            if len(batch) < 100:
                break
        return out


def sync(today: str | None = None, dry_run: bool | None = None, client=None) -> dict:
    found = active(today, client)
    if found is None:
        result = {"generated_at": store.now_iso(), "dry_run": True, "open": [], "note": "Supabase is not configured; reminders were not checked"}
        OUT.write_text(json.dumps(result, ensure_ascii=False, indent=1) + "\n")
        return result
    want = {r["key"]: r for r in found}
    token = os.environ.get("GITHUB_TOKEN")
    dry_run = dry_run if dry_run is not None else not token
    owner = _repo().split("/")[0]
    created, closed, existing = [], [], []
    if dry_run:
        log.info("dry run: %d reminders active", len(want))
        result = {"generated_at": store.now_iso(), "dry_run": True, "open": [{**r, "url": None} for r in want.values()]}
        OUT.write_text(json.dumps(result, ensure_ascii=False, indent=1) + "\n")
        return result
    gh = GitHub(token, _repo())
    gh.req("POST", "/labels", json={"name": LABEL, "color": "f2a33a", "description": "Horizons reminder"})
    issues = gh.reminder_issues()
    seen = {}
    for i in issues:
        m = MARK.search(i.get("body") or "")
        if m:
            seen.setdefault(m.group(1), i)
    for key, r in want.items():
        if key in seen:
            existing.append(key)
            continue
        body = r["body"] + f"\n\n<sub>Opened by Horizons' daily reminder job. Closes itself when the condition clears.</sub>\n<!-- catalyst-reminder:{key} -->"
        i = gh.req("POST", "/issues", json={"title": r["title"], "body": body, "labels": [LABEL], "assignees": [owner]}).json()
        seen[key] = i
        created.append(key)
    for key, i in seen.items():
        if i["state"] == "open" and key not in want:
            gh.req("POST", f"/issues/{i['number']}/comments", json={"body": "The condition has cleared, so this reminder is closing itself."})
            gh.req("PATCH", f"/issues/{i['number']}", json={"state": "closed", "state_reason": "completed"})
            i["state"] = "closed"
            closed.append(key)
    open_now = [{"key": k, "kind": k.split(":")[0], "title": i["title"], "url": i["html_url"], "number": i["number"],
                 "created_at": i["created_at"]} for k, i in seen.items() if i["state"] == "open"]
    result = {"generated_at": store.now_iso(), "dry_run": False, "open": sorted(open_now, key=lambda x: x["created_at"], reverse=True),
              "created": created, "closed": closed}
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=1) + "\n")
    return result
