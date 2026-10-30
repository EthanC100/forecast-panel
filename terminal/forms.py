"""Handle a submitted Issue Form: parse, validate, write one write-once record, and return the
comment to post. Run by .github/workflows/forms.yml on `issues: opened`:

    python -m terminal.forms "$GITHUB_EVENT_PATH" --comment comment.md --result result.json

Only issues opened by the repository owner are processed (the repository is public). Invalid
submissions are recorded as rejected (with the errors) so the journal keeps every submission, and
the issue is closed as "not planned"; submit a new form instead of editing. Edits made to an issue
after it is opened are ignored: only the body at submission is read.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
from pathlib import Path

import yaml

from terminal import store
from terminal.book import (TRADES_DIR, Instrument, _equity_hint, load_config, load_records, validate_levels,
                           write_once)
from terminal.judgement import JUDGE_DIR, ai_probability, load_judgements, market_probability, pct

TEMPLATES = store.ROOT / ".github" / "ISSUE_TEMPLATE"
FORMS = {"open-trade": "[Open trade]", "close-trade": "[Close trade]", "quick-update": "[Quick update]",
         "full-call": "[Full call]", "resolve-question": "[Resolve]"}
DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}")


# --------------------------------------------------------------------------
# Parsing
# --------------------------------------------------------------------------


def template_fields(form: str) -> dict[str, str]:
    """label -> field id, read from the form's YAML so the parser follows the template."""
    doc = yaml.safe_load((TEMPLATES / f"{form}.yml").read_text())
    return {b["attributes"]["label"]: b["id"] for b in doc["body"] if b.get("id")}


def parse_body(body: str, form: str) -> dict[str, str | None]:
    labels = template_fields(form)
    out = {fid: None for fid in labels.values()}
    parts = re.split(r"^### (.+?)\s*$", body or "", flags=re.M)
    for i in range(1, len(parts) - 1, 2):
        label, value = parts[i].strip(), parts[i + 1].strip()
        if label in labels:
            out[labels[label]] = None if value in ("", "_No response_", "None") else value
    return out


def detect_form(issue: dict) -> str | None:
    names = {l["name"] for l in issue.get("labels", [])}
    for form in FORMS:
        if form in names:
            return form
    title = issue.get("title") or ""
    for form, prefix in FORMS.items():
        if title.startswith(prefix):
            return form
    body = issue.get("body") or ""
    for form in FORMS:
        labels = template_fields(form)
        if sum(f"### {l}" in body for l in labels) >= max(2, len(labels) - 2):
            return form
    return None


def _ts(s: str) -> dt.datetime:
    return dt.datetime.fromisoformat(s.replace("Z", "+00:00"))


def num(s: str | None) -> float | None:
    if s is None:
        return None
    t = s.replace("$", "").replace(",", "").replace("%", "").replace("bp", "").strip()
    try:
        return float(t)
    except ValueError:
        return None


def date_ok(s: str | None) -> bool:
    if not s or not DATE_RE.fullmatch(s.strip()):
        return False
    try:
        dt.date.fromisoformat(s.strip())
        return True
    except ValueError:
        return False


def prob(s: str | None) -> float | None:
    v = num(s)
    return None if v is None or not 0 <= v <= 100 or v % 5 else round(v / 100, 2)


# --------------------------------------------------------------------------
# Handlers. Each returns (record path, record, comment lines, accepted?)
# --------------------------------------------------------------------------


def _base(issue: dict, kind: str, rid: str) -> dict:
    return {"type": kind, "id": rid, "issue": issue["number"], "issue_url": issue.get("html_url"),
            "submitted_at": issue["created_at"], "submitted_by": issue["user"]["login"], "recorded_at": store.now_iso()}


def open_trade(issue: dict, f: dict) -> tuple[Path, dict, list[str], bool]:
    cfg = load_config()
    tid = f"T{issue['number']:05d}"
    errs, notes = [], []
    code = (f["instrument"] or "").upper().replace("/", "").replace("-", "").replace(" ", "")
    code = {"OAT": "OATBUND", "OATBUNDSPREAD": "OATBUND"}.get(code, code)
    if code not in cfg["instruments"]:
        errs.append(f"unknown instrument {f['instrument']!r}; use one of {', '.join(cfg['instruments'])}")
    direction = (f["direction"] or "").lower()
    if direction not in ("long", "short"):
        errs.append("direction must be long or short")
    size_type = "risk" if (f["size_type"] or "").startswith("Risk") else "notional"
    size, stop, target = num(f["size"]), num(f["stop"]), num(f["target"])
    if not size or size <= 0:
        errs.append(f"size {f['size']!r} is not a positive number")
    if stop is None:
        errs.append(f"stop {f['stop']!r} is not a number")
    if f["target"] and target is None:
        errs.append(f"target {f['target']!r} is not a number")
    horizon = (f["horizon"] or "").strip()
    if not date_ok(horizon):
        errs.append(f"horizon {f['horizon']!r} is not a YYYY-MM-DD date")
    elif horizon <= issue["created_at"][:10]:
        errs.append("horizon must be after the submission date")
    thesis = (f["thesis"] or "").strip()
    if not thesis or "\n" in thesis:
        errs.append("thesis must be one line")
    if not (f["close_early"] or "").strip():
        errs.append("say what would make you close early")
    rec = {**_base(issue, "open", tid), "trade_id": tid, "instrument": code, "direction": direction, "size_type": size_type,
           "size": size, "stop": stop, "target": target, "horizon": horizon, "link": (f["link"] or "").strip() or None,
           "thesis": thesis, "close_early": (f["close_early"] or "").strip(), "warnings": []}
    if not errs:
        inst = Instrument(code, cfg["instruments"][code])
        last = inst.latest(before=_ts(issue["created_at"]))
        if not last:
            errs.append(f"no data for {code} yet")
        else:
            sign = 1 if direction == "long" else -1
            errs += validate_levels(inst, sign, last[1], stop, target)
            if not errs:
                dur = inst.duration(last[0], last[1])
                unit = inst.unit_loss_to(last[1], stop, dur)
                notional = size / unit if size_type == "risk" else size
                risk = notional * unit + inst.cost(notional, dur)
                equity = _equity_hint()
                rec["estimate_at_submission"] = {"reference_close": {"date": last[0], "value": last[1], "series": inst.series_id},
                                                 "notional_usd": round(notional, 2), "risk_to_stop_usd": round(risk, 2),
                                                 "risk_pct_of_equity": round(100 * risk / equity, 2), "equity_usd": equity}
                if 100 * risk / equity > cfg["risk_warning_pct_of_equity"]:
                    rec["warnings"].append(f"Risk to stop is about ${risk:,.0f}, {100 * risk / equity:.1f}% of equity "
                                           f"(above the {cfg['risk_warning_pct_of_equity']}% guideline).")
                if inst.cfg.get("low_frequency"):
                    rec["warnings"].append(f"{code} is low frequency: the entry, marks and stops wait for the next print, which can take weeks.")
                if inst.series and inst.series.get("proxy"):
                    rec["warnings"].append(f"{code} is marked on a proxy ({inst.series['name']}).")
                nxt = inst.close_dt(last[0])
                notes.append(f"Entry: the first {code} close published after {issue['created_at'].replace('T', ' ').replace('Z', ' UTC')} "
                             f"(values land daily around {inst.cfg.get('close_utc')} UTC). The latest close is {last[1]} on {last[0]}.")
                notes.append(f"Estimated at that close: notional ${notional:,.0f}, risk to stop ${risk:,.0f} "
                             f"({100 * risk / equity:.2f}% of equity ${equity:,.0f}).")
    if errs:
        rec.update({"rejected": True, "errors": errs})
    lines = [f"**{'Rejected' if errs else 'Recorded'}: {tid}** · {direction or '?'} {code or '?'} · stop {stop} · "
             f"target {target if target is not None else 'none'} · horizon {horizon or '?'}"]
    lines += [f"- ❌ {e}" for e in errs] + [f"- {n}" for n in notes] + [f"- ⚠️ {w}" for w in rec["warnings"]]
    if not errs:
        lines.append(f"- To close it: open a **Close trade** form with trade ID `{tid}`.")
    return TRADES_DIR / f"{tid}-open.json", rec, lines, not errs


def close_trade(issue: dict, f: dict) -> tuple[Path, dict, list[str], bool]:
    tid = (f["trade_id"] or "").strip().upper()
    if re.fullmatch(r"T?\d{1,5}", tid):
        tid = f"T{int(tid.lstrip('T')):05d}"
    errs = []
    trades = load_records()
    t = trades.get(tid)
    if not t or "open" not in t or t["open"].get("rejected"):
        errs.append(f"no open trade {tid}")
    elif "exit" in t:
        errs.append(f"{tid} is already closed ({t['exit']['reason']} on {t['exit']['exit_date']})")
    elif "close_request" in t:
        errs.append(f"{tid} already has a close request (issue #{t['close_request']['issue']})")
    lines_pm = [l.strip() for l in (f["postmortem"] or "").splitlines() if l.strip()]
    if len(lines_pm) != 2:
        errs.append(f"the post-mortem must be exactly two lines; it has {len(lines_pm)}")
    rec = {**_base(issue, "close_request", tid), "trade_id": tid, "postmortem": lines_pm}
    path = TRADES_DIR / f"{tid}-closereq.json"
    if errs:
        rec.update({"rejected": True, "errors": errs})
        path = TRADES_DIR.parent / "judgements" / f"X{issue['number']:05d}-rejected-close.json"
        rec["type"] = "rejected_close"
    lines = [f"**{'Rejected' if errs else 'Close requested'}: {tid}**"] + [f"- ❌ {e}" for e in errs]
    if not errs:
        lines.append("- Exit: the first close published after this submission. The book records the exit and P&L on the next daily run.")
    return path, rec, lines, not errs


def _reveal(rec: dict) -> list[str]:
    m, a = rec.get("market_at_entry"), rec.get("ai_at_entry")
    out = [f"- Market-implied at submission: **{pct(m['prob'])}** ({m['source']}, {str(m['as_of'])[:16]})" if m
           else "- Market-implied at submission: none (no market linked to this question id)"]
    out.append(f"- AI probability: **{pct(a['prob'])}** ({a['source']}, {a['as_of']})" if a else "- AI probability: none recorded for this question")
    return out


def quick_update(issue: dict, f: dict) -> tuple[Path, dict, list[str], bool]:
    rid = f"U{issue['number']:05d}"
    errs = []
    target = (f["target"] or "").strip()
    p = prob(f["probability"])
    calls = {r["id"]: r for r in load_judgements() if r["type"] == "call" and not r.get("rejected")}
    qid = None
    if target.upper().startswith("J"):
        target = f"J{int(re.sub(r'[^0-9]', '', target) or 0):05d}"
        if target not in calls:
            errs.append(f"no call {target}")
        else:
            qid = calls[target].get("question_id")
    elif re.fullmatch(r"q[1-9]\d*|pm:\d+|ks:[A-Za-z0-9._-]+", target):
        qid = target
    else:
        errs.append("target must be a call id (J00015) or a question id (q1, pm:<id>, ks:<ticker>)")
    if p is None:
        errs.append("probability must be 0-100 in 5% steps")
    direction = (f["direction"] or "").strip()
    if not (f["what_changed"] or "").strip():
        errs.append("say what changed")
    rec = {**_base(issue, "update", rid), "target": target, "question_id": qid, "probability": p, "direction": direction,
           "what_changed": (f["what_changed"] or "").strip()}
    if not errs:
        rec["market_at_entry"] = market_probability(qid)
        rec["ai_at_entry"] = ai_probability(qid)
        prev = [r for r in load_judgements() if not r.get("rejected") and
                ((r["type"] == "call" and r["id"] == target) or (r["type"] == "update" and r.get("target") == target))]
        if prev:
            last = sorted(prev, key=lambda r: r["submitted_at"])[-1]["probability"]
            actual = "Up" if p > last else "Down" if p < last else "Unchanged"
            if actual != direction:
                rec["direction_note"] = f"direction says {direction}, but the probability moved {actual.lower()} from {pct(last)}"
    else:
        rec.update({"rejected": True, "errors": errs})
    lines = [f"**{'Rejected' if errs else 'Recorded'}: {rid}** · {target} → {pct(p)} ({direction})"] + [f"- ❌ {e}" for e in errs]
    if not errs:
        lines += _reveal(rec) + ([f"- ⚠️ {rec['direction_note']}"] if rec.get("direction_note") else [])
    return JUDGE_DIR / f"{rid}-update.json", rec, lines, not errs


def full_call(issue: dict, f: dict) -> tuple[Path, dict, list[str], bool]:
    rid = f"J{issue['number']:05d}"
    errs = []
    if not (f["question"] or "").strip():
        errs.append("the question is empty")
    qid = (f["question_id"] or "").strip() or None
    if not date_ok(f["resolution_date"]):
        errs.append(f"resolution date {f['resolution_date']!r} is not YYYY-MM-DD")
    factors = []
    for n in (1, 2, 3):
        text = (f.get(f"factor{n}") or "").strip()
        if text:
            d, s = f.get(f"factor{n}_direction"), f.get(f"factor{n}_size")
            if not d or not s:
                errs.append(f"factor {n} needs a direction and a size")
            factors.append({"factor": text, "direction": "raises" if (d or "").startswith("Raises") else "lowers", "size": (s or "").lower()})
    if not factors:
        errs.append("give at least one factor")
    scenarios = []
    for line in (f["scenarios"] or "").splitlines():
        m = re.match(r"\s*(.+?)\s*[:=\-–]\s*(\d+(?:\.\d+)?)\s*%?\s*$", line)
        if m:
            scenarios.append({"scenario": m.group(1).lstrip("-• ").strip(), "pct": float(m.group(2))})
        elif line.strip():
            errs.append(f"cannot read scenario line {line.strip()!r}; write 'Name: 40'")
    total = sum(s["pct"] for s in scenarios)
    if scenarios and abs(total - 100) > 1e-9:
        errs.append(f"scenario probabilities total {total:g}, not 100")
    if not scenarios:
        errs.append("give the scenarios with probabilities")
    p = prob(f["probability"])
    if p is None:
        errs.append("probability must be 0-100 in 5% steps")
    linked = (f["linked_trade"] or "").strip().upper() or None
    if linked:
        linked = f"T{int(re.sub(r'[^0-9]', '', linked) or 0):05d}"
        if linked not in load_records():
            errs.append(f"linked trade {linked} does not exist")
    change = (f["change_mind"] or "").strip()
    if not DATE_RE.search(change):
        errs.append("'what would change my mind' needs at least one date (YYYY-MM-DD)")
    premortem = (f["premortem"] or "").strip()
    if not premortem or "\n" in premortem:
        errs.append("the pre-mortem must be one line")
    rec = {**_base(issue, "call", rid), "question": (f["question"] or "").strip(), "question_id": qid,
           "resolution_date": (f["resolution_date"] or "").strip(), "base_rate": (f["base_rate"] or "").strip(),
           "factors": factors, "scenarios": scenarios, "probability": p, "linked_trade": linked,
           "change_mind": change, "premortem": premortem, "confidence": (f["confidence"] or "").lower()}
    point_raw = (f.get("point") or "").strip()
    if point_raw:
        point = num(point_raw)
        if point is None:
            errs.append(f"my forecast {point_raw!r} is not a number")
        rec["point"] = point
    if not errs:
        rec["market_at_entry"] = market_probability(qid)
        rec["ai_at_entry"] = ai_probability(qid)
    else:
        rec.update({"rejected": True, "errors": errs})
    lines = [f"**{'Rejected' if errs else 'Recorded'}: {rid}** · {rec['question']} · my probability {pct(p)} · resolves {rec['resolution_date']}"]
    lines += [f"- ❌ {e}" for e in errs]
    if not errs:
        lines += _reveal(rec) + [f"- Update it with a **Quick update** form using `{rid}`."]
    return JUDGE_DIR / f"{rid}-call.json", rec, lines, not errs


def resolve_question(issue: dict, f: dict) -> tuple[Path, dict, list[str], bool]:
    rid = f"R{issue['number']:05d}"
    errs = []
    target = (f["target"] or "").strip()
    if target.upper().startswith("J"):
        target = f"J{int(re.sub(r'[^0-9]', '', target) or 0):05d}"
    recs = load_judgements()
    known = {r["id"] for r in recs if r["type"] == "call" and not r.get("rejected")} | \
            {r.get("question_id") for r in recs if r.get("question_id")} | {r.get("target") for r in recs if r["type"] == "update"}
    if target not in known:
        errs.append(f"no call or question {target!r} to resolve")
    if any(r["type"] == "resolve" and r["target"] == target and not r.get("rejected") for r in recs):
        errs.append(f"{target} is already resolved")
    outcome = {"Yes": 1, "No": 0}.get((f["outcome"] or "").strip())
    if outcome is None:
        errs.append("outcome must be Yes or No")
    if not (f["source"] or "").strip().startswith("http"):
        errs.append("give a link to the source of the outcome")
    rec = {**_base(issue, "resolve", rid), "target": target, "outcome": outcome, "source": (f["source"] or "").strip()}
    if errs:
        rec.update({"rejected": True, "errors": errs})
    lines = [f"**{'Rejected' if errs else 'Recorded'}: {rid}** · {target} resolved {'YES' if outcome == 1 else 'NO' if outcome == 0 else '?'}"]
    lines += [f"- ❌ {e}" for e in errs]
    return JUDGE_DIR / f"{rid}-resolve.json", rec, lines, not errs


def rel(path: Path) -> str:
    try:
        return str(path.relative_to(store.ROOT))
    except ValueError:
        return str(path)


HANDLERS = {"open-trade": open_trade, "close-trade": close_trade, "quick-update": quick_update,
            "full-call": full_call, "resolve-question": resolve_question}


def handle(event: dict) -> dict:
    issue = event["issue"]
    owner = (event.get("repository") or {}).get("owner", {}).get("login")
    form = detect_form(issue)
    if not form:
        return {"handled": False, "reason": "not a terminal form"}
    if issue["user"]["login"] != owner and issue.get("author_association") != "OWNER":
        return {"handled": True, "accepted": False, "close": "not_planned",
                "comment": "This form is only processed for the repository owner. Nothing was recorded."}
    path, rec, lines, ok = HANDLERS[form](issue, parse_body(issue.get("body") or "", form))
    write_once(path, rec)
    site = "https://ethanc100.github.io/forecast-panel/#record"
    lines.append("")
    lines.append(f"Recorded in `{rel(path)}`; records are never edited after submission. "
                 f"[Portfolio, judgements and journal]({site}) update after the rebuild.")
    if not ok:
        lines.append("Fix the issues above and submit a new form; editing this issue changes nothing.")
    return {"handled": True, "accepted": ok, "form": form, "path": rel(path),
            "close": "completed" if ok else "not_planned", "comment": "\n".join(lines) + "\n\n---\n_Recorded by the terminal's forms workflow._"}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("event")
    ap.add_argument("--comment", default="comment.md")
    ap.add_argument("--result", default="result.json")
    a = ap.parse_args(argv)
    res = handle(json.loads(Path(a.event).read_text()))
    Path(a.result).write_text(json.dumps({k: v for k, v in res.items() if k != "comment"}))
    if res.get("comment"):
        Path(a.comment).write_text(res["comment"])
    print(json.dumps({k: v for k, v in res.items() if k != "comment"}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
