"""Monthly review: on the 1st, a draft page for the previous month in data/book/reviews/YYYY-MM.md.

The draft lists the calls made and resolved, scores against the market and the AI, the best and
worst resolved calls, trades opened and closed with P&L (in dollars and in units of risk), the
equity change, and the post-mortems and pre-mortems as raw material for lessons. It is written
once: an existing file is never overwritten, so edits made on GitHub (or on a phone) stay.
"""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

from terminal import store
from terminal.judgement import brier, load_judgements

DIR = store.ROOT / "data" / "book" / "reviews"
INDEX = DIR / "index.json"


def _read(path: Path, default=None):
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return default


def previous_month(today: dt.date | None = None) -> str:
    today = today or dt.date.today()
    first = today.replace(day=1)
    return (first - dt.timedelta(days=1)).strftime("%Y-%m")


def _pct(p):
    return "–" if p is None else f"{round(100 * p)}%"


def _f(x, d=3):
    return "–" if x is None else f"{x:.{d}f}"


def draft(month: str) -> str:
    recs = [r for r in load_judgements() if not r.get("rejected")]
    state = _read(store.ROOT / "data" / "book" / "judgements.json", {"questions": []})
    book = _read(store.ROOT / "data" / "book" / "state.json", {"trades": [], "equity": {"curve": []}})
    title = dt.date.fromisoformat(month + "-01").strftime("%B %Y")
    calls = [r for r in recs if r["type"] == "call" and r["submitted_at"][:7] == month]
    updates = [r for r in recs if r["type"] == "update" and r["submitted_at"][:7] == month]
    resolved = [q for q in state.get("questions", []) if q.get("resolution") and (q["resolution"].get("date") or "")[:7] == month]
    L = [f"# Monthly review: {title}", "",
         f"_Draft generated on {store.today()} from the record. Edit freely: this file is never regenerated._", "",
         "## Summary", "",
         f"- Calls made: **{len(calls)}**; quick updates: **{len(updates)}**; questions resolved: **{len(resolved)}**"]
    scored = []
    for q in resolved:
        f = q["forecasts"][-1]
        y = int(q["resolution"]["outcome"])
        m, a = (f.get("market") or {}).get("prob"), (f.get("ai") or {}).get("prob")
        scored.append({"q": q, "me": f["prob"], "y": y, "b": brier(f["prob"], y), "mb": brier(m, y) if m is not None else None,
                       "m": m, "a": a, "ab": brier(a, y) if a is not None else None})
    if scored:
        def avg(k):
            xs = [s[k] for s in scored if s[k] is not None]
            return (sum(xs) / len(xs), len(xs)) if xs else (None, 0)
        me, mk, ai = avg("b"), avg("mb"), avg("ab")
        L.append(f"- Brier (lower is better): me **{_f(me[0])}** (n={me[1]}), market at entry {_f(mk[0])} (n={mk[1]}), AI {_f(ai[0])} (n={ai[1]})")
    eq = [p for p in book.get("equity", {}).get("curve", []) if p[0][:7] <= month]
    in_m = [p for p in eq if p[0][:7] == month]
    if in_m:
        start = [p for p in eq if p[0][:7] < month]
        base = start[-1][1] if start else book.get("starting_capital_usd", in_m[0][1])
        L.append(f"- Paper book: ${in_m[-1][1]:,.0f} at month end, {in_m[-1][1] - base:+,.0f} on the month")
    L += ["", "## Calls made", ""]
    L += [f"- {c['id']} · {c['submitted_at'][:10]} · {c['question']} · **{_pct(c.get('probability'))}**"
          f" (market {_pct((c.get('market_at_entry') or {}).get('prob'))}, AI {_pct((c.get('ai_at_entry') or {}).get('prob'))}) · confidence {c.get('confidence') or '–'}"
          for c in calls] or ["- None."]
    L += ["", "## Resolved", ""]
    if scored:
        L += ["| question | outcome | me | market | AI | Brier me / market |", "|---|---|---|---|---|---|"]
        L += [f"| {s['q']['question'][:60]} | {'YES' if s['y'] else 'NO'} | {_pct(s['me'])} | {_pct(s['m'])} | {_pct(s['a'])} | {_f(s['b'])} / {_f(s['mb'])} |"
              for s in scored]
        best = min(scored, key=lambda s: s["b"])
        worst = max(scored, key=lambda s: s["b"])
        L += ["", f"**Best call:** {best['q']['question']} ({_pct(best['me'])}, resolved {'YES' if best['y'] else 'NO'}; Brier {_f(best['b'])})",
              f"**Worst call:** {worst['q']['question']} ({_pct(worst['me'])}, resolved {'YES' if worst['y'] else 'NO'}; Brier {_f(worst['b'])})"]
        if worst["q"].get("call", {}).get("premortem"):
            L.append(f"  - Its pre-mortem said: _{worst['q']['call']['premortem']}_")
    else:
        L.append("- Nothing resolved this month.")
    L += ["", "## Trades", ""]
    opened = [v for v in book.get("trades", []) if v.get("fill") and v["fill"]["entry_date"][:7] == month]
    closed = [v for v in book.get("trades", []) if v.get("exit") and v["exit"]["exit_date"][:7] == month]
    L += [f"- Opened {v['trade_id']}: {v['open']['direction']} {v['open']['instrument']} at {v['fill']['entry_value']} on {v['fill']['entry_date']} · {v['open'].get('thesis')}"
          for v in opened] or ["- No trades opened."]
    for v in closed:
        p, risk = v["exit"]["pnl"], v["fill"].get("risk_to_stop_usd") or 0
        r = f"{p['total'] / risk:+.2f}R" if risk else "–"
        L.append(f"- Closed {v['trade_id']} ({v['exit']['reason']}): ${p['total']:+,.0f} = {r} "
                 f"(price {p['price']:+,.0f}, carry {p['carry']:+,.0f}, cost {p['cost']:+,.0f})")
    if not closed:
        L.append("- No trades closed.")
    L += ["", "## Lessons", "", "Raw material from the record:", ""]
    pms = [(v["trade_id"], (v.get("close_request") or {}).get("postmortem")) for v in closed]
    L += [f"- {tid} post-mortem: " + " / ".join(pm) for tid, pm in pms if pm]
    L += [f"- {s['q']['key']} pre-mortem: {s['q']['call']['premortem']}" for s in scored if (s["q"].get("call") or {}).get("premortem")]
    L += ["", "My lessons (edit):", "", "1. ", "2. ", "3. ", "", "## Next month", "", "- Calls to update: ", "- Catalysts to prepare for: ", ""]
    return "\n".join(L)


def generate(month: str | None = None, force: bool = False) -> Path | None:
    month = month or previous_month()
    DIR.mkdir(parents=True, exist_ok=True)
    path = DIR / f"{month}.md"
    if path.exists() and not force:
        out = None
    else:
        path.write_text(draft(month))
        out = path
    index()
    return out


def index() -> list[dict]:
    items = []
    for p in sorted(DIR.glob("*.md"), reverse=True):
        text = p.read_text()
        items.append({"month": p.stem, "file": f"data/book/reviews/{p.name}", "title": (text.splitlines() or [p.stem])[0].lstrip("# "),
                      "edited": "Draft generated" not in text[:400] or "(edit):\n\n1. \n" not in text})
    INDEX.write_text(json.dumps({"generated_at": store.now_iso(), "reviews": items}, indent=1) + "\n")
    return items
