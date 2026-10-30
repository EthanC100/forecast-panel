/* Horizons: a paper portfolio and record app. Four tabs (Portfolio, Markets, Algorithm, Strategy),
   decisions pasted from Claude chats, sign-in by email magic link. Private data (decisions, trades,
   close requests, notes) lives in Supabase behind row-level security; prices and the algorithm come
   from the public data files the pipeline publishes (../data/). The daily workflow fills trades at
   the next end-of-day close and marks them to market; this page only reads those results and writes
   requests. */
(function () {
  "use strict";
  const CFG = window.HZ_CONFIG || {};
  const DATA = "../data/";
  const ACCOUNT = 100000;
  const MARKETS = { BR: "Brazil", MX: "Mexico", FR: "France", GOLD: "Gold" };
  const app = document.getElementById("app");
  const $ = (id) => document.getElementById(id);

  // ---------------- helpers ----------------
  const el = (tag, attrs, ...kids) => {
    const n = document.createElement(tag);
    if (attrs) for (const [k, v] of Object.entries(attrs)) {
      if (v == null || v === false) continue;
      if (k === "class") n.className = v; else if (k === "text") n.textContent = v;
      else if (k.startsWith("on")) n.addEventListener(k.slice(2), v); else n.setAttribute(k, v);
    }
    for (const kid of kids.flat(3)) if (kid != null && kid !== false) n.appendChild(typeof kid === "object" ? kid : document.createTextNode(String(kid)));
    return n;
  };
  const svg = (tag, attrs, ...kids) => {
    const n = document.createElementNS("http://www.w3.org/2000/svg", tag);
    for (const [k, v] of Object.entries(attrs || {})) if (v != null) n.setAttribute(k, v);
    kids.forEach((k) => k != null && n.appendChild(typeof k === "string" ? document.createTextNode(k) : k));
    return n;
  };
  const fmt = (v, d = 2) => v == null || !isFinite(v) ? "–" : Number(v).toLocaleString("en-US", { minimumFractionDigits: d, maximumFractionDigits: d });
  const sign = (v) => (v > 0 ? "+" : v < 0 ? "−" : "");
  const signed = (v, d = 2, suf = "") => v == null || !isFinite(v) ? "–" : sign(v) + fmt(Math.abs(v), d) + suf;
  /** money gain or loss: green with +, red with − */
  const money = (v, d = 0) => el("span", { class: "num " + (v > 0 ? "gain" : v < 0 ? "loss" : "flat") }, v == null ? "–" : sign(v) + "$" + fmt(Math.abs(v), d));
  const pctPL = (v, d = 2) => el("span", { class: "num " + (v > 0 ? "gain" : v < 0 ? "loss" : "flat") }, signed(v, d, "%"));
  /** a market move: sign, neutral colour */
  const move = (v, d, suf) => el("span", { class: "num flat" }, signed(v, d, suf));
  const today = () => new Date().toISOString().slice(0, 10);
  const dShort = (iso) => iso ? new Date(iso.slice(0, 10) + "T12:00:00Z").toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "2-digit", timeZone: "UTC" }) : "–";
  const dLong = (iso) => iso ? new Date(iso.slice(0, 10) + "T12:00:00Z").toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric", timeZone: "UTC" }) : "–";
  const getJSON = (p) => fetch(DATA + p, { cache: "no-cache" }).then((r) => { if (!r.ok) throw new Error(p + ": " + r.status); return r.json(); });
  const cache = {};
  const json = (p) => (cache[p] = cache[p] || getJSON(p).catch((e) => { delete cache[p]; throw e; }));
  const maybe = (p) => json(p).catch(() => null);
  const series = (id) => id ? maybe("series/" + id + ".json").then((s) => (s && s.history || []).filter((r) => r[1] != null && isFinite(r[1])).map((r) => [r[0], +r[1]])) : Promise.resolve([]);
  const toastEl = $("toast"); let toastT;
  const toast = (m) => { toastEl.textContent = m; toastEl.classList.add("on"); clearTimeout(toastT); toastT = setTimeout(() => toastEl.classList.remove("on"), 3200); };
  const skel = () => el("div", {}, el("div", { class: "skel" }), el("div", { class: "skel block" }));
  const sheetEl = $("sheet");
  const sheet = (role, ...kids) => { sheetEl.replaceChildren(el("div", { class: "panel " + role }, el("div", { class: "grab" }), ...kids)); sheetEl.hidden = false; };
  const closeSheet = () => { sheetEl.hidden = true; sheetEl.replaceChildren(); };
  sheetEl.addEventListener("click", (e) => { if (e.target === sheetEl) closeSheet(); });
  document.addEventListener("keydown", (e) => { if (e.key === "Escape" && !sheetEl.hidden) closeSheet(); });

  // instruments: book metadata (name, kind, series, unit) from the public book state
  let INST = {};
  const kindOf = (code) => (INST[code] && INST[code].kind) || (window.Decision.INSTRUMENTS[code] || [])[1] || "fx";
  const nameOf = (code) => (INST[code] && INST[code].name) || (window.Decision.INSTRUMENTS[code] || [code])[0];
  const dec = (code) => ({ fx: 4, price: 2, yield: 2, spread_bp: 1 })[kindOf(code)] ?? 2;
  const unitOf = (code) => ({ yield: "%", spread_bp: "bp" })[kindOf(code)] || "";
  /** distance from the current level to a level: % for fx/price, bp for yields and spreads */
  function distance(code, cur, lvl) {
    if (cur == null || lvl == null) return null;
    const k = kindOf(code);
    if (k === "fx" || k === "price") return { v: 100 * (lvl / cur - 1), d: 2, suf: "%" };
    if (k === "yield") return { v: 100 * (lvl - cur), d: 0, suf: "bp" };
    return { v: lvl - cur, d: 1, suf: "bp" };
  }
  const dirLabel = (code, dir) => {
    const k = kindOf(code);
    if (k === "yield" || k === "spread_bp") return dir === "long" ? "Long (gains if " + (k === "spread_bp" ? "the spread narrows" : "the yield falls") + ")" : "Short (gains if " + (k === "spread_bp" ? "the spread widens" : "the yield rises") + ")";
    return dir === "long" ? "Long" : "Short";
  };

  // ---------------- charts ----------------
  /** lineChart(rows, {ranges, refs:[{v, cls}], second, decimals, unit, mini, label, drawdown}) */
  function lineChart(rows, o = {}) {
    const box = el("div"), read = el("div", { class: "readout" });
    const all = (rows || []).filter((r) => r[1] != null && isFinite(r[1]));
    if (all.length < 2) return el("div", { class: "empty small" }, o.empty || "Not enough data for a chart yet.");
    const d = o.decimals ?? 2, unit = o.unit || "";
    let range = o.range ?? (o.ranges ? o.ranges[0][1] : 0);
    const draw = () => {
      const lastT = Date.parse(all[all.length - 1][0]);
      let data = range ? all.filter((r) => Date.parse(r[0]) >= lastT - range * 864e5) : all;
      if (data.length < 2) data = all.slice(-2);
      const t0 = Date.parse(data[0][0]);
      const sec = (o.second || []).filter((r) => Date.parse(r[0]) >= t0);
      const W = 340, H = o.mini ? 64 : 170, L = o.mini ? 2 : 4, R = o.mini ? 2 : 40, T = 6, B = o.mini ? 4 : 18;
      const ys = data.map((r) => r[1]).concat(sec.map((r) => r[1])).concat((o.refs || []).map((r) => r.v).filter((v) => v != null && isFinite(v)));
      let lo = Math.min(...ys), hi = Math.max(...ys); const pad = (hi - lo) * .06 || Math.abs(hi) * .01 || 1; lo -= pad; hi += pad;
      const t1 = Date.parse(data[data.length - 1][0]);
      const x = (t) => L + (t - t0) / ((t1 - t0) || 1) * (W - L - R), y = (v) => T + (hi - v) / (hi - lo) * (H - T - B);
      const path = (rs) => rs.map((r, i) => (i ? "L" : "M") + x(Date.parse(r[0])).toFixed(1) + " " + y(r[1]).toFixed(1)).join("");
      const g = svg("svg", { class: "chart", viewBox: `0 0 ${W} ${H}`, role: "img", "aria-label": (o.label || "Chart") + ", latest " + fmt(data[data.length - 1][1], d) + unit });
      if (!o.mini) for (let i = 0; i <= 3; i++) {
        const v = lo + (hi - lo) * i / 3;
        g.appendChild(svg("line", { class: "grid", x1: L, x2: W - R, y1: y(v), y2: y(v) }));
        g.appendChild(svg("text", { class: "lbl", x: W - R + 4, y: y(v) + 3 }, fmt(v, Math.abs(hi - lo) < 2 ? Math.max(1, Math.min(d, 3)) : Math.min(d, 1))));
      }
      if (!o.mini) [0, data.length - 1].forEach((i, k) => g.appendChild(svg("text", { class: "lbl", x: x(Date.parse(data[i][0])), y: H - 4, "text-anchor": k ? "end" : "start" }, dShort(data[i][0]))));
      if (o.drawdown) {   // shade below the running peak
        let peak = -Infinity; const top = [], bot = [];
        data.forEach((r) => { peak = Math.max(peak, r[1]); top.push([r[0], peak]); bot.push(r); });
        g.appendChild(svg("path", { class: "dd", d: path(top) + bot.slice().reverse().map((r) => "L" + x(Date.parse(r[0])).toFixed(1) + " " + y(r[1]).toFixed(1)).join("") + "Z" }));
      }
      if (!o.drawdown) g.appendChild(svg("path", { class: "fill", d: path(data) + `L${x(t1)} ${H - B}L${x(t0)} ${H - B}Z` }));
      (o.refs || []).forEach((r) => { if (r.v != null && isFinite(r.v)) g.appendChild(svg("line", { class: "ref " + r.cls, x1: L, x2: W - R, y1: y(r.v), y2: y(r.v) })); });
      if (sec.length > 1) g.appendChild(svg("path", { class: "ln2", d: path(sec) }));
      g.appendChild(svg("path", { class: "ln", d: path(data) }));
      if (!o.mini) {
        const hair = svg("line", { class: "hair", y1: T, y2: H - B, visibility: "hidden" }); g.appendChild(hair);
        const setRead = (i) => { read.textContent = dLong(data[i][0]) + ": " + fmt(data[i][1], d) + unit; };
        const show = (ev) => {
          const rc = g.getBoundingClientRect(), px = (ev.clientX - rc.left) / rc.width * W;
          let i = 0, best = 1e9; data.forEach((r, k) => { const dd = Math.abs(x(Date.parse(r[0])) - px); if (dd < best) { best = dd; i = k; } });
          hair.setAttribute("x1", x(Date.parse(data[i][0]))); hair.setAttribute("x2", x(Date.parse(data[i][0]))); hair.setAttribute("visibility", "visible"); setRead(i);
        };
        g.addEventListener("pointermove", show); g.addEventListener("pointerdown", show);
        g.addEventListener("pointerleave", () => { hair.setAttribute("visibility", "hidden"); setRead(data.length - 1); });
        setRead(data.length - 1);
      }
      box.replaceChildren(g);
      if (o.onRange) o.onRange(data);
    };
    const seg = o.ranges ? el("div", { class: "seg", role: "group", "aria-label": "Range" }, ...o.ranges.map(([lab, days]) => {
      const b = el("button", { type: "button", class: days === range ? "on" : "", "aria-pressed": String(days === range) }, lab);
      b.addEventListener("click", () => { range = days; seg.querySelectorAll("button").forEach((z) => { z.classList.toggle("on", z === b); z.setAttribute("aria-pressed", String(z === b)); }); draw(); });
      return b;
    })) : null;
    draw();
    return el("div", {}, seg ? el("div", { class: "row spread", style: "margin-bottom:6px" }, o.title || el("span"), seg) : null, box, o.mini ? null : read);
  }
  const RANGES = [["1M", 31], ["3M", 92], ["1Y", 366], ["5Y", 1827]];

  // ---------------- Supabase ----------------
  const sb = CFG.supabaseUrl && CFG.supabaseKey && window.supabase
    ? window.supabase.createClient(CFG.supabaseUrl, CFG.supabaseKey, { auth: { persistSession: true, autoRefreshToken: true, detectSessionInUrl: true, flowType: "pkce" } }) : null;
  const S = { session: null, owner: null, trades: [], decisions: [], closes: [], notes: [], loaded: false };
  async function loadDb() {
    const q = (t, order) => sb.from(t).select("*").order(order || "created_at", { ascending: true });
    const [t, d, c, n] = await Promise.all([q("trades"), q("decisions"), q("trade_closes", "requested_at"), q("notes")]);
    for (const r of [t, d, c, n]) if (r.error) throw new Error(r.error.message);
    S.trades = t.data; S.decisions = d.data; S.closes = c.data; S.notes = n.data; S.loaded = true;
  }
  const reload = () => loadDb().then(route).catch((e) => toast("Could not refresh: " + e.message));

  // ---------------- book maths (from the workflow's marks) ----------------
  const totalOf = (t) => +t.pnl_total || 0;
  function equityNow() {
    return ACCOUNT + S.trades.filter((t) => t.status === "open" || t.status === "closed").reduce((a, t) => a + totalOf(t), 0);
  }
  function equityCurve() {
    const tr = S.trades.filter((t) => (t.status === "open" || t.status === "closed") && Array.isArray(t.marks) && t.marks.length);
    if (!tr.length) return [];
    const dates = [...new Set(tr.flatMap((t) => t.marks.map((m) => m[0])))].sort();
    const idx = tr.map(() => -1);
    const first = dates[0];
    const start = new Date(Date.parse(first) - 864e5).toISOString().slice(0, 10);
    const out = [[start, ACCOUNT]];
    for (const d of dates) {
      let sum = 0;
      tr.forEach((t, k) => { while (idx[k] + 1 < t.marks.length && t.marks[idx[k] + 1][0] <= d) idx[k]++; if (idx[k] >= 0) sum += +t.marks[idx[k]][5] || 0; });
      out.push([d, ACCOUNT + sum]);
    }
    return out;
  }
  function maxDrawdown(curve) {
    let peak = -Infinity, worst = 0, cur = 0;
    curve.forEach((r) => { peak = Math.max(peak, r[1]); const dd = r[1] / peak - 1; worst = Math.min(worst, dd); cur = dd; });
    return { worst: 100 * worst, current: 100 * cur };
  }
  const openRisk = () => S.trades.filter((t) => t.status === "open").reduce((a, t) => a + (+t.risk_usd || 0), 0);
  const pendingClose = (t) => S.closes.find((c) => c.trade_id === t.id && !c.processed_at);

  // ---------------- Portfolio ----------------
  async function pagePortfolio() {
    const curve = equityCurve(), eq = equityNow(), dd = maxDrawdown(curve);
    const open = S.trades.filter((t) => t.status === "open"), pending = S.trades.filter((t) => t.status === "pending");
    const closed = S.trades.filter((t) => t.status === "closed").sort((a, b) => (b.exit_date || "").localeCompare(a.exit_date || ""));
    const rejected = S.trades.filter((t) => t.status === "rejected");
    const dayChg = curve.length > 1 ? curve[curve.length - 1][1] - curve[curve.length - 2][1] : null;
    const head = el("div", { class: "card" },
      el("div", { class: "label" }, "Account value"),
      el("div", { class: "big" }, "$" + fmt(eq, 0)),
      el("div", { class: "row", style: "gap:14px;flex-wrap:wrap" }, el("span", {}, money(eq - ACCOUNT), " ", el("span", { class: "tiny" }, "(", pctPL(100 * (eq / ACCOUNT - 1)), ") since start")),
        dayChg != null ? el("span", {}, money(dayChg), el("span", { class: "tiny" }, " last day")) : null),
      el("div", { class: "kv" }, kv("Starting balance", "$" + fmt(ACCOUNT, 0)), kv("Open positions", String(open.length)), kv("Risk to stops", "$" + fmt(openRisk(), 0)),
        kv("Max drawdown", fmt(dd.worst, 1) + "%"), kv("From peak now", fmt(dd.current, 1) + "%")),
      el("div", { style: "margin-top:14px" }, curve.length > 1 ? lineChart(curve, { ranges: [["1M", 31], ["3M", 92], ["1Y", 366], ["All", 0]], range: 0, decimals: 0, label: "Equity", drawdown: true, title: el("span", { class: "label" }, "Equity and drawdown") })
        : el("div", { class: "empty small" }, "The equity curve starts once a trade has filled.")));
    const out = [head];
    out.push(section("Open positions", open.length ? open.length + " open" : ""));
    if (!open.length && !pending.length) out.push(el("div", { class: "card" }, el("div", { class: "empty" }, "No open paper trades. Paste a decision with Action Buy or Sell, or copy a position from the Algorithm tab.")));
    for (const t of open) out.push(await positionCard(t));
    for (const t of pending) out.push(pendingCard(t));
    if (rejected.length) { out.push(section("Not filled")); rejected.slice(-5).forEach((t) => out.push(el("div", { class: "card" }, el("div", { class: "row spread" }, el("h3", {}, nameOf(t.instrument)), el("span", { class: "chip warn" }, "rejected")), el("div", { class: "small muted" }, t.reject_reason || "")))); }
    out.push(section("Closed trades", closed.length ? closed.length + " closed" : ""));
    out.push(closed.length ? el("div", { class: "card flush" }, el("div", { class: "list" }, ...closed.map(closedRow))) : el("div", { class: "card" }, el("div", { class: "empty" }, "No closed trades yet.")));
    return out;
  }
  const kv = (k, v) => el("div", {}, el("div", { class: "k" }, k), el("div", { class: "v" }, v));
  const section = (title, aside) => el("div", { class: "section" }, el("h2", {}, title), aside ? el("span", { class: "tiny" }, aside) : null);

  async function positionCard(t) {
    const code = t.instrument, sid = INST[code] && INST[code].series;
    const rows = await series(sid);
    const from = t.entry_date ? new Date(Date.parse(t.entry_date) - 30 * 864e5).toISOString().slice(0, 10) : null;
    const recent = rows.filter((r) => !from || r[0] >= from);
    const cur = t.last_value != null ? +t.last_value : (rows.length ? rows[rows.length - 1][1] : null);
    const sd = distance(code, cur, t.stop_level), td = distance(code, cur, t.target_level);
    const pc = pendingClose(t);
    const r = t.risk_usd ? (+t.pnl_total || 0) / t.risk_usd : null;
    return el("div", { class: "card" },
      el("div", { class: "row spread" }, el("div", { class: "grow" }, el("h3", {}, nameOf(code)), el("div", { class: "tiny" }, dirLabel(code, t.direction), " · since ", dLong(t.entry_date), t.source === "algorithm" ? " · from the algorithm" : "")),
        el("div", { class: "right" }, el("div", { class: "mid" }, money(t.pnl_total)), el("div", { class: "tiny" }, r != null ? signed(r, 2, "R") : ""))),
      el("div", { class: "kv" }, kv("Entry", fmt(t.entry_value, dec(code)) + unitOf(code)), kv("Current", fmt(cur, dec(code)) + unitOf(code) + (t.last_date ? " · " + dShort(t.last_date) : "")),
        kv("Price", money(t.pnl_price)), kv("Carry", money(t.pnl_carry)), kv("Cost", money(t.pnl_cost)),
        kv("To stop", sd ? el("span", {}, fmt(t.stop_level, dec(code)), " (", move(sd.v, sd.d, sd.suf), ")") : "–"),
        kv("To target", td ? el("span", {}, fmt(t.target_level, dec(code)), " (", move(td.v, td.d, td.suf), ")") : "none"),
        kv("Size", "$" + fmt(t.notional_usd, 0) + " · risk $" + fmt(t.risk_usd, 0))),
      el("div", { style: "margin-top:10px" }, lineChart(recent, { mini: true, decimals: dec(code), refs: [{ v: +t.entry_value, cls: "entry" }, { v: +t.stop_level, cls: "stop" }, { v: t.target_level != null ? +t.target_level : null, cls: "target" }], label: nameOf(code) })),
      el("div", { class: "legend" }, el("span", {}, "— entry"), el("span", { class: "loss" }, "— stop"), t.target_level != null ? el("span", { class: "gain" }, "— target") : null),
      pc ? el("div", { class: "chip warn", style: "margin-top:10px" }, "Closing at the next end-of-day close")
        : el("div", { class: "btns" }, el("button", { type: "button", class: "btn danger", onclick: () => closeFlow(t) }, "Close")));
  }
  function pendingCard(t) {
    return el("div", { class: "card" },
      el("div", { class: "row spread" }, el("div", {}, el("h3", {}, nameOf(t.instrument)), el("div", { class: "tiny" }, dirLabel(t.instrument, t.direction), " · requested ", dShort(t.requested_at))), el("span", { class: "chip" }, "Opens at the next close")),
      el("div", { class: "kv" }, kv("Risk", fmt(t.risk_pct, 2) + "% of account"), kv("Stop", fmt(t.stop_level, dec(t.instrument)) + unitOf(t.instrument)), kv("Horizon", dLong(t.horizon))),
      el("div", { class: "btns" }, el("button", { type: "button", class: "btn small", onclick: async () => {
        const { error } = await sb.from("trades").delete().eq("id", t.id);
        if (error) toast(error.message); else { toast("Cancelled"); reload(); }
      } }, "Cancel")));
  }
  function closedRow(t) {
    const r = t.risk_usd ? (+t.pnl_total || 0) / t.risk_usd : null;
    const c = S.closes.find((x) => x.trade_id === t.id && x.note);
    return el("div", { class: "item" },
      el("div", { class: "row spread" }, el("div", { class: "grow" }, el("b", {}, nameOf(t.instrument)), " ", el("span", { class: "tiny" }, t.direction)), money(t.pnl_total)),
      el("div", { class: "tiny" }, dShort(t.entry_date), " ", fmt(t.entry_value, dec(t.instrument)), " → ", dShort(t.exit_date), " ", fmt(t.exit_value, dec(t.instrument)), " · ", t.exit_reason || "", r != null ? " · " + signed(r, 2, "R") : ""),
      c ? el("div", { class: "small muted text" }, c.note) : null);
  }
  function closeFlow(t) {
    const note = el("textarea", { class: "i", style: "min-height:110px", placeholder: "Optional note (what happened, what you'd do differently)" });
    sheet("r-portfolio", el("h2", {}, "Close " + nameOf(t.instrument) + "?"),
      el("p", { class: "small muted" }, "It closes at the next end-of-day close. Current P&L: ", money(t.pnl_total), "."),
      el("label", { class: "f" }, "Note", note),
      el("div", { class: "btns" }, el("button", { type: "button", class: "btn danger", onclick: async (e) => {
        e.currentTarget.disabled = true;
        const { error } = await sb.from("trade_closes").insert({ trade_id: t.id, note: note.value.trim() || null });
        if (error) { toast(error.message); e.currentTarget.disabled = false; return; }
        closeSheet(); toast("Closes at the next end-of-day close"); reload();
      } }, "Close position"), el("button", { type: "button", class: "btn", onclick: closeSheet }, "Cancel")));
  }

  // ---------------- Markets ----------------
  const WATCH = [["usdbrl", "USD/BRL", "fx"], ["usdmxn", "USD/MXN", "fx"], ["eurusd", "EUR/USD", "fx"], ["oatbund", "France–Germany 10y spread", "spread_bp"],
    ["br10y", "Brazil 10y proxy", "yield"], ["us10y", "US 10y", "yield"], ["gold", "Gold", "price"], ["silver", "Silver", "price"]];
  async function pageMarkets() {
    const summary = await maybe("summary.json");
    const tiles = {}; ((summary && summary.tiles) || []).forEach((t) => (tiles[t.key] = t));
    const pick = async (key) => {
      if (key === "gold" || key === "silver") {
        const daily = await series("gl." + key);
        if (daily.length > 30) return { rows: daily, src: "COMEX front-month futures (Yahoo " + (key === "gold" ? "GC=F" : "SI=F") + ")", unit: "USD/oz" };
        return { rows: await series("gl." + key + ".wb_m"), src: "World Bank monthly average (daily prices unavailable)", unit: "USD/oz" };
      }
      const t = tiles[key], sid = t && t.meta && t.meta.series;
      return { rows: await series(sid), src: t && t.meta ? t.meta.source : "", unit: t ? t.unit : "" };
    };
    let range = 92;
    const cards = [];
    const body = el("div");
    const segBtns = el("div", { class: "seg", role: "group", "aria-label": "Range" });
    const loaded = await Promise.all(WATCH.map(([k]) => pick(k)));
    const render = () => {
      body.replaceChildren(...WATCH.map(([k, label, kind], i) => {
        const { rows, src, unit } = loaded[i];
        if (!rows.length) return el("div", { class: "card r-markets" }, el("h3", {}, label), el("div", { class: "empty small" }, "No data yet."));
        const last = rows[rows.length - 1], prev = rows[rows.length - 2];
        const tEnd = Date.parse(last[0]);
        const base = rows.find((r) => Date.parse(r[0]) >= tEnd - range * 864e5) || rows[0];
        const ch = (a, b) => kind === "yield" ? { v: 100 * (a - b), d: 0, s: "bp" } : kind === "spread_bp" ? { v: a - b, d: 1, s: "bp" } : { v: 100 * (a / b - 1), d: 2, s: "%" };
        const c1 = prev ? ch(last[1], prev[1]) : null, cr = ch(last[1], base[1]);
        const dd = kind === "fx" ? 4 : kind === "price" ? 2 : kind === "yield" ? 2 : 1;
        return el("div", { class: "card r-markets" },
          el("div", { class: "row spread" }, el("div", { class: "grow" }, el("h3", {}, label), el("div", { class: "tiny" }, unit, " · ", dShort(last[0]))),
            el("div", { class: "right" }, el("div", { class: "mid" }, fmt(last[1], dd) + (kind === "yield" ? "%" : "")),
              el("div", { class: "small" }, c1 ? move(c1.v, c1.d, c1.s) : "–", el("span", { class: "tiny" }, prev && Date.parse(last[0]) - Date.parse(prev[0]) > 5 * 864e5 ? " since " + dShort(prev[0]) + " · " : " 1D · "), move(cr.v, cr.d, cr.s), el("span", { class: "tiny" }, " " + RANGES.find((r) => r[1] === range)[0])))),
          el("div", { style: "margin-top:8px" }, lineChart(rows, { range, decimals: dd, unit: kind === "yield" ? "%" : kind === "spread_bp" ? "bp" : "", label })),
          el("div", { class: "tiny" }, src));
      }));
    };
    RANGES.forEach(([lab, days]) => {
      const b = el("button", { type: "button", class: days === range ? "on" : "", "aria-pressed": String(days === range) }, lab);
      b.addEventListener("click", () => { range = days; segBtns.querySelectorAll("button").forEach((z) => { z.classList.toggle("on", z === b); z.setAttribute("aria-pressed", String(z === b)); }); render(); });
      segBtns.appendChild(b);
    });
    render();
    cards.push(el("div", { class: "row spread", style: "margin:4px 0 12px" }, el("span", { class: "tiny" }, "End-of-day levels. Changes are market moves, not gains or losses."), segBtns), body);
    return cards;
  }

  // ---------------- Algorithm ----------------
  async function pageAlgorithm() {
    const a = await maybe("algorithm.json");
    if (!a) return [el("div", { class: "card" }, el("div", { class: "empty" }, "The algorithm's positions appear after the next data run."))];
    const pnl = (a.pnl || []).map((r) => Array.isArray(r) ? r : [r.month, r.net, r.carry_basket, r.cumulative_net, r.cumulative_carry_basket, r.sample]);
    const cumN = pnl.filter((r) => r[3] != null).map((r) => [r[0] + "-28", 100 * (r[3] - 1)]);
    const cumC = pnl.filter((r) => r[4] != null).map((r) => [r[0] + "-28", 100 * (r[4] - 1)]);
    const last = pnl[pnl.length - 1];
    const tm = a.this_month || {};
    const out = [el("div", { class: "card r-algorithm" },
      el("div", { class: "label" }, "em-macro systematic strategy"),
      el("div", { class: "row spread", style: "flex-wrap:wrap" }, el("h2", {}, "Positions for " + (a.effective_from || "this month")), el("span", { class: "tiny" }, "signals as of " + (a.as_of || "–"))),
      el("div", { class: "kv" }, kv("Last month", last ? pctPL(100 * last[1]) : "–"), kv("Carry basket", last ? pctPL(100 * last[2]) : "–"),
        kv("Since " + (pnl.length ? pnl[0][0] : "start"), cumN.length ? pctPL(cumN[cumN.length - 1][1], 1) : "–"), kv("Carry basket since " + (pnl.length ? pnl[0][0] : "start"), cumC.length ? pctPL(cumC[cumC.length - 1][1], 1) : "–"),
        tm.n_positions != null ? kv("Positions", String(tm.n_positions)) : null),
      el("div", { style: "margin-top:12px" }, lineChart(cumN, { ranges: [["1Y", 366], ["5Y", 1827], ["All", 0]], range: 1827, second: cumC, decimals: 1, unit: "%", label: "Cumulative return", title: el("span", { class: "label" }, "Paper P&L vs the carry basket") })),
      el("div", { class: "legend" }, el("span", {}, el("i"), "algorithm"), el("span", {}, el("i", { class: "dash" }), "carry basket")),
      el("div", { class: "tiny", style: "margin-top:8px" }, (last && last[5] ? "Latest month: " + last[5] + ". " : ""), "Source: ", el("a", { href: a.source || "https://github.com/EthanC100/em-macro/tree/main/results/systematic", target: "_blank", rel: "noopener" }, "em-macro results/systematic")))];
    const groups = {};
    (a.positions || []).forEach((p) => (groups[p.book || "other"] = groups[p.book || "other"] || []).push(p));
    for (const [g, ps] of Object.entries(groups)) {
      out.push(section(g === "fx" ? "Currencies" : g === "bond" ? "Bonds" : g, ps.length + " positions"));
      out.push(el("div", { class: "card flush r-algorithm" }, el("div", { class: "list" }, ...ps.map(algoRow))));
    }
    return out;
  }
  const bar = (label, z) => [el("span", { class: "tiny" }, label), el("div", { class: "bar", role: "img", "aria-label": label + " score " + (z == null ? "none" : fmt(z, 2)) },
    z == null ? null : el("i", { style: z >= 0 ? `left:50%;width:${Math.min(50, Math.abs(z) / 3 * 50)}%` : `right:50%;width:${Math.min(50, Math.abs(z) / 3 * 50)}%` })),
    el("span", { class: "tiny num right" }, z == null ? "–" : signed(z, 2))];
  function algoRow(p) {
    const cp = p.copyable && typeof p.copyable === "object" ? p.copyable : null;
    const code = cp ? cp.instrument : typeof p.copyable === "string" ? p.copyable : null;
    const z = (k) => p[k] === "" || p[k] == null ? null : +p[k];
    return el("div", { class: "item" },
      el("div", { class: "row spread" }, el("div", { class: "grow" }, el("b", {}, p.instrument), " ", el("span", { class: "chip role" }, p.side), el("div", { class: "tiny" }, p.description)),
        el("div", { class: "right tiny" }, fmt(+p.size_pct_of_capital, 1) + "% of capital", el("br"), "risk share " + fmt(+p.risk_share_pct, 1) + "%")),
      el("div", { class: "bars" }, ...bar("Carry", z("carry_z")), ...bar("Trend", z("trend_z")), ...bar("Value", z("value_z"))),
      el("div", { class: "btns" }, code ? el("button", { type: "button", class: "btn small primary", onclick: () => copyFlow({ ...p, ...(cp || {}), side: p.side }, code) }, "Copy into my portfolio")
        : el("span", { class: "tiny" }, "Not in the paper book (no price series here).")));
  }
  function copyFlow(p, code) {
    const dir = p.direction || (p.side === "long" ? "long" : "short");
    const risk = el("input", { class: "i", type: "number", step: "0.1", min: "0.1", max: "2", value: "1", inputmode: "decimal" });
    const stop = el("input", { class: "i", type: "number", step: "any", value: p.suggested_stop != null ? String(p.suggested_stop) : "", inputmode: "decimal" });
    const hz = el("input", { class: "i", type: "date", value: p.horizon || endOfNextMonth() });
    const msg = el("div");
    sheet("r-algorithm", el("h2", {}, "Copy " + p.instrument + " into my portfolio"),
      el("p", { class: "small muted" }, dirLabel(code, dir) + " " + nameOf(code) + ". It opens at the next end-of-day close."),
      el("label", { class: "f" }, "Risk (% of account to the stop, max 2%)", risk), el("label", { class: "f" }, "Stop level (" + (unitOf(code) || "price") + ")", stop),
      p.suggested_stop != null ? el("div", { class: "tiny" }, "Suggested: " + (p.stop_basis || "two standard deviations of a month's move") + (p.level != null ? " from the latest level " + fmt(p.level, dec(code)) + (p.level_date ? " (" + dShort(p.level_date) + ")" : "") : "") + ".") : null,
      el("label", { class: "f" }, "Horizon", hz), msg,
      el("div", { class: "btns" }, el("button", { type: "button", class: "btn primary", onclick: async (e) => {
        const r = parseFloat(risk.value), s = parseFloat(stop.value);
        const errs = [];
        if (!(r > 0)) errs.push("Risk must be above 0%."); if (r > 2) errs.push("Risk is " + r + "% of the account. The maximum is 2%.");
        if (!isFinite(s)) errs.push("Enter a stop level.");
        if (errs.length) { msg.replaceChildren(el("div", { class: "errors" }, el("ul", {}, ...errs.map((x) => el("li", {}, x))))); return; }
        e.currentTarget.disabled = true;
        const { error } = await sb.from("trades").insert({ instrument: code, direction: dir, risk_pct: r, stop_level: s, horizon: hz.value || null, source: "algorithm",
          note: "Copied from em-macro systematic (" + (p.instrument_em || p.instrument) + " " + p.side + ")" });
        if (error) { msg.replaceChildren(el("div", { class: "errors" }, error.message)); e.currentTarget.disabled = false; return; }
        closeSheet(); toast("Opens at the next end-of-day close"); reload();
      } }, "Copy"), el("button", { type: "button", class: "btn", onclick: closeSheet }, "Cancel")));
  }
  function endOfNextMonth() { const d = new Date(); return new Date(Date.UTC(d.getUTCFullYear(), d.getUTCMonth() + 2, 0)).toISOString().slice(0, 10); }

  // ---------------- Strategy ----------------
  function pageStrategy() {
    const out = [el("p", { class: "tiny", style: "margin:4px 0 12px" }, "Decision records pasted from your Claude chats with Paste decision (top right).")];
    for (const [c, name] of Object.entries(MARKETS)) {
      const ds = S.decisions.filter((d) => d.country === c).sort((a, b) => (b.decision_date + b.created_at).localeCompare(a.decision_date + a.created_at));
      const latest = ds[0];
      const notes = S.notes.filter((n) => n.country === c).slice(-3).reverse();
      out.push(el("div", { class: "card r-strategy" },
        el("div", { class: "row spread" }, el("h2", {}, name), latest ? el("span", { class: "chip role" }, latest.action) : null),
        latest ? decisionBody(latest) : el("div", { class: "empty" }, "No decision yet."),
        ds.length > 1 ? el("details", { style: "margin-top:12px" }, el("summary", { class: "small", style: "cursor:pointer;font-weight:600" }, "Past decisions (" + (ds.length - 1) + ")"),
          el("div", { class: "list", style: "margin-top:6px" }, ...ds.slice(1).map((d) => el("button", { type: "button", class: "item", style: "border:0;background:none;width:100%;text-align:left;cursor:pointer", onclick: () => sheet("r-strategy", el("h2", {}, name + " · " + dLong(d.decision_date)), decisionBody(d)) },
            el("div", { class: "row spread" }, el("span", {}, el("b", {}, dShort(d.decision_date)), " ", d.action, " ", nameOf(d.instrument) || d.instrument_label || ""), scoreChip(d)))))) : null,
        notes.length ? el("div", { style: "margin-top:10px" }, el("div", { class: "label" }, "Notes"), ...notes.map((n) => el("div", { class: "small text", style: "margin-top:4px" }, el("span", { class: "tiny" }, dShort(n.created_at) + " "), n.body))) : null,
        el("div", { class: "btns" }, el("button", { type: "button", class: "btn small", onclick: () => noteFlow(c, name) }, "Add note"))));
    }
    return out;
  }
  const scoreChip = (d) => d.outcome == null ? (d.probability != null ? el("span", { class: "tiny" }, fmt(100 * d.probability, 0) + "%") : null)
    : el("span", { class: "chip" }, (d.outcome ? "Right" : "Wrong") + " · Brier " + fmt(d.brier, 2));
  function decisionBody(d) {
    const t = d.trade_id ? S.trades.find((x) => x.id === d.trade_id) : null;
    const field = (k, v) => v ? el("div", { style: "margin-top:10px" }, el("div", { class: "label" }, k), el("div", { class: "small text" }, v)) : null;
    return el("div", {},
      el("div", { class: "kv" }, kv("Date", dLong(d.decision_date)), kv("Instrument", d.instrument_label || nameOf(d.instrument)), kv("Action", d.action),
        kv("Risk", fmt(d.risk_pct, 2) + "%"), kv("Probability right", d.probability != null ? fmt(100 * d.probability, 0) + "%" : "–"), kv("Horizon", dLong(d.horizon)),
        kv("Stop", d.stop_text || "–"), d.outcome != null ? kv("Scored", el("span", {}, d.outcome ? "Right" : "Wrong", " · Brier ", fmt(d.brier, 2))) : null,
        t ? kv("Trade", el("span", {}, t.status, t.pnl_total != null ? [" · ", money(t.pnl_total)] : null)) : null),
      field("Entry trigger", d.entry_trigger), field("Thesis", d.thesis), field("Key factors", d.key_factors), field("What would change my mind", d.change_mind),
      field("How this differs from market consensus", d.vs_consensus));
  }
  function noteFlow(country, name) {
    const ta = el("textarea", { class: "i", style: "min-height:120px" });
    sheet("r-strategy", el("h2", {}, "Note on " + name), el("label", { class: "f" }, "Note", ta),
      el("div", { class: "btns" }, el("button", { type: "button", class: "btn primary", onclick: async () => {
        if (!ta.value.trim()) return;
        const { error } = await sb.from("notes").insert({ country, body: ta.value.trim() });
        if (error) toast(error.message); else { closeSheet(); toast("Saved"); reload(); }
      } }, "Save"), el("button", { type: "button", class: "btn", onclick: closeSheet }, "Cancel")));
  }

  // ---------------- Paste decision ----------------
  function pasteFlow() {
    const ta = el("textarea", { class: "i", placeholder: "DECISION RECORD\nDate: …\nCountry: …\nInstrument: …\nAction: …\nSize (% of account at risk, max 2%): …\nProbability my view is right: …\nHorizon (date): …\nEntry trigger: …\nStop / exit if wrong: …\nThesis: …\nKey factors: …\nWhat would change my mind: …\nHow this differs from market consensus: …", "aria-label": "Decision record" });
    const msg = el("div");
    sheet("r-strategy", el("h2", {}, "Paste decision"),
      el("p", { class: "small muted" }, "Paste the DECISION RECORD block from your Claude chat."),
      navigator.clipboard && navigator.clipboard.readText ? el("button", { type: "button", class: "btn small", onclick: async () => { try { ta.value = await navigator.clipboard.readText(); } catch (e) { toast("Paste into the box instead"); } } }, "Paste from clipboard") : null,
      ta, msg,
      el("div", { class: "btns" }, el("button", { type: "button", class: "btn primary", onclick: () => {
        const r = window.Decision.parse(ta.value);
        if (!r.ok) { msg.replaceChildren(el("div", { class: "errors" }, el("b", {}, "This record can't be saved:"), el("ul", {}, ...r.errors.map((x) => el("li", {}, x))))); return; }
        confirmFlow(r);
      } }, "Check"), el("button", { type: "button", class: "btn", onclick: closeSheet }, "Cancel")));
    setTimeout(() => ta.focus(), 50);
  }
  async function confirmFlow(r) {
    const d = r.decision, eq = equityNow();
    const trades = d.action === "Buy" || d.action === "Sell";
    const sid = INST[d.instrument] && INST[d.instrument].series;
    const rows = trades ? await series(sid) : [];
    const level = rows.length ? rows[rows.length - 1] : null;
    const errors = [], warnings = [...r.warnings];
    if (trades && level && !window.Decision.stopSideOk(r.kind, r.direction, level[1], d.stop_level))
      errors.push("The stop " + fmt(d.stop_level, dec(d.instrument)) + " is on the wrong side of the latest level " + fmt(level[1], dec(d.instrument)) + " for a " + d.action.toLowerCase() + ". " + dirLabel(d.instrument, r.direction) + ".");
    const openOnInst = S.trades.filter((t) => t.status === "open" && t.instrument === d.instrument);
    if (d.action === "Close" && !openOnInst.length) warnings.push("There is no open trade on " + nameOf(d.instrument) + " to close; the decision is saved on its own.");
    const sd = level ? distance(d.instrument, level[1], d.stop_level) : null;
    const row = (k, v) => el("div", { class: "item" }, el("div", { class: "tiny" }, k), el("div", { class: "small text" }, v || "–"));
    sheet("r-strategy", el("h2", {}, "Confirm decision"),
      el("div", { class: "card flush", style: "margin-top:12px" }, el("div", { class: "list" },
        row("Date", dLong(d.decision_date)), row("Market", MARKETS[d.country]), row("Instrument", (d.instrument_label || "") + (window.Decision.INSTRUMENTS[d.instrument] ? " → " + nameOf(d.instrument) : "")),
        row("Action", d.action + (trades ? " · " + dirLabel(d.instrument, r.direction) : "")),
        row("Size", fmt(d.risk_pct, 2) + "% of the account at risk" + (trades ? " ≈ $" + fmt(eq * d.risk_pct / 100, 0) + " to the stop" : "")),
        row("Probability my view is right", d.probability != null ? fmt(100 * d.probability, 0) + "%" : "–"), row("Horizon", dLong(d.horizon)),
        row("Stop / exit if wrong", (d.stop_text || "–") + (trades && level ? " · latest " + fmt(level[1], dec(d.instrument)) + " (" + dShort(level[0]) + ")" + (sd ? ", stop " + signed(sd.v, sd.d, sd.suf) + " away" : "") : "")),
        row("Entry trigger", d.entry_trigger), row("Thesis", d.thesis), row("Key factors", d.key_factors), row("What would change my mind", d.change_mind), row("How this differs from market consensus", d.vs_consensus))),
      trades ? el("p", { class: "small" }, "Saving opens a paper trade at the next end-of-day close. The size is set at the fill so the loss to your stop is " + fmt(d.risk_pct, 2) + "% of the account.") : null,
      d.action === "Close" && openOnInst.length ? el("p", { class: "small" }, "Saving also closes your open " + nameOf(d.instrument) + " trade at the next end-of-day close.") : null,
      warnings.length ? el("div", { class: "warnings" }, el("ul", {}, ...warnings.map((x) => el("li", {}, x)))) : null,
      errors.length ? el("div", { class: "errors" }, el("ul", {}, ...errors.map((x) => el("li", {}, x)))) : null,
      el("div", { class: "btns" }, el("button", { type: "button", class: "btn primary", disabled: errors.length ? "disabled" : null, onclick: (e) => save(e, r, openOnInst) }, "Save"),
        el("button", { type: "button", class: "btn", onclick: pasteFlow }, "Back")));
  }
  async function save(e, r, openOnInst) {
    const btn = e.currentTarget; btn.disabled = true;
    const d = r.decision;
    const row = { decision_date: d.decision_date, country: d.country, instrument: d.instrument, instrument_label: d.instrument_label, action: d.action, risk_pct: d.risk_pct,
      probability: d.probability, horizon: d.horizon, entry_trigger: d.entry_trigger, stop_text: d.stop_text, stop_level: d.stop_level, thesis: d.thesis,
      key_factors: d.key_factors, change_mind: d.change_mind, vs_consensus: d.vs_consensus, raw: d.raw };
    const ins = await sb.from("decisions").insert(row).select().single();
    if (ins.error) { toast(ins.error.message); btn.disabled = false; return; }
    let msg = "Decision saved";
    if (r.direction) {
      const tr = await sb.from("trades").insert({ decision_id: ins.data.id, instrument: d.instrument, direction: r.direction, risk_pct: d.risk_pct, stop_level: d.stop_level,
        horizon: d.horizon, source: "decision", note: "Decision of " + d.decision_date }).select().single();
      if (tr.error) { toast("Decision saved, but the trade was not: " + tr.error.message); closeSheet(); reload(); return; }
      await sb.from("decisions").update({ trade_id: tr.data.id }).eq("id", ins.data.id);
      msg = "Saved. The trade opens at the next end-of-day close.";
    } else if (d.action === "Close" && openOnInst.length) {
      const res = await sb.from("trade_closes").insert(openOnInst.map((t) => ({ trade_id: t.id, note: "Decision of " + d.decision_date })));
      msg = res.error ? "Decision saved; the close failed: " + res.error.message : "Saved. The position closes at the next end-of-day close.";
    }
    closeSheet(); toast(msg); location.hash = "#strategy"; reload();
  }

  // ---------------- sign-in ----------------
  function pageSignIn(note) {
    const email = el("input", { class: "i", type: "email", autocomplete: "email", placeholder: "you@example.com", "aria-label": "Email" });
    const code = el("input", { class: "i", inputmode: "numeric", autocomplete: "one-time-code", placeholder: "6-digit code", "aria-label": "Code from the email", maxlength: "10" });
    const msg = el("div", { class: "small", style: "margin-top:12px" }, note || "");
    const codeBox = el("div", { hidden: "hidden" }, el("label", { class: "f" }, "Or type the code from the email (for the installed app)", code),
      el("div", { class: "btns", style: "justify-content:center" }, el("button", { type: "button", class: "btn", onclick: async () => {
        const { error } = await sb.auth.verifyOtp({ email: email.value.trim(), token: code.value.trim(), type: "email" });
        if (error) msg.textContent = error.message;
      } }, "Sign in with code")));
    return [el("div", { class: "signin" }, el("img", { src: "icons/icon-192.png", alt: "" }), el("h2", {}, "Horizons"), el("p", { class: "muted" }, "Sign in with a link sent to your email. This device stays signed in."),
      el("label", { class: "f", style: "text-align:left" }, "Email", email),
      el("div", { class: "btns", style: "justify-content:center" }, el("button", { type: "button", class: "btn primary r-markets", onclick: async (e) => {
        if (!email.value.includes("@")) { msg.textContent = "Enter your email."; return; }
        e.currentTarget.disabled = true;
        const { error } = await sb.auth.signInWithOtp({ email: email.value.trim(), options: { emailRedirectTo: location.origin + location.pathname } });
        e.currentTarget.disabled = false;
        if (error) { msg.textContent = error.message; return; }
        msg.textContent = "Check your email and open the link on this device."; codeBox.hidden = false;
      } }, "Email me a sign-in link")), msg, codeBox)];
  }
  function pageNotOwner() {
    return [el("div", { class: "signin" }, el("h2", {}, "Almost there"),
      el("p", { class: "small" }, "You're signed in as ", el("b", {}, S.session.user.email), ", but this account isn't the owner yet, so it can't read or write anything."),
      el("p", { class: "small muted" }, "In Supabase, open SQL Editor and run the owner line from supabase/schema.sql with this email, then reload."),
      el("div", { class: "btns", style: "justify-content:center" }, el("button", { type: "button", class: "btn", onclick: () => location.reload() }, "Reload"), el("button", { type: "button", class: "btn", onclick: () => sb.auth.signOut() }, "Sign out")))];
  }
  function pageNotConfigured() {
    return [el("div", { class: "signin" }, el("h2", {}, "Not connected"), el("p", { class: "small muted" }, "This copy of Horizons has no Supabase settings. The deploy writes them from the repository secrets SUPABASE_URL and SUPABASE_ANON_KEY."))];
  }
  $("account").addEventListener("click", () => sheet("", el("h2", {}, "Account"), el("p", { class: "small" }, "Signed in as ", el("b", {}, S.session ? S.session.user.email : "–"), " on this device."),
    el("div", { class: "btns" }, el("button", { type: "button", class: "btn danger", onclick: async () => { await sb.auth.signOut(); closeSheet(); } }, "Sign out"),
      el("a", { class: "btn", href: "../" }, "Open Catalyst (archive)"), el("button", { type: "button", class: "btn", onclick: closeSheet }, "Close"))));
  $("paste").addEventListener("click", pasteFlow);

  // ---------------- routing ----------------
  const PAGES = { portfolio: ["Portfolio", pagePortfolio, "r-portfolio"], markets: ["Markets", pageMarkets, "r-markets"], algorithm: ["Algorithm", pageAlgorithm, "r-algorithm"], strategy: ["Strategy", pageStrategy, "r-strategy"] };
  let n = 0;
  async function route() {
    const k = ++n;
    const signedIn = !!(S.session && S.owner);
    $("tabs").hidden = !signedIn; $("paste").hidden = !signedIn; $("account").hidden = !S.session;
    if (!sb) return show("Horizons", pageNotConfigured(), "");
    if (!S.session) return show("Horizons", pageSignIn(), "");
    if (S.owner === false) return show("Horizons", pageNotOwner(), "");
    if (!S.loaded) { app.replaceChildren(skel()); try { await loadDb(); } catch (e) { return show("Horizons", [el("div", { class: "err" }, "Could not load your data: " + e.message)], ""); } }
    const key = (location.hash.replace("#", "").split("/")[0]) || "portfolio";
    const [title, fn, role] = PAGES[key] || PAGES.portfolio;
    document.querySelectorAll(".tabs a").forEach((a) => { const on = a.dataset.t === (PAGES[key] ? key : "portfolio"); a.classList.toggle("on", on); a.toggleAttribute("aria-current", on); });
    app.replaceChildren(skel());
    try { const nodes = await fn(); if (k === n) show(title, nodes, role); } catch (e) { if (k === n) show(title, [el("div", { class: "err" }, String(e.message || e))], role); }
  }
  function show(title, nodes, role) { $("title").textContent = title; app.className = role; app.replaceChildren(...nodes.filter(Boolean)); document.title = title === "Horizons" ? "Horizons" : title + " · Horizons"; }
  window.addEventListener("hashchange", () => { route(); window.scrollTo(0, 0); });

  async function start() {
    const st = await maybe("book/state.json");
    INST = (st && st.instruments) || {};
    if (!sb) return route();
    const { data } = await sb.auth.getSession();
    S.session = data.session;
    if (S.session) { const r = await sb.rpc("is_owner"); S.owner = r.error ? null : !!r.data; }
    sb.auth.onAuthStateChange(async (ev, session) => {
      const had = S.session && S.session.user.id;
      S.session = session;
      if (!session) { S.owner = null; S.loaded = false; return route(); }
      if (had !== session.user.id) { const r = await sb.rpc("is_owner"); S.owner = r.error ? null : !!r.data; S.loaded = false; route(); }
    });
    route();
  }
  if ("serviceWorker" in navigator && location.protocol !== "file:") navigator.serviceWorker.register("sw.js").catch(() => null);
  start();
})();
