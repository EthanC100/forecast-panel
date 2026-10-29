/* Charts: one interactive time-chart engine (crosshair, tap/drag for values, zoom, stacked comparison
   panel, calendar markers, numbered notes on the largest moves) plus bar, waterfall and band helpers.
   Every chart prints its numbers too: the latest value, a data table, or a value on each bar. */
(function () {
  "use strict";
  const T = window.TERM;
  const nn = T.nn;
  const { el, fmt, signed, meta } = T;
  const NS = "http://www.w3.org/2000/svg";
  const ns = (t, a, ...kids) => {
    const n = document.createElementNS(NS, t);
    for (const [k, v] of Object.entries(a || {})) if (v != null) n.setAttribute(k, v);
    kids.forEach((c) => c != null && n.appendChild(typeof c === "string" ? document.createTextNode(c) : c));
    return n;
  };
  function ticks(a, b, n) {
    const span = b - a || Math.abs(a) || 1, s0 = span / n, mag = 10 ** Math.floor(Math.log10(s0)), e = s0 / mag;
    const step = (e >= 7.5 ? 10 : e >= 3.5 ? 5 : e >= 1.5 ? 2 : 1) * mag, out = [];
    for (let v = Math.ceil(a / step) * step; v <= b + step * 1e-6; v += step) out.push(+v.toFixed(10));
    return { list: out, dec: Math.max(0, -Math.floor(Math.log10(step) + 1e-9)) };
  }
  const DAY = 864e5;
  const iso = (t) => new Date(t).toISOString().slice(0, 10);
  const nearest = (xs, t) => { let lo = 0, hi = xs.length - 1; if (hi < 0) return -1; while (hi - lo > 1) { const m = (lo + hi) >> 1; if (xs[m] < t) lo = m; else hi = m; } return Math.abs(xs[lo] - t) <= Math.abs(xs[hi] - t) ? lo : hi; };

  /**
   * timeChart({ panels: [{ title, lines: [{ label, points: [[iso, v]], color }], fmt, height, shade: [[iso0, iso1]], zero }],
   *             x0, x1, ahead, markers: [{ t, title, sub, href, source }], annos: [{ t, v, n }] })
   * Panels share the x-axis and crosshair (small multiples instead of a second y-axis).
   */
  function timeChart(o) {
    const wrap = el("div", { class: "viz" }), tip = el("div", { class: "tip", role: "status" });
    const svg = ns("svg", { role: "img", "aria-label": o.aria || "chart" });
    wrap.append(...nn(svg, tip));
    const panels = o.panels.map((p) => ({ ...p, lines: p.lines.map((l) => ({ ...l, xs: l.points.map((q) => Date.parse(q[0])), ys: l.points.map((q) => q[1]) })) }));
    const allX = panels.flatMap((p) => p.lines.flatMap((l) => l.xs));
    const x0 = o.x0 != null ? o.x0 : Math.min(...allX), xData1 = Math.max(...allX), x1 = o.x1 != null ? o.x1 : xData1;
    let pop = null;
    function render() {
      const W = Math.max(280, wrap.clientWidth || 600), narrow = W < 460;
      const yr = panels.map((p) => {
        const ys = p.lines.flatMap((l) => l.ys.filter((v, i) => v != null && l.xs[i] >= x0 && l.xs[i] <= x1));
        if (p.zero) ys.push(0);
        let a = Math.min(...ys), b = Math.max(...ys); const pad = (b - a) * 0.08 || Math.abs(b) * 0.02 || 1; a -= pad; b += pad;
        return { a, b, t: ticks(a, b, narrow ? 3 : 4) };
      });
      const labW = Math.max(...panels.map((p, i) => Math.max(...yr[i].t.list.map((v) => (p.fmt ? p.fmt(v) : fmt(v, yr[i].t.dec)).length)))) * 6.6 + 10;
      const P = { l: Math.max(34, labW), r: 12 }, TITLE = 18, GAP = 10, AX = 26;
      let y = 0; const geo = panels.map((p) => { const h = p.height || (narrow ? 170 : 210); const g = { top: y + TITLE, h }; y += TITLE + h + GAP; return g; });
      const H = y - GAP + AX + (o.markers && o.markers.length ? 14 : 0);
      svg.setAttribute("viewBox", `0 0 ${W} ${H}`); svg.textContent = "";
      const X = (t) => P.l + ((t - x0) / (x1 - x0 || 1)) * (W - P.l - P.r);
      const lastPlotBottom = geo[geo.length - 1].top + geo[geo.length - 1].h;
      if (xData1 < x1) svg.appendChild(ns("rect", { x: X(xData1), y: geo[0].top, width: X(x1) - X(xData1), height: lastPlotBottom - geo[0].top, fill: "var(--surface-2)", opacity: 0.6 }));
      if (xData1 < x1) svg.appendChild(ns("text", { x: X(xData1) + 4, y: geo[0].top + 11, class: "lbl-t" }, "ahead"));
      panels.forEach((p, i) => {
        const g = geo[i], { a, b, t } = yr[i];
        const Y = (v) => g.top + (1 - (v - a) / (b - a)) * g.h;
        p._Y = Y;
        svg.appendChild(ns("text", { x: 0, y: g.top - 6, class: "lbl-t", "font-weight": 650 }, p.title || ""));
        (p.shade || []).forEach(([s0, s1]) => {
          const xa = X(Math.max(x0, Date.parse(s0))), xb = X(Math.min(x1, Date.parse(s1)));
          if (xb > xa) svg.appendChild(ns("rect", { x: xa, y: g.top, width: xb - xa, height: g.h, fill: "var(--bad-soft)" }));
        });
        const gl = ns("g", { class: "gridl" }), ax = ns("g", { class: "axis" });
        t.list.forEach((v) => { const yy = Y(v); gl.appendChild(ns("line", { x1: P.l, x2: W - P.r, y1: yy, y2: yy })); ax.appendChild(ns("text", { x: P.l - 6, y: yy + 4, "text-anchor": "end" }, p.fmt ? p.fmt(v) : fmt(v, t.dec))); });
        svg.append(...nn(gl, ax));
        if (p.zero && a < 0 && b > 0) svg.appendChild(ns("line", { x1: P.l, x2: W - P.r, y1: Y(0), y2: Y(0), class: "base" }));
        p.lines.forEach((l) => {
          let d = "", pen = false;
          l.xs.forEach((xx, k) => { const v = l.ys[k]; if (v == null || xx < x0 || xx > x1) { pen = false; return; } d += (pen ? "L" : "M") + X(xx).toFixed(1) + "," + Y(v).toFixed(1); pen = true; });
          svg.appendChild(ns("path", { d, class: "line", stroke: l.color || "var(--cat-1)" }));
          // label the last value directly when there are several lines
          if (p.lines.length > 1) { const k = l.ys.length - 1; if (k >= 0 && l.xs[k] <= x1) svg.appendChild(ns("text", { x: Math.min(X(l.xs[k]) + 4, W - 4), y: Y(l.ys[k]) - 4, class: "lbl-t", "text-anchor": X(l.xs[k]) > W - 60 ? "end" : "start" }, l.label)); }
        });
      });
      // x axis
      const ax = ns("g", { class: "axis" }), nx = narrow ? 3 : 5, span = x1 - x0;
      for (let i = 0; i <= nx; i++) {
        const tt = x0 + (span * i) / nx, d = iso(tt);
        ax.appendChild(ns("text", { x: X(tt), y: lastPlotBottom + 16, "text-anchor": i === 0 ? "start" : i === nx ? "end" : "middle" }, span > 500 * DAY ? d.slice(0, 7) : d.slice(5)));
      }
      svg.append(...nn(ax, ns("line", { class: "base", x1: P.l, x2: W - P.r, y1: lastPlotBottom, y2: lastPlotBottom })));
      // annotations: numbered circles on the first line of the first panel
      (o.annos || []).forEach((n) => {
        const cx = X(Date.parse(n.t)), cy = panels[0]._Y(n.v);
        svg.append(...nn(ns("circle", { cx, cy, r: 8, fill: "var(--surface)", stroke: "var(--text)", "stroke-width": 1.5 }),
          ns("text", { x: cx, y: cy + 3.5, "text-anchor": "middle", "font-size": 10, "font-weight": 800, fill: "var(--text)" }, String(n.n))));
      });
      // event markers under the last panel; markers closer than 14px merge into one tap target listing them all
      const ms = (o.markers || []).map((m) => ({ ...m, x: X(Date.parse(m.t)) })).filter((m) => m.x >= P.l - 1 && m.x <= W - P.r + 1).sort((a, b) => a.x - b.x);
      const groups = []; ms.forEach((m) => { const g = groups[groups.length - 1]; if (g && m.x - g[g.length - 1].x < 14) g.push(m); else groups.push([m]); });
      groups.forEach((g) => {
        const cx = g.reduce((a, m) => a + m.x, 0) / g.length, cy = lastPlotBottom + 24, up = g.some((m) => m.upcoming);
        const node = ns("g", { tabindex: 0, role: "button", "aria-label": g.map((m) => m.t + " " + m.title).join("; "), style: "cursor:pointer" },
          ns("rect", { x: cx - 12, y: cy - 12, width: 24, height: 24, fill: "transparent" }),
          ns("path", { d: `M${cx},${cy - 5} L${cx + 5},${cy + 4} L${cx - 5},${cy + 4} Z`, fill: up ? "var(--accent)" : "var(--text-3)" }),
          g.length > 1 ? ns("text", { x: cx + 7, y: cy + 4, class: "lbl-t", "font-size": 9 }, String(g.length)) : null);
        const open = (ev) => { ev.stopPropagation(); showPop(g, cx / W); };
        node.addEventListener("click", open); node.addEventListener("keydown", (ev) => { if (ev.key === "Enter") open(ev); });
        svg.appendChild(node);
      });
      // crosshair over every panel
      const hair = ns("line", { class: "hair", y1: geo[0].top, y2: lastPlotBottom });
      const dots = panels.map((p) => p.lines.map((l) => ns("circle", { r: 4, class: "dotm", fill: l.color || "var(--cat-1)", style: "display:none" })));
      const hit = ns("rect", { x: P.l, y: geo[0].top, width: W - P.l - P.r, height: lastPlotBottom - geo[0].top, fill: "transparent", style: "cursor:crosshair" });
      svg.append(...nn(hair, ...dots.flat(), hit));
      const move = (e) => {
        const r = svg.getBoundingClientRect(), px = ((e.clientX - r.left) / r.width) * W;
        const t = x0 + ((px - P.l) / (W - P.l - P.r)) * span;
        tip.textContent = ""; let hx = null, date = null;
        panels.forEach((p, i) => p.lines.forEach((l, j) => {
          const k = nearest(l.xs, Math.min(t, xData1)); if (k < 0 || l.ys[k] == null) { dots[i][j].style.display = "none"; return; }
          const cx = X(l.xs[k]), cy = p._Y(l.ys[k]); if (hx == null) { hx = cx; date = l.points[k][0]; }
          dots[i][j].setAttribute("cx", cx); dots[i][j].setAttribute("cy", cy); dots[i][j].style.display = "block";
          tip.append(...nn(el("div", {}, el("span", { class: "k", style: "background:" + (l.color || "var(--cat-1)") }), el("strong", { class: "num" }, p.fmt ? p.fmt(l.ys[k], true) : fmt(l.ys[k], 2)), " ", el("span", { class: "tiny" }, l.label || p.title || ""))));
        }));
        if (hx == null) return;
        tip.prepend(el("div", { class: "tiny" }, date));
        hair.setAttribute("x1", hx); hair.setAttribute("x2", hx); hair.style.display = "block";
        tip.style.display = "block"; tip.style.left = hx / W > 0.55 ? "8px" : "auto"; tip.style.right = hx / W > 0.55 ? "auto" : "8px";
      };
      const leave = () => { hair.style.display = "none"; dots.flat().forEach((d) => (d.style.display = "none")); tip.style.display = "none"; };
      hit.addEventListener("pointermove", move); hit.addEventListener("pointerdown", move); hit.addEventListener("pointerleave", leave);
    }
    function showPop(list, rel) {
      if (pop) pop.remove();
      pop = el("div", { class: "evpop", style: (rel > 0.5 ? "right:8px;" : "left:8px;") + "bottom:30px" },
        el("button", { class: "x", type: "button", "aria-label": "Close", onclick: () => { pop.remove(); pop = null; } }, "×"),
        ...list.slice(0, 6).map((m, i) => el("div", { style: i ? "margin-top:8px;padding-top:8px;border-top:1px solid var(--border)" : "" },
          el("div", { class: "tiny" }, m.t + (m.upcoming ? " · upcoming" : "")), el("b", {}, m.title), m.sub ? el("div", { class: "small muted" }, m.sub) : null,
          el("div", { class: "row small", style: "margin-top:4px" }, m.href ? el("a", { href: m.href }, "open in calendar →") : null, m.source ? el("a", { href: m.source, target: "_blank", rel: "noopener" }, "source") : null))),
        list.length > 6 ? el("div", { class: "tiny", style: "margin-top:6px" }, "+" + (list.length - 6) + " more; zoom in to separate them") : null);
      wrap.appendChild(pop);
    }
    render();
    if (window.ResizeObserver) { let w0 = 0; new ResizeObserver(() => { const w = wrap.clientWidth; if (Math.abs(w - w0) > 2) { w0 = w; render(); } }).observe(wrap); }
    return wrap;
  }

  // ---------------- series card (country pages) ----------------
  const RANGES = { "1M": 31, "3M": 92, "1Y": 365, "5Y": 1826 };
  const COUNTRY_OF = { br: "BR", mx: "MX", fr: "FR", de: "FR", us: "GLOBAL" };
  function decimalsFor(s) { const u = (s.unit || "").toLowerCase(); return / per usd|per usd|brl|mxn/.test(u) ? 4 : u.startsWith("%") ? 2 : 1; }
  function changeOf(s, a, b) { const u = (s.unit || "").toLowerCase(); if (/per usd|brl|mxn/.test(u)) return { v: 100 * (b / a - 1), u: "%", d: 2 }; if (u.startsWith("%")) return { v: 100 * (b - a), u: " bp", d: 0 }; return { v: b - a, u: " " + (s.unit || ""), d: 1 }; }

  function eventsFor(cal, country) {
    if (!cal) return [];
    const up = cal.events.map((e) => ({ ...e, upcoming: true })), past = (cal.past_events || []).map((e) => ({ ...e, upcoming: false }));
    return up.concat(past).filter((e) => e.country === country || (e.country === "GLOBAL" && e.importance >= 3 && e.type === "rates"));
  }

  /** Card body for one stored series. compareWith: other chart items offered in the compare menu. */
  function seriesCard(item, ctx) {
    const st = { range: T.store.get("terminal.range", "1Y"), cmp: "" };
    const root = el("div"), body = el("div", {}, T.skel("block"));
    const country = ctx.country || COUNTRY_OF[item.series.split(".")[0]] || "GLOBAL";
    root.append(...nn(el("h2", {}, "How has " + item.name + " moved, and what explains its largest moves?"), body));
    const opts = [["", "Compare with…"]].concat((ctx.compareWith || []).map((c) => [c.series, c.name])).concat(item.series === "us.ust10y" ? [] : [["us.ust10y", "US 10-year Treasury yield"]]);
    Promise.all([T.loadSeries(item.series), T.calendar().catch(() => null)]).then(([s, cal]) => {
      const evs = eventsFor(cal, country);
      const dec = decimalsFor(s);
      const all = s.history.filter((r) => typeof r[1] === "number").map((r) => [r[0], r[1]]);
      function draw() {
        const last = all[all.length - 1][0], lastT = Date.parse(last), span = RANGES[st.range] * DAY;
        const from = iso(lastT - span), pts = all.filter((p) => p[0] >= from);
        const ahead = Math.max(7, Math.round(RANGES[st.range] * 0.12));
        const x1 = lastT + ahead * DAY;
        const view = el("div");
        const head = el("div", { class: "vizhead" },
          el("div", {}, el("span", { class: "lvl", style: "font-size:var(--fs-xl);font-weight:750" }, fmt(all[all.length - 1][1], dec)), " ",
            el("span", { class: "tiny" }, (s.unit || "") + " · " + last + " · " + pts.length + " observations in view")),
          el("div", { class: "row" }, (() => { const tb = el("div", { class: "tabs mini", role: "tablist", "aria-label": "zoom" });
            Object.keys(RANGES).forEach((k) => tb.appendChild(el("button", { type: "button", class: st.range === k ? "on" : "", "aria-pressed": String(st.range === k), onclick: () => { st.range = k; T.store.set("terminal.range", k); draw(); } }, k))); return tb; })(),
          (() => { const sel = el("select", { "aria-label": "Compare with another instrument", onchange: (e) => { st.cmp = e.target.value; draw(); } });
            opts.forEach(([v, l]) => { const o = el("option", { value: v }, l); if (v === st.cmp) o.selected = true; sel.appendChild(o); }); return sel; })()));
        view.append(...nn(head));
        if (pts.length < 2) { view.append(...nn(el("div", { class: "empty" }, "Fewer than two observations in this window (" + (s.frequency || "") + " data): pick a longer range."))); return body.replaceChildren(...nn(view)), finish(view, pts); }
        // the five largest moves in view, each matched to calendar events between the two observations
        const moves = [];
        for (let i = 1; i < pts.length; i++) moves.push({ i, c: changeOf(s, pts[i - 1][1], pts[i][1]), from: pts[i - 1][0], t: pts[i][0], v: pts[i][1] });
        const top = moves.filter((m) => isFinite(m.c.v)).sort((a, b) => Math.abs(b.c.v) - Math.abs(a.c.v)).slice(0, 5).sort((a, b) => a.t < b.t ? -1 : 1);
        top.forEach((m, k) => {
          m.n = k + 1;
          const lo = iso(Date.parse(m.from) - DAY);
          const cands = evs.filter((e) => !e.upcoming && e.date >= lo && e.date <= m.t).sort((a, b) => b.importance - a.importance || (a.date < b.date ? 1 : -1));
          m.ev = cands[0] || null; m.others = Math.max(0, cands.length - 1);
        });
        const panels = [{ title: item.name + (s.unit ? " (" + s.unit + ")" : ""), lines: [{ label: item.name, points: pts, color: "var(--cat-1)" }], fmt: (v, full) => fmt(v, full ? dec : Math.min(dec, 2)) }];
        const render2 = (cmpS) => {
          if (cmpS) {
            const cp = cmpS.history.filter((r) => typeof r[1] === "number" && r[0] >= from).map((r) => [r[0], r[1]]);
            const cd = decimalsFor(cmpS);
            if (cp.length > 1) panels.push({ title: cmpS.name + (cmpS.unit ? " (" + cmpS.unit + ")" : ""), lines: [{ label: cmpS.name, points: cp, color: "var(--cat-2)" }], fmt: (v, full) => fmt(v, full ? cd : Math.min(cd, 2)), height: 120 });
          }
          const markers = evs.filter((e) => e.date >= from && Date.parse(e.date) <= x1).map((e) => ({ t: e.date, title: e.title, upcoming: e.upcoming, source: e.source,
            sub: [e.type, "importance " + e.importance, e.status].join(" · "), href: e.upcoming ? "#calendar/12m?ev=" + encodeURIComponent(e.id) : null }));
          const chart = timeChart({ panels, x0: Date.parse(from), x1, markers, annos: top.map((m) => ({ t: m.t, v: m.v, n: m.n })), aria: item.name + " over " + st.range });
          view.append(...nn(chart,
            el("div", { class: "legend" }, el("span", {}, el("i", { class: "ln", style: "background:var(--cat-1)" }), item.name), cmpS ? el("span", {}, el("i", { class: "ln", style: "background:var(--cat-2)" }), cmpS.name + " (panel below)") : null,
              markers.length ? el("span", {}, "▲ calendar event (tap; blue = upcoming)") : null, el("span", {}, "① largest moves")),
            el("ol", { class: "annos", "aria-label": "Largest moves in view" }, ...top.map((m) => el("li", {}, el("span", { class: "n" }, String(m.n)),
              el("span", {}, el("b", { class: "num" }, signed(m.c.v, m.c.d) + m.c.u), " on " + m.t + (s.frequency && /month/.test(s.frequency) ? " (monthly average)" : "") + ": ",
                m.ev ? [m.ev.title, m.others ? " (+" + m.others + " more)" : "", " · ", m.ev.source ? el("a", { href: m.ev.source, target: "_blank", rel: "noopener" }, "source") : "no source"]
                  : el("span", { class: "muted" }, "no calendar event between " + m.from + " and " + m.t)))))));
          finish(view, pts);
        };
        if (st.cmp) T.loadSeries(st.cmp).then(render2).catch(() => render2(null)); else render2(null);
        body.replaceChildren(...nn(view));
      }
      function finish(view, pts) {
        const tb = el("tbody"); pts.slice(-30).reverse().forEach((p) => tb.appendChild(el("tr", {}, el("td", {}, p[0]), el("td", { class: "r num" }, fmt(p[1], dec)))));
        view.append(...nn(el("details", {}, el("summary", {}, "Data table (latest 30 in view)"), el("div", { class: "scroll" }, el("table", {}, el("thead", {}, el("tr", {}, el("th", {}, "date"), el("th", { class: "r" }, "value"))), tb))),
          el("div", { class: "tiny" }, "Notes explain the five largest moves between consecutive observations with calendar events dated between them (em-macro's history covers Brazil and Mexico rate decisions and elections)."),
          meta(item.meta), item.proxy_note ? el("details", {}, el("summary", {}, "how the proxy differs from DI1"), el("div", { class: "small muted" }, item.proxy_note)) : null));
      }
      draw();
    }).catch((err) => body.replaceChildren(...nn(el("div", { class: "err" }, String(err)))));
    return root;
  }

  // ---------------- bars, waterfall, band ----------------
  /** Horizontal bars around zero; every bar prints its value. rows: [{ label, value, note, tone: "up"|"down"|"" }] */
  function bars(rows, o) {
    o = o || {};
    const vals = rows.map((r) => r.value).filter((v) => v != null);
    const lo = Math.min(0, ...vals), hi = Math.max(0, ...vals), span = hi - lo || 1;
    const pos = (v) => (100 * (v - lo)) / span;
    return el("div", { class: "hbars", role: "list" }, ...rows.map((r) => el("div", { class: "hb", role: "listitem" },
      el("div", { class: "hb-l" }, el("span", {}, r.label), el("b", { class: "num" + (r.tone ? " " + r.tone : "") }, r.value == null ? "–" : (o.fmt ? o.fmt(r.value) : signed(r.value, 1)))),
      el("div", { class: "hb-t" }, lo < 0 ? el("i", { class: "z", style: "left:" + pos(0) + "%" }) : null,
        r.value == null ? null : el("span", { class: "hb-b " + (r.tone || ""), style: `left:${Math.min(pos(0), pos(r.value))}%;width:${Math.max(0.6, Math.abs(pos(r.value) - pos(0)))}%` })),
      r.note ? el("div", { class: "tiny" }, r.note) : null)));
  }

  /** Waterfall: steps [{ label, value, kind: "base"|"factor" }], then the total and an optional actual. */
  function waterfall(steps, o) {
    let run = 0; const rows = steps.map((s) => { const a = s.kind === "base" ? 0 : run; run = s.kind === "base" ? s.value : run + s.value; return { ...s, a, b: run }; });
    const total = o.total, actual = o.actual;
    // the scale starts near the lowest running total, so factor steps stay visible next to a large baseline
    const ext = rows.filter((r) => r.kind !== "base").flatMap((r) => [r.a, r.b]).concat([total, actual == null ? total : actual, rows[0].b]);
    const mn = Math.min(...ext), mx = Math.max(...ext), padv = (mx - mn) * 0.12 || 1;
    const lo = mn > 0 && mn - padv > 0 ? mn - padv : Math.min(0, mn - padv), hi = mx + padv * 0.3, span = hi - lo || 1, pos = (v) => Math.max(0, (100 * (v - lo)) / span);
    const line = (label, a, b, cls, val) => el("div", { class: "hb" },
      el("div", { class: "hb-l" }, el("span", {}, label), el("b", { class: "num" }, val)),
      el("div", { class: "hb-t" }, lo <= 0 ? el("i", { class: "z", style: "left:" + pos(0) + "%" }) : null, el("span", { class: "hb-b " + cls, style: `left:${Math.min(pos(a), pos(b))}%;width:${Math.max(0.6, Math.abs(pos(b) - pos(a)))}%` })));
    const u = o.unit ? " " + o.unit : "";
    const u0 = o.unit ? " " + o.unit : "";
    return el("div", { class: "hbars wf" }, lo > 0 ? el("div", { class: "tiny" }, "Scale starts at " + fmt(lo, 0) + u0 + ", not zero, so the factor steps are visible.") : null,
      ...rows.map((r) => line(r.label, r.kind === "base" ? lo : r.a, r.b, r.kind === "base" ? "base" : r.value >= 0 ? "pos" : "neg", r.kind === "base" ? fmt(r.value, 0) + u : signed(r.value, 1) + u)),
      line(o.totalLabel || "Model fair value", Math.max(0, lo), total, "total", fmt(total, 0) + u),
      actual != null ? line(o.actualLabel || "Actual level", Math.max(0, lo), actual, "actual", fmt(actual, 0) + u) : null);
  }

  /** Band chart for a few horizons: mean line with a shaded range. x labels are categories. */
  function band(o) {
    const wrap = el("div", { class: "viz" }), svg = ns("svg", { role: "img", "aria-label": o.aria || "event study" }); wrap.appendChild(svg);
    function render() {
      const W = Math.max(260, wrap.clientWidth || 400), H = 170, P = { l: 44, r: 12, t: 10, b: 26 };
      const ys = o.points.flatMap((p) => [p.lo, p.hi, p.mean]).concat([0]);
      let a = Math.min(...ys), b = Math.max(...ys); const pad = (b - a) * 0.1 || 1; a -= pad; b += pad;
      const tk = ticks(a, b, 4), n = o.points.length;
      const X = (i) => P.l + (i / (n - 1)) * (W - P.l - P.r), Y = (v) => P.t + (1 - (v - a) / (b - a)) * (H - P.t - P.b);
      svg.setAttribute("viewBox", `0 0 ${W} ${H}`); svg.textContent = "";
      const gl = ns("g", { class: "gridl" }), ax = ns("g", { class: "axis" });
      tk.list.forEach((v) => { gl.appendChild(ns("line", { x1: P.l, x2: W - P.r, y1: Y(v), y2: Y(v) })); ax.appendChild(ns("text", { x: P.l - 6, y: Y(v) + 4, "text-anchor": "end" }, fmt(v, tk.dec))); });
      o.points.forEach((p, i) => ax.appendChild(ns("text", { x: X(i), y: H - 6, "text-anchor": i === 0 ? "start" : i === n - 1 ? "end" : "middle" }, p.label)));
      svg.append(...nn(gl, ax, ns("line", { class: "base", x1: P.l, x2: W - P.r, y1: Y(0), y2: Y(0) })));
      let up = "", dn = "";
      o.points.forEach((p, i) => { up += (i ? "L" : "M") + X(i) + "," + Y(p.hi); dn = "L" + X(i) + "," + Y(p.lo) + dn; });
      svg.appendChild(ns("path", { d: up + dn + "Z", fill: "var(--accent-2)", opacity: 0.8 }));
      let d = ""; o.points.forEach((p, i) => { d += (i ? "L" : "M") + X(i) + "," + Y(p.mean); });
      svg.appendChild(ns("path", { d, class: "line", stroke: "var(--cat-1)" }));
      o.points.forEach((p, i) => { svg.append(...nn(ns("circle", { cx: X(i), cy: Y(p.mean), r: 3.5, fill: "var(--cat-1)", stroke: "var(--surface)", "stroke-width": 2 })));
        if (i) svg.appendChild(ns("text", { x: X(i) - (i === n - 1 ? 4 : 0), y: Y(p.mean) - 7, class: "lbl-v", "text-anchor": i === n - 1 ? "end" : "middle" }, signed(p.mean, o.dec == null ? 2 : o.dec))); });
    }
    render(); if (window.ResizeObserver) new ResizeObserver(render).observe(wrap);
    return wrap;
  }

  /** Where today's reading sits in its history: past readings as dots, extreme zones shaded, today as a marker with its value. */
  function rangeStrip(o) {
    const wrap = el("div", { class: "viz" }), svg = ns("svg", { role: "img", "aria-label": o.aria || "reading against its history" }); wrap.appendChild(svg);
    function render() {
      const up = Math.max(0, ...(o.marks || []).map((m) => m.dy || 0));
      const W = Math.max(240, wrap.clientWidth || 360), H = 54 + up, P = { l: 8, r: 8 };
      const lo = o.min, hi = o.max, X = (v) => P.l + ((Math.min(hi, Math.max(lo, v)) - lo) / (hi - lo)) * (W - P.l - P.r), cy = 30 + up;
      svg.setAttribute("viewBox", `0 0 ${W} ${H}`); svg.textContent = "";
      (o.zones || []).forEach(([a, b]) => svg.appendChild(ns("rect", { x: X(a), y: cy - 9, width: Math.max(1, X(b) - X(a)), height: 18, fill: "var(--warn-soft)" })));
      svg.appendChild(ns("line", { x1: P.l, x2: W - P.r, y1: cy, y2: cy, stroke: "var(--axis)", "stroke-width": 1.5 }));
      (o.ticks || [lo, hi]).forEach((t, i, arr) => svg.appendChild(ns("text", { x: X(t), y: H - 2, class: "lbl-t", "text-anchor": i === 0 ? "start" : i === arr.length - 1 ? "end" : "middle" }, o.fmt ? o.fmt(t) : String(t))));
      (o.history || []).forEach((v) => svg.appendChild(ns("circle", { cx: X(v), cy, r: 3.5, fill: "var(--text-3)", opacity: 0.55 })));
      (o.marks || []).forEach((m) => { const x = X(m.v);
        svg.append(...nn(ns("line", { x1: x, x2: x, y1: cy - 12, y2: cy + 12, stroke: m.color || "var(--accent)", "stroke-width": 3, "stroke-linecap": "round" }),
          ns("text", { x: Math.min(W - 4, Math.max(4, x)), y: cy - 16 - (m.dy || 0), class: "lbl-v", "text-anchor": x < 40 ? "start" : x > W - 40 ? "end" : "middle" }, m.label))); });
    }
    render(); if (window.ResizeObserver) new ResizeObserver(render).observe(wrap);
    return wrap;
  }

  T.charts = { ns, ticks, timeChart, seriesCard, bars, waterfall, band, rangeStrip, iso, DAY };
})();
