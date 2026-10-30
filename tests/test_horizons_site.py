"""Horizons app shell: its own manifest and icons, a service worker that only clears its own caches,
every module the router loads exists and is in the offline shell, and it reads Catalyst's data files."""

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HZ = ROOT / "site" / "horizons"


def test_manifest_and_icons():
    m = json.loads((HZ / "manifest.webmanifest").read_text())
    assert m["name"] == m["short_name"] == "Horizons"
    assert m["scope"] == "./" and m["start_url"].startswith("./")
    for i in m["icons"]:
        assert (HZ / i["src"]).exists(), i["src"]
    assert any(i["purpose"] == "maskable" for i in m["icons"])
    html = (HZ / "index.html").read_text()
    assert 'apple-mobile-web-app-title" content="Horizons"' in html and "manifest.webmanifest" in html


def test_router_modules_exist_and_are_cached():
    core = (HZ / "hz.js").read_text()
    mods = set(re.findall(r'\["(hz-[a-z]+)", "page[A-Za-z]+"\]', core)) | {"hz-terms", "hz-help"}
    sw = (HZ / "sw.js").read_text()
    for m in mods:
        assert (HZ / f"{m}.js").exists(), m
        assert f'"{m}.js"' in sw, m


def test_caches_are_separate():
    hz_sw = (HZ / "sw.js").read_text()
    cat_sw = (ROOT / "site" / "sw.js").read_text()
    assert 'k.startsWith("horizons-")' in hz_sw and 'k.startsWith("prism-")' in cat_sw
    assert re.search(r'VERSION = "horizons-', hz_sw) and 'VERSION = "prism-v3"' in cat_sw


def test_reads_the_shared_data():
    core = (HZ / "hz.js").read_text()
    assert 'const DATA = "../data/"' in core
    assert "localStorage" in core and '"horizons." + k' in core
