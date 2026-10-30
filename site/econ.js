/* Economists and policy (consensus forecasts, independent fiscal assessments, policy tracker,
   consensus-gap flags) and External drivers (sensitivities, stability, what-if sliders, weekly
   attribution, trade exposures). Loaded on demand by country pages, Crowd and Record.
   Data: data/consensus.json and data/drivers.json. */
(function () {
  "use strict";
  const T = window.TERM;
  const { el, nn, fmt, signed, meta, badge } = T;
  const D = { c: null, d: null };
  const getC = () => (D.c = D.c || T.getJSON("data/consensus.json"));
  const getD = () => (D.d = D.d || T.getJSON("data/drivers.json"));
  const CTRY_INSTR = { MX: ["USDMXN"], BR: ["USDBRL", "BR10Y"], FR: ["OATBUND", "EURUSD"] };
  const UNIT = (u) => (u === "pct" ? "%" : u === "bp" ? "bp" : " pt");
  const COLORS = ["var(--cat-1)", "var(--cat-2)", "var(--t-mon)", "var(--t-pol)", "var(--t-fis)", "var(--ink-GLOBAL)"];
  const link = (url, label) => (url ? el("a", { href: url, target: "_blank", rel: "noopener" }, label) : el("span", {}, label));
  const CONSENSUS_EVIDENCE = { badge: "context", reason: "Economist consensus: what forecasters expect, shown for comparison; not a tested signal." };

  // ---------------- consensus forecasts ----------------
  function rangeBar(r) {
    if (r.min == null || r.max == null || r.max === r.min) return null;
    const lo = r.min, hi = r.max, pos = (v) => (100 * (v - lo)) / (hi - lo);
    return el("div", { class: "rbar", title: "range " + fmt(lo, 2) + " to " + fmt(hi, 2) + (r.sd != null ? ", sd " + fmt(r.sd, 2) : "") },
      r.sd != null ? el("span", { class: "rbar-sd", style: `left:${Math.max(0, pos(r.median - r.sd))}%;width:${Math.min(100, pos(r.median + r.sd)) - Math.max(0, pos(r.median - r.sd))}%` }) : null,
      el("span", { class: "rbar-m", style: `left:${pos(r.median)}%` }),
      r.mine && r.mine.my_point != null ? el("span", { class: "rbar-me", style: `left:${Math.min(100, Math.max(0, pos(r.mine.my_point)))}%`, title: "my forecast " + r.mine.my_point }) : null);
  }
  function viewBtn(r) {
    const above = "Will " + r.label.toLowerCase() + " for " + r.year + " come in above the " + r.source + " consensus median of " + fmt(r.median, 2) + (r.unit && r.unit.startsWith("%") ? "%" : " " + (r.unit || "")) + "?";
    return T.formBtn("My view", "full-call", { question: above, question_id: r.id, resolution_date: (r.year + 1) + "-03-31",
      base_rate: "Consensus median " + fmt(r.median, 2) + " (range " + fmt(r.min, 2) + " to " + fmt(r.max, 2) + (r.sd != null ? ", sd " + fmt(r.sd, 2) : "") + "), " + r.source + ", as of " + r.as_of,
      scenarios: "Above the median: \nAt or below the median: ", title: "[Full call] " + r.id }, "small");
  }
  function gapChip(g) {
    if (!g) return null;
    if (!g.flagged) return el("span", { class: "chip", title: g.basis }, "my view: in line");
    const txt = g.gap != null ? "my view " + signed(g.gap, 2) + (g.gap_in_sd != null ? " (" + signed(g.gap_in_sd, 1) + " sd)" : "") : "my view ≠ consensus (" + Math.round(100 * g.my_prob) + "%)";
    return el("span", { class: "chip flag", title: g.basis + ". Where an edge would have to come from." }, txt);
  }
  function consensusCard(code) {
    return getC().then((C) => {
      const rows = C.forecasts[code] || [];
      if (!rows.length) return el("article", { class: "card" }, el("h2", {}, "Consensus forecasts"), el("div", { class: "empty" }, "No consensus data yet."));
      const byVar = {}; rows.forEach((r) => (byVar[r.var] = byVar[r.var] || []).push(r));
      const t = el("table", { class: "cons" }, el("thead", {}, el("tr", {}, el("th", {}, "forecast"), el("th", { class: "r" }, "median", el("div", { class: "tiny" }, "3m move")),
        el("th", {}, "range", el("div", { class: "tiny" }, "bar: min to max, shaded ±1 sd")))));
      const tb = el("tbody");
      Object.values(byVar).forEach((list) => list.forEach((r, i) => tb.appendChild(el("tr", { class: r.mine && r.mine.flagged ? "gap-row" : "" },
        el("td", {}, i === 0 ? el("b", {}, r.label) : null, el("div", { class: "small" }, String(r.year), " ", viewBtn(r)), gapChip(r.mine)),
        el("td", { class: "r num" }, el("b", {}, fmt(r.median, 2)),
          el("div", { class: "tiny", title: r.change_3m_note || "change in the median over the last three months" }, r.change_3m == null ? "3m –" : "3m " + signed(r.change_3m, 2))),
        el("td", {}, el("div", { class: "rwrap" }, el("span", { class: "tiny num" }, fmt(r.min, 2)), rangeBar(r), el("span", { class: "tiny num" }, fmt(r.max, 2))),
          el("div", { class: "tiny" }, (r.sd == null ? "" : "sd " + fmt(r.sd, 2)) + (r.respondents == null ? "" : " · " + Math.round(r.respondents) + (code === "FR" ? " institutions" : " respondents"))))))));
      t.appendChild(tb);
      const first = rows[0];
      const srcs = code === "FR"
        ? el("div", { class: "small" }, "Sources: ", ...rows.filter((r) => r.var === "gdp" && r.year === C.year).flatMap((r) => r.institutions.map((x, j) => [j ? " · " : "", link(x.url, x.institution), " (" + x.edition + ", " + x.edition_date + ")"])))
        : null;
      const fr = code === "FR" ? el("details", {}, el("summary", {}, "each institution's numbers"), el("div", { class: "scroll" }, el("table", {},
        el("thead", {}, el("tr", {}, el("th", {}, "forecast"), el("th", {}, "year"), ...["IMF", "OECD", "European Commission"].map((n) => el("th", { class: "r" }, n)))),
        el("tbody", {}, ...rows.map((r) => el("tr", {}, el("td", { class: "small" }, r.label), el("td", {}, String(r.year)),
          ...["IMF", "OECD", "European Commission"].map((n) => { const x = r.institutions.find((y) => y.institution === n); return el("td", { class: "r num" }, x ? fmt(x.value, 2) : "–"); }))))))) : null;
      return el("article", { class: "card" }, el("h2", {}, code === "FR" ? "What the IMF, OECD and European Commission forecast" : "What economists forecast (" + first.source + ")"),
        el("div", { class: "scroll" }, t), srcs, fr,
        el("div", { class: "tiny" }, code === "FR" ? "Median of the three institutions; range and sd across them. The ECB policy rate is not forecast by these institutions; the OECD's 3-month euro-area rate stands in." :
          "Median, range and standard deviation across respondents; 3m move = change in the median since the survey about three months earlier. \"My view\" opens a pre-filled Full call; add a number in \"My forecast\" to compare it with the median."),
        meta(code === "FR" ? { source: "IMF WEO, OECD EO, European Commission", as_of: first.as_of, evidence: CONSENSUS_EVIDENCE } :
          { source: first.source, source_url: first.source_url, source_id: first.source_id, as_of: first.as_of, evidence: CONSENSUS_EVIDENCE }));
    });
  }

  // ---------------- independent assessments ----------------
  function assessmentsCard(code) {
    return getC().then((C) => {
      const items = ((C.assessments || {}).items || []).filter((x) => x.country === code);
      const box = el("article", { class: "card" }, el("h2", {}, "Independent fiscal assessments"));
      if (!items.length) { box.append(...nn(el("div", { class: "empty" }, "Not yet run: the monthly job summarises the latest publication from each body."))); return box; }
      items.forEach((x) => {
        const head = el("div", { class: "lbl" }, el("b", {}, x.name), x.verified === false ? el("span", { class: "chip flag-red", title: (x.problems || []).join("; ") }, "✕ unverified") : x.verified ? el("span", { class: "chip" }, "✓ numbers checked") : null);
        const body = [];
        if (x.status === "unavailable") body.push(el("div", { class: "small muted" }, "No publication could be read this month: " + (x.error || "")));
        else {
          body.push(el("div", { class: "small" }, link(x.url, x.title), x.date || x.listed_date ? el("span", { class: "tiny" }, " · " + (x.date || x.listed_date)) : null));
          if (x.summary) body.push(el("p", { class: "small", style: "margin:4px 0" }, x.summary));
          else if (x.status) body.push(el("div", { class: "tiny" }, x.status === "no_ai" ? "Summary pending: the API key is not available to this run." : (x.error || x.status)));
          if (x.key_number) body.push(el("div", { class: "small" }, el("b", {}, "Key number: "), el("span", { class: "num" }, x.key_number.value), " · " + x.key_number.what, x.stance && x.stance !== "not a comparison" ? el("span", { class: "chip est", style: "margin-left:6px" }, x.stance) : null));
          if (x.verified === false) body.push(el("div", { class: "tiny bad-line" }, "✕ " + (x.problems || []).join("; ")));
        }
        if (x.newer) body.push(el("div", { class: "tiny" }, "Newer: ", link(x.newer.url, x.newer.title), " (" + (x.newer.date || "") + ") — " + x.newer.why));
        box.append(...nn(el("div", { class: "assess" }, head, ...body)));
      });
      box.append(...nn(el("div", { class: "tiny" }, "Summaries by the Claude API, refreshed monthly; every number must appear in the cited document, or the summary is marked unverified. Updated " + ((C.assessments || {}).generated_at || "").slice(0, 10) + ".")));
      return box;
    });
  }

  // ---------------- policy tracker ----------------
  function src(s) { return s ? el("div", { class: "tiny" }, link(s.url, s.label), s.date ? " · " + s.date : "") : null; }
  function policyCard(p) {
    const nx = p.next || {};
    const nextEl = nx.date ? el("span", { class: "small" }, el("b", {}, "Next: "), nx.event ? el("a", { href: "#calendar/3m?ev=" + encodeURIComponent(nx.event) }, nx.title || nx.label) : (nx.label || ""), " · " + nx.date + (nx.date ? " (" + (T.daysUntil(nx.date) >= 0 ? "in " + T.daysUntil(nx.date) + "d" : "passed") + ")" : "")) : el("span", { class: "small" }, el("b", {}, "Next: "), nx.label || "–");
    const eff = el("table", { class: "eff-t" }, el("tbody", {}, ...["deficit", "inflation", "growth"].map((k) => el("tr", {}, el("th", {}, k), el("td", { class: "small" }, ((p.effects || {})[k] || {}).text || "–")))));
    const cons = p.consensus && p.consensus.median != null ? el("div", { class: "small" }, el("b", {}, "Economist consensus: "), p.consensus.label + " " + p.consensus.year + ": median " + fmt(p.consensus.median, 2) + (p.consensus.dispersion != null ? " (sd " + fmt(p.consensus.dispersion, 2) + ")" : "") + ", " + p.consensus.source, p.consensus.note ? el("div", { class: "tiny" }, p.consensus.note) : null) : null;
    const v = p.view || {};
    const btn = T.formBtn("My view", "full-call", { question: v.question || p.name, question_id: p.question_id, resolution_date: v.resolution_date || "",
      base_rate: "Government: " + p.claim.text.trim().slice(0, 160) + " | " + p.assessment.by + ": " + p.assessment.text.trim().slice(0, 160),
      title: "[Full call] " + p.question_id }, "small");
    return el("details", { class: "policy card" },
      el("summary", {}, el("span", { class: "pname" }, p.name), " ", gapChip(p.mine), el("div", { class: "tiny" }, p.status)),
      el("p", { class: "small" }, p.what),
      el("div", { class: "grid two" },
        el("div", { class: "claim" }, el("div", { class: "k" }, "Government's case"), el("div", { class: "small" }, p.claim.text), src(p.claim.source)),
        el("div", { class: "claim indep" }, el("div", { class: "k" }, "Independent view: " + p.assessment.by), el("div", { class: "small" }, p.assessment.text), src(p.assessment.source))),
      el("div", { class: "k small", style: "margin-top:8px" }, "Likely effect"), eff, cons,
      el("div", { class: "row", style: "margin-top:8px;justify-content:space-between" }, nextEl, el("span", {}, btn, v.point_label ? el("span", { class: "tiny" }, " add “" + v.point_label + "” as My forecast") : null)));
  }
  function policiesCard(code) {
    return getC().then((C) => {
      const ps = C.policies[code] || [];
      return el("article", { class: "card" }, el("h2", {}, "Policy tracker"),
        ps.length ? el("div", { class: "policies" }, ...ps.map(policyCard)) : el("div", { class: "empty" }, "No policies listed."),
        el("div", { class: "tiny" }, "Hand-curated from free, official or openly published sources (data/terminal/inputs/policies.yaml); every claim links to its source. Effects are quantified only where a cited source does."));
    });
  }

  // ---------------- external drivers: sensitivities and stability ----------------
  function stabilityChart(pts, dr, inst) {
    const ns = T.charts.ns, ticks = T.charts.ticks;
    const wrap = el("div", { class: "viz" }), svg = ns("svg", { role: "img", "aria-label": "rolling one-year beta" }); wrap.appendChild(svg);
    function render() {
      if (!pts || pts.length < 3) { svg.textContent = ""; return; }
      const W = Math.max(260, wrap.clientWidth || 400), H = 160, P = { l: 44, r: 10, t: 10, b: 24 };
      const ys = pts.flatMap((p) => [p[2], p[3]]).concat([0]);
      let a = Math.min(...ys), b = Math.max(...ys); const pad = (b - a) * 0.08 || 0.1; a -= pad; b += pad;
      const tk = ticks(a, b, 4), n = pts.length, X = (i) => P.l + (i / (n - 1)) * (W - P.l - P.r), Y = (v) => P.t + (1 - (v - a) / (b - a)) * (H - P.t - P.b);
      svg.setAttribute("viewBox", `0 0 ${W} ${H}`); svg.textContent = "";
      const gl = ns("g", { class: "gridl" }), ax = ns("g", { class: "axis" });
      tk.list.forEach((v) => { gl.appendChild(ns("line", { x1: P.l, x2: W - P.r, y1: Y(v), y2: Y(v) })); ax.appendChild(ns("text", { x: P.l - 6, y: Y(v) + 4, "text-anchor": "end" }, fmt(v, Math.max(1, tk.dec)))); });
      [0, Math.floor((n - 1) / 2), n - 1].forEach((i) => ax.appendChild(ns("text", { x: X(i), y: H - 6, "text-anchor": i === 0 ? "start" : i === n - 1 ? "end" : "middle" }, pts[i][0].slice(0, 7))));
      svg.append(gl, ax, ns("line", { class: "base", x1: P.l, x2: W - P.r, y1: Y(0), y2: Y(0) }));
      let up = "", dn = ""; pts.forEach((p, i) => { up += (i ? "L" : "M") + X(i) + "," + Y(p[3]); dn = "L" + X(i) + "," + Y(p[2]) + dn; });
      svg.appendChild(ns("path", { d: up + dn + "Z", fill: "var(--accent-2)", opacity: 0.8 }));
      let d = ""; pts.forEach((p, i) => { d += (i ? "L" : "M") + X(i) + "," + Y(p[1]); });
      svg.appendChild(ns("path", { d, class: "line", stroke: "var(--cat-1)" }));
      const l = pts[n - 1]; svg.appendChild(ns("text", { x: X(n - 1) - 4, y: Y(l[1]) - 7, class: "lbl-v", "text-anchor": "end" }, fmt(l[1], 2)));
    }
    render(); if (window.ResizeObserver) new ResizeObserver(render).observe(wrap);
    return el("div", {}, wrap, el("div", { class: "tiny" }, "One-year beta to " + dr.label + ", re-estimated each month end; shaded ±2 standard errors. A band that crosses zero often means the link is not reliable."));
  }
  function instrSensitivity(code, I, R) {
    const r = I.instruments[code];
    if (!r || !r.available) return el("div", { class: "empty" }, (r && r.label || code) + ": no data yet.");
    const per = (f) => (f === "W" ? "weekly" : "monthly");
    const t = el("table", {}, el("thead", {}, el("tr", {}, el("th", {}, "driver"), el("th", { class: "r" }, "1-year beta"), el("th", { class: "r" }, "3-year beta"), el("th", { class: "r", title: "share of the instrument's moves the driver alone accounts for, 3 years" }, "R²"), el("th", {}, "in words (3-year)"))));
    const tb = el("tbody");
    const avail = r.univariate.filter((u) => u.available);
    avail.forEach((u) => tb.appendChild(el("tr", {},
      el("td", {}, I.drivers[u.driver].label, el("div", { class: "tiny" }, per(u.freq) + " changes")),
      el("td", { class: "r num" }, u["1y"] ? fmt(u["1y"].beta, 3) + " ±" + fmt(u["1y"].se, 3) : "–", u["1y"] ? el("div", { class: "tiny" }, "n " + u["1y"].n) : null),
      el("td", { class: "r num" }, u["3y"] ? el("b", {}, fmt(u["3y"].beta, 3)) : "–", u["3y"] ? " ±" + fmt(u["3y"].se, 3) : "", u["3y"] ? el("div", { class: "tiny" }, "n " + u["3y"].n) : null),
      el("td", { class: "r num" }, u["3y"] ? fmt(u["3y"].r2, 2) : "–"),
      el("td", { class: "small" }, u.sentence || "–"))));
    t.appendChild(tb);
    const sel = el("select", { "aria-label": "driver for the stability chart" }, ...avail.map((u) => el("option", { value: u.driver }, I.drivers[u.driver].label)));
    const holder = el("div");
    const draw = () => { holder.replaceChildren(stabilityChart(r.stability[sel.value], I.drivers[sel.value], r)); };
    sel.addEventListener("change", draw); draw();
    return el("div", { class: "instr" }, el("h3", {}, r.label, el("span", { class: "tiny" }, " · " + (r.freq === "W" ? "weekly" : "monthly") + " data to " + r.as_of)),
      el("div", { class: "scroll" }, t), el("div", { class: "tiny" }, "Beta = typical move of " + r.label + " (" + UNIT(r.unit).trim() + ") per unit move of the driver (% for the dollar, euro, oil and commodities; bp for yields and spreads; points for the VIX). ± one standard error."),
      el("div", { class: "row", style: "margin-top:6px" }, el("span", { class: "small" }, "Stability:"), sel), holder);
  }
  function sensitivityCard(code) {
    return getD().then((I) => el("article", { class: "card" }, el("h2", {}, "How it moves with global drivers"),
      ...CTRY_INSTR[code].map((c) => instrSensitivity(c, I)),
      el("details", {}, el("summary", {}, "Global: US 10-year"), instrSensitivity("US10Y", I)),
      el("div", { class: "tiny" }, I.notes.join(" ")),
      meta({ source: "FRED, ECB, BCB, Banxico, Tesouro (as stored)", as_of: I.generated_at, evidence: { badge: "context", reason: "Describes past co-movement; not a forecast and not a tested signal." } })));
  }

  // ---------------- what-if sliders ----------------
  const SLIDER = { usd: [-3, 3, 0.25], us10y: [-50, 50, 5], us2y: [-50, 50, 5], vix: [-10, 15, 1], brent: [-25, 25, 2.5], iron: [-20, 20, 2], soy: [-20, 20, 2],
    bund: [-40, 40, 5], eur: [-3, 3, 0.25], itsp: [-40, 40, 5], essp: [-40, 40, 5] };
  function whatIfCard(code) {
    return getD().then((I) => {
      const instr = CTRY_INSTR[code].map((c) => I.instruments[c]).filter((r) => r && r.available && r.model);
      const keys = [...new Set(instr.flatMap((r) => r.model.drivers.concat(r.monthly_model ? r.monthly_model.drivers : [])))];
      const x = {}; keys.forEach((k) => (x[k] = 0));
      const outs = el("div", { class: "grid" });
      const draw = () => {
        outs.replaceChildren(...instr.map((r) => {
          const useM = r.monthly_model && r.monthly_model.drivers.some((k) => !r.model.drivers.includes(k) && x[k]);
          const m = useM ? r.monthly_model : r.model;
          const v = m.drivers.map((k) => x[k] || 0);
          const eff = m.beta.reduce((s, b, i) => s + b * v[i], 0);
          let q = 0; m.cov.forEach((row, i) => row.forEach((c, j) => { q += v[i] * c * v[j]; }));
          const half = 1.645 * Math.sqrt(q + m.resid_sd * m.resid_sd);
          const ignored = keys.filter((k) => x[k] && !m.drivers.includes(k)).map((k) => I.drivers[k].label);
          const u = UNIT(r.unit);
          const words = r.unit === "pct" && r.label.startsWith("USD/") ? (eff > 0 ? " (the " + r.asset + " weaker)" : eff < 0 ? " (the " + r.asset + " stronger)" : "") : "";
          return el("div", { class: "wi-out" }, el("div", { class: "lbl" }, el("b", {}, r.label), el("span", { class: "tiny" }, "typical " + (m.freq === "W" ? "week" : "month"))),
            el("div", { class: "lvl num" }, signed(eff, r.unit === "pct" ? 2 : 1) + u, el("span", { class: "small" }, words)),
            el("div", { class: "tiny" }, "90% of such " + (m.freq === "W" ? "weeks" : "months") + ": " + signed(eff - half, r.unit === "pct" ? 2 : 1) + " to " + signed(eff + half, r.unit === "pct" ? 2 : 1) + u),
            ignored.length ? el("div", { class: "tiny" }, "Not in this instrument's model: " + ignored.join(", ")) : null,
            el("div", { class: "tiny" }, "Model R² " + fmt(m.r2, 2) + ", " + m.n + " " + (m.freq === "W" ? "weeks" : "months") + " to " + m.end));
        }));
      };
      const sl = el("div", { class: "grid" }, ...keys.map((k) => {
        const [lo, hi, st] = SLIDER[k] || [-10, 10, 1], d = I.drivers[k], lab = el("b", { class: "num" }, "0" + UNIT(d.unit));
        const inp = el("input", { type: "range", min: lo, max: hi, step: st, value: 0, "aria-label": "move in " + d.label,
          oninput: (e) => { x[k] = +e.target.value; lab.textContent = signed(x[k], st < 1 ? 2 : 0) + UNIT(d.unit); draw(); } });
        return el("div", { class: "slider" }, el("div", { class: "top-l" }, el("span", {}, d.label), lab), inp);
      }));
      draw();
      return el("article", { class: "card" }, el("h2", {}, "What if a global driver moves?"),
        el("div", { class: "note-box small" }, "This describes typical co-movement over the last three years, not a forecast: it shows how these instruments have usually moved in a week (or month) when the drivers moved by these amounts, holding the other drivers still."),
        sl, outs,
        el("div", { class: "tiny" }, "Effects use the three-year multi-driver regression; the 90% range adds the uncertainty in the betas and the usual unexplained move. Brazil's iron ore and soybean sliders switch to the monthly model."));
    });
  }

  // ---------------- weekly attribution ----------------
  function stack(parts, local, scale, names) {
    const segs = parts.map((p, i) => ({ v: p.contrib, c: COLORS[i % COLORS.length], t: names[p.driver] + " " + signed(p.contrib, 2) })).concat([{ v: local, c: "var(--text-3)", t: "local " + signed(local, 2), local: true }]);
    const pos = segs.filter((s) => s.v > 0), neg = segs.filter((s) => s.v < 0);
    const w = (v) => (50 * Math.abs(v)) / scale + "%";
    return el("div", { class: "stk", role: "img", "aria-label": segs.map((s) => s.t).join(", ") },
      el("div", { class: "stk-neg" }, ...neg.reverse().map((s) => el("span", { class: s.local ? "loc" : "", style: `width:${w(s.v)};background:${s.c}`, title: s.t }))),
      el("div", { class: "stk-pos" }, ...pos.map((s) => el("span", { class: s.local ? "loc" : "", style: `width:${w(s.v)};background:${s.c}`, title: s.t }))));
  }
  function attributionCard(code) {
    return getD().then((I) => {
      const names = {}; Object.entries(I.drivers).forEach(([k, d]) => (names[k] = d.label));
      const blocks = CTRY_INSTR[code].map((c) => I.instruments[c]).filter((r) => r && r.available && r.attribution && r.attribution.length).map((r) => {
        const A = r.attribution, last = A[A.length - 1], u = UNIT(r.unit);
        const scale = Math.max(...A.flatMap((a) => [Math.abs(a.move), a.parts.reduce((s, p) => s + Math.max(0, p.contrib), 0) + Math.max(0, a.local), -a.parts.reduce((s, p) => s + Math.min(0, p.contrib), 0) - Math.min(0, a.local)])) || 1;
        const legend = el("div", { class: "legend small" }, ...last.parts.map((p, i) => el("span", {}, el("i", { style: "background:" + COLORS[i % COLORS.length] }), names[p.driver])), el("span", {}, el("i", { class: "loc", style: "background:var(--text-3)" }), "local remainder"));
        return el("div", { class: "instr" }, el("h3", {}, r.label, el("span", { class: "tiny" }, " · " + (r.freq === "W" ? "week" : "month") + " to " + last.end + (last.partial ? " (in progress)" : ""))),
          el("p", { class: "small", style: "margin:2px 0 6px" }, el("b", {}, last.reading)),
          el("div", { class: "stk-row big" }, el("span", { class: "tiny" }, "move " + signed(last.move, r.unit === "pct" ? 2 : 0) + u),
            stack(last.parts, last.local, Math.max(Math.abs(last.move), last.parts.reduce((s, p) => s + Math.abs(p.contrib), 0) + Math.abs(last.local)) / 1.6 || 1, names)),
          legend,
          el("details", {}, el("summary", {}, "previous " + (A.length - 1) + " " + (r.freq === "W" ? "weeks" : "months")),
            el("div", { class: "tiny" }, "same scale for every week, so sizes compare"),
            ...A.slice(0, -1).reverse().map((a) => el("div", { class: "stk-row" }, el("span", { class: "tiny" }, a.end.slice(5) + " " + signed(a.move, r.unit === "pct" ? 2 : 0) + u), stack(a.parts, a.local, scale, names)))));
      });
      return el("article", { class: "card" }, el("h2", {}, "This week's move: global or local?"), ...blocks,
        el("div", { class: "tiny" }, "Each bar splits the move into beta × the driver's move (coloured, from the three-year model) and the local remainder (grey). Bars right of centre push the instrument up, left push it down. The latest week can be in progress, and drivers published with a lag (the Fed's broad dollar index, EUR/USD) can hold the last complete week back."));
    });
  }

  // ---------------- consensus gaps (Crowd page) ----------------
  function gapsCard() {
    return getC().then((C) => {
      const gs = C.gaps || [];
      const box = el("article", { class: "card" + (C.n_flagged ? " feature" : "") }, el("h2", {}, "Where my view departs from the economists"));
      if (!gs.length) box.append(...nn(el("p", { class: "small" }, "No logged views yet. Use \"My view\" on a forecast or policy on a country page; the Full call's \"My forecast\" number is compared with the consensus.")));
      else box.append(...nn(el("div", { class: "scroll" }, el("table", {}, el("thead", {}, el("tr", {}, el("th", {}, ""), el("th", {}, "forecast or policy"), el("th", { class: "r" }, "mine"), el("th", { class: "r" }, "consensus"), el("th", { class: "r" }, "gap"), el("th", {}, "record"))),
        el("tbody", {}, ...gs.map((g) => el("tr", { class: g.flagged ? "gap-row" : "" }, el("td", {}, g.flagged ? el("span", { class: "chip flag" }, "gap") : ""), el("td", { class: "small" }, T.ctryChip(g.country || "GLOBAL"), " ", g.label || g.question_id),
          el("td", { class: "r num" }, g.my_point != null ? fmt(g.my_point, 2) : g.my_prob != null ? Math.round(100 * g.my_prob) + "%" : "–"),
          el("td", { class: "r num" }, g.consensus_median != null ? fmt(g.consensus_median, 2) + (g.dispersion != null ? " ±" + fmt(g.dispersion, 2) : "") : "–"),
          el("td", { class: "r num" }, g.gap_in_sd != null ? signed(g.gap_in_sd, 1) + " sd" : "–"), el("td", { class: "tiny" }, g.record || ""))))))));
      box.append(...nn(el("div", { class: "tiny" }, C.gap_rule + " An edge has to come from somewhere the consensus is wrong; these are the places you are betting it is."), badge({ badge: "untested", reason: "Your record against the consensus is scored once these questions resolve." })));
      return box;
    });
  }

  // ---------------- open-trade exposure (Record page) ----------------
  function exposureFor(tradeId) {
    return getD().then((I) => {
      const t = (I.trades || []).find((x) => x.trade_id === tradeId);
      if (!t) return null;
      if (!t.biggest) return el("div", { class: "tiny" }, t.note || "no driver model");
      const b = t.biggest, d = I.drivers[b.driver];
      return el("div", { class: "tiny", title: t.all.map((x) => I.drivers[x.driver].label + ": " + signed(x.pnl_usd, 0)).join("; ") },
        "Biggest external exposure: " + d.label + ". A one-sd " + (b.freq === "W" ? "weekly" : "monthly") + " move (" + signed(b.driver_sd, 2) + UNIT(d.unit) + ") has typically come with " + signed(b.pnl_usd, 0) + " USD of P&L" + (t.model !== t.instrument ? " (using " + t.model + "'s betas)" : "") + ".");
    });
  }

  T.econ = { consensusCard, assessmentsCard, policiesCard, sensitivityCard, whatIfCard, attributionCard, gapsCard, exposureFor };
})();
