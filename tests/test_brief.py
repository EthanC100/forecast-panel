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


def fake_calls(snap_holder):
    def call_all(reqs, cfg, sp, use_batch=True):
        out = {}
        for cid, role, params in reqs:
            B.record_spend(sp, role, "batch", B.cost_of(usage(), role, True, cfg))
            snap = json.loads(B.SNAPSHOT.read_text())
            if role == "extraction":
                d = next(x for x in snap["items"] if x["kind"] == "data")
                out[cid] = ({"facts": [{"text": f"{d['name']} at {d['value']}", "source_ids": [d["id"]], "country": "BR", "kind": "data"},
                                       {"text": "Investors are worried.", "source_ids": [], "country": "BR", "kind": "headline"}]}, None)
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


def test_end_to_end_mocked(tmp_brief, monkeypatch):
    monkeypatch.setattr(B.store, "secret", lambda n: "test-key" if n == "ANTHROPIC_API_KEY" else None)
    monkeypatch.setattr(B, "call_all", fake_calls(None))
    b = B.run(fetch_headlines=False)
    assert b["status"] == "ok" and b["verified"] is True
    assert len(b["facts"]) == 1 and b["moved_to_judgement"][0]["text"] == "Investors are worried."
    assert b["judgement"]["ran"] and all(q["ok"] for q in b["judgement"]["questions"])
    assert (tmp_brief / "briefs" / f"{b['date']}.json").exists()
    sp = json.loads((tmp_brief / "spend.json").read_text())
    assert sp["months"][b["date"][:7]]["calls"] == 1 + len(b["judgement"]["questions"])
    # the spend file and the brief never name a model
    cfg = B.conf()
    for m in cfg["models"].values():
        assert m not in (tmp_brief / "spend.json").read_text() and m not in json.dumps(b)
    # second run the same day: judgement already exists, so it is carried, not re-run (unless due)
    monkeypatch.setattr(B, "judgement_due", lambda snap, cfg, force=False: (False, "not due"))
    b2 = B.run(fetch_headlines=False)
    assert not b2["judgement"]["ran"] and b2["judgement"]["carried"]


def test_cap_forces_extraction_only(tmp_brief, monkeypatch):
    monkeypatch.setattr(B.store, "secret", lambda n: "test-key" if n == "ANTHROPIC_API_KEY" else None)
    monkeypatch.setattr(B, "call_all", fake_calls(None))
    B.SPEND.write_text(json.dumps({"currency": "USD", "months": {B.store.today()[:7]: {"usd": 8.01, "calls": 1, "by_role": {}}}, "log": []}))
    b = B.run(fetch_headlines=False, force_judgement=True)
    assert b["mode"] == "extraction_only" and not b["judgement"]["ran"]
    assert "cap" in b["judgement"]["why"]


def test_no_key_publishes_without_ai(tmp_brief, monkeypatch):
    monkeypatch.setattr(B.store, "secret", lambda n: None)
    b = B.run(fetch_headlines=False)
    assert b["status"] == "no_ai" and b["facts"] == []
