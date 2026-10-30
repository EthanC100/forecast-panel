// Contrast of Prism's colour tokens, light and dark (node scripts/contrast.js).
// Text pairs need 4.5:1, including text on translucent cards composited over the page's colour blobs.
// Graphical marks (icons, chart lines, chip dots) need 3:1 unless they carry a text label next to them.
const fs = require("fs");
const css = fs.readFileSync(__dirname + "/../site/terminal.css", "utf8");
const grab = (re) => Object.fromEntries([...css.match(re)[1].matchAll(/--([\w-]+):\s*(#[0-9a-f]{6}|rgba\([^)]*\))/gi)].map((m) => [m[1], m[2]]));
const light = grab(/:root \{([\s\S]*?)\n\}/), dark = { ...light, ...grab(/:root\[data-theme="dark"\] \{([\s\S]*?)\n\}/) };
const rgb = (c) => c.startsWith("#") ? [1, 3, 5].map((i) => parseInt(c.slice(i, i + 2), 16)).concat(1) : c.match(/[\d.]+/g).map(Number);
const over = (top, under) => { const [r, g, b, a] = rgb(top), u = rgb(under); return "#" + [r, g, b].map((v, i) => Math.round(v * a + u[i] * (1 - a)).toString(16).padStart(2, "0")).join(""); };
const lum = (h) => { const c = rgb(h).slice(0, 3).map((v) => v / 255).map((v) => v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4); return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]; };
const ratio = (a, b) => { const [x, y] = [lum(a), lum(b)].sort((p, q) => q - p); return (x + 0.05) / (y + 0.05); };

function surfaces(t) {
  // the page background shows the three soft country blobs; cards are translucent glass over them
  const blobs = ["soft-FR", "soft-MX", "soft-BR", "bg"].map((k) => t[k]);
  const glass = blobs.map((b) => over(t.glass, b));
  return { surface: [t.surface], bg: blobs, glass, "surface-2": [t["surface-2"]], header: ["f-today", "f-calendar", "f-scenarios", "f-crowd", "f-record", "soft-FR", "soft-BR", "soft-MX"].map((k) => t[k]) };
}
const TEXT = ["text", "text-2", "text-3", "accent", "good-ink", "bad-ink", "warn-ink"];
let fail = 0;
for (const [mode, t] of [["light", light], ["dark", dark]]) {
  const S = surfaces(t), rows = [];
  const check = (name, fg, bgs, min) => { const worst = Math.min(...bgs.map((b) => ratio(fg, b))); rows.push([name, worst, min]); if (worst < min) fail++; };
  for (const k of TEXT) for (const s of ["surface", "glass", "bg", "surface-2"]) check(`${k} on ${s}`, t[k], S[s], 4.5);
  for (const k of ["text", "text-2", "text-3"]) check(`${k} on page headers / feature cards`, t[k], S.header, 4.5);
  for (const c of ["FR", "BR", "MX", "GLOBAL"]) { check(`ink-${c} on soft-${c} (country chip)`, t["ink-" + c], [t["soft-" + c]], 4.5); check(`ink-${c} on glass`, t["ink-" + c], S.glass, 4.5); }
  for (const s of ["today", "calendar", "scenarios", "crowd", "record"]) {
    check(`i-${s} on f-${s} (selected nav)`, t["i-" + s], [t["f-" + s]], 4.5);
    check(`bg on i-${s} (selected tab)`, t.bg, [t["i-" + s]], 4.5);
    check(`s-${s} icon on glass`, t["s-" + s], S.glass, 3);
  }
  for (const c of ["FR", "BR", "MX"]) { check(`bg on ink-${c} (selected tab)`, t.bg, [t["ink-" + c]], 4.5); check(`line-${c} chart line on glass`, t["line-" + c], S.glass, 3); }
  check("on-accent on accent (buttons)", t["on-accent"], [t.accent], 4.5);
  for (const k of ["cat-1", "cat-2", "t-mon", "t-fis", "t-pol", "fav", "good", "bad"]) check(`${k} mark on glass`, t[k], S.glass, k === "t-pol" || k === "t-fis" || k === "fav" || k === "good" || k === "bad" ? 2.5 : 3);
  for (const [n, r, m] of rows) console.log(`${mode.padEnd(5)} ${n.padEnd(44)} ${r.toFixed(2).padStart(6)}  ${r >= m ? "ok" : "FAIL (need " + m + ")"}`);
}
console.log(fail ? fail + " failures" : "all pass");
console.log("Marks checked at 2.5:1 (timeline types, favourable/adverse sides, gain/loss fills) always sit next to a text label or value (relief rule).");
process.exit(fail ? 1 : 0);
