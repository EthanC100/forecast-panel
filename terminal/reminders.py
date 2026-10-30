"""Reminders as GitHub issues assigned to the repository owner, so they arrive as phone notifications.

Daily (.github/workflows/reminders.yml):
    stale       a judgement (call or question) with no update for 14 days and still unresolved
    signpost    a date I wrote in a call's "what would change my mind", or a dated signpost on a
                scenario page, from the day before until six days after
    horizon     an open paper trade past its horizon date
    move        an open trade whose instrument has moved more than 2 standard deviations since entry
                (sd of daily changes over the year before entry, scaled by the square root of the
                number of closes since entry)
    catalyst    an importance-3 catalyst within 3 days with no call from me on it

Each issue carries a hidden key (<!-- catalyst-reminder:KEY -->), so a reminder is opened once; an
open reminder whose condition has cleared is closed with a comment. Without GITHUB_TOKEN it is a dry
run. The open reminders are written to data/book/reminders.json for the site.
"""

from __future__ import annotations

import datetime as dt
import json
import logging
import math
import os
import re
from urllib.parse import urlencode

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


def form_url(template: str, **params) -> str:
    return f"https://github.com/{_repo()}/issues/new?" + urlencode({"template": f"{template}.yml", **params})


def _z_move(inst_code: str, cfg: dict, fill: dict) -> tuple[float, float, int] | None:
    from terminal.book import Instrument
    inst = Instrument(inst_code, cfg["instruments"][inst_code], fill.get("series_used"))
    obs = inst.obs
    before = [v for d, v in obs if d <= fill["entry_date"]][-251:]
    after = [(d, v) for d, v in obs if d > fill["entry_date"]]
    if len(before) < 30 or not after:
        return None
    if inst.kind == "fx":
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


def active(today: str | None = None) -> list[dict]:
    from terminal.judgement import load_judgements
    today = today or store.today()
    td = dt.date.fromisoformat(today)
    out = []
    recs = [r for r in load_judgements() if not r.get("rejected")]
    state = _read(store.ROOT / "data" / "book" / "judgements.json", {"questions": []})
    calls = [r for r in recs if r["type"] == "call"]
    # stale judgements
    for q in state.get("questions", []):
        if q.get("resolution") or not q.get("forecasts"):
            continue
        if q.get("resolution_date") and q["resolution_date"] < today:
            continue
        last = q["forecasts"][-1]["submitted_at"][:10]
        if (td - dt.date.fromisoformat(last)).days >= STALE_DAYS:
            out.append({"key": f"stale:{q['key']}:{last}", "kind": "stale",
                        "title": f"Update {q['key']}? No change since {last}: {q['question'][:70]}",
                        "body": f"Your last forecast on **{q['question']}** was {round(100 * q['forecasts'][-1]['prob'])}% on {last}, "
                                f"{(td - dt.date.fromisoformat(last)).days} days ago. Resolves {q.get('resolution_date') or 'unset'}.\n\n"
                                f"- [Quick update]({form_url('quick-update', target=q['key'], title='[Quick update] ' + q['key'])}) "
                                f"(even 'no change' keeps the record honest)\n- [Record]({SITE}#record/judgements)"})
    # signposts: dates in "what would change my mind", and dated scenario signposts
    resolved = {q["key"] for q in state.get("questions", []) if q.get("resolution")}
    for c in calls:
        if c["id"] in resolved:
            continue
        for d in sorted(set(re.findall(r"\d{4}-\d{2}-\d{2}", c.get("change_mind") or ""))):
            try:
                gap = (dt.date.fromisoformat(d) - td).days
            except ValueError:
                continue
            if -6 <= gap <= 1:
                out.append({"key": f"signpost:{c['id']}:{d}", "kind": "signpost",
                            "title": f"Signpost {d} for {c['id']}: {c['question'][:70]}",
                            "body": f"You wrote that this could change your mind:\n\n> {c['change_mind']}\n\n"
                                    f"The date {d} is {'tomorrow' if gap == 1 else 'today' if gap == 0 else f'{-gap} days ago'}. "
                                    f"[Quick update]({form_url('quick-update', target=c['id'], title='[Quick update] ' + c['id'])})"})
    scen = _read(store.DATA / "scenarios.json", {"scenarios": []})
    for s in scen.get("scenarios", []):
        for b in s.get("branches", []):
            for sp in b.get("signposts", []):
                for d in re.findall(r"\d{4}-\d{2}-\d{2}", sp):
                    try:
                        gap = (dt.date.fromisoformat(d) - td).days
                    except ValueError:
                        continue
                    if -6 <= gap <= 1:
                        out.append({"key": f"signpost:sc:{s['id']}:{d}", "kind": "signpost", "title": f"Signpost {d}: {s['title']}",
                                    "body": f"Scenario signpost ({b['label']}): {sp}\n\n[Scenario page]({SITE}#scenarios/{s['id']})"})
    # trades
    book = _read(store.ROOT / "data" / "book" / "state.json", {"trades": []})
    from terminal.book import load_config
    cfg = load_config()
    for v in book.get("trades", []):
        if v.get("status") != "open":
            continue
        tid, op = v["trade_id"], v["open"]
        if op.get("horizon") and op["horizon"] < today:
            out.append({"key": f"horizon:{tid}", "kind": "horizon", "title": f"{tid} is past its horizon ({op['horizon']}): {op['direction']} {op['instrument']}",
                        "body": f"Thesis: {op.get('thesis')}\n\nClose it or write down why it stays open.\n\n"
                                f"- [Close trade]({form_url('close-trade', trade_id=tid, title='[Close trade] ' + tid)})\n- [Portfolio]({SITE}#record/portfolio)"})
        try:
            z = _z_move(op["instrument"], cfg, v["fill"])
        except Exception as exc:  # noqa: BLE001
            log.warning("move check %s: %s", tid, exc)
            z = None
        if z and abs(z[0]) > 2:
            way = "up" if z[0] > 0 else "down"
            unit = "%" if cfg["instruments"][op["instrument"]]["kind"] == "fx" else ""
            out.append({"key": f"move:{tid}:{way}", "kind": "move",
                        "title": f"{op['instrument']} moved {z[0]:+.1f} sd since {tid} opened",
                        "body": f"{op['instrument']} has moved {z[1]:+.3g}{unit} in {z[2]} closes since entry on {v['fill']['entry_date']} "
                                f"({z[0]:+.1f} standard deviations of its usual move over that time). Your P&L: "
                                f"${(v.get('pnl') or {}).get('total', 0):,.0f}.\n\nThesis: {op.get('thesis')}\nClose early if: {op.get('close_early')}\n\n"
                                f"[Close trade]({form_url('close-trade', trade_id=tid, title='[Close trade] ' + tid)})"})
    # importance-3 catalysts within 3 days with no call
    cal = _read(store.DATA / "calendar.json", {"events": []})
    called = {c.get("question_id") for c in calls}
    sc_by_event = {s["event"]["id"]: s["id"] for s in scen.get("scenarios", []) if s.get("event")}
    for e in cal.get("events", []):
        gap = (dt.date.fromisoformat(e["date"]) - td).days
        if e.get("importance", 0) < 3 or not 0 <= gap <= 3:
            continue
        ids = {e["id"], "ev:" + e["id"]} | ({"sc:" + sc_by_event[e["id"]]} if e["id"] in sc_by_event else set())
        if ids & called:
            continue
        params = {"question": e["title"] + ": ", "question_id": e["id"], "resolution_date": e["date"], "title": "[Full call] " + e["title"]}
        if e.get("base_rate"):
            params["base_rate"] = e["base_rate"].get("text", "")
        out.append({"key": f"catalyst:{e['id']}", "kind": "catalyst",
                    "title": f"{e['title']} in {gap} day{'s' if gap != 1 else ''} ({e['date']}): no call yet",
                    "body": f"{e['country']} · importance {e['importance']} · {e.get('status')}. {e.get('note') or ''}\n\n"
                            f"- [Make a call]({form_url('full-call', **params)})\n- [Calendar]({SITE}#calendar/2w?ev={e['id']})"
                            + (f"\n- [Scenario page]({SITE}#scenarios/{sc_by_event[e['id']]})" if e["id"] in sc_by_event else "")})
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


def sync(today: str | None = None, dry_run: bool | None = None) -> dict:
    want = {r["key"]: r for r in active(today)}
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
    gh.req("POST", "/labels", json={"name": LABEL, "color": "f2a33a", "description": "Catalyst reminder"})
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
        body = r["body"] + f"\n\n<sub>Opened by Catalyst's daily reminder job. Closes itself when the condition clears.</sub>\n<!-- catalyst-reminder:{key} -->"
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
