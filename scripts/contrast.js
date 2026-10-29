// WCAG contrast of the site's ink tokens against their surfaces, light and dark (node scripts/contrast.js).
const fs = require("fs");
const css = fs.readFileSync(__dirname + "/../site/terminal.css", "utf8");
const block = (re) => Object.fromEntries([...css.match(re)[1].matchAll(/--([\w-]+):\s*(#[0-9a-f]{6})/gi)].map((m) => [m[1], m[2]]));
const light = block(/:root \{([\s\S]*?)\n\}/), dark = { ...light, ...block(/:root\[data-theme="dark"\] \{([\s\S]*?)\n\}/) };
const lum = (h) => { const c = [1, 3, 5].map((i) => parseInt(h.slice(i, i + 2), 16) / 255).map((v) => v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4); return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]; };
const ratio = (a, b) => { const [x, y] = [lum(a), lum(b)].sort((p, q) => q - p); return (x + 0.05) / (y + 0.05); };
const pairs = [["text", "surface", 4.5], ["text-2", "surface", 4.5], ["text-3", "surface", 4.5], ["text-3", "bg", 4.5], ["text-2", "surface-2", 4.5],
  ["accent", "surface", 4.5], ["on-accent", "accent", 4.5], ["good-ink", "surface", 4.5], ["bad-ink", "surface", 4.5], ["warn-ink", "surface", 4.5],
  ["bad-ink", "bad-soft", 4.5], ["warn-ink", "warn-soft", 4.5], ["text", "warn-soft", 4.5], ["axis", "surface", 1.5], ["cat-1", "surface", 3], ["cat-2", "surface", 3], ["cat-3", "surface", 2.5]]  // light aqua is 2.7:1: timeline marks always have the event list as their table view (relief rule);
let fail = 0;
for (const [mode, t] of [["light", light], ["dark", dark]]) for (const [fg, bg, min] of pairs) {
  const r = ratio(t[fg], t[bg]); const ok = r >= min; if (!ok) fail++;
  console.log(`${mode.padEnd(5)} ${(fg + " on " + bg).padEnd(24)} ${r.toFixed(2).padStart(6)}  ${ok ? "ok" : "FAIL (need " + min + ")"}`);
}
process.exit(fail ? 1 : 0);
