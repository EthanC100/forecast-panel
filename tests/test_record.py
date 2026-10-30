"""Phase 5: the track record (scoring side by side, skill split, groups, blend, trades in R),
reminders and the monthly review draft."""

import json

import pytest

from terminal import book, judgement, record, reminders, review, store


@pytest.fixture
def root(tmp_path, monkeypatch):
    (tmp_path / "data" / "book").mkdir(parents=True)
    (tmp_path / "data" / "terminal").mkdir(parents=True)
    monkeypatch.setattr(store, "ROOT", tmp_path)
    monkeypatch.setattr(store, "DATA", tmp_path / "data" / "terminal")
    monkeypatch.setattr(record, "BOOK", tmp_path / "data" / "book")
    monkeypatch.setattr(record, "load_judgements", lambda: [])
    monkeypatch.setattr(judgement, "load_judgements", lambda: [])
    monkeypatch.setattr(book, "load_config", lambda: {"instruments": {}})
    return tmp_path


def _write(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj))


def _question(i, me, ai, market, first, y, conf="high", sub="2026-06-01", res="2026-10-01", text="Will the Senate pass the budget?"):
    return {"key": f"J{i:05d}", "question": text, "question_id": f"q{i}", "resolution_date": res,
            "resolution": {"outcome": y, "date": res},
            "forecasts": [{"prob": first, "submitted_at": "2026-05-01T00:00:00Z"},
                          {"prob": me, "submitted_at": sub + "T00:00:00Z", "ai": {"prob": ai}, "market": {"prob": market}}],
            "call": {"confidence": conf}}


def test_decomposition_matches_brier():
    pairs = [(0.9, 1), (0.8, 1), (0.7, 0), (0.2, 0), (0.1, 0), (0.3, 1), (0.6, 1), (0.4, 0)]
    d = record.decomposition(pairs)
    mean_brier = sum((p - y) ** 2 for p, y in pairs) / len(pairs)
    # Brier = reliability - resolution + uncertainty, up to the within-bin variance (zero here: one forecast per bin)
    assert d["calibration_error"] - d["discrimination"] + d["uncertainty"] == pytest.approx(mean_brier, abs=1e-3)
    assert 0.5 < d["auc"] <= 1
    assert record.decomposition([]) == {"n": 0}


def test_catalyst_type_and_lead():
    assert record.catalyst_type("fc:BR.policy_rate.2026", "", {}, {}) == "central bank"
    assert record.catalyst_type(None, "Will S&P downgrade France?", {}, {}) == "rating"
    assert record.catalyst_type(None, "Will the tax cut pass in the budget?", {}, {}) == "budget"
    assert record.catalyst_type("ev:x", "anything", {"x": {"type": "politics"}}, {}) == "election"
    assert record._lead_bucket("2026-01-01T00:00:00Z", "2026-05-01") == "90+ days"
    assert record._lead_bucket("2026-04-01T00:00:00Z", "2026-05-01") == "30-90 days"
    assert record._lead_bucket("2026-04-20T00:00:00Z", "2026-05-01") == "under 30 days"


def test_questions_side_by_side_groups_and_blend(root):
    qs = [_question(i, 0.8 if i % 2 else 0.3, 0.6, 0.5, 0.5, i % 2) for i in range(1, 13)]
    _write(root / "data" / "book" / "judgements.json", {"questions": qs})
    r = record.questions_record()
    assert r["n_resolved"] == 12 and r["noisy"]
    sb = r["side_by_side"]
    assert {sb[w]["n"] for w in ("me", "ai", "market", "no_change")} == {12}
    assert sb["me"]["brier"] < sb["market"]["brier"] == sb["no_change"]["brier"]
    budget = next(g for g in r["by_type"] if g["group"] == "budget")
    assert budget["n"] == 12 and not budget.get("insufficient")
    assert next(g for g in r["by_type"] if g["group"] == "rating")["insufficient"]
    assert next(g for g in r["by_lead"] if g["group"] == "90+ days")["n"] == 12
    assert not r["blend"]["ready"] and r["blend"]["n_shared"] == 12
    qs += [_question(i, 0.7, 0.6, 0.5, 0.5, 1) for i in range(13, 21)]
    _write(root / "data" / "book" / "judgements.json", {"questions": qs})
    b = record.questions_record()["blend"]
    assert b["ready"] and b["blend"]["n"] == 20 and b["verdict"]


def test_trades_in_r(root, monkeypatch):
    monkeypatch.setattr(book, "load_records", lambda: {})
    view = lambda tid, inst, total, status="closed": {
        "trade_id": tid, "status": status, "open": {"instrument": inst, "thesis_type": "carry"},
        "fill": {"risk_to_stop_usd": 1000, "entry_date": "2026-10-01"},
        "pnl": {"total": total, "price": total - 50, "carry": 80, "cost": -30}, "exit": {"exit_date": "2026-10-20"} if status == "closed" else None}
    _write(root / "data" / "book" / "state.json", {"starting_capital_usd": 100000, "trades": [view("T1", "USDBRL", 500), view("T2", "USDBRL", -250),
                                                                                             view("T3", "US10Y", 100, "open")],
                                                   "equity": {"return_pct": 0.35}, "systematic": {"available": False}, "benchmarks": []})
    t = record.trades_record()
    assert t["closed"]["n"] == 2 and t["closed"]["total_r"] == pytest.approx(0.25)
    assert t["closed"]["carry_r"] == pytest.approx(0.16) and t["closed"]["cost_r"] == pytest.approx(-0.06)
    assert t["closed"]["price_r"] + t["closed"]["carry_r"] + t["closed"]["cost_r"] == pytest.approx(t["closed"]["total_r"])
    usd = t["by_instrument"][0]
    assert usd["group"] == "USDBRL" and usd["hit_rate_pct"] == 50 and usd["insufficient"]
    assert t["by_thesis"][0]["group"] == "carry" and t["open"]["n"] == 1


def test_reminders_catalyst_and_stale(root, monkeypatch):
    _write(store.DATA / "calendar.json", {"events": [
        {"id": "e1", "date": "2026-11-04", "country": "BR", "title": "Copom decision", "importance": 3, "status": "confirmed"},
        {"id": "e2", "date": "2026-11-04", "country": "MX", "title": "Minor release", "importance": 2, "status": "confirmed"},
        {"id": "e3", "date": "2026-11-20", "country": "FR", "title": "Too far", "importance": 3, "status": "confirmed"}]})
    _write(root / "data" / "book" / "judgements.json", {"questions": [
        {"key": "J00001", "question": "Q?", "resolution_date": "2027-01-01", "forecasts": [{"prob": 0.4, "submitted_at": "2026-10-10T00:00:00Z"}]}]})
    keys = {r["key"] for r in reminders.active("2026-11-02")}
    assert keys == {"catalyst:e1", "stale:J00001:2026-10-10"}
    monkeypatch.setattr(judgement, "load_judgements", lambda: [{"id": "J00002", "type": "call", "question_id": "e1", "question": "Copom",
                                                                 "change_mind": "the 2026-11-03 IPCA print"}])
    keys = {r["key"] for r in reminders.active("2026-11-02")}
    assert "catalyst:e1" not in keys and "signpost:J00002:2026-11-03" in keys


def test_review_written_once(root, monkeypatch):
    monkeypatch.setattr(review, "DIR", root / "data" / "book" / "reviews")
    monkeypatch.setattr(review, "INDEX", root / "data" / "book" / "reviews" / "index.json")
    monkeypatch.setattr(review, "load_judgements", lambda: [])
    assert review.previous_month(__import__("datetime").date(2026, 11, 1)) == "2026-10"
    p = review.generate("2026-10")
    assert p and "# Monthly review: October 2026" in p.read_text()
    p.write_text(p.read_text().replace("1. \n", "1. Size down before Copom.\n", 1))
    assert review.generate("2026-10") is None
    assert "Size down before Copom" in p.read_text()
    ix = json.loads(review.INDEX.read_text())["reviews"]
    assert ix[0]["month"] == "2026-10" and ix[0]["edited"]


def test_thesis_type_parse():
    from terminal import forms
    key = "Relative value (one leg against another)".split(" (")[0].strip().lower()
    assert forms.THESIS_TYPE.get(key) == "relative value"
    assert forms.THESIS_TYPE.get("valuation") == "valuation"
