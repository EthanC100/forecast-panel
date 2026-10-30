"""AI brief: snapshot privacy, number/id validation, judgement checks, spend cap and an end-to-end
run with the API mocked out."""

import json
from types import SimpleNamespace

import pytest

from terminal import brief as B


@pytest.fixture
def tmp_brief(tmp_path, monkeypatch):
    for name in ("SNAPSHOT", "PREV_SNAPSHOT", "INDEX", "LATEST", "JUDGEMENT", "SPEND"):
        monkeypatch.setattr(B, name, tmp_path / getattr(B, name).name)
    monkeypatch.setattr(B, "ARCHIVE", tmp_path / "briefs")
    monkeypatch.setattr(B, "apply_to_scenarios", lambda: None)
    monkeypatch.setattr(B, "em_items", lambda: [{"id": "em:6", "kind": "research", "title": "em-macro hold-out", "text": "R2 of 0.15 out of sample"}])
    return tmp_path


def test_snapshot_has_no_private_fields(tmp_brief):
    snap = B.build_snapshot(fetch_headlines=False)
    txt = json.dumps(snap)
    for k in B.PRIVATE_KEYS:
        assert f'"{k}"' not in txt
    ids = [x["id"] for x in snap["items"]]
    assert len(ids) == len(set(ids))
    assert any(i.startswith("sc:") for i in ids) and any(i.startswith("ev:") for i in ids)
    # every id a scenario page refers to (its event, its market rows) is itself an item
    for sc in [x for x in snap["items"] if x["kind"] == "scenario"]:
        refs = [m["id"] for m in sc["markets"]] + ([sc["event"]] if sc["event"] else [])
        assert all(r in ids for r in refs), refs


def test_number_matching():
    vals = {5.342, 0.14, 18677.0, 13.8, -2.0}
    assert B.check_text("USD/BRL rose 0.14% to 5.34 on 28 Oct 2026", vals) == []
    assert B.check_text("net long 18,677 contracts, 14% of open interest", vals) == []
    assert B.check_text("the spread fell 2bp", vals) == []
    assert B.check_text("USD/BRL rose to 5.40", vals) == ["number 5.40 is not a snapshot value"]
    assert B.numbers_in("Copom on 4 Nov, ev:2026-11-04-br-copom and 2026-11-04; year 2027") == []


def test_facts_validation_moves_unsourced():
    index = {"s:x": {"id": "s:x", "value": 1.25}}
    facts = [{"text": "x is 1.25", "source_ids": ["s:x"]}, {"text": "x is 1.4", "source_ids": ["s:x"]},
             {"text": "y moved", "source_ids": ["s:nope"]}, {"text": "markets are calm", "source_ids": []}]
    kept, moved, problems = B.validate_facts(facts, index)
    assert [f["ok"] for f in kept] == [True, False, False]
    assert moved and moved[0]["text"] == "markets are calm"
    assert len(problems) == 2


def test_judgement_validation():
    sc = {"branches": [{"id": "a"}, {"id": "b"}, {"id": "c"}], "yes_branches": ["c"]}
    index = {"s:x": {"value": 3.0}}
    good = {"p_yes": 20, "branches": [{"id": "a", "p": 50}, {"id": "b", "p": 30}, {"id": "c", "p": 20}],
            "factors": [{"text": "x is 3.0", "effect": "raises", "source_ids": ["s:x"]}], "base_rate_used": "starts at 20%",
            "what_would_change_view": "", "most_likely_wrong": "", "source_ids": []}
    assert B.validate_judgement(good, sc, index, {3.0}) == []
    bad = {**good, "p_yes": 25, "branches": [{"id": "a", "p": 50}, {"id": "b", "p": 25}, {"id": "c", "p": 20}],
           "factors": good["factors"] * 4 + [{"text": "y is 7.5", "effect": "lowers", "source_ids": ["s:nope"]}]}
    p = B.validate_judgement(bad, sc, index, {3.0})
    assert any("sum to 95" in x for x in p) and any("at most 3" in x for x in p)
    assert any("unknown source id s:nope" in x for x in p) and any("7.5" in x for x in p)


def usage(i=1000, o=500, read=0, write=0):
    return SimpleNamespace(input_tokens=i, output_tokens=o, cache_read_input_tokens=read, cache_creation_input_tokens=write,
                           cache_creation=SimpleNamespace(ephemeral_1h_input_tokens=write, ephemeral_5m_input_tokens=0))


def test_cost_batch_and_cache():
    cfg = B.conf()
    c = B.cost_of(usage(i=1_000_000, o=0), "judgement", True, cfg)
    assert c["usd"] == pytest.approx(cfg["prices"]["judgement"]["input"] * 0.5)
    c = B.cost_of(usage(i=0, o=0, read=1_000_000, write=1_000_000), "judgement", False, cfg)
    assert c["usd"] == pytest.approx(cfg["prices"]["judgement"]["cache_read"] + cfg["prices"]["judgement"]["cache_write_1h"])


def fake_calls(snap_holder, region_p=60):
    def call_all(reqs, cfg, sp, use_batch=True):
        out = {}
        for cid, role, params in reqs:
            B.record_spend(sp, role, "batch", B.cost_of(usage(), role, True, cfg))
            snap = json.loads(B.SNAPSHOT.read_text())
            if role == "extraction":
                d = next(x for x in snap["items"] if x["kind"] == "data")
                dev = {"text": f"{d['name']} at {d['value']}", "source_ids": [d["id"]], "kind": "data"}
                regions = {r: {"developments": [], "week_change": []} for r in B.REGIONS}
                regions["BR"] = {"developments": [dev, {"text": "Investors are worried.", "source_ids": [], "kind": "market"}], "week_change": []}
                out[cid] = ({"top": [{"text": dev["text"], "source_ids": dev["source_ids"]}], "regions": regions}, None)
            elif cid.startswith("r-"):
                r = cid[2:]
                assets = list(B.__dict__["REGIONS"] and __import__("terminal.horizons", fromlist=["x"]).ASSETS[r])
                ev = [e["event_id"] for e in B.upcoming_for(snap, r)][:1]
                out[cid] = ({"why_it_matters": [{"text": "A rate decision moves short yields.", "for": "bonds" if r != "GOLD" else "gold", "source_ids": []}],
                             "watch": [{"event_id": e, "what_to_watch": "the vote split"} for e in ev],
                             "risks": [{"text": "A fiscal surprise.", "source_ids": []}],
                             "consensus": {"view": "Surveys expect no change.", "source_ids": []}, "might_be_wrong": "Inflation is stickier.",
                             **({} if not B.views_on() else {"views": [{"asset": a, "lean": "long", "p": region_p, "confidence": "low", "horizon_weeks": 8,
                                        "reasons": [{"text": "carry is high", "source_ids": []}], "resembles": {"episode_id": "", "why": ""},
                                        "main_risk": "a global sell-off", "would_change": "a budget miss", "source_ids": []} for a in assets]})}, None)
            else:
                sc = next(x for x in snap["items"] if x["id"] == "sc:" + cid[2:])
                n = len(sc["branches"])
                ps = [100 // n // 5 * 5] * n
                ps[0] += 100 - sum(ps)
                br = [{"id": b["id"], "p": p} for b, p in zip(sc["branches"], ps)]
                yes = sum(b["p"] for b in br if b["id"] in sc["yes_branches"])
                out[cid] = ({"question_id": sc["id"], "base_rate_used": "the page's base rate", "p_yes": yes, "branches": br,
                             "factors": [], "what_would_change_view": "a new vote", "confidence": "low",
                             "most_likely_wrong": "the crowd is right", "source_ids": [sc["id"]]}, None)
        return out
    return call_all


@pytest.fixture
def tmp_views(tmp_path, monkeypatch):
    from terminal import horizons as H
    monkeypatch.setattr(H, "PATH", tmp_path / "horizons" / "views.json")
    return H


@pytest.fixture
def views_on(monkeypatch):
    """Horizons' views are stopped by default (brief.yaml horizons_views: false); these tests switch them on."""
    real = B.conf
    monkeypatch.setattr(B, "conf", lambda: {**real(), "horizons_views": True})


def test_views_stopped_by_default(tmp_brief, tmp_views, monkeypatch):
    monkeypatch.setattr(B.store, "secret", lambda n: "test-key" if n == "ANTHROPIC_API_KEY" else None)
    seen = []
    real_fake = fake_calls(None)

    def spy(reqs, cfg, sp, use_batch=True):
        seen.extend(params for cid, role, params in reqs if cid.startswith("r-"))
        return real_fake(reqs, cfg, sp, use_batch)
    monkeypatch.setattr(B, "call_all", spy)
    assert B.conf().get("horizons_views") is False and not B.views_on()
    b = B.run(fetch_headlines=False, force_judgement=True)
    assert b["status"] == "ok" and b["verified"] is True, b["problems"]
    assert all(b["report"]["regions"][r]["judgement"]["verified"] for r in B.REGIONS)
    assert not tmp_views.PATH.exists()
    assert seen and all("views" not in p["output_config"]["format"]["schema"]["properties"] for p in seen)
    assert "Horizons' view" not in B.judgement_system(json.loads(B.SNAPSHOT.read_text()))


def test_end_to_end_mocked(tmp_brief, tmp_views, views_on, monkeypatch):
    monkeypatch.setattr(B.store, "secret", lambda n: "test-key" if n == "ANTHROPIC_API_KEY" else None)
    monkeypatch.setattr(B, "call_all", fake_calls(None))
    b = B.run(fetch_headlines=False, force_judgement=True)
    assert b["status"] == "ok" and b["verified"] is True, b["problems"]
    assert len(b["facts"]) == 1 and b["moved_to_judgement"][0]["text"] == "Investors are worried."
    assert b["top"] and b["top"][0]["ok"]
    rep = b["report"]["regions"]
    assert set(rep) == set(B.REGIONS) and rep["BR"]["developments"][0]["ok"]
    assert all(rep[r]["judgement"]["verified"] for r in B.REGIONS)
    assert all(0 <= e["days_to"] <= B.UPCOMING_DAYS for r in B.REGIONS for e in rep[r]["upcoming"])
    assert b["judgement"]["ran"] and all(q["ok"] for q in b["judgement"]["questions"])
    assert (tmp_brief / "briefs" / f"{b['date']}.json").exists()
    v = json.loads(tmp_views.PATH.read_text())
    assert v["label"] == "Horizons' view, not financial advice"
    assert set(v["views"]["BR"]) == {"bond", "currency"} and set(v["views"]["GOLD"]) == {"gold"}
    assert v["views"]["BR"]["currency"]["question_id"] == f"hz:BR.currency.{b['date']}" and v["views"]["BR"]["currency"]["p_long"] == 0.6
    sp = json.loads((tmp_brief / "spend.json").read_text())
    assert sp["months"][b["date"][:7]]["calls"] == 1 + len(b["judgement"]["questions"]) + len(B.REGIONS)
    assert sp["expected_month_usd"]["total_usd"] > 0 and set(sp["expected_month_usd"]["breakdown"]) >= {"extraction_daily_x30", "judgement_weekly_x4.3"}
    # the spend file and the brief never name a model
    cfg = B.conf()
    for m in cfg["models"].values():
        assert m not in (tmp_brief / "spend.json").read_text() and m not in json.dumps(b)
    # second run the same day: judgement already exists, so it is carried, not re-run (unless due)
    monkeypatch.setattr(B, "judgement_due", lambda snap, cfg, force=False: (False, "not due"))
    b2 = B.run(fetch_headlines=False)
    assert not b2["judgement"]["ran"] and b2["judgement"]["carried"]
    assert b2["report"]["regions"]["MX"]["judgement"]["verified"]       # region notes carried too


def test_cap_forces_extraction_only(tmp_brief, tmp_views, views_on, monkeypatch):
    monkeypatch.setattr(B.store, "secret", lambda n: "test-key" if n == "ANTHROPIC_API_KEY" else None)
    monkeypatch.setattr(B, "call_all", fake_calls(None))
    cap = B.conf()["monthly_cap_usd"]
    B.SPEND.write_text(json.dumps({"currency": "USD", "months": {B.store.today()[:7]: {"usd": cap + 0.01, "calls": 1, "by_role": {}}}, "log": []}))
    b = B.run(fetch_headlines=False, force_judgement=True)
    assert b["mode"] == "extraction_only" and not b["judgement"]["ran"]
    assert "cap" in b["judgement"]["why"]
    assert not tmp_views.PATH.exists()           # no Horizons' views above the cap
    assert b["report"]["regions"]["BR"]["developments"]  # facts still run


def test_report_validation_rejects_bad_ids_and_numbers():
    index = {"s:x": {"id": "s:x", "value": 1.25}, "s:y": {"id": "s:y", "value": 7.0}}
    data = {"top": [{"text": "x is 1.25", "source_ids": ["s:x"]}],
            "regions": {"BR": {"developments": [{"text": "x is 1.25", "source_ids": ["s:x"], "kind": "data"},
                                                {"text": "x is 9.9", "source_ids": ["s:x"], "kind": "data"},
                                                {"text": "z moved", "source_ids": ["s:nope"], "kind": "market"}],
                               "week_change": [{"text": "a rumour", "source_ids": []}]}}}
    regions, top, moved, problems = B.validate_report(data, index)
    assert [f["ok"] for f in regions["BR"]["developments"]] == [True, False, False]
    assert set(regions) == set(B.REGIONS) and regions["MX"] == {"developments": [], "week_change": []}
    assert moved == [{"text": "a rumour", "why": "no source cited, so it is a claim, not a fact", "region": "BR"}]
    assert any("9.9" in p for p in problems) and any("s:nope" in p for p in problems) and top[0]["ok"]


def test_view_validation(tmp_views):
    H = tmp_views
    index = {"s:x": {"value": 5.0}}
    ok = {"asset": "currency", "lean": "short", "p": 65, "confidence": "medium", "horizon_weeks": 6,
          "reasons": [{"text": "x is 5.0", "source_ids": ["s:x"]}], "resembles": {"episode_id": "br-2015", "why": "fiscal slippage"},
          "main_risk": "a rally", "would_change": "a primary surplus", "source_ids": ["s:x"]}
    assert H.validate_view(ok, "BR", index, {5.0}, {"br-2015"}, B.check_text) == []
    bad = {**ok, "p": 40, "horizon_weeks": 20, "resembles": {"episode_id": "made-up", "why": ""},
           "reasons": [{"text": "x is 6.2", "source_ids": ["s:nope"]}]}
    p = H.validate_view(bad, "BR", index, {5.0}, {"br-2015"}, B.check_text)
    assert any("at least 50" in x for x in p) and any("4-13" in x for x in p) and any("made-up" in x for x in p)
    assert any("s:nope" in x for x in p) and any("6.2" in x for x in p)
    assert H.validate_view({**ok, "lean": "none", "p": None}, "BR", index, {5.0}, set(), B.check_text) == ["unknown episode br-2015"]
    assert H.validate_view({**ok, "asset": "gold"}, "BR", index, set(), set(), B.check_text)[0].startswith("asset")


def test_scope_near_catalyst():
    cfg = B.conf()
    snap = {"date": "2026-11-02", "items": [
        {"id": "ev:a", "kind": "event", "country": "BR", "importance": 3, "days_to": 2, "date": "2026-11-04", "title": "Copom"},
        {"id": "ev:b", "kind": "event", "country": "GLOBAL", "importance": 3, "days_to": 30, "date": "2026-12-02", "title": "FOMC"},
        {"id": "sc:br", "kind": "scenario", "country": "BR", "event": "ev:a"}, {"id": "sc:fr", "kind": "scenario", "country": "FR", "event": None}]}
    assert B.judgement_scope(snap, cfg, "weekly judgement") is None
    regions, qs = B.judgement_scope(snap, cfg, "within 3 days of Copom")
    assert regions == {"BR"} and qs == {"sc:br"}


def test_hz_resolution_and_scoring(tmp_views, tmp_path, monkeypatch):
    H = tmp_views
    monkeypatch.setattr(H.store, "SERIES_DIR", tmp_path)
    monkeypatch.setattr(H.store, "series_path", lambda sid: tmp_path / f"{sid}.json")
    H.store.save_series({"id": "br.usdbrl.ptax", "name": "USD/BRL"}, [["2026-09-01", 5.30], ["2026-10-01", 5.10], ["2026-11-02", 5.00]])
    monkeypatch.setattr(H, "series_for", lambda code: ["br.usdbrl.ptax"])
    view = H.finish_view({"asset": "currency", "lean": "long", "p": 70, "confidence": "high", "horizon_weeks": 4, "reasons": [],
                          "resembles": {"episode_id": "", "why": ""}, "main_risk": "", "would_change": "", "source_ids": []}, "BR", "2026-09-01")
    assert view["entry_value"] == 5.30 and view["horizon_end"] == "2026-09-29" and view["p_long"] == 0.7
    H.record("2026-09-01", {"BR": {"currency": {**view, "ok": True}}}, True)
    st = H.resolve(H.load(), today="2026-11-03")
    h = st["history"][0]
    # long the real = USD/BRL falls; it fell from 5.30 to 5.30? no: last value on or before 2026-09-29 is 5.30 -> no gain
    assert h["resolved"] and h["exit_value"] == 5.30 and h["outcome"] == 0 and h["brier"] == pytest.approx(0.49)
    view2 = {**view, "date": "2026-10-01", "entry_value": 5.10, "horizon_end": "2026-11-02", "question_id": "hz:BR.currency.2026-10-01"}
    H.record("2026-10-01", {"BR": {"currency": {**view2, "ok": True}}}, True)
    monkeypatch.setattr(H.store, "today", lambda: "2026-11-03")
    assert H.hz_outcome("hz:BR.currency.2026-10-01")["outcome"] == 1      # 5.10 -> 5.00: the real gained
    q = [{"question_id": "hz:BR.currency.2026-10-01", "resolution": {"outcome": 1}, "forecasts": [{"prob": 0.5}]}]
    sc = H.score(q)
    assert sc["n_resolved"] == 2 and sc["overall"]["hit_rate_pct"] == 50.0 and sc["noisy"] and sc["overall"]["insufficient"]
    assert sc["vs_me"]["n"] == 1 and sc["vs_me"]["me"]["brier"] == 0.25 and sc["vs_me"]["horizons"]["brier"] == pytest.approx(0.09)


def test_no_key_publishes_without_ai(tmp_brief, monkeypatch):
    monkeypatch.setattr(B.store, "secret", lambda n: None)
    b = B.run(fetch_headlines=False)
    assert b["status"] == "no_ai" and b["facts"] == []
