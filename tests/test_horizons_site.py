"""Horizons (the portfolio app at /horizons/): its own manifest and icons, a service worker that only
clears its own caches and never caches Supabase, the Supabase settings written at deploy (not
committed), the schema's row-level security, and the decision-record parser (run with node)."""

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
HZ = ROOT / "site" / "horizons"


def test_manifest_icons_and_shell():
    m = json.loads((HZ / "manifest.webmanifest").read_text())
    assert m["name"] == m["short_name"] == "Horizons" and m["scope"] == "./"
    for i in m["icons"]:
        assert (HZ / i["src"]).exists(), i["src"]
    html = (HZ / "index.html").read_text()
    assert 'apple-mobile-web-app-title" content="Horizons"' in html
    for f in re.findall(r'<script src="([^"]+)"', html):
        if f.startswith("http"):
            assert re.search(r"@\d+\.\d+\.\d+/", f), f"pin an exact version: {f}"
        elif f != "config.js":
            assert (HZ / f).exists(), f
    assert not any(HZ.glob("hz*.js")), "the old Horizons modules are gone"


def test_caches_and_config():
    sw = (HZ / "sw.js").read_text()
    assert 'k.startsWith("horizons-")' in sw and "url.origin !== location.origin" in sw and 'endsWith("/config.js")' in sw
    assert 'k.startsWith("prism-")' in (ROOT / "site" / "sw.js").read_text()
    assert "site/horizons/config.js" in (ROOT / ".gitignore").read_text()
    pages = (ROOT / ".github" / "workflows" / "pages.yml").read_text()
    assert "SUPABASE_ANON_KEY" in pages and "site/horizons/config.js" in pages
    for wf in (ROOT / ".github" / "workflows").glob("*.yml"):
        text = wf.read_text()
        if "uses: ./.github/workflows/pages.yml" in text:
            assert re.search(r"uses: \./\.github/workflows/pages\.yml\n\s+secrets: inherit", text), wf.name


def test_schema_row_level_security():
    sql = (ROOT / "supabase" / "schema.sql").read_text()
    for t in ("decisions", "trades", "trade_closes", "notes"):
        assert f"alter table public.{t}" in sql and f"enable row level security" in sql
        assert re.search(rf"create policy \"[^\"]+\" on public\.{t} for select to authenticated\s+using \(user_id = \(select auth\.uid\(\)\) and \(select public\.is_owner\(\)\)\)", sql), t
    assert "risk_pct <= 2" in sql and "revoke all on public.decisions" in sql


@pytest.mark.skipif(not shutil.which("node"), reason="node not installed")
def test_decision_parser():
    js = """
const D = require(process.argv[1]);
const ok = `DECISION RECORD
Date: 2026-10-30
Country: Brazil
Instrument: USD/BRL
Action: Sell
Size (% of account at risk, max 2%): 1%
Probability my view is right: 60%
Horizon (date): 2026-12-31
Entry trigger: next close
Stop / exit if wrong: 5.62 (exit if Copom cuts)
Thesis: The real overshot.
Key factors: carry
What would change my mind: a target cut
How this differs from market consensus: Focus sees 5.50`;
const a = D.parse(ok), b = D.parse(ok.replace("1%", "2.5%")), c = D.parse(ok.replace("Action: Sell", "Action: Hold").replace("5.62 (exit if Copom cuts)", "n/a"));
console.log(JSON.stringify({ a: [a.ok, a.direction, a.decision.instrument, a.decision.country, a.decision.risk_pct, a.decision.probability, a.decision.stop_level, a.decision.horizon],
  b: [b.ok, b.errors], c: [c.ok, c.direction], nohead: D.parse(ok.replace("DECISION RECORD\\n", "")).ok,
  side: [D.stopSideOk("fx", "short", 5.37, 5.62), D.stopSideOk("fx", "short", 5.37, 5.1), D.stopSideOk("yield", "long", 14.9, 15.5)] }));
"""
    out = json.loads(subprocess.run(["node", "-e", js, str(HZ / "decision.js")], capture_output=True, text=True, check=True).stdout)
    assert out["a"] == [True, "short", "USDBRL", "BR", 1, 0.6, 5.62, "2026-12-31"]
    assert out["b"][0] is False and any("maximum is 2%" in e for e in out["b"][1])
    assert out["c"] == [True, None]
    assert out["nohead"] is False
    assert out["side"] == [True, False, True]
