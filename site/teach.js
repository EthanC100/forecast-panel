/* Teaching visuals and calculators. Each one is titled with the question it answers, shows its source
   and as-of time, and prints its numbers next to the picture. Data: stored series, the paper book's
   instrument settings (data/book/state.json) and em-macro's published results (data/teach.json). */
(function () {
  "use strict";
  const T = window.TERM;
  const nn = T.nn;
  const { el, fmt, signed, meta } = T;
  const C = () => T.charts;
  const need = () => T.need("charts");
  const teach = () => T.json("data/teach.json");
  const book = () => T.json("data/book/state.json");
  const DAY = 864e5;
  const iso = (t) => new Date(t).toISOString().slice(0, 10);
  const valueOn = (s, date) => { let last = null; for (const r of s.history) { if (r[0] > date) break; if (typeof r[1] === "number") last = r; } return last; };
  const lastObs = (s) => { for (let i = s.history.length - 1; i >= 0; i--) if (typeof s.history[i][1] === "number") return s.history[i]; return null; };
  const EM = { badge: "context", reason: "em-macro's published model output, shown to explain the market; not a trading signal." };
  const POSTHOC = { badge: "context", reason: "em-macro labels this model post-hoc: chosen after its 2020+ test, so it is not a clean out-of-sample result." };
  const CTRY = { FR: "France", BR: "Brazil", MX: "Mexico" };

  // animated bars: widths grow in sequence when the card opens (instant with reduced motion)
  function animate(node) {
    const bs = node.querySelectorAll(".hb-b");
    bs.forEach((b) => { b.dataset.w = b.style.width; b.style.width = "0%"; });
    requestAnimationFrame(() => requestAnimationFrame(() => bs.forEach((b, i) => { b.style.transitionDelay = (i * 0.45) + "s"; b.style.width = b.dataset.w; })));
    return node;
  }

  // ---------------- How a currency trade makes money ----------------
  function fxTrade(instr) {
    const ccy = instr === "USDBRL" ? "BRL" : "MXN";
    const ids = instr === "USDBRL" ? ["br.usdbrl.ptax", "br.selic.target", "Selic"] : ["mx.usdmxn.fix", "mx.policy.target", "Banxico target rate"];
    return Promise.all([need(), T.loadSeries(ids[0]), T.loadSeries(ids[1]), T.loadSeries("us.ust10y").catch(() => null), T.loadSeries("us.fedfunds"), book()]).then(([, spot, loc, , ff, b]) => {
      const end = lastObs(spot), start = valueOn(spot, iso(Date.parse(end[0]) - 91 * DAY));
      const days = Math.round((Date.parse(end[0]) - Date.parse(start[0])) / DAY);
      const rLoc = lastObs(loc)[1], rUsd = lastObs(ff)[1], cost = b.instruments[instr].cost, N = 100000;
      // the classic carry trade: long the local currency = short USD/xxx (book convention: long = long USD)
      const price = -N * (end[1] - start[1]) / end[1];
      const carry = N * (rLoc - rUsd) / 100 * days / 360;
      const costUsd = -N * cost / 100;
      const total = price + carry + costUsd;
      const money = (v) => (v < 0 ? "−$" : "+$") + fmt(Math.abs(v), 0);
      const rows = [
        { label: "Price change: USD/" + ccy + " " + fmt(start[1], 4) + " → " + fmt(end[1], 4), value: price, tone: price >= 0 ? "up" : "down" },
        { label: "Carry: " + ccy + " rate " + fmt(rLoc, 2) + "% − US rate " + fmt(rUsd, 2) + "% for " + days + " days", value: carry, tone: carry >= 0 ? "up" : "down" },
        { label: "Trading cost: " + fmt(cost, 3) + "% round trip", value: costUsd, tone: "down" },
        { label: "Total", value: total, tone: total >= 0 ? "up" : "down" }];
      return animate(el("div", {},
        el("div", { class: "q" }, "What would $100,000 lent in " + ccy + " (and borrowed in USD) have made over the last 3 months?"),
        el("p", { class: "small" }, "You sell dollars and buy " + ccy + ". You earn the " + ccy + " interest rate and pay the US rate: that is the carry. If the " + ccy + " weakens (USD/" + ccy + " rises), the price change eats into it. Costs are paid once."),
        C().bars(rows, { fmt: money }),
        el("div", { class: "formula" }, "P&L = −N × (S_end − S_start) / S_end  +  N × (r_" + ccy + " − r_USD) × days / 360  −  N × cost\n    = " + money(price) + " " + money(carry) + " " + money(costUsd) + " = " + money(total)),
        el("p", { class: "tiny" }, "Long USD/" + ccy + " (the book's 'long') is the mirror image: the price change flips sign and you pay the carry instead. Real numbers from " + start[0] + " to " + end[0] + "."),
        meta({ source: spot.source + ", " + loc.source + ", FRED", source_url: spot.source_url, as_of: end[0], evidence: { badge: "context", reason: "Arithmetic on real past prices, not a forecast." } }, { noId: true })));
    });
  }

  // ---------------- How a spread trade makes money ----------------
  function spreadTrade() {
    return Promise.all([need(), T.loadSeries("fr.spread.oat_bund").catch(() => null), T.loadSeries("fr.spread.oat_bund.ecb_m"), T.loadSeries("fr.oat10y").catch(() => null),
      T.loadSeries("fr.oat10y.ecb_m"), T.loadSeries("de.bund10y.ecb_m"), book()]).then(([, sd, sm, od, om, bm, b]) => {
      const s = sd && sd.history.length ? sd : sm, o = od && od.history.length ? od : om;
      const end = lastObs(s), start = valueOn(s, iso(Date.parse(end[0]) - 92 * DAY));
      const oat = valueOn(o, end[0]), bund = valueOn(bm, end[0]);
      const D = b.instruments.OATBUND.duration, N = 100000, dS = end[1] - start[1];
      const pnl = -N * D * dS / 10000;
      const money = (v) => (v < 0 ? "−$" : "+$") + fmt(Math.abs(v), 0);
      const scen = [-25, -10, 10, 25].map((x) => ({ label: "spread " + (x > 0 ? "widens " : "tightens ") + Math.abs(x) + " bp", value: -N * D * x / 10000, tone: x < 0 ? "up" : "down" }));
      return animate(el("div", {},
        el("div", { class: "q" }, "What does a long-France, short-Germany bond position gain or lose when the spread moves?"),
        el("p", { class: "small" }, "The spread is France's 10-year yield minus Germany's: " + fmt(oat && oat[1], 2) + "% − " + fmt(bund && bund[1], 2) + "% = " + fmt(end[1], 1) + " bp (" + end[0] + "). ",
          "Widening means investors want more extra yield to hold French debt (bad for the position); tightening is the opposite. A bond's price moves by about duration × the yield change."),
        C().bars(scen, { fmt: money }),
        el("div", { class: "formula" }, "P&L ≈ −N × duration × Δspread / 10,000\n$100,000 × " + D + " × 1 bp / 10,000 = $" + fmt(N * D / 10000, 0) + " per basis point"),
        el("p", { class: "small" }, "Over the last 3 months the spread moved " + signed(dS, 1) + " bp (" + start[0] + " → " + end[0] + "), so the position made ", el("b", { class: pnl >= 0 ? "up" : "down" }, money(pnl)), " before costs."),
        meta({ source: s.source, source_url: s.source_url, as_of: end[0], evidence: { badge: "context", reason: "Arithmetic on real past yields, not a forecast." }, degraded: s.id && s.id.endsWith("ecb_m") ? { effect: "Monthly averages: the daily path is not visible.", upgrade: "add WEBSTAT_CLIENT_ID" } : null }, { noId: true })));
    });
  }

  // ---------------- What moves this market ----------------
  function driversCard(code) {
    return Promise.all([need(), teach()]).then(([, t]) => {
      const sets = (t.countries[code] || {}).drivers;
      if (!sets || sets.error) return null;
      let k = 0;
      const card = el("article", { class: "card" }), body = el("div");
      const draw = () => {
        const d = sets[k];
        const what = d.kind === "spread" ? "spread" : "currency";
        const upBad = true; // a wider spread and a weaker currency are both adverse
        const rows = d.rows.map((r) => {
          const ch = r.change_12m, dirTxt = ch == null || Math.abs(ch) < 0.05 ? "little change in 12 months" : (ch > 0 ? "▲ pushed it up " : "▼ pushed it down ") + fmt(Math.abs(ch), 1) + " in 12 months";
          return { label: r.plain, value: r.effect_per_sd, note: "t = " + fmt(r.t, 1) + (r.significant ? "" : " (not significant)") + " · " + dirTxt, tone: "" };
        });
        body.replaceChildren(...nn(
          el("div", { class: "q" }, "Effect of a one-standard-deviation change in each factor on " + CTRY[code] + "'s " + d.target + " (" + d.unit + "), largest first."),
          C().bars(rows, { fmt: (v) => signed(v, 1) }),
          el("p", { class: "tiny" }, "Bars: the model's estimated effect (+ = " + (what === "spread" ? "wider spread" : "weaker currency") + "). Notes: how much that factor's contribution changed over the last 12 months (" + d.compare_to + " → " + d.as_of + "); " + (upBad ? "▲ is adverse" : "") + ". Top 10 of " + d.n_factors + " factors."),
          meta({ source: "em-macro risk model (" + d.model + ")", source_url: d.source_url, as_of: d.as_of, evidence: d.model.includes("post-hoc") ? POSTHOC : EM }, { noId: true })));
      };
      const tabs = sets.length > 1 ? el("div", { class: "tabs mini" }, ...sets.map((s, i) => el("button", { type: "button", class: i === k ? "on" : "", onclick: (e) => { k = i; [...e.target.parentNode.children].forEach((b, j) => b.classList.toggle("on", j === i)); draw(); } }, s.kind === "spread" ? "Spread" : "Currency"))) : null;
      draw();
      card.append(...nn(el("div", { class: "vizhead" }, el("h2", { style: "margin:0" }, "What moves " + CTRY[code] + "'s " + (sets.length > 1 ? "markets" : "spread") + " most?"), tabs), body));
      return card;
    });
  }

  // ---------------- Fair-value breakdown ----------------
  function waterfallCard(code) {
    return Promise.all([need(), teach()]).then(([, t]) => {
      const w = (t.countries[code] || {}).waterfall;
      if (!w || w.error) return null;
      const gap = w.actual == null ? null : w.actual - w.fair_value;
      return el("article", { class: "card" },
        el("h2", {}, "How does em-macro's model arrive at " + CTRY[code] + "'s fair spread, and how far is the actual?"),
        el("div", { class: "q" }, w.target + ", " + w.as_of + ". ", el("span", { class: "chip warn" }, "post-hoc model")),
        C().waterfall(w.steps, { total: w.fair_value, actual: w.actual, unit: "bp" }),
        el("p", { class: "small" }, "Actual " + fmt(w.actual, 0) + " bp vs model " + fmt(w.fair_value, 0) + " bp: ", el("b", {}, gap == null ? "–" : signed(gap, 0) + " bp"),
          gap == null ? "" : gap > 0 ? " above the model (cheap by its measure)." : " below the model (expensive by its measure)."),
        el("p", { class: "tiny" }, "Each bar starts where the previous one ended: the country's 2005-19 average, then each factor's contribution today, adding up to the fair value. em-macro: " + w.model + "; the gap does not forecast 3- or 6-month spread changes."),
        meta({ source: "em-macro risk model", source_url: w.source_url, as_of: w.as_of, evidence: POSTHOC }, { noId: true }));
    });
  }

  // ---------------- What-if sliders ----------------
  function whatIfCard(code) {
    return Promise.all([need(), teach()]).then(([, t]) => {
      const W = t.what_if; if (!W || W.error) return null;
      const items = W.countries[code] || [], val = {};
      items.forEach((i) => { val[i.key] = 0; });
      const out = el("div");
      const assets = code === "FR" ? ["spread_bp"] : ["spread_bp", "fx_pct"];
      const NAME = { spread_bp: "Spread change (bp)", fx_pct: "Currency, real terms (% , + = weaker)" };
      function calc() {
        out.textContent = "";
        assets.forEach((a) => {
          let est = 0, v2 = 0;
          items.forEach((i) => { const e = i.effects[a]; if (!e) return; est += e.per_unit * val[i.key]; v2 += (e.se_per_unit * val[i.key]) ** 2; });
          const half = 1.645 * Math.sqrt(v2), lo = est - half, hi = est + half;
          const lim = Math.max(10, Math.abs(lo), Math.abs(hi)) * 1.1, pos = (v) => 50 + (50 * v) / lim;
          out.append(...nn(el("div", { class: "hb" },
            el("div", { class: "hb-l" }, el("span", {}, NAME[a]), el("b", { class: "num " + (est > 0.05 ? "down" : est < -0.05 ? "up" : "") }, signed(est, a === "fx_pct" ? 2 : 1) + "  [" + signed(lo, 1) + ", " + signed(hi, 1) + "]")),
            el("div", { class: "hb-t tall" }, el("i", { class: "z", style: "left:50%" }),
              el("span", { class: "hb-band", style: `left:${pos(lo)}%;width:${Math.max(0.5, pos(hi) - pos(lo))}%` }),
              el("span", { class: "hb-pt", style: `left:${pos(est)}%` })))));
        });
      }
      const sliders = items.map((i) => {
        const lab = el("b", { class: "num" }, "0");
        const inp = el("input", { type: "range", min: i.min, max: i.max, step: i.step, value: 0, "aria-label": i.label,
          oninput: (e) => { val[i.key] = parseFloat(e.target.value); lab.textContent = signed(val[i.key], i.step < 1 ? 2 : 0); calc(); } });
        return el("div", { class: "slider" }, el("div", { class: "top-l" }, el("span", {}, i.label, i.now != null ? el("span", { class: "tiny" }, " (now " + fmt(i.now, 1) + ")") : null), lab), inp,
          i.unit_note ? el("div", { class: "tiny" }, i.unit_note) : null);
      });
      calc();
      return el("article", { class: "card" },
        el("h2", {}, "What would a change in deficit, rating, seat share or populism do to " + CTRY[code] + "'s " + (code === "FR" ? "spread" : "spread and currency") + "?"),
        ...sliders, el("div", { class: "k small", style: "margin-top:8px" }, "Estimated effect, with 90% band"), out,
        el("p", { class: "tiny" }, W.caveat + " " + W.band + ". " + (code === "FR" ? "" : W.currency_note)),
        el("button", { type: "button", class: "btn small", onclick: (e) => { const card = e.target.closest(".card"); card.querySelectorAll("input[type=range]").forEach((r) => { r.value = 0; r.dispatchEvent(new Event("input")); }); } }, "reset"),
        meta({ source: "em-macro what-if (risk model)", source_url: W.source_url, as_of: (items[0] && Object.values(items[0].effects)[0] || {}).as_of, evidence: EM }, { noId: true }));
    });
  }

  // ---------------- Event study ----------------
  function eventStudyCard(code) {
    return Promise.all([need(), teach()]).then(([, t]) => {
      const E = t.event_study; if (!E || E.error || !E.groups[code]) return null;
      const G = E.groups[code], groups = [...new Set(G.map((g) => g.group))];
      let gi = 0, ai = 0;
      const body = el("div");
      function draw() {
        const assets = G.filter((g) => g.group === groups[gi]), g = assets[Math.min(ai, assets.length - 1)];
        const pts = g.path.map((p) => ({ label: p.day === 0 ? "day before" : "day " + p.day, mean: p.mean, lo: p.lo, hi: p.hi }));
        body.replaceChildren(...nn(
          el("div", { class: "row" }, el("div", { class: "tabs mini" }, ...groups.map((n, i) => el("button", { type: "button", class: i === gi ? "on" : "", onclick: () => { gi = i; draw(); } }, n))),
            el("div", { class: "tabs mini" }, ...assets.map((a, i) => el("button", { type: "button", class: i === ai ? "on" : "", onclick: () => { ai = i; draw(); } }, a.asset)))),
          el("div", { class: "q", style: "margin-top:8px" }, "Average " + g.asset + " move after " + g.group.toLowerCase() + " (" + g.n + " events, " + g.first.slice(0, 4) + "–" + g.last.slice(0, 4) + "), " + g.unit + "; shaded: " + g.range + "."),
          C().band({ points: pts, dec: g.unit === "%" ? 2 : 1, aria: "event study" }),
          el("div", { class: "scroll" }, el("table", {}, el("thead", {}, el("tr", {}, el("th", {}, "horizon"), el("th", { class: "r" }, "mean"), el("th", { class: "r" }, "median"), el("th", { class: "r" }, "range"))),
            el("tbody", {}, ...g.path.slice(1).map((p) => el("tr", {}, el("td", {}, "day " + p.day), el("td", { class: "r num" }, signed(p.mean, 2)), el("td", { class: "r num" }, signed(p.median, 2)), el("td", { class: "r num" }, signed(p.lo, 1) + " to " + signed(p.hi, 1))))))),
          el("p", { class: "tiny" }, "Measure: " + E.measure + ". Horizons are days 1, 5 and 20, not to scale. " + E.missing),
          meta({ source: "em-macro event study", source_url: E.source_url, as_of: g.last, evidence: { badge: "tested_no_lead", reason: "em-macro's event studies: average reactions are small relative to the spread across events; the surprise regressions added little out of sample." } }, { noId: true })));
      }
      draw();
      return el("article", { class: "card" }, el("h2", {}, "How has " + (code === "BR" ? "Brazil" : "Mexico") + " moved around past elections and rate decisions?"), body);
    });
  }

  // ---------------- The systematic algorithm ----------------
  function systematicCard() {
    return Promise.all([need(), teach()]).then(([, t]) => {
      const S = t.systematic; if (!S || S.error) return null;
      const z = (v) => { if (v == null) return el("span", { class: "tiny" }, "n/a"); const w = Math.min(50, Math.abs(v) * 16.7);
        return el("span", { class: "zb" }, el("span", { class: "zt" }, el("i", { style: `left:${v < 0 ? 50 - w : 50}%;width:${w}%` })), el("b", { class: "num" }, signed(v, 1))); };
      const book = (name, key, total) => {
        const rows = S.rows.filter((r) => r.book === key).sort((a, b) => b.score - a.score);
        const longs = rows.filter((r) => r.side === "long"), shorts = rows.filter((r) => r.side === "short");
        const tr = (r) => el("tr", {}, el("td", {}, el("b", {}, r.instrument), el("div", { class: "tiny" }, r.description)), el("td", {}, z(r.carry_z)), el("td", {}, z(r.trend_z)), el("td", {}, z(r.value_z)),
          el("td", { class: "r num" }, el("b", {}, signed(r.score, 2))), el("td", { class: "r" }, el("span", { class: "chip" }, (r.side === "long" ? "▲ long " : "▼ short ") + fmt(Math.abs(r.size_pct), 0) + "%")));
        return el("div", {}, el("h3", {}, name + ": " + rows.length + " of " + total + " positions taken"),
          el("div", { class: "scroll" }, el("table", { class: "sys" }, el("thead", {}, el("tr", {}, el("th", {}, "instrument"), el("th", {}, "carry z"), el("th", {}, "trend z"), el("th", {}, "value z"), el("th", { class: "r" }, "score"), el("th", { class: "r" }, "position"))),
            el("tbody", {}, el("tr", {}, el("td", { colspan: 6, class: "tiny" }, "Top third → long")), ...longs.map(tr),
              el("tr", {}, el("td", { colspan: 6, class: "tiny" }, "Middle third → no position (not published)")),
              el("tr", {}, el("td", { colspan: 6, class: "tiny" }, "Bottom third → short")), ...shorts.map(tr)))));
      };
      return el("article", { class: "card" },
        el("h2", {}, "How does em-macro's systematic strategy choose this month's positions?"),
        el("div", { class: "q" }, "Signals for " + S.as_of + " (positions held from " + S.effective_from + "). Each signal is a z-score across the book; the average ranks them."),
        book("Currencies", "fx", S.universe.fx), book("Bonds", "bond", S.universe.bond),
        el("div", { class: "formula" }, S.formula.join("\n")),
        el("p", { class: "tiny" }, S.note + " Position size is % of capital (leverage is high by design)."),
        meta({ source: "em-macro systematic strategy", source_url: S.source_url, as_of: S.as_of, evidence: { badge: "tested_leads", reason: "Frozen on 2005-2019 and tested once on 2020-Sep 2026: +6.0% a year, Sharpe 0.65 (em-macro section 10). The edge came almost entirely from carry." } }, { noId: true }));
    });
  }

  // ---------------- Overview: map ----------------
  function mapCard() {
    return Promise.all([need(), T.json("geo.json"), T.loadSeries("fr.spread.oat_bund").catch(() => null), T.loadSeries("fr.spread.oat_bund.ecb_m"), T.loadSeries("br.usdbrl.ptax"), T.loadSeries("mx.usdmxn.fix")])
      .then(([, geo, frd, frm, br, mx]) => {
        const fr = frd && frd.history.length ? frd : frm;
        const spec = [["FR", fr, "OAT-Bund spread", "bp"], ["BR", br, "USD/BRL", "%"], ["MX", mx, "USD/MXN", "%"]];
        const cells = spec.map(([code, s, name, unit]) => {
          const end = lastObs(s), start = valueOn(s, iso(Date.parse(end[0]) - 31 * DAY));
          const ch = unit === "%" ? 100 * (end[1] / start[1] - 1) : end[1] - start[1];
          // typical one-month move over 3 years: the colour shows how unusual this month is
          const obs = s.history.filter((r) => typeof r[1] === "number" && r[0] >= iso(Date.parse(end[0]) - 3 * 365 * DAY));
          const mo = []; for (let i = 0; i < obs.length; i++) { const p = valueOn(s, iso(Date.parse(obs[i][0]) - 31 * DAY)); if (p && p[0] >= obs[0][0]) mo.push(unit === "%" ? 100 * (obs[i][1] / p[1] - 1) : obs[i][1] - p[1]); }
          const sd = Math.sqrt(mo.reduce((a, v) => a + v * v, 0) / Math.max(1, mo.length));
          const zz = sd ? ch / sd : 0, adverse = ch > 0; // wider spread / weaker currency
          const alpha = Math.min(1, Math.abs(zz) / 2);
          const g = geo.countries[code];
          const svg = C().ns("svg", { viewBox: "-2 -2 104 104", role: "img", "aria-label": CTRY[code] + " " + name + " " + signed(ch, 1) + unit },
            C().ns("path", { d: g.path, "stroke-linejoin": "round", fill: Math.abs(zz) < 0.25 ? "var(--surface-2)" : adverse ? "var(--bad)" : "var(--good)", "fill-opacity": Math.abs(zz) < 0.25 ? 1 : 0.18 + 0.62 * alpha, stroke: "var(--c-" + code + ")", "stroke-width": 1.6 }));
          return el("a", { class: "mapc", href: "#country/" + code, "aria-label": "Open " + CTRY[code] }, svg,
            el("div", { class: "small" }, el("b", {}, CTRY[code])),
            el("div", { class: "num " + (Math.abs(zz) < 0.25 ? "" : adverse ? "down" : "up") }, el("b", {}, signed(ch, unit === "%" ? 2 : 1) + (unit === "%" ? "%" : " bp")), " " + name),
            el("div", { class: "tiny" }, "typical month ±" + fmt(sd, unit === "%" ? 1 : 0) + (unit === "%" ? "%" : " bp") + " · " + signed(zz, 1) + " sd"));
        });
        return el("article", { class: "card" }, el("h2", {}, "Where did markets move most in the last month?"),
          el("div", { class: "mapgrid" }, ...cells),
          el("div", { class: "legend" }, el("span", {}, el("i", { style: "background:var(--bad);opacity:.6" }), "adverse (wider spread, weaker currency)"), el("span", {}, el("i", { style: "background:var(--good);opacity:.6" }), "favourable"), el("span", {}, "darker = more unusual; tap to open")),
          meta({ source: "stored series; outlines: " + geo.source, as_of: lastObs(br)[0], evidence: { badge: "context", reason: "Recent moves, not a signal." }, degraded: fr.id.endsWith("ecb_m") ? { effect: "France uses monthly averages until Webstat is configured.", upgrade: "add WEBSTAT_CLIENT_ID" } : null }, { noId: true }));
      });
  }

  // ---------------- Overview: correlation heatmap ----------------
  const HEAT = [["br.usdbrl.ptax", "BRL", "USD/BRL"], ["mx.usdmxn.fix", "MXN", "USD/MXN"], ["br.di.f27.proxy", "DI27", "DI Jan-27"], ["br.di.f29.proxy", "DI29", "DI Jan-29"], ["br.di.f31.proxy", "DI31", "DI Jan-31"],
    ["br.td.pre_longest", "BR10", "Brazil 10y"], ["us.ust10y", "US10", "US 10y"], ["de.bund10y", "DE10", "Bund 10y"]];
  function heatmapCard() {
    return Promise.all([need(), ...HEAT.map(([id]) => T.loadSeries(id.replace(".proxy", "")).catch(() => T.loadSeries(id)).catch(() => null))]).then(([, ...ss]) => {
      const ok = HEAT.map((h, i) => ({ h, s: ss[i] })).filter((x) => x.s && x.s.history.length);
      const end = ok.map((x) => lastObs(x.s)[0]).sort().pop(), from = iso(Date.parse(end) - 92 * DAY);
      const ch = ok.map(({ s }) => {
        const m = {}, h = s.history.filter((r) => typeof r[1] === "number" && r[0] >= iso(Date.parse(from) - 7 * DAY));
        const pct = /per usd|brl|mxn/i.test(s.unit || "");
        for (let i = 1; i < h.length; i++) if (h[i][0] >= from) m[h[i][0]] = pct ? 100 * Math.log(h[i][1] / h[i - 1][1]) : h[i][1] - h[i - 1][1];
        return m;
      });
      const corr = (a, b) => { const ks = Object.keys(a).filter((k) => k in b); if (ks.length < 20) return [null, ks.length];
        const x = ks.map((k) => a[k]), y = ks.map((k) => b[k]), mx = x.reduce((p, v) => p + v, 0) / x.length, my = y.reduce((p, v) => p + v, 0) / y.length;
        let sxy = 0, sxx = 0, syy = 0; for (let i = 0; i < x.length; i++) { sxy += (x[i] - mx) * (y[i] - my); sxx += (x[i] - mx) ** 2; syy += (y[i] - my) ** 2; }
        return [sxx && syy ? sxy / Math.sqrt(sxx * syy) : null, ks.length]; };
      const n = ok.length, grid = el("div", { class: "heat", style: `grid-template-columns: 44px repeat(${n}, minmax(30px, 1fr))` });
      grid.appendChild(el("span"));
      ok.forEach(({ h }) => grid.appendChild(el("span", { class: "hh", title: h[2] }, h[1])));
      ok.forEach(({ h }, i) => {
        grid.appendChild(el("span", { class: "hh r", title: h[2] }, h[1]));
        ok.forEach(({ h: h2 }, j) => {
          const [r, k] = i === j ? [1, null] : corr(ch[i], ch[j]);
          const a = r == null ? 0 : Math.abs(r);
          grid.appendChild(el("span", { class: "hc" + (a > 0.6 ? " strong" : ""), tabindex: 0, title: h[2] + " vs " + h2[2] + (r == null ? ": not enough common days" : ": " + fmt(r, 2) + (k ? " over " + k + " days" : "")),
            style: r == null ? "" : `background: color-mix(in srgb, var(--accent) ${Math.round(a * 85)}%, var(--surface))` }, r == null ? "–" : (r < 0 ? "−" : "") + fmt(Math.abs(r), 2).replace(/^0/, "")));
        });
      });
      return el("article", { class: "card" }, el("h2", {}, "Which instruments have moved together over the last 3 months?"),
        el("div", { class: "q" }, "Correlation of daily changes, " + from + " to " + end + " (% for currencies, bp for yields). Darker = stronger link, either sign."),
        el("div", { class: "scroll" }, grid),
        el("p", { class: "tiny" }, "1.00 = always move the same way, −1.00 = always opposite, 0 = unrelated. DI tenors and the Brazil 10-year are Tesouro proxies. Left out: the OAT-Bund spread (monthly until Webstat is set up) and the Mexico 10-year (auction yields only)."),
        meta({ source: "stored daily series", as_of: end, evidence: { badge: "context", reason: "Descriptive; correlations change over time." } }, { noId: true }));
    });
  }

  // ---------------- Calendar timeline ----------------
  const TYPE = { rates: ["Monetary policy", "var(--t-mon)"], fiscal: ["Fiscal and ratings", "var(--t-fis)"], ratings: ["Fiscal and ratings", "var(--t-fis)"],
    election: ["Elections and politics", "var(--t-pol)"], politics: ["Elections and politics", "var(--t-pol)"] };
  const typeOf = (t) => TYPE[t] || ["Other (trade, surveys)", "var(--cat-0)"];
  function timelineCard(cal) {
    return need().then(() => {
      const ns = C().ns, today = Date.parse(T.todayISO()), end = today + 365 * DAY;
      const rows = [["FR", "France"], ["BR", "Brazil"], ["MX", "Mexico"], ["GLOBAL", "Global"]];
      const evs = cal.events.filter((e) => { const t = Date.parse(e.date); return t >= today && t <= end && e.importance >= 2; });
      const W = 760, L = 70, R = 12, RH = 46, TOP = 22, H = TOP + rows.length * RH + 8;
      const X = (t) => L + ((t - today) / (end - today)) * (W - L - R);
      const svg = ns("svg", { viewBox: `0 0 ${W} ${H}`, role: "img", "aria-label": "12-month catalyst timeline", style: `min-width:${W}px` });
      for (let m = 0; m <= 12; m++) {
        const d = new Date(today); d.setUTCDate(1); d.setUTCMonth(d.getUTCMonth() + m); const t = d.getTime(); if (t < today || t > end) continue;
        svg.append(...nn(ns("line", { x1: X(t), x2: X(t), y1: TOP - 4, y2: H - 6, stroke: "var(--grid)" }),
          ns("text", { x: X(t) + 3, y: 12, class: "lbl-t" }, d.toLocaleDateString("en-GB", { month: "short", timeZone: "UTC" }) + (d.getUTCMonth() === 0 ? " '" + String(d.getUTCFullYear()).slice(2) : ""))));
      }
      rows.forEach(([code, name], i) => {
        const cy = TOP + i * RH + RH / 2;
        svg.append(...nn(ns("text", { x: 0, y: cy + 4, class: "lbl-t", "font-weight": 700, fill: "var(--ink-" + code + ", var(--text-2))" }, name), ns("line", { x1: L, x2: W - R, y1: cy, y2: cy, stroke: "var(--axis)" })));
        const mine = evs.filter((e) => e.country === code).sort((a, b) => a.importance - b.importance);
        const used = {};
        mine.forEach((e) => {
          const x = X(Date.parse(e.date)), slot = Math.round(x / 8); used[slot] = (used[slot] || 0) + 1;
          const yy = cy + ((used[slot] - 1) % 3 - (used[slot] > 1 ? 1 : 0)) * 9, r = e.importance >= 3 ? 7 : 4.5;
          const [, col] = typeOf(e.type), ua = T.underAttended(e);
          const g = ns("a", { href: "#calendar/12m?ev=" + encodeURIComponent(e.id), "aria-label": e.date + " " + e.title + (ua ? " (under-attended)" : "") },
            ns("title", {}, e.date + " · " + e.title + (ua ? " · under-attended" : "")),
            ns("circle", { cx: x, cy: yy, r: 12, fill: "transparent" }),
            ua ? ns("circle", { cx: x, cy: yy, r: r + 4, fill: "none", stroke: "var(--warn)", "stroke-width": 2.5 }) : null,
            ns("circle", { cx: x, cy: yy, r, fill: col, stroke: "var(--surface)", "stroke-width": 2 }));
          svg.appendChild(g);
        });
      });
      svg.appendChild(ns("line", { x1: L, x2: L, y1: TOP - 4, y2: H - 6, stroke: "var(--text-2)", "stroke-width": 1.5 }));
      const ua = evs.filter(T.underAttended).length;
      const seen = {}; evs.forEach((e) => { seen[typeOf(e.type)[0]] = typeOf(e.type)[1]; });
      return el("article", { class: "card" }, el("h2", {}, "When are the next 12 months' catalysts, and which are under-attended?"),
        el("div", { class: "q" }, evs.length + " events of importance 2-3; " + ua + " under-attended (amber ring). Bigger dot = importance 3. Tap a dot to open it in the list."),
        el("div", { class: "scroll" }, svg),
        el("div", { class: "legend" }, ...Object.entries(seen).map(([k, c]) => el("span", {}, el("i", { style: "background:" + c + ";border-radius:50%" }), k)), el("span", {}, el("i", { class: "ring" }), "under-attended")),
        meta({ source: "catalyst calendar", as_of: cal.generated_at, evidence: { badge: "context", reason: "Dates and importance; attention from GDELT (see the list)." } }, { noId: true }));
    });
  }

  T.teach = { fxTrade, spreadTrade, driversCard, waterfallCard, whatIfCard, eventStudyCard, systematicCard, mapCard, heatmapCard, timelineCard };
})();
