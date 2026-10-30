/* Horizons core: routing, settings (Explain mode, theme), the term layer, explain blocks, charts,
   progress rings, GitHub form links and Ask Claude. Pages live in modules loaded on demand:
   hz-home.js (Home, brief), hz-country.js (Brazil, Mexico, France), hz-gold.js, hz-markets.js
   (Calendar, Scenarios, Crowd), hz-record.js (Record), hz-help.js (walkthrough and lessons),
   hz-terms.js (definitions). Data: the same files Catalyst reads, under ../data/. */
(function () {
  "use strict";
  const HZ = window.HZ = { pages: {}, mods: {}, cache: {} };
  const app = document.getElementById("app");
  const DATA = "../data/";
  const REPO = "EthanC100/forecast-panel";
  HZ.REPO = REPO;
  HZ.CATALYST = "../";
  HZ.NAMES = { BR: "Brazil", MX: "Mexico", FR: "France", GOLD: "Gold", US: "United States", GLOBAL: "Global", DE: "Germany" };
  HZ.CURRENCY = { BR: "Brazilian real", MX: "Mexican peso", FR: "euro" };

  // ---------------- storage (keys: horizons.*) ----------------
  const store = HZ.store = {
    get(k, d) { try { const v = localStorage.getItem("horizons." + k); return v === null ? d : v; } catch (e) { return d; } },
    set(k, v) { try { localStorage.setItem("horizons." + k, v); } catch (e) { /* private mode */ } },
  };

  // ---------------- DOM helpers ----------------
  const el = HZ.el = (tag, attrs, ...kids) => {
    const n = document.createElement(tag);
    if (attrs) for (const [k, v] of Object.entries(attrs)) {
      if (v == null || v === false) continue;
      if (k === "class") n.className = v; else if (k === "text") n.textContent = v; else if (k === "html") n.innerHTML = v;
      else if (k.startsWith("on")) n.addEventListener(k.slice(2), v); else n.setAttribute(k, v);
    }
    for (const kid of kids.flat(3)) if (kid != null && kid !== false) n.appendChild(typeof kid === "string" || typeof kid === "number" ? document.createTextNode(String(kid)) : kid);
    return n;
  };
  const svg = HZ.svg = (tag, attrs, ...kids) => {
    const n = document.createElementNS("http://www.w3.org/2000/svg", tag);
    for (const [k, v] of Object.entries(attrs || {})) if (v != null) n.setAttribute(k, v);
    for (const kid of kids.flat()) if (kid != null && kid !== false) n.appendChild(typeof kid === "string" ? document.createTextNode(kid) : kid);
    return n;
  };
  HZ.nn = (...a) => a.flat().filter((x) => x != null && x !== false);
  const fmt = HZ.fmt = (v, d = 2) => v == null || Number.isNaN(+v) ? "–" : Number(v).toLocaleString("en-US", { minimumFractionDigits: d, maximumFractionDigits: d });
  const sign = (v) => (v > 0 ? "+" : v < 0 ? "−" : "±");
  HZ.signed = (v, d = 1, unit = "") => v == null ? "–" : sign(v) + fmt(Math.abs(v), d) + unit;
  /** A market move: sign and number, neutral colour (green and red are kept for my gains and losses). */
  HZ.chg = (v, d = 1, unit = "") => el("span", { class: "num flat" }, HZ.signed(v, d, unit));
  /** A gain or loss: green with + or red with −. */
  HZ.pnl = (v, d = 0, prefix = "$") => v == null ? el("span", {}, "–") : el("span", { class: "num " + (v > 0 ? "up" : v < 0 ? "down" : "flat") }, sign(v) + prefix + fmt(Math.abs(v), d));
  HZ.pct = (p, d = 0) => p == null ? "–" : fmt(100 * p, d) + "%";
  HZ.today = () => new Date().toISOString().slice(0, 10);
  HZ.daysUntil = (iso) => Math.round((Date.parse(iso.slice(0, 10) + "T12:00:00Z") - Date.parse(HZ.today() + "T12:00:00Z")) / 864e5);
  HZ.dateLong = (iso) => iso ? new Date(iso.slice(0, 10) + "T12:00:00Z").toLocaleDateString("en-GB", { weekday: "short", day: "numeric", month: "short", year: "numeric", timeZone: "UTC" }) : "–";
  HZ.dateShort = (iso) => iso ? new Date(iso.slice(0, 10) + "T12:00:00Z").toLocaleDateString("en-GB", { day: "numeric", month: "short", timeZone: "UTC" }) : "–";
  HZ.ago = (iso) => { if (!iso) return ""; const d = -HZ.daysUntil(iso); return d <= 0 ? "today" : d === 1 ? "yesterday" : d + " days ago"; };
  HZ.inDays = (iso) => { const d = HZ.daysUntil(iso); return d === 0 ? "today" : d === 1 ? "tomorrow" : d > 0 ? "in " + d + " days" : -d + " days ago"; };

  // ---------------- data ----------------
  HZ.getJSON = (p) => fetch(DATA + p, { cache: "no-cache" }).then((r) => { if (!r.ok) throw new Error(p + ": HTTP " + r.status); return r.json(); });
  HZ.json = (p) => (HZ.cache[p] = HZ.cache[p] || HZ.getJSON(p).catch((e) => { delete HZ.cache[p]; throw e; }));
  HZ.maybe = (p) => HZ.json(p).catch(() => null);
  HZ.text = (p) => fetch(DATA + p, { cache: "no-cache" }).then((r) => { if (!r.ok) throw new Error(p + ": HTTP " + r.status); return r.text(); });
  HZ.series = (id) => HZ.json("series/" + id + ".json");
  HZ.need = (name) => (HZ.mods[name] = HZ.mods[name] || new Promise((res, rej) => {
    const s = el("script", { src: name + ".js" }); s.onload = () => res(HZ); s.onerror = () => rej(new Error(name + ".js failed to load")); document.head.appendChild(s);
  }));

  // ---------------- lazy blocks ----------------
  const io = "IntersectionObserver" in window ? new IntersectionObserver((ents) => ents.forEach((e) => {
    if (e.isIntersecting) { io.unobserve(e.target); const f = e.target._mount; e.target._mount = null; if (f) f(); }
  }), { rootMargin: "400px 0px" }) : null;
  HZ.skel = (kind) => kind === "lines" ? el("div", { "aria-hidden": "true" }, el("div", { class: "skel line" }), el("div", { class: "skel line w60" }), el("div", { class: "skel line w40" }))
    : el("div", { "aria-hidden": "true" }, el("div", { class: "skel line w40" }), el("div", { class: "skel block" }));
  /** A placeholder that builds itself when it scrolls near the screen; `build` returns a node, an array or a promise. */
  HZ.lazy = (build, kind) => {
    const holder = el("div", { class: "lazy" }, HZ.skel(kind || "block"));
    holder._mount = () => Promise.resolve().then(build).then((n) => {
      const nodes = HZ.nn(n);
      if (nodes.length) { holder.replaceWith(...nodes); nodes.forEach((x) => HZ.glossarize(x)); } else holder.remove();
    }).catch((err) => holder.replaceWith(el("div", { class: "err" }, "Could not load this part: " + String(err.message || err))));
    if (io) io.observe(holder); else setTimeout(holder._mount, 0);
    return holder;
  };

  // ---------------- cards ----------------
  /** card({title, cls, sub, id}, ...body): a soft translucent card with overlapping colour shapes. */
  HZ.card = (o, ...body) => el("article", { class: "card pop " + (o.cls || ""), id: o.id || null },
    o.title ? el("div", { class: "ch" }, el("span", { class: "dot", "aria-hidden": "true" }), el("h2", {}, o.title), ...(o.chips || [])) : null,
    o.sub ? el("p", { class: "muted small", style: "margin-top:0" }, o.sub) : null, ...body);
  HZ.pageHead = (title, sub, cls) => el("div", { class: "phead " + (cls || "") }, el("h1", {}, title), sub ? el("p", { class: "sub" }, sub) : null);
  HZ.source = (label, url, asOf) => el("div", { class: "src" }, "Source: ", url ? el("a", { href: url, target: "_blank", rel: "noopener" }, label || url) : (label || "–"), asOf ? " · as of " + String(asOf).slice(0, 16).replace("T", " ") : "");
  HZ.err = (e) => el("div", { class: "err" }, String((e && e.message) || e));

  // ---------------- Explain mode ----------------
  const MODES = ["full", "light", "off"];
  HZ.mode = () => { const m = store.get("explain", "full"); return MODES.includes(m) ? m : "full"; };
  HZ.setMode = (m) => { store.set("explain", m); route(); };
  /** explain({what, how, now}): Full shows all three; Light only "what to look for right now"; Off nothing. Each part is text or a node. */
  HZ.explain = (o) => {
    const m = HZ.mode();
    if (m === "off" || !o) return null;
    const part = (k, v) => v ? el("p", {}, el("b", { class: "k" }, k), v) : null;
    if (m === "light") return o.now ? el("div", { class: "explain now" }, part("What to look for right now", o.now)) : null;
    return el("div", { class: "explain" }, part("What this shows", o.what), part("How to read it", o.how), part("What to look for right now", o.now));
  };

  // ---------------- terms ----------------
  HZ.TERMS = {};
  let termRe = null, seen = new Set();
  HZ.addTerms = (dict) => {
    Object.assign(HZ.TERMS, dict);
    const words = [];
    for (const [k, t] of Object.entries(HZ.TERMS)) for (const w of [t.t, ...(t.aka || [])]) words.push([w, k]);
    words.sort((a, b) => b[0].length - a[0].length);
    HZ.termIndex = new Map(words.map(([w, k]) => [w.toLowerCase(), k]));
    const esc = (s) => s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
    termRe = new RegExp("(^|[^\\p{L}\\p{N}])(" + words.map(([w]) => esc(w)).join("|") + ")(?=$|[^\\p{L}\\p{N}])", "giu");
  };
  const SKIP = new Set(["A", "BUTTON", "SCRIPT", "STYLE", "TEXTAREA", "INPUT", "SELECT", "OPTION", "CODE", "svg", "SVG", "TITLE", "SUMMARY"]);
  /** Wrap known terms in `root` so they can be tapped; in Full mode the first use on the page also shows its meaning inline. */
  HZ.glossarize = (root) => {
    if (!termRe || !root || !root.nodeType) return;
    const full = HZ.mode() === "full";
    const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, { acceptNode(n) {
      for (let p = n.parentNode; p && p !== root.parentNode; p = p.parentNode) {
        if (p.nodeType === 1 && (SKIP.has(p.nodeName) || p.classList.contains("term") || p.classList.contains("gl") || p.classList.contains("noterm") || p.classList.contains("src"))) return NodeFilter.FILTER_REJECT;
      }
      return n.nodeValue.trim().length > 2 ? NodeFilter.FILTER_ACCEPT : NodeFilter.FILTER_REJECT;
    } });
    const nodes = []; while (walker.nextNode()) nodes.push(walker.currentNode);
    for (const node of nodes) {
      const text = node.nodeValue; termRe.lastIndex = 0;
      let m, last = 0; const frag = document.createDocumentFragment(); let hit = false;
      // headings, table cells, chips and big labels stay tappable but take no inline definition
      const heading = !!node.parentNode.closest("h1, h2, h3, td, th, .chip, .lean, .big, .view, .pl");
      while ((m = termRe.exec(text))) {
        const word = m[2], key = HZ.termIndex.get(word.toLowerCase()); if (!key) continue;
        const start = m.index + m[1].length;
        frag.appendChild(document.createTextNode(text.slice(last, start)));
        frag.appendChild(el("button", { type: "button", class: "term", "data-term": key, "aria-label": word + ": definition" }, word));
        if (full && !heading && !seen.has(key)) frag.appendChild(el("span", { class: "gl" }, " (" + HZ.TERMS[key].short + ")"));
        if (!heading) seen.add(key);
        last = start + word.length; hit = true;
      }
      if (!hit) continue;
      frag.appendChild(document.createTextNode(text.slice(last)));
      node.parentNode.replaceChild(frag, node);
    }
  };
  /** A term written by a page on purpose (always tappable, and inline-explained in Full mode the first time). */
  HZ.term = (key, label) => {
    const t = HZ.TERMS[key];
    const b = el("button", { type: "button", class: "term", "data-term": key }, label || (t ? t.t : key));
    if (!t || HZ.mode() !== "full" || seen.has(key)) { seen.add(key); return b; }
    seen.add(key); return el("span", {}, b, el("span", { class: "gl" }, " (" + t.short + ")"));
  };
  HZ.define = (key) => {
    const t = HZ.TERMS[key]; if (!t) return;
    HZ.sheet(el("div", {}, el("span", { class: "label" }, "Definition"), el("h2", { id: "sheet-title" }, t.t),
      el("p", {}, t.long || t.short), t.example ? el("p", { class: "small muted" }, el("b", {}, "Example: "), t.example) : null,
      t.lesson ? el("div", { class: "btns" }, el("a", { class: "btn soft", href: "#help/" + t.lesson, onclick: () => HZ.closeSheet() }, "Short lesson: " + (t.lessonTitle || "learn more"))) : null), "s-help");
  };
  document.addEventListener("click", (e) => { const b = e.target.closest && e.target.closest(".term"); if (b) { e.preventDefault(); HZ.define(b.dataset.term); } });

  // ---------------- sheet, toast ----------------
  const sheetEl = document.getElementById("sheet");
  let lastFocus = null;
  HZ.sheet = (content, cls) => {
    lastFocus = document.activeElement;
    const close = el("button", { type: "button", class: "btn small close", onclick: () => HZ.closeSheet(), "aria-label": "Close" }, "Close");
    sheetEl.replaceChildren(el("div", { class: "panel " + (cls || "") }, close, content));
    sheetEl.hidden = false; close.focus();
    HZ.glossarize(sheetEl.firstChild);
  };
  HZ.closeSheet = () => { sheetEl.hidden = true; sheetEl.replaceChildren(); if (lastFocus && lastFocus.focus) lastFocus.focus(); };
  sheetEl.addEventListener("click", (e) => { if (e.target === sheetEl) HZ.closeSheet(); });
  document.addEventListener("keydown", (e) => { if (e.key === "Escape" && !sheetEl.hidden) HZ.closeSheet(); });
  const toastEl = document.getElementById("toast"); let toastT = null;
  HZ.toast = (msg, ms) => { toastEl.textContent = msg; toastEl.classList.add("on"); clearTimeout(toastT); toastT = setTimeout(() => toastEl.classList.remove("on"), ms || 3200); };

  // ---------------- progress ring ----------------
  /** ring(fraction 0..1, centre text, {size, cls, title}): an animated progress ring. */
  HZ.ring = (frac, text, o = {}) => {
    const size = o.size || 64, r = size / 2 - 6, c = 2 * Math.PI * r, f = Math.max(0, Math.min(1, frac || 0));
    const val = svg("circle", { class: "val", cx: size / 2, cy: size / 2, r, fill: "none", "stroke-width": 8, "stroke-dasharray": c, "stroke-dashoffset": c, transform: `rotate(-90 ${size / 2} ${size / 2})` });
    const s = svg("svg", { class: "ring " + (o.cls || ""), width: size, height: size, viewBox: `0 0 ${size} ${size}`, role: "img", "aria-label": o.title || text },
      svg("circle", { class: "trk", cx: size / 2, cy: size / 2, r, fill: "none", "stroke-width": 8 }), val,
      svg("text", { x: "50%", y: "50%", "text-anchor": "middle", "dominant-baseline": "central", style: size < 56 ? "font-size:12px" : null }, text));
    requestAnimationFrame(() => requestAnimationFrame(() => val.setAttribute("stroke-dashoffset", c * (1 - f))));
    return s;
  };
  HZ.meter = (frac, label) => el("div", { class: "meter", role: "img", "aria-label": label || HZ.pct(frac) }, el("i", { style: `width:${Math.max(2, Math.min(100, 100 * (frac || 0)))}%` }));

  // ---------------- charts ----------------
  /** lineChart(rows [[date, value], ...], {unit, decimals, events:[{date,label}], band:[lo,hi], name, range}) -> a chart you can touch to read. */
  HZ.lineChart = (rows, o = {}) => {
    const all = (rows || []).filter((r) => r && r[1] != null && !Number.isNaN(+r[1]));
    const wrap = el("div", { class: "chartbox" });
    if (all.length < 2) { wrap.appendChild(el("div", { class: "empty" }, "Not enough data to draw this chart yet.")); return wrap; }
    const ranges = o.ranges || [["1Y", 365], ["5Y", 1826], ["All", 0]];
    let cur = o.range != null ? o.range : 365;
    const read = el("div", { class: "chartread", "aria-live": "polite" });
    const box = el("div");
    const d = o.decimals != null ? o.decimals : 2, unit = o.unit ? " " + o.unit : "";
    const draw = () => {
      const lastT = Date.parse(all[all.length - 1][0]);
      const pts = cur ? all.filter((r) => Date.parse(r[0]) >= lastT - cur * 864e5) : all;
      const data = pts.length >= 2 ? pts : all.slice(-2);
      const W = 360, H = 210, L = 42, R = 10, T = 12, B = 24;   // drawn near phone width so labels stay readable
      const xs = data.map((r) => Date.parse(r[0])), ys = data.map((r) => +r[1]);
      let lo = Math.min(...ys), hi = Math.max(...ys); if (o.band) { lo = Math.min(lo, o.band[0]); hi = Math.max(hi, o.band[1]); }
      const pad = (hi - lo) * .08 || Math.abs(hi) * .02 || 1; lo -= pad; hi += pad;
      const x = (t) => L + (t - xs[0]) / ((xs[xs.length - 1] - xs[0]) || 1) * (W - L - R);
      const y = (v) => T + (hi - v) / (hi - lo) * (H - T - B);
      const path = data.map((r, i) => (i ? "L" : "M") + x(xs[i]).toFixed(1) + " " + y(ys[i]).toFixed(1)).join("");
      const g = svg("svg", { class: "chart", viewBox: `0 0 ${W} ${H}`, role: "img", "aria-label": (o.name || "Chart") + ": latest " + fmt(ys[ys.length - 1], d) + unit + " on " + data[data.length - 1][0] });
      for (let i = 0; i <= 3; i++) {
        const v = lo + (hi - lo) * i / 3;
        g.appendChild(svg("line", { class: "ax", x1: L, x2: W - R, y1: y(v), y2: y(v) }));
        g.appendChild(svg("text", { class: "lbl", x: L - 6, y: y(v) + 4, "text-anchor": "end" }, fmt(v, Math.abs(hi - lo) < 1 ? Math.max(d, 2) : Math.min(d, 1))));
      }
      [0, Math.floor(data.length / 2), data.length - 1].forEach((i, k) => g.appendChild(svg("text", { class: "lbl", x: x(xs[i]), y: H - 6, "text-anchor": k === 0 ? "start" : k === 2 ? "end" : "middle" }, HZ.dateShort(data[i][0]) + (cur === 0 || cur > 400 ? " " + data[i][0].slice(2, 4) : ""))));
      if (o.band) g.appendChild(svg("rect", { class: "band", x: L, width: W - L - R, y: y(o.band[1]), height: Math.max(0, y(o.band[0]) - y(o.band[1])) }));
      g.appendChild(svg("path", { class: "area", d: path + `L${x(xs[xs.length - 1])} ${H - B}L${x(xs[0])} ${H - B}Z` }));
      g.appendChild(svg("path", { class: "ln", d: path }));
      (o.events || []).forEach((ev) => {
        const t = Date.parse(ev.date); if (t < xs[0] || t > xs[xs.length - 1]) return;
        g.appendChild(svg("line", { class: "ev", x1: x(t), x2: x(t), y1: T, y2: H - B }));
        g.appendChild(svg("text", { class: "lbl", x: x(t) + 3, y: T + 10 }, ev.label.slice(0, 14)));
      });
      g.appendChild(svg("circle", { class: "last", cx: x(xs[xs.length - 1]), cy: y(ys[ys.length - 1]), r: 5 }));
      const hair = svg("line", { class: "hair", y1: T, y2: H - B, visibility: "hidden" }); g.appendChild(hair);
      const show = (ev) => {
        const rect = g.getBoundingClientRect(); const px = (ev.clientX - rect.left) / rect.width * W;
        let i = 0, best = 1e18; xs.forEach((t, k) => { const dd = Math.abs(x(t) - px); if (dd < best) { best = dd; i = k; } });
        hair.setAttribute("x1", x(xs[i])); hair.setAttribute("x2", x(xs[i])); hair.setAttribute("visibility", "visible");
        read.textContent = HZ.dateLong(data[i][0]) + ": " + fmt(ys[i], d) + unit;
      };
      g.addEventListener("pointermove", show); g.addEventListener("pointerdown", show);
      g.addEventListener("pointerleave", () => { hair.setAttribute("visibility", "hidden"); read.textContent = "Latest: " + fmt(ys[ys.length - 1], d) + unit + " on " + HZ.dateLong(data[data.length - 1][0]) + ". Touch the chart to read any day."; });
      read.textContent = "Latest: " + fmt(ys[ys.length - 1], d) + unit + " on " + HZ.dateLong(data[data.length - 1][0]) + ". Touch the chart to read any day.";
      box.replaceChildren(g);
    };
    const tabs = el("div", { class: "tabs", role: "group", "aria-label": "Chart range" }, ...ranges.map(([lab, days]) => {
      const b = el("button", { type: "button", class: days === cur ? "on" : "", "aria-pressed": String(days === cur) }, lab);
      b.addEventListener("click", () => { cur = days; tabs.querySelectorAll("button").forEach((x) => { x.classList.remove("on"); x.setAttribute("aria-pressed", "false"); }); b.classList.add("on"); b.setAttribute("aria-pressed", "true"); draw(); });
      return b;
    }));
    draw();
    wrap.append(o.noRanges ? null : tabs, box, read);
    return wrap;
  };
  /** Simple stats over a series history for "what to look for right now". */
  HZ.stats = (rows, days = 365) => {
    const all = (rows || []).filter((r) => r && r[1] != null);
    if (!all.length) return null;
    const last = all[all.length - 1], lastT = Date.parse(last[0]);
    const win = all.filter((r) => Date.parse(r[0]) >= lastT - days * 864e5).map((r) => +r[1]);
    const mean = win.reduce((a, b) => a + b, 0) / win.length;
    const sd = Math.sqrt(win.reduce((a, b) => a + (b - mean) ** 2, 0) / Math.max(1, win.length - 1));
    const ago = (n) => { const t = lastT - n * 864e5; let v = null; for (const r of all) { if (Date.parse(r[0]) <= t) v = +r[1]; else break; } return v; };
    const lo = Math.min(...win), hi = Math.max(...win);
    return { last: +last[1], date: last[0], mean, sd, z: sd ? (+last[1] - mean) / sd : 0, lo, hi, pos: hi > lo ? (+last[1] - lo) / (hi - lo) : .5, w1: ago(7), m1: ago(30), y1: ago(365), n: win.length };
  };
  HZ.zWords = (z) => z == null ? "" : Math.abs(z) < .5 ? "close to its average of the past year" : Math.abs(z) < 1.5 ? (z > 0 ? "somewhat above" : "somewhat below") + " its average of the past year"
    : Math.abs(z) < 2.5 ? (z > 0 ? "well above" : "well below") + " its average of the past year (unusual)" : (z > 0 ? "far above" : "far below") + " its average of the past year (rare)";

  // ---------------- GitHub forms ----------------
  HZ.issueUrl = (template, params) => {
    const q = new URLSearchParams({ template: template + ".yml" });
    for (const [k, v] of Object.entries(params || {})) if (v != null && v !== "") q.set(k, String(v));
    return "https://github.com/" + REPO + "/issues/new?" + q.toString();
  };
  HZ.formBtn = (label, template, params, cls) => el("a", { class: "btn " + (cls || "soft"), href: HZ.issueUrl(template, params), target: "_blank", rel: "noopener" }, label);
  HZ.callBtn = (o, label, cls) => HZ.formBtn(label || "Make a call", "full-call", { title: "[Full call] " + (o.title || o.question || ""), question: o.question, question_id: o.question_id, resolution_date: o.resolution_date, base_rate: o.base_rate }, cls || "primary");
  HZ.tradeBtn = (instrument, o, label, cls) => HZ.formBtn(label || "Open a paper trade", "open-trade", { title: "[Open trade] " + instrument, instrument, link: o && o.link, horizon: o && o.horizon, thesis: o && o.thesis }, cls || "soft");

  // ---------------- Ask Claude ----------------
  /** Each page registers what it shows: HZ.ctx.add(section, lines). Ask Claude turns it into one clear text package. */
  const ctx = HZ.ctx = { title: "", sections: [], question: "", reset(title, question) { this.title = title; this.sections = []; this.question = question || ""; },
    add(section, lines) { const ls = HZ.nn(lines).map(String).filter((s) => s.trim()); if (ls.length) this.sections.push([section, ls]); },
    ask(q) { this.question = q; } };
  HZ.packageText = () => {
    const L = [`Horizons: ${ctx.title || "page"} (${HZ.today()})`, "",
      "I'm using Horizons, my personal research app on Brazil, Mexico and France bonds and currencies and on gold. Below is what this page shows, with dates. Facts come from the sources named; anything marked as a view or judgement is a model's opinion, not a fact.", ""];
    for (const [s, ls] of ctx.sections) { L.push("## " + s); ls.forEach((x) => L.push(x.startsWith("- ") ? x : "- " + x)); L.push(""); }
    L.push("Suggested opening question: " + (ctx.question || "What matters most on this page right now, and what am I most likely missing?"));
    return L.join("\n");
  };
  const copy = (text) => (navigator.clipboard && window.isSecureContext ? navigator.clipboard.writeText(text) : Promise.reject(new Error("no clipboard")))
    .catch(() => { const t = el("textarea", { style: "position:fixed;opacity:0" }); t.value = text; document.body.appendChild(t); t.select(); let ok = false; try { ok = document.execCommand("copy"); } catch (e) { ok = false; } t.remove(); if (!ok) throw new Error("copy failed"); });
  HZ.ask = () => {
    const text = HZ.packageText();
    const pref = store.get("claude", "");
    let left = false; const onHide = () => { if (document.hidden) { left = true; store.set("claude", "app"); } };
    const show = (copied) => HZ.sheet(el("div", {}, el("span", { class: "label" }, "Ask Claude"), el("h2", { id: "sheet-title" }, copied ? "Copied. Paste it into Claude." : "Copy this into Claude"),
      el("p", { class: "small" }, "This page's key data, the brief, Horizons' view and your calls are on your clipboard (" + text.length.toLocaleString() + " characters), with a suggested first question. Paste it into a new chat. It uses your own Claude subscription; Horizons makes no API call for this."),
      el("div", { class: "btns" }, el("a", { class: "btn primary", href: "claude://", onclick: () => store.set("claude", "app") }, "Open the Claude app"),
        el("a", { class: "btn soft", href: "https://claude.ai/new", target: "_blank", rel: "noopener", onclick: () => store.set("claude", "web") }, "Open claude.ai")),
      el("details", {}, el("summary", {}, "See the text"), el("pre", { class: "small noterm", style: "white-space:pre-wrap;max-height:40vh;overflow:auto" }, text)),
      copied ? null : el("button", { type: "button", class: "btn", onclick: () => copy(text).then(() => HZ.toast("Copied")).catch(() => HZ.toast("Select the text above and copy it")) }, "Copy again")), "s-home");
    const done = copy(text).then(() => true).catch(() => false);
    if (pref === "web") { window.open("https://claude.ai/new", "_blank", "noopener"); done.then((ok) => HZ.toast(ok ? "Copied: paste it into Claude" : "Copy failed: use the text in Horizons")); return; }
    document.addEventListener("visibilitychange", onHide);
    location.href = "claude://";      // the app opens if it is installed; otherwise nothing happens and the sheet offers claude.ai
    setTimeout(() => { document.removeEventListener("visibilitychange", onHide); if (!left) done.then(show); }, 1500);
  };
  document.getElementById("ask").addEventListener("click", HZ.ask);
  HZ.askBtn = (label) => el("button", { type: "button", class: "btn soft", onclick: HZ.ask }, label || "Ask Claude about this page");

  // ---------------- menu: help and settings ----------------
  HZ.applyTheme = (t) => { if (t) document.documentElement.setAttribute("data-theme", t); else document.documentElement.removeAttribute("data-theme"); };
  HZ.applyTheme(store.get("theme", ""));
  const seg = (label, opts, cur, set) => el("div", {}, el("div", { class: "label", style: "margin-top:12px" }, label),
    el("div", { class: "tabs", role: "radiogroup", "aria-label": label }, ...opts.map(([v, t, hint]) => el("button", { type: "button", role: "radio", "aria-checked": String(v === cur), class: v === cur ? "on" : "", title: hint || null, onclick: () => set(v) }, t))));
  HZ.menu = () => HZ.sheet(el("div", {}, el("span", { class: "label" }, "Menu"), el("h2", { id: "sheet-title" }, "Help and settings"),
    el("div", { class: "btns" }, el("a", { class: "btn primary", href: "#help", onclick: () => HZ.closeSheet() }, "Help and lessons"),
      el("button", { type: "button", class: "btn soft", onclick: () => { HZ.closeSheet(); HZ.need("hz-help").then(() => HZ.walkthrough(true)); } }, "Replay the welcome tour")),
    seg("Explain mode", [["full", "Full", "Explanations under every chart and table, and terms explained the first time"], ["light", "Light", "Only 'what to look for right now'"], ["off", "Off", "Clean data"]],
      HZ.mode(), (v) => { HZ.closeSheet(); HZ.setMode(v); HZ.toast("Explain mode: " + v); }),
    el("p", { class: "tiny" }, "Full: what each chart shows, how to read it and what to look for now, with terms explained the first time. Light: only what to look for now. Off: clean data. Terms stay tappable in every mode."),
    seg("Theme", [["", "Auto"], ["light", "Light"], ["dark", "Dark"]], store.get("theme", ""), (v) => { store.set("theme", v); HZ.applyTheme(v); HZ.closeSheet(); }),
    el("div", { class: "btns" }, el("a", { class: "btn", href: "#glossary", onclick: () => HZ.closeSheet() }, "Glossary"), el("a", { class: "btn", href: HZ.CATALYST }, "Open Catalyst"),
      el("a", { class: "btn", href: "https://github.com/" + REPO + "#how-to-use-catalyst", target: "_blank", rel: "noopener" }, "README"))), "s-help");
  document.getElementById("menu").addEventListener("click", HZ.menu);

  // ---------------- routing ----------------
  const ROUTES = {
    home: ["hz-home", "pageHome"], brief: ["hz-home", "pageBrief"], country: ["hz-country", "pageCountry"], gold: ["hz-gold", "pageGold"],
    calendar: ["hz-markets", "pageCalendar"], scenarios: ["hz-markets", "pageScenarios"], crowd: ["hz-markets", "pageCrowd"],
    record: ["hz-record", "pageRecord"], help: ["hz-help", "pageHelp"], glossary: ["hz-help", "pageGlossary"],
  };
  const NAV = { home: "home", brief: "home", calendar: "calendar", scenarios: "scenarios", crowd: "scenarios", record: "record" };
  let routeN = 0;
  function route() {
    const n = ++routeN;
    const full = location.hash.replace(/^#/, "") || "home";
    const [path, query] = full.split("?");
    const parts = path.split("/"); const page = ROUTES[parts[0]] ? parts[0] : "home"; const arg = parts.slice(1).join("/");
    seen = new Set();
    ctx.reset(page);
    document.querySelectorAll(".bar a").forEach((a) => a.classList.toggle("on", a.dataset.p === NAV[page]));
    document.querySelectorAll(".places a").forEach((a) => a.classList.toggle("on", a.getAttribute("href") === "#" + path));
    document.querySelectorAll(".bar a").forEach((a) => a.toggleAttribute("aria-current", a.dataset.p === NAV[page]));
    app.replaceChildren(HZ.skel("lines"), HZ.skel());
    const [mod, fn] = ROUTES[page];
    termsReady.then(() => HZ.need(mod)).then(() => HZ[fn](arg, new URLSearchParams(query || ""))).then((node) => {
      if (n !== routeN) return;
      app.replaceChildren(...HZ.nn(node));
      HZ.glossarize(app);
      document.title = (ctx.title && ctx.title !== page ? ctx.title + " · " : "") + "Horizons";
    }).catch((err) => { if (n === routeN) app.replaceChildren(el("div", { class: "card" }, el("h2", {}, "Something went wrong"), HZ.err(err))); });
  }
  HZ.route = route;
  const termsReady = HZ.need("hz-terms").catch(() => null);

  // offline notice
  const off = document.getElementById("offline");
  const net = () => off.classList.toggle("on", navigator.onLine === false);
  window.addEventListener("online", net); window.addEventListener("offline", net); net();
  if ("serviceWorker" in navigator && location.protocol !== "file:") navigator.serviceWorker.register("sw.js").catch(() => { /* not fatal */ });

  window.addEventListener("hashchange", () => { route(); window.scrollTo(0, 0); });
  route();
  // first open: the welcome walkthrough, once; afterwards it lives in the menu
  if (store.get("welcomed", "") !== "1") termsReady.then(() => HZ.need("hz-help")).then(() => HZ.walkthrough(false)).catch(() => null);
})();
