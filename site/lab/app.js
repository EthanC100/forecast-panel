/* Forecast panel dashboard. Static: reads window.PANEL_DATA (site/data.js). */
(function () {
  "use strict";
  const D = window.PANEL_DATA || {};
  const app = document.getElementById("app");
  const LS = { blind: "panel.blind", answered: "panel.answered", theme: "panel.theme" };

  // ---------- storage (every access guarded: private windows / file:// may throw) ----------
  const store = {
    get(k, fallback) { try { const v = localStorage.getItem(k); return v === null ? fallback : v; } catch (e) { return fallback; } },
    set(k, v) { try { localStorage.setItem(k, v); } catch (e) { /* ignore */ } },
  };
  let blind = store.get(LS.blind, "1") === "1";
  let answered = {};
  try { answered = JSON.parse(store.get(LS.answered, "{}")) || {}; } catch (e) { answered = {}; }

  // ---------- helpers ----------
  const el = (tag, attrs, ...kids) => {
    const n = document.createElement(tag);
    if (attrs) for (const [k, v] of Object.entries(attrs)) {
      if (k === "class") n.className = v; else if (k === "text") n.textContent = v;
      else if (k.startsWith("on")) n.addEventListener(k.slice(2), v); else if (v != null) n.setAttribute(k, v);
    }
    for (const kid of kids.flat()) if (kid != null) n.appendChild(typeof kid === "string" ? document.createTextNode(kid) : kid);
    return n;
  };
  const pct = (p, d = 0) => p == null ? "–" : (100 * p).toFixed(d) + "%";
  const num = (v, d = 2) => v == null ? "–" : Number(v).toFixed(d);
  const signed = (v, d = 1) => v == null ? "–" : (v > 0 ? "+" : "") + Number(v).toFixed(d);
  const isoWeek = (date) => {
    const d = new Date(Date.UTC(date.getUTCFullYear(), date.getUTCMonth(), date.getUTCDate()));
    const day = d.getUTCDay() || 7; d.setUTCDate(d.getUTCDate() + 4 - day);
    const y0 = new Date(Date.UTC(d.getUTCFullYear(), 0, 1));
    return d.getUTCFullYear() + "-W" + String(Math.ceil(((d - y0) / 864e5 + 1) / 7)).padStart(2, "0");
  };
  const thisWeek = isoWeek(new Date());
  const cssVar = (name) => getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  const COLORS = { market: "--s-market", me: "--s-me", claude: "--s-claude", agg: "--s-agg", metaculus: "--s-metaculus", swift: "--s-swift", gjopen: "--s-gjopen", tension: "--s-tension", tension2: "--s-tension2" };
  const SOURCE_LABEL = { polymarket: "Polymarket", metaculus: "Metaculus", swift_centre: "Swift Centre", gjopen: "GJ Open", my_prob: "Me", claude_prob: "Claude", aggregate_plain: "Panel (plain)", aggregate_extremized: "Panel (extremized)" };
  const SOURCE_COLOR = { polymarket: "market", metaculus: "metaculus", swift_centre: "swift", gjopen: "gjopen", my_prob: "me", claude_prob: "claude", aggregate_plain: "agg", aggregate_extremized: "agg" };
  const key = (c) => el("span", { class: "key", style: "background:var(" + COLORS[c] + ")" });

  // ---------- line chart (SVG, crosshair + tooltip + legend + table) ----------
  function lineChart(opts) {
    // opts: { series: [{name, color, points: [[iso, v]], step, dashed, markers}], fmt, min, max, height, table }
    const wrap = el("div", { class: "chart" });
    const series = opts.series.filter((s) => s.points && s.points.length);
    if (!series.length) { wrap.appendChild(el("div", { class: "empty", text: opts.empty || "No data yet." })); return wrap; }
    const fmt = opts.fmt || ((v) => num(v, 2));
    const H = opts.height || 220, PAD = { t: 12, r: 14, b: 26, l: 44 };
    const allX = series.flatMap((s) => s.points.map((p) => Date.parse(p[0])));
    const allY = series.flatMap((s) => s.points.map((p) => p[1])).filter((v) => v != null);
    let x0 = Math.min(...allX), x1 = Math.max(...allX); if (x1 === x0) { x0 -= 864e5 * 3; x1 += 864e5 * 3; }
    let y0 = opts.min != null ? opts.min : Math.min(...allY), y1 = opts.max != null ? opts.max : Math.max(...allY);
    if (opts.min == null || opts.max == null) { const padY = (y1 - y0) * 0.08 || Math.abs(y1) * 0.05 || 1; if (opts.min == null) y0 -= padY; if (opts.max == null) y1 += padY; }
    const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
    const tip = el("div", { class: "tip" });
    const legend = el("div", { class: "legend" });
    wrap.append(legend, svg, tip);
    series.forEach((s) => legend.appendChild(el("span", {}, key(s.color), s.name + " ", el("span", { class: "v", text: fmt(s.points[s.points.length - 1][1]) }))));

    function render() {
      const W = Math.max(280, wrap.clientWidth || 600);
      svg.setAttribute("viewBox", `0 0 ${W} ${H}`); svg.innerHTML = "";
      const X = (t) => PAD.l + ((t - x0) / (x1 - x0)) * (W - PAD.l - PAD.r);
      const Y = (v) => PAD.t + (1 - (v - y0) / (y1 - y0)) * (H - PAD.t - PAD.b);
      const ns = (t, a) => { const n = document.createElementNS("http://www.w3.org/2000/svg", t); for (const [k, v] of Object.entries(a || {})) n.setAttribute(k, v); return n; };
      const grid = ns("g", { class: "grid" }), axis = ns("g", { class: "axis" });
      const yt = 4;
      for (let i = 0; i <= yt; i++) {
        const v = y0 + ((y1 - y0) * i) / yt, y = Y(v);
        grid.appendChild(ns("line", { x1: PAD.l, x2: W - PAD.r, y1: y, y2: y }));
        const t = ns("text", { x: PAD.l - 6, y: y + 4, "text-anchor": "end" }); t.textContent = fmt(v); axis.appendChild(t);
      }
      const nx = W < 420 ? 3 : 5;
      for (let i = 0; i <= nx; i++) {
        const t = x0 + ((x1 - x0) * i) / nx, d = new Date(t);
        const lab = (x1 - x0) > 400 * 864e5 ? d.toISOString().slice(0, 7) : d.toISOString().slice(5, 10);
        const tx = ns("text", { x: X(t), y: H - 8, "text-anchor": i === 0 ? "start" : i === nx ? "end" : "middle" }); tx.textContent = lab; axis.appendChild(tx);
      }
      axis.appendChild(ns("line", { x1: PAD.l, x2: W - PAD.r, y1: Y(y0), y2: Y(y0) }));
      svg.append(grid, axis);
      series.forEach((s) => {
        const col = "var(" + COLORS[s.color] + ")";
        const pts = s.points.filter((p) => p[1] != null).map((p) => [X(Date.parse(p[0])), Y(p[1])]);
        if (pts.length > 1) {
          let d = "";
          pts.forEach((p, i) => { if (i === 0) d += `M${p[0]},${p[1]}`; else d += s.step ? `H${p[0]}V${p[1]}` : `L${p[0]},${p[1]}`; });
          const path = ns("path", { d, class: "line", stroke: col }); if (s.dashed) path.setAttribute("stroke-dasharray", "5 4");
          svg.appendChild(path);
        }
        if (s.markers || pts.length <= 2) pts.forEach((p) => svg.appendChild(ns("circle", { cx: p[0], cy: p[1], r: 4, fill: col, class: "dot" })));
      });
      const hair = ns("line", { class: "hair", y1: PAD.t, y2: H - PAD.b }); svg.appendChild(hair);
      const dots = series.map((s) => { const c = ns("circle", { r: 4.5, fill: "var(" + COLORS[s.color] + ")", class: "dot", style: "display:none" }); svg.appendChild(c); return c; });
      const hit = ns("rect", { x: 0, y: 0, width: W, height: H, fill: "transparent" }); svg.appendChild(hit);
      const move = (ev) => {
        const r = svg.getBoundingClientRect(); const px = ((ev.clientX - r.left) / r.width) * W;
        if (px < PAD.l || px > W - PAD.r) return leave();
        const t = x0 + ((px - PAD.l) / (W - PAD.l - PAD.r)) * (x1 - x0);
        // nearest point across all series decides the hairline date
        let best = null;
        series.forEach((s) => s.points.forEach((p) => { const d = Math.abs(Date.parse(p[0]) - t); if (!best || d < best.d) best = { d, t: Date.parse(p[0]) }; }));
        const xt = X(best.t); hair.setAttribute("x1", xt); hair.setAttribute("x2", xt); hair.style.display = "block";
        tip.innerHTML = ""; tip.appendChild(el("div", { class: "tiny", text: new Date(best.t).toISOString().slice(0, 10) }));
        series.forEach((s, i) => {
          let last = null; for (const p of s.points) { if (Date.parse(p[0]) <= best.t + 1) last = p; else break; }
          if (last && last[1] != null && best.t - Date.parse(last[0]) < 120 * 864e5) {
            dots[i].setAttribute("cx", X(Date.parse(last[0]))); dots[i].setAttribute("cy", Y(last[1])); dots[i].style.display = "block";
            tip.appendChild(el("div", { class: "r" }, key(s.color), el("strong", { text: fmt(last[1]) }), el("span", { class: "muted", text: s.name })));
          } else dots[i].style.display = "none";
        });
        tip.style.display = "block"; tip.style.left = (xt / W) > 0.6 ? "8px" : "auto"; tip.style.right = (xt / W) > 0.6 ? "auto" : "8px";
      };
      const leave = () => { hair.style.display = "none"; tip.style.display = "none"; dots.forEach((d) => (d.style.display = "none")); };
      hit.addEventListener("pointermove", move); hit.addEventListener("pointerleave", leave);
    }
    render();
    if (window.ResizeObserver) new ResizeObserver(() => render()).observe(wrap);
    if (opts.table !== false) {
      const det = el("details", {}, el("summary", { text: "Data table" }));
      const tb = el("table", {}, el("thead", {}, el("tr", {}, el("th", { text: "date" }), ...series.map((s) => el("th", { class: "r", text: s.name })))));
      const dates = [...new Set(series.flatMap((s) => s.points.map((p) => p[0])))].sort().slice(-60).reverse();
      const body = el("tbody");
      dates.forEach((d) => body.appendChild(el("tr", {}, el("td", { text: d }), ...series.map((s) => { const p = s.points.find((q) => q[0] === d); return el("td", { class: "r", text: p && p[1] != null ? fmt(p[1]) : "" }); }))));
      tb.appendChild(body); det.appendChild(el("div", { class: "tbl-wrap" }, tb)); wrap.appendChild(det);
    }
    return wrap;
  }

  // ---------- pieces ----------
  const revealed = (qid) => !blind || answered[qid] === thisWeek;
  function markAnswered(qid, on) { if (on) answered[qid] = thisWeek; else delete answered[qid]; store.set(LS.answered, JSON.stringify(answered)); route(); }

  function numberTile(label, color, value, asOf, note, ref) {
    const t = el("div", { class: "num" + (value == null ? " empty" : ""), style: "border-left-color:var(" + COLORS[color] + ")", title: note || "" });
    t.append(el("div", { class: "v", text: value == null ? "no value" : pct(value) }), el("div", { class: "k" }, key(color), label));
    if (asOf) t.appendChild(el("div", { class: "d", text: "as of " + asOf }));
    else if (value == null && note) t.appendChild(el("div", { class: "d", text: note.length > 60 ? note.slice(0, 57) + "…" : note }));
    return t;
  }

  function contextBlock(q) {
    const ctx = q.context || {};
    if (ctx.type === "election") {
      const s = [];
      if (q.odds_history && q.odds_history.length) s.push({ name: "Betting odds (favourite)", color: "market", points: q.odds_history });
      if (q.polls_history && q.polls_history.length) s.push({ name: "Poll average (margin, pp)", color: "me", points: q.polls_history });
      return el("div", {}, el("h3", { text: "Context: polls and odds (em-macro)" }), lineChart({ series: s, fmt: (v) => num(v, 1), height: 150, empty: "No poll or odds series mapped in site/config.yaml." }));
    }
    const t = (D.tension && D.tension.series) || [];
    const last = t[t.length - 1];
    return el("div", {}, el("h3", {}, "Context: tension index ", el("span", { class: "muted small", text: last ? "(" + last[0] + ": " + num(last[1], 0) + ", GPR nowcast " + num(last[2], 0) + ")" : "" })),
      lineChart({ series: [{ name: "Tension index", color: "tension", points: t.map((r) => [r[0], r[1]]) }, { name: "GPR nowcast", color: "tension2", points: t.map((r) => [r[0], r[2]]) }], fmt: (v) => num(v, 0), height: 140, table: false, empty: "tension-index data unavailable" }));
  }

  function questionCard(q) {
    const open = !q.resolved;
    const show = revealed(q.id);
    const card = el("article", { class: "card" });
    card.appendChild(el("div", { class: "card-head" }, el("div", {}, el("div", { class: "tiny", text: q.id.toUpperCase() + " · resolves " + q.resolution_date }), el("h2", { text: q.question })),
      el("span", { class: "badge" + (q.resolved ? (q.outcome === 1 ? " good" : " bad") : ""), text: q.resolved ? "resolved " + (q.outcome === 1 ? "YES" : "NO") : "open" })));
    if (q.resolution_note) card.appendChild(el("details", {}, el("summary", { text: "Market: " + (q.market || "") }), el("p", { class: "small muted", text: q.resolution_note })));

    // my entries, always visible
    const mine = el("div", {});
    const myLast = q.my_history.length ? q.my_history[q.my_history.length - 1] : null;
    mine.appendChild(el("h3", {}, key("me"), " My forecast ", el("span", { class: "muted small", text: myLast ? pct(myLast[1]) + " (entered " + myLast[0] + ")" : "not entered yet" })));
    if (q.my_history.length > 1) mine.appendChild(el("div", { class: "small muted", text: "Past entries: " + q.my_history.map((p) => p[0] + " " + pct(p[1])).join(" · ") }));
    mine.appendChild(el("div", { class: "tiny", text: "Entered weekly in gold-events/data/forward_log.csv (my_prob_" + q.id + "), carried forward until updated." }));
    card.appendChild(mine);

    if (!show) {
      const box = el("div", { class: "blind-box" }, el("div", { text: "Blind mode: other forecasters' numbers and the market chart are hidden until you mark this question answered for week " + thisWeek + "." }),
        el("div", { style: "margin-top:10px" }, el("button", { class: "btn primary", type: "button", onclick: () => markAnswered(q.id, true), text: "I've answered this week — reveal" })));
      card.appendChild(box);
    } else {
      const series = [{ name: "Polymarket", color: "market", points: q.market_history }];
      if (q.aggregate_history.length) series.push({ name: "Panel (extremized)", color: "agg", points: q.aggregate_history.map((r) => [r[0], r[2]]), dashed: true, markers: true });
      if (q.claude_history.length) series.push({ name: "Claude", color: "claude", points: q.claude_history, step: true, markers: true });
      if (q.my_history.length) series.push({ name: "Me", color: "me", points: q.my_history, step: true, markers: true });
      card.appendChild(lineChart({ series, fmt: (v) => pct(v), min: 0, max: 1 }));
      const nums = el("div", { class: "numbers" });
      const L = q.latest || {};
      ["polymarket", "metaculus", "swift_centre", "gjopen", "claude_prob"].forEach((s) => { const r = L[s] || {}; nums.appendChild(numberTile(SOURCE_LABEL[s], SOURCE_COLOR[s], r.prob, r.prob != null ? r.as_of : null, r.notes, r.ref)); });
      const ag = q.aggregate_history[q.aggregate_history.length - 1];
      nums.appendChild(numberTile("Panel plain / extremized", "agg", ag ? ag[2] : null, ag ? ag[0] : null, ag ? "plain " + pct(ag[1]) + ", extremized " + pct(ag[2]) : "no aggregate yet"));
      if (ag) nums.lastChild.querySelector(".v").textContent = pct(ag[1]) + " / " + pct(ag[2]);
      card.appendChild(nums);
      if (blind) card.appendChild(el("div", { class: "row" }, el("button", { class: "btn small", type: "button", onclick: () => markAnswered(q.id, false), text: "Hide again (unmark this week)" })));
    }
    card.appendChild(contextBlock(q));
    return card;
  }

  // ---------- pages ----------
  function pageWeek() {
    const qs = (D.questions || []);
    const open = qs.filter((q) => !q.resolved), done = qs.filter((q) => q.resolved);
    const frag = el("div", {});
    frag.appendChild(el("div", { class: "row", style: "justify-content:space-between;margin-bottom:10px" },
      el("div", {}, el("h1", { text: "This week · " + thisWeek }), el("div", { class: "muted small", text: open.length + " open question" + (open.length === 1 ? "" : "s") + (blind ? " · blind mode on: answer first, then reveal" : " · blind mode off") })),
      blind ? el("div", { class: "row" }, el("button", { class: "btn small", type: "button", onclick: () => { open.forEach((q) => (answered[q.id] = thisWeek)); store.set(LS.answered, JSON.stringify(answered)); route(); }, text: "Reveal all (answered)" }),
        el("button", { class: "btn small", type: "button", onclick: () => { answered = {}; store.set(LS.answered, "{}"); route(); }, text: "Hide all" })) : null));
    const grid = el("div", { class: "grid" });
    open.forEach((q) => grid.appendChild(questionCard(q)));
    frag.appendChild(grid);
    if (done.length) { frag.appendChild(el("h2", { text: "Resolved", style: "margin-top:18px" })); const g2 = el("div", { class: "grid" }); done.forEach((q) => g2.appendChild(questionCard(q))); frag.appendChild(g2); }
    return frag;
  }

  let scoreWho = "my_prob";
  function calibrationChart(cal) {
    const wrap = el("div", { class: "chart" });
    if (!cal || !cal.length) { wrap.appendChild(el("div", { class: "empty", text: "No scored forecasts yet. Each dot will show, for a forecast bin, how often the question resolved Yes." })); return wrap; }
    const W = 320, H = 300, P = 36;
    const ns = (t, a) => { const n = document.createElementNS("http://www.w3.org/2000/svg", t); for (const [k, v] of Object.entries(a || {})) n.setAttribute(k, v); return n; };
    const svg = ns("svg", { viewBox: `0 0 ${W} ${H}`, style: "max-width:380px" });
    const X = (v) => P + v * (W - 2 * P), Y = (v) => H - P + (-v) * (H - 2 * P);
    const g = ns("g", { class: "grid" }); for (let i = 0; i <= 4; i++) { g.appendChild(ns("line", { x1: X(i / 4), x2: X(i / 4), y1: Y(0), y2: Y(1) })); g.appendChild(ns("line", { x1: X(0), x2: X(1), y1: Y(i / 4), y2: Y(i / 4) })); }
    svg.appendChild(g);
    svg.appendChild(ns("line", { x1: X(0), y1: Y(0), x2: X(1), y2: Y(1), stroke: "var(--text-3)", "stroke-dasharray": "4 4" }));
    const ax = ns("g", { class: "axis" });
    for (let i = 0; i <= 4; i++) { const tx = ns("text", { x: X(i / 4), y: H - P + 16, "text-anchor": "middle" }); tx.textContent = (i * 25) + "%"; ax.appendChild(tx); const ty = ns("text", { x: P - 6, y: Y(i / 4) + 4, "text-anchor": "end" }); ty.textContent = (i * 25) + "%"; ax.appendChild(ty); }
    const xl = ns("text", { x: W / 2, y: H - 4, "text-anchor": "middle" }); xl.textContent = "forecast"; ax.appendChild(xl);
    const yl = ns("text", { x: 10, y: 12 }); yl.textContent = "observed"; ax.appendChild(yl);
    svg.appendChild(ax);
    const maxN = Math.max(...cal.map((c) => c.n));
    cal.forEach((c) => { const d = ns("circle", { cx: X(c.mean_forecast), cy: Y(c.observed), r: 4 + 8 * Math.sqrt(c.n / maxN), fill: "var(--s-me)", class: "dot", opacity: .85 }); const t = ns("title"); t.textContent = `${c.bin}: n=${c.n}, mean forecast ${pct(c.mean_forecast)}, observed ${pct(c.observed)}`; d.appendChild(t); svg.appendChild(d); });
    wrap.appendChild(svg);
    return wrap;
  }

  function pageScorecard() {
    const S = D.scorecard || { forecasters: {}, resolved: [] };
    const F = S.forecasters || {};
    const frag = el("div", {});
    frag.appendChild(el("h1", { text: "Scorecard" }));
    frag.appendChild(el("p", { class: "muted small", text: "Points per resolved question = 100 × (market Brier − forecaster Brier), both scored on the same Monday snapshots before resolution, so beating Polymarket earns points and losing to it costs them. " + (S.resolved.length ? S.resolved.length + " resolved." : "No question has resolved yet; " + (S.weeks_logged || 0) + " weekly snapshot" + (S.weeks_logged === 1 ? "" : "s") + " logged so far.") }));
    const hero = el("div", { class: "hero" });
    Object.entries(F).forEach(([k, f]) => hero.appendChild(el("div", { class: "h" }, el("div", { class: "v " + (f.total_points > 0 ? "pos" : f.total_points < 0 ? "neg" : ""), text: signed(f.total_points, 1) }), el("div", { class: "k" }, key(SOURCE_COLOR[k]), f.label + " · " + f.n_scored_weeks + " scored weeks"))));
    frag.appendChild(el("div", { class: "card wide" }, hero,
      el("h3", { text: "Running total" }),
      lineChart({ series: Object.entries(F).map(([k, f]) => ({ name: f.label, color: SOURCE_COLOR[k], step: true, markers: true, points: f.per_question.filter((p) => p.points != null).map((p) => [p.resolution_date, p.running_total]) })), fmt: (v) => signed(v, 0), empty: "The running total starts with the first resolved question (q1, q2 and q4 resolve on 2026-12-31)." })));
    const seg = el("div", { class: "seg" });
    Object.entries(F).forEach(([k, f]) => seg.appendChild(el("button", { class: k === scoreWho ? "active" : "", type: "button", onclick: () => { scoreWho = k; route(); }, text: f.label })));
    const f = F[scoreWho] || { per_question: [], calibration: [], open: {} };
    const tb = el("table", {}, el("thead", {}, el("tr", {}, el("th", { text: "question" }), el("th", { class: "r", text: "weeks" }), el("th", { class: "r", text: "Brier" }), el("th", { class: "r", text: "market Brier" }), el("th", { class: "r", text: "points" }), el("th", { class: "r", text: "running" }))));
    const tbody = el("tbody");
    f.per_question.forEach((p) => tbody.appendChild(el("tr", {}, el("td", { text: p.id + " · " + ((S.resolved.find((r) => r.id === p.id) || {}).question || "") }), el("td", { class: "r", text: p.n_weeks }), el("td", { class: "r", text: num(p.brier, 4) }), el("td", { class: "r", text: num(p.market_brier, 4) }), el("td", { class: "r " + (p.points > 0 ? "pos" : p.points < 0 ? "neg" : ""), text: p.points == null ? "no forecast" : signed(p.points, 1) }), el("td", { class: "r", text: signed(p.running_total, 1) }))));
    if (!f.per_question.length) tbody.appendChild(el("tr", {}, el("td", { colspan: 6, class: "empty", text: "Nothing resolved yet." })));
    tb.appendChild(tbody);
    // open questions: my number always, others only when revealed
    const ob = el("tbody");
    (D.questions || []).filter((q) => !q.resolved).forEach((q) => {
      const show = revealed(q.id), mine = f.open[q.id];
      const mk = (p) => (scoreWho === "my_prob" || show) ? pct(p) : "hidden";
      const L = q.latest || {};
      ob.appendChild(el("tr", {}, el("td", { text: q.id + " · " + q.question }), el("td", { class: "r", text: mine == null ? "–" : mk(mine) }), el("td", { class: "r", text: show ? pct(L.polymarket && L.polymarket.prob) : "hidden" })));
    });
    frag.appendChild(el("div", { class: "grid" },
      el("div", { class: "card wide" }, el("div", { class: "row", style: "justify-content:space-between" }, el("h3", { text: "Per resolved question" }), seg), el("div", { class: "tbl-wrap" }, tb)),
      el("div", { class: "card" }, el("h3", { text: "Calibration · " + f.label }), el("div", { class: "tiny", text: "Every scored weekly forecast, binned by the probability given; dot size = count. Dots below the diagonal mean over-confident Yes forecasts." }), calibrationChart(f.calibration)),
      el("div", { class: "card" }, el("h3", { text: "Open questions · " + f.label + " vs market" }), el("div", { class: "tbl-wrap" }, el("table", {}, el("thead", {}, el("tr", {}, el("th", { text: "question" }), el("th", { class: "r", text: f.label }), el("th", { class: "r", text: "Polymarket" }))), ob)),
        el("div", { class: "tiny", text: blind ? "Blind mode hides unrevealed numbers; reveal a question on This week." : "" }))));
    return frag;
  }

  function pageCountry(keyName) {
    const C = D.countries || {}; const c = C[keyName] || C.brazil; if (!c) return el("div", { class: "empty", text: "No country data." });
    const frag = el("div", {});
    const nav = el("div", { class: "subnav" });
    Object.entries(C).forEach(([k, v]) => nav.appendChild(el("a", { href: "#country/" + k, class: k === keyName ? "active" : "", text: v.name })));
    frag.append(nav, el("h1", { text: c.name }));
    const grid = el("div", { class: "grid" });
    const cardChart = (block, fmt) => block && block.series && block.series.length ? el("div", { class: "card" }, el("h3", { text: block.label }), lineChart({ series: [{ name: block.label, color: "market", points: block.series }], fmt }), el("div", { class: "tiny", text: "Source: " + block.source + (block.frequency ? " (" + block.frequency + ")" : "") })) : null;
    grid.append(cardChart(c.yield, (v) => num(v, 2)), cardChart(c.spread, (v) => num(v, 2)), cardChart(c.fx, (v) => num(v, 3)), cardChart(c.germany_daily, (v) => num(v, 2)));
    // events
    const ev = el("div", { class: "card" }, el("h3", { text: "Upcoming events" }));
    if (c.events && c.events.length) { const ul = el("ul", { class: "plain" }); c.events.forEach((e) => ul.appendChild(el("li", {}, el("span", { class: "ev-date", text: e.date }), e.title + " ", e.confirmed ? null : el("span", { class: "badge warn", text: "to confirm" }), " ", e.source ? el("a", { href: e.source, class: "tiny", target: "_blank", rel: "noopener", text: "source" }) : null))); ev.appendChild(ul); }
    else ev.appendChild(el("div", { class: "empty", text: "None listed. Add dates to site/events.yaml." }));
    if (c.recent_decisions && c.recent_decisions.length) {
      ev.appendChild(el("h3", { text: "Recent rate decisions (em-macro)", style: "margin-top:12px" }));
      const t = el("table", {}, el("thead", {}, el("tr", {}, el("th", { text: "date" }), el("th", { text: "decision" }), el("th", { class: "r", text: "change bp" }), el("th", { class: "r", text: "rate after" }))));
      const b = el("tbody"); c.recent_decisions.slice().reverse().forEach((r) => b.appendChild(el("tr", {}, el("td", { text: r.date }), el("td", { text: r.decision }), el("td", { class: "r", text: signed(r.change_bp, 0) }), el("td", { class: "r", text: num(r.rate_after, 2) + "%" }))));
      t.appendChild(b); ev.appendChild(el("div", { class: "tbl-wrap" }, t));
    }
    if (c.last_election) ev.appendChild(el("p", { class: "small muted", text: "Last election in em-macro: " + c.last_election.election + " (" + c.last_election.date + "), winner " + c.last_election.winner + "; poll margin " + signed(c.last_election.poll_margin_pp, 1) + " pp vs actual " + signed(c.last_election.actual_margin_pp, 1) + " pp." }));
    grid.appendChild(ev);
    // risk model
    const rm = c.risk_model || { status: "not_built" };
    const card = el("div", { class: "card" }, el("h3", { text: "em-macro risk model" }));
    if (rm.status !== "built") {
      card.appendChild(el("div", { class: "blind-box" }, el("strong", { text: "model not yet built" }), el("div", { class: "tiny", style: "margin-top:6px", text: "Fair-value estimate, factor breakdown and most similar past cases will appear here once em-macro publishes " + (rm.expected_files || []).join(", ") + "." })));
    } else {
      card.appendChild(el("div", { class: "tiny", text: "As of " + rm.date }));
      const fv = el("div", { class: "numbers" }); (rm.fair_value || []).forEach((r) => fv.appendChild(el("div", { class: "num" }, el("div", { class: "v", text: num(r.fair_value, 2) }), el("div", { class: "k", text: (r.asset || "") + " fair value (actual " + num(r.actual, 2) + ", gap " + signed(r.gap, 2) + ")" }))));
      card.appendChild(fv);
      if (rm.factors && rm.factors.length) { card.appendChild(el("h3", { text: "Factor breakdown" })); const t = el("table", {}, el("thead", {}, el("tr", {}, el("th", { text: "asset" }), el("th", { text: "factor" }), el("th", { class: "r", text: "contribution" })))); const b = el("tbody"); rm.factors.forEach((r) => b.appendChild(el("tr", {}, el("td", { text: r.asset || "" }), el("td", { text: r.factor }), el("td", { class: "r", text: signed(r.contribution, 2) })))); t.appendChild(b); card.appendChild(el("div", { class: "tbl-wrap" }, t)); }
      if (rm.similar_cases && rm.similar_cases.length) { card.appendChild(el("h3", { text: "Most similar past cases" })); const ul = el("ul", { class: "plain" }); rm.similar_cases.forEach((r) => ul.appendChild(el("li", {}, el("span", { class: "ev-date", text: (r.case_country || "") + " " + (r.case_date || "") }), "similarity " + num(r.similarity, 2) + (r.outcome_note ? " · " + r.outcome_note : "")))); card.appendChild(ul); }
    }
    grid.appendChild(card);
    frag.appendChild(grid);
    return frag;
  }

  function pageIndicators() {
    const frag = el("div", {}, el("h1", { text: "Indicators" }));
    const t = (D.tension && D.tension.series) || []; const last = t[t.length - 1];
    const g = el("div", { class: "grid" });
    const tc = el("div", { class: "card wide" }, el("h3", { text: "Tension index, last 90 days" }));
    if (last) tc.appendChild(el("div", { class: "hero" }, el("div", { class: "h" }, el("div", { class: "v", text: num(last[1], 0) }), el("div", { class: "k", text: "tension index · " + last[0] })), el("div", { class: "h" }, el("div", { class: "v", text: num(last[2], 0) }), el("div", { class: "k", text: "GPR nowcast" })), last[3] != null ? el("div", { class: "h" }, el("div", { class: "v", text: num(last[3], 0) + " / " + num(last[4], 0) }), el("div", { class: "k", text: "threats / acts" })) : null));
    tc.appendChild(lineChart({ series: [{ name: "Tension index", color: "tension", points: t.map((r) => [r[0], r[1]]) }, { name: "GPR nowcast", color: "tension2", points: t.map((r) => [r[0], r[2]]) }], fmt: (v) => num(v, 0), empty: "tension-index unavailable" }));
    tc.appendChild(el("div", { class: "tiny", text: (D.tension && D.tension.note) || "" }));
    g.appendChild(tc);
    const rows = (D.gold && D.gold.rows) || [];
    const gc = el("div", { class: "card wide" }, el("h3", { text: "Gold model: weekly expected 5-day move (gold-events)" }));
    const lastRow = rows[rows.length - 1];
    if (lastRow) gc.appendChild(el("div", { class: "hero" }, el("div", { class: "h" }, el("div", { class: "v " + (lastRow.pred_gold_5d > 0 ? "pos" : "neg"), text: signed(100 * lastRow.pred_gold_5d, 2) + "%" }), el("div", { class: "k", text: "gold, week of " + lastRow.log_date + " (" + lastRow.model_version + ")" })), el("div", { class: "h" }, el("div", { class: "v " + (lastRow.pred_silver_5d > 0 ? "pos" : "neg"), text: signed(100 * lastRow.pred_silver_5d, 2) + "%" }), el("div", { class: "k", text: "silver" })), el("div", { class: "h" }, el("div", { class: "v", text: num(lastRow.gpr_level, 0) }), el("div", { class: "k", text: "GPR level · Δ week " + signed(lastRow.gpr_change_week, 0) }))));
    gc.appendChild(lineChart({ series: [{ name: "Expected gold 5d (%)", color: "agg", points: rows.map((r) => [r.log_date, r.pred_gold_5d == null ? null : 100 * r.pred_gold_5d]), markers: true }, { name: "Realised gold 5d (%)", color: "market", points: rows.filter((r) => r.realised_gold_5d != null).map((r) => [r.log_date, 100 * r.realised_gold_5d]), markers: true }], fmt: (v) => signed(v, 2), empty: "no forward-log rows yet" }));
    const tb = el("table", {}, el("thead", {}, el("tr", {}, el("th", { text: "week" }), el("th", { text: "model" }), el("th", { class: "r", text: "exp. gold" }), el("th", { class: "r", text: "exp. silver" }), el("th", { class: "r", text: "realised gold" }), el("th", { class: "r", text: "realised silver" }), el("th", { class: "r", text: "my tension" }), el("th", { class: "r", text: "Claude tension" }))));
    const b = el("tbody"); rows.slice().reverse().slice(0, 26).forEach((r) => b.appendChild(el("tr", {}, el("td", { text: r.log_date }), el("td", { text: r.model_version || "" }), el("td", { class: "r", text: r.pred_gold_5d == null ? "–" : signed(100 * r.pred_gold_5d, 2) + "%" }), el("td", { class: "r", text: r.pred_silver_5d == null ? "–" : signed(100 * r.pred_silver_5d, 2) + "%" }), el("td", { class: "r", text: r.realised_gold_5d == null ? "–" : signed(100 * r.realised_gold_5d, 2) + "%" }), el("td", { class: "r", text: r.realised_silver_5d == null ? "–" : signed(100 * r.realised_silver_5d, 2) + "%" }), el("td", { class: "r", text: r.my_tension_score == null ? "–" : num(r.my_tension_score, 0) }), el("td", { class: "r", text: r.claude_tension_score == null ? "–" : num(r.claude_tension_score, 0) }))));
    tb.appendChild(b); gc.appendChild(el("div", { class: "tbl-wrap" }, tb));
    gc.appendChild(el("div", { class: "tiny", text: (D.gold && D.gold.note) || "" }));
    g.appendChild(gc);
    if (D.validation && D.validation.panels) {
      const vc = el("div", { class: "card wide" }, el("h3", { text: "Aggregation method check (reports/validation.md)" }));
      Object.entries(D.validation.panels).forEach(([k, p]) => vc.appendChild(el("p", { class: "small muted", text: k + ": " + p.n_questions + " resolved questions, Brier raw " + num(p.brier_by_a["1.0"], 4) + " vs extremized a=1.5 " + num(p.brier_by_a["1.5"], 4) + " (best a " + p.best_a + ")" })));
      g.appendChild(vc);
    }
    if (D.notes && D.notes.length) g.appendChild(el("div", { class: "card wide" }, el("h3", { text: "Build notes" }), el("ul", { class: "notes" }, ...D.notes.map((n) => el("li", { text: n })))));
    frag.appendChild(g);
    return frag;
  }

  // ---------- routing, theme, blind ----------
  function route() {
    const h = (location.hash || "#week").slice(1);
    const [page, arg] = h.split("/");
    document.querySelectorAll(".tabs a").forEach((a) => a.classList.toggle("active", a.dataset.route === page));
    app.innerHTML = "";
    app.appendChild(page === "scorecard" ? pageScorecard() : page === "country" ? pageCountry(arg || "brazil") : page === "indicators" ? pageIndicators() : pageWeek());
    window.scrollTo({ top: 0 });
  }
  window.addEventListener("hashchange", route);
  const blindToggle = document.getElementById("blind-toggle");
  blindToggle.checked = blind;
  blindToggle.addEventListener("change", () => { blind = blindToggle.checked; store.set(LS.blind, blind ? "1" : "0"); route(); });
  const themeBtn = document.getElementById("theme-toggle");
  const applyTheme = (t) => { if (t === "light" || t === "dark") document.documentElement.setAttribute("data-theme", t); else document.documentElement.removeAttribute("data-theme"); themeBtn.textContent = t === "dark" ? "☾" : t === "light" ? "☀" : "◐"; themeBtn.title = "Theme: " + (t || "auto"); };
  let theme = store.get(LS.theme, ""); applyTheme(theme);
  themeBtn.addEventListener("click", () => { theme = theme === "" ? "light" : theme === "light" ? "dark" : ""; store.set(LS.theme, theme); applyTheme(theme); });
  document.getElementById("generated").textContent = D.generated ? "Data generated " + D.generated : "No data.js found: run python build_site.py";
  route();
})();
