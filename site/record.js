/* Record: paper book (Portfolio), judgements, track record, monthly reviews and journal. Loaded after terminal.js; uses its helpers via window.TERM. */
(function () {
  "use strict";
  const T = window.TERM;
  const nn = T.nn;
  const { el, fmt, signed, meta, getJSON } = T;
  const R = { tab: "portfolio", book: null, judge: null, journal: null, err: null };
  const CTX = { badge: "context", reason: "Your own paper book: shown for record-keeping, not a signal." };
  const money = (v) => v == null ? "–" : (v < 0 ? "−$" : "$") + fmt(Math.abs(v), 0);
  const pctS = (p) => p == null ? "–" : Math.round(100 * p) + "%";

  function load() {
    if (R.book || R.err) return Promise.resolve();
    return Promise.all([getJSON("data/book/state.json"), getJSON("data/book/judgements.json"), getJSON("data/book/journal.json")])
      .then(([b, j, n]) => { R.book = b; R.judge = j; R.journal = n; })
      .catch((e) => { R.err = String(e); });
  }

  function stat(label, value, m, cls) {
    return el("div", { class: "h" }, el("div", { class: "v num " + (cls || "") }, value), el("div", { class: "k" }, label), m ? meta(m, { noId: true }) : null);
  }

  function tableOf(head, rows) {
    const t = el("table", {}, el("thead", {}, el("tr", {}, ...head.map((h) => el("th", { class: h.r ? "r" : "" }, h.t || h)))));
    const tb = el("tbody"); rows.forEach((r) => tb.appendChild(r)); t.appendChild(tb);
    return el("div", { class: "scroll" }, t);
  }

  function portfolio() {
    const b = R.book, f = el("div");
    const m = { source: "paper book (data/book/state.json)", as_of: b.as_of, evidence: CTX };
    f.append(...nn(el("div", { class: "row" }, T.tradeLink("USDBRL", null, "Size and open a trade", "primary"), T.formBtn("Close trade", "close-trade", {}),
      el("span", { class: "tiny" }, "Trades are submitted as GitHub forms; entry and exit are the next close after you submit."))));
    const e = b.equity, s = b.stats, dd = e.worst_drawdown;
    f.append(...nn(el("article", { class: "card feature", style: "margin-top:10px" }, el("div", { class: "hero" },
      stat("equity", money(e.current), m), stat("P&L since " + b.start_date, money(e.pnl_usd) + " (" + signed(e.return_pct, 2) + "%)", m, e.pnl_usd > 0 ? "up" : e.pnl_usd < 0 ? "down" : ""),
      stat("worst drawdown", fmt(dd.pct, 2) + "%", Object.assign({}, m, { as_of: dd.to || b.as_of })),
      stat("risk at stake (to stops)", money(b.risk_at_stake_usd) + (b.risk_at_stake_pct != null ? " · " + fmt(b.risk_at_stake_pct, 2) + "%" : ""), m),
      stat("hit rate", s.hit_rate_pct == null ? "–" : fmt(s.hit_rate_pct, 0) + "%", m),
      stat("avg win / avg loss", money(s.avg_win_usd) + " / " + money(s.avg_loss_usd), m),
      stat("open · pending · closed", s.n_open + " · " + s.n_pending + " · " + s.n_closed, m)))));
    const vg = el("div", { class: "grid wide", style: "margin-top:12px" });
    vg.append(...nn(equityCard(b, m), exposureCard(b, m), versusCard(b)));
    f.append(...nn(vg));

    const trades = b.trades || [];
    const open = trades.filter((t) => t.status === "open");
    f.append(...nn(el("div", { class: "sec" }, el("h2", {}, "Open positions"))));
    if (!open.length) f.append(...nn(el("div", { class: "empty" }, "No open positions.")));
    else f.append(...nn(el("article", { class: "card" }, tableOf(["trade", "instrument", "entry", "mark", { t: "notional", r: 1 }, { t: "P&L (price / carry / cost)", r: 1 }, { t: "total", r: 1 }, { t: "risk to stop", r: 1 }, "flags", ""],
      open.map((t) => el("tr", {},
        el("td", {}, el("a", { href: t.open.issue_url, target: "_blank", rel: "noopener" }, t.trade_id)),
        el("td", {}, t.open.direction + " " + t.open.instrument, el("div", { class: "tiny" }, "stop " + t.open.stop + " · target " + (t.open.target ?? "–") + " · horizon " + t.open.horizon),
          T.lazy("lines", () => T.need("econ").then(() => T.econ.exposureFor(t.trade_id)))),
        el("td", { class: "num" }, String(t.fill.entry_value), el("div", { class: "tiny" }, t.fill.entry_date)),
        el("td", { class: "num" }, String(t.mark.value), el("div", { class: "tiny" }, el("span", { class: "dot " + T.freshness(t.mark.date).cls }), " " + t.mark.date)),
        el("td", { class: "r num" }, money(t.fill.notional_usd)),
        el("td", { class: "r num small" }, money(t.pnl.price) + " / " + money(t.pnl.carry) + " / " + money(t.pnl.cost)),
        el("td", { class: "r num " + (t.pnl.total > 0 ? "up" : t.pnl.total < 0 ? "down" : "") }, el("b", {}, money(t.pnl.total))),
        el("td", { class: "r num" }, money(t.risk_to_stop_now)),
        el("td", { class: "small" }, ...(t.flags || []).map((x) => el("div", { class: "chip flag", style: "margin:1px 0" }, x)), ...(t.fill.warnings || []).map((x) => el("div", { class: "tiny" }, "⚠ " + x))),
        el("td", {}, t.close_request ? el("span", { class: "tiny" }, "closing") : T.formBtn("Close", "close-trade", { trade_id: t.trade_id, title: "[Close trade] " + t.trade_id }, "small"))))))));

    const pending = trades.filter((t) => t.status === "pending");
    if (pending.length) f.append(...nn(el("div", { class: "sec" }, el("h2", {}, "Awaiting the next close")), el("article", { class: "card" }, tableOf(["trade", "instrument", "submitted", { t: "est. notional", r: 1 }, { t: "est. risk to stop", r: 1 }, "notes"],
      pending.map((t) => { const est = t.open.estimate_at_submission || {}; return el("tr", {}, el("td", {}, el("a", { href: t.open.issue_url, target: "_blank", rel: "noopener" }, t.trade_id)), el("td", {}, t.open.direction + " " + t.open.instrument),
        el("td", { class: "small" }, t.open.submitted_at.replace("T", " ").slice(0, 16)), el("td", { class: "r num" }, money(est.notional_usd)), el("td", { class: "r num" }, money(est.risk_to_stop_usd) + (est.risk_pct_of_equity != null ? " (" + fmt(est.risk_pct_of_equity, 1) + "%)" : "")),
        el("td", { class: "tiny" }, (t.open.warnings || []).join(" "))); })))));

    const closed = trades.filter((t) => t.status === "closed");
    f.append(...nn(el("div", { class: "sec" }, el("h2", {}, "Closed trades"))));
    if (!closed.length) f.append(...nn(el("div", { class: "empty" }, "None yet.")));
    else f.append(...nn(el("article", { class: "card" }, tableOf(["trade", "instrument", "entry", "exit", "reason", { t: "P&L", r: 1 }, "post-mortem"],
      closed.map((t) => el("tr", {}, el("td", {}, el("a", { href: t.open.issue_url, target: "_blank", rel: "noopener" }, t.trade_id)), el("td", {}, t.open.direction + " " + t.open.instrument),
        el("td", { class: "num small" }, t.fill.entry_value + " · " + t.fill.entry_date), el("td", { class: "num small" }, t.exit.exit_value + " · " + t.exit.exit_date), el("td", { class: "small" }, t.exit.reason),
        el("td", { class: "r num " + (t.pnl.total > 0 ? "up" : "down") }, el("b", {}, money(t.pnl.total))), el("td", { class: "small" }, ((t.close_request || {}).postmortem || []).join(" / "))))))));
    const rej = trades.filter((t) => t.status === "rejected");
    if (rej.length) f.append(...nn(el("details", { style: "margin-top:8px" }, el("summary", {}, rej.length + " rejected trade forms"), el("ul", { class: "small" }, ...rej.map((t) => el("li", {}, el("a", { href: t.open.issue_url, target: "_blank", rel: "noopener" }, t.trade_id), ": " + (t.open.errors || []).join("; ")))))));

    // systematic
    const sy = b.systematic || {};
    f.append(...nn(el("div", { class: "sec" }, el("h2", {}, "Systematic algorithm (em-macro)"), sy.source ? el("a", { class: "small", href: "https://github.com/EthanC100/em-macro/tree/main/results/systematic", target: "_blank", rel: "noopener" }, "source") : null)));
    if (!sy.available) f.append(...nn(el("div", { class: "empty" }, sy.message || "Not available.")));
    else {
      const sm = { source: "em-macro results/systematic", source_url: "https://github.com/EthanC100/em-macro/tree/main/results/systematic", as_of: sy.as_of, evidence: { badge: "tested_no_lead", reason: "em-macro §10: frozen 2005-2019 design, 2020+ test +6.0% a year, Sharpe 0.65; a strategy test, not a lead test of these numbers." } };
      const eqS = sy.since_start.length ? sy.since_start[sy.since_start.length - 1][1] : null;
      f.append(...nn(el("article", { class: "card" }, el("div", { class: "hero" },
        stat("paper equity since " + b.start_date.slice(0, 7) + " (scaled to $" + fmt(b.starting_capital_usd / 1000, 0) + "k)", eqS == null ? "no month yet" : money(eqS), sm),
        stat("cumulative since 2006", fmt(sy.full_history[sy.full_history.length - 1][1], 3) + "×", sm), stat("latest sample label", sy.latest_sample || "–", sm)),
        el("div", { class: "tiny" }, sy.note),
        el("h3", {}, "How has the strategy's cumulative net return grown since 2006 (×)?"),
        T.lazy("block", () => T.need("charts").then(() => T.charts.timeChart({ panels: [{ title: "cumulative net (×)", lines: [{ label: "systematic", points: sy.full_history.map((r) => [r[0] + "-01", r[1]]), color: "var(--cat-1)" }], fmt: (v) => fmt(v, 2), height: 150 }] }))),
        el("div", { class: "small" }, "Latest: ", el("b", {}, fmt(sy.full_history[sy.full_history.length - 1][1], 3) + "×"), " at " + sy.full_history[sy.full_history.length - 1][0] + "."),
        meta(sm, { noId: true })),
        T.lazy("block", () => T.need("teach").then(() => T.teach.systematicCard()))));
    }
    // buy and hold
    const bh = b.benchmarks || [];
    f.append(...nn(el("div", { class: "sec" }, el("h2", {}, "Buy-and-hold of each instrument"), el("span", { class: "tiny" }, "$100k notional, long as quoted, with carry, no costs"))));
    f.append(...nn(el("article", { class: "card" }, tableOf(["instrument", "position", { t: "since " + b.start_date, r: 1 }, { t: "last 12 months", r: 1 }],
      bh.map((r) => el("tr", {}, el("td", {}, r.name, r.proxy ? el("span", { class: "chip est", style: "margin-left:4px" }, "proxy") : null), el("td", { class: "small" }, r.description),
        el("td", { class: "r num" }, r.since_start ? signed(r.since_start.return_pct, 2) + "%" : "–", r.since_start ? el("div", { class: "tiny" }, r.since_start.from + " → " + r.since_start.to) : null),
        el("td", { class: "r num" }, r.last_12m ? signed(r.last_12m.return_pct, 2) + "%" : "–", r.last_12m ? el("div", { class: "tiny" }, r.last_12m.from + " → " + r.last_12m.to) : null)))),
      meta({ source: "stored daily closes", as_of: b.as_of, evidence: { badge: "context", reason: "Benchmarks for the paper book." } }, { noId: true }))));
    f.append(...nn(el("details", { style: "margin-top:10px" }, el("summary", {}, "Assumptions (data/book/config.yaml)"), el("ul", { class: "small muted" }, ...(b.assumptions || []).map((a) => el("li", {}, a))),
      tableOf(["code", "instrument", "series", "duration", "round-trip cost", "close (UTC)"], Object.entries(b.instruments).map(([k, i]) => el("tr", {}, el("td", {}, k), el("td", {}, i.name, i.low_frequency ? el("span", { class: "chip est", style: "margin-left:4px" }, "low frequency") : null),
        el("td", { class: "small" }, i.series + (i.proxy ? " (proxy)" : ""), i.degraded ? el("a", { class: "chip deg", style: "margin-left:4px", href: "#status", title: i.degraded.effect }, "degraded") : null), el("td", {}, i.duration == null ? "–" : String(i.duration)), el("td", {}, i.cost + " " + i.cost_unit), el("td", {}, i.close_utc || "–")))))));
    return f;
  }


  // ---------------- portfolio visuals ----------------
  function drawdowns(curve) {
    const out = []; let peak = -Infinity, start = null;
    curve.forEach(([d, v], i) => {
      if (v >= peak) { if (start) out.push([start, d]); peak = v; start = null; }
      else if (!start) start = curve[i - 1][0];
    });
    if (start) out.push([start, curve[curve.length - 1][0]]);
    return out;
  }
  function equityCard(b, m) {
    const c = b.equity.curve;
    const card = el("article", { class: "card" }, el("h2", {}, "How has the paper book's equity moved, and where were the drawdowns?"));
    if (c.length < 2) { card.append(...nn(el("p", { class: "small" }, "Equity is ", el("b", {}, money(c.length ? c[c.length - 1][1] : b.starting_capital_usd)), " on " + (c.length ? c[c.length - 1][0] : b.start_date) + ". The curve appears after the second daily mark."), meta(m))); return card; }
    const dd = drawdowns(c);
    card.append(...nn(T.lazy("block", () => T.need("charts").then(() => T.charts.timeChart({ panels: [{ title: "equity (USD)", lines: [{ label: "equity", points: c, color: "var(--cat-1)" }], shade: dd, fmt: (v, full) => full ? money(v) : "$" + fmt(v / 1000, 1) + "k", height: 170 }] }))),
      el("div", { class: "legend" }, el("span", {}, el("i", { style: "background:var(--bad-soft)" }), "drawdown (below the previous peak)")),
      el("p", { class: "small" }, "Now ", el("b", {}, money(c[c.length - 1][1])), "; worst drawdown ", el("b", {}, fmt(b.equity.worst_drawdown.pct, 2) + "%"), "."), meta(m)));
    return card;
  }
  function exposureCard(b, m) {
    const open = (b.trades || []).filter((t) => t.status === "open");
    const card = el("article", { class: "card" }, el("h2", {}, "Where is the book's money at risk, by country and instrument?"));
    if (!open.length) { card.append(...nn(el("p", { class: "small" }, "No open positions, so no exposure: ", el("b", {}, "$0"), " at risk."), meta(m))); return card; }
    const byC = {}, byI = {};
    open.forEach((t) => { const i = t.open.instrument, ctry = (b.instruments[i] || {}).country || "?", sgn = t.fill.direction_sign;
      byC[ctry] = (byC[ctry] || 0) + (t.risk_to_stop_now || 0); byI[i] = (byI[i] || 0) + sgn * t.fill.notional_usd; });
    card.append(...nn(T.lazy("lines", () => T.need("charts").then(() => el("div", {},
      el("div", { class: "k small" }, "risk to stop by country (USD)"), T.charts.bars(Object.entries(byC).map(([k, v]) => ({ label: T.COUNTRY[k] || k, value: v })), { fmt: money }),
      el("div", { class: "k small" }, "net notional by instrument (USD, + = long as quoted)"), T.charts.bars(Object.entries(byI).map(([k, v]) => ({ label: k, value: v })), { fmt: money })))), meta(m)));
    return card;
  }
  function versusCard(b) {
    const sy = b.systematic || {}, card = el("article", { class: "card" }, el("h2", {}, "Is my paper book beating em-macro's systematic strategy (both 100 at my start)?"));
    if (!sy.available) { card.append(...nn(el("p", { class: "small" }, sy.message || "Systematic results not available."))); return card; }
    const start = b.start_date.slice(0, 7);
    const sys = sy.full_history.filter((r) => r[0] >= start);
    const mine = b.equity.curve;
    if (sys.length < 1 || mine.length < 2) {
      const last = sy.full_history[sy.full_history.length - 1];
      card.append(...nn(el("p", { class: "small" }, "The comparison starts once both have results after " + b.start_date + ". Book: ", el("b", {}, money(b.equity.current)), " (" + mine.length + " daily mark" + (mine.length === 1 ? "" : "s") + "). Systematic: latest month ",
        el("b", {}, last[0]), " (", el("b", {}, fmt(last[1], 3) + "×"), " since 2006), before your start."), el("div", { class: "tiny" }, "em-macro publishes monthly; the first month after your start appears early next month.")));
      return card;
    }
    const base = sy.full_history.filter((r) => r[0] < start).pop() || sys[0];
    const sysIdx = [[b.start_date, 100]].concat(sys.map((r) => [r[0] + "-28", 100 * r[1] / base[1]]));
    const mineIdx = mine.map(([d, v]) => [d, 100 * v / b.starting_capital_usd]);
    card.append(...nn(T.lazy("block", () => T.need("charts").then(() => T.charts.timeChart({ panels: [{ title: "index, 100 at " + b.start_date, lines: [{ label: "my book", points: mineIdx, color: "var(--cat-1)" }, { label: "systematic", points: sysIdx, color: "var(--cat-2)" }], fmt: (v) => fmt(v, 1), height: 170 }] }))),
      el("div", { class: "legend" }, el("span", {}, el("i", { class: "ln", style: "background:var(--cat-1)" }), "my book " + fmt(mineIdx[mineIdx.length - 1][1], 1)), el("span", {}, el("i", { class: "ln", style: "background:var(--cat-2)" }), "systematic " + fmt(sysIdx[sysIdx.length - 1][1], 1))),
      el("div", { class: "tiny" }, "Systematic is monthly (net of its costs, run at 10% volatility); the book is daily. Different risk levels: compare direction more than size.")));
    return card;
  }
  function brierCard(j) {
    const res = (j.questions || []).filter((q) => q.resolution).map((q) => { const f = q.forecasts[q.forecasts.length - 1]; return { d: q.resolution.date, me: f.brier, mk: f.market_brier }; }).filter((x) => x.me != null).sort((a, b) => a.d < b.d ? -1 : 1);
    const card = el("article", { class: "card" }, el("h2", {}, "Are my forecasts getting better than the market's over time (Brier score, lower is better)?"));
    if (res.length < 2) { card.append(...nn(el("p", { class: "small" }, res.length + " resolved question" + (res.length === 1 ? "" : "s") + " so far" + (res.length ? ": my Brier " + fmt(res[0].me, 3) + (res[0].mk != null ? ", market " + fmt(res[0].mk, 3) : "") : "") + ". The running average appears after two resolutions."))); return card; }
    let sm = 0, sk = 0, nk = 0; const me = [], mk = [];
    res.forEach((r, i) => { sm += r.me; me.push([r.d, sm / (i + 1)]); if (r.mk != null) { sk += r.mk; nk++; mk.push([r.d, sk / nk]); } });
    card.append(...nn(T.lazy("block", () => T.need("charts").then(() => T.charts.timeChart({ panels: [{ title: "running average Brier score", lines: [{ label: "mine", points: me, color: "var(--cat-1)" }].concat(mk.length > 1 ? [{ label: "market at entry", points: mk, color: "var(--cat-2)" }] : []), fmt: (v) => fmt(v, 3), zero: true, height: 160 }] }))),
      el("div", { class: "small" }, "Now: mine ", el("b", {}, fmt(me[me.length - 1][1], 3)), mk.length ? [", market ", el("b", {}, fmt(mk[mk.length - 1][1], 3))] : "", " over " + res.length + " resolved questions.")));
    return card;
  }

  // ---------------- trade sizing (#trade/<INSTRUMENT>) ----------------
  T.pageTrade = function (code, params) {
    const f = el("div"), body = el("div", {}, T.skel("lines"));
    f.append(...nn(el("div", { class: "sec" }, el("h1", {}, "Size a trade"), el("a", { class: "small", href: "#record/portfolio" }, "portfolio →")), body));
    load().then(() => T.need("charts")).then(() => {
      if (R.err) throw new Error("book data not found: " + R.err);
      const b = R.book, codes = Object.keys(b.instruments); code = codes.includes((code || "").toUpperCase()) ? code.toUpperCase() : codes[0];
      const st = { code, dir: params.get("direction") || "long", entry: null, stop: params.get("stop") ? +params.get("stop") : null, target: params.get("target") ? +params.get("target") : null,
        risk: 1, days: params.get("horizon") ? Math.max(1, T.daysUntil(params.get("horizon"))) : 30, link: params.get("link") || "" };
      const out = el("div"), form = el("div", { class: "calc" });
      const inst = () => b.instruments[st.code];
      const rates = {};
      const rate = (id) => id ? (rates[id] = rates[id] || T.loadSeries(id).then((s) => { for (let i = s.history.length - 1; i >= 0; i--) if (typeof s.history[i][1] === "number") return s.history[i][1]; return null; })) : Promise.resolve(null);
      function durationOf(i, entry) {
        if (i.kind === "fx") return null;
        if (i.duration === "zero_coupon") return Math.max(0, (Date.parse(i.maturity) - Date.now()) / 864e5 / 365.25) / (1 + entry / 100);
        return +i.duration;
      }
      const money = (v) => v == null ? "–" : (v < 0 ? "−$" : "+$") + fmt(Math.abs(v), 0);
      function compute() {
        const i = inst(), d = st.dir === "long" ? 1 : -1, e = st.entry, eq = b.equity.current;
        if (e == null || st.stop == null) { out.replaceChildren(...nn(el("p", { class: "small" }, "Enter a stop to size the trade."))); return; }
        const g = d * i.favourable, errs = [];
        if (g * (e - st.stop) <= 0) errs.push("The stop is on the winning side: for a " + st.dir + " " + st.code + " it must be " + (g > 0 ? "below" : "above") + " the entry.");
        if (st.target != null && g * (st.target - e) <= 0) errs.push("The target is on the losing side.");
        const D = durationOf(i, e);
        const unitLoss = i.kind === "fx" ? Math.abs(st.stop - e) / st.stop : D * Math.abs(st.stop - e) / i.scale;
        const costRate = i.kind === "fx" ? i.cost / 100 : D * i.cost / 10000;
        const riskUsd = eq * st.risk / 100, N = riskUsd / (unitLoss + costRate);
        Promise.all([rate(i.rate_usd), rate(i.rate_local)]).then(([ru, rl]) => {
          const carry = i.kind === "fx" && ru != null && rl != null ? d * N * (ru - rl) / 100 * st.days / 360 : 0;
          const price = (lvl) => i.kind === "fx" ? d * N * (lvl - e) / lvl : -d * N * D * (lvl - e) / i.scale;
          const cost = N * costRate;
          const atStop = price(st.stop) + carry - cost, atTarget = st.target == null ? null : price(st.target) + carry - cost;
          const rr = atTarget != null && atStop < 0 ? atTarget / -atStop : null;
          out.replaceChildren(...nn(
            errs.length ? el("div", { class: "err" }, errs.join(" ")) : null,
            el("div", { class: "hero", style: "margin-top:10px" },
              el("div", { class: "h" }, el("div", { class: "v" }, "$" + fmt(N, 0)), el("div", { class: "k" }, "notional to trade")),
              el("div", { class: "h" }, el("div", { class: "v down" }, money(atStop)), el("div", { class: "k" }, "P&L at the stop")),
              el("div", { class: "h" }, el("div", { class: "v up" }, money(atTarget)), el("div", { class: "k" }, "P&L at the target")),
              el("div", { class: "h" }, el("div", { class: "v" }, rr == null ? "–" : fmt(rr, 2) + " : 1"), el("div", { class: "k" }, "reward-to-risk"))),
            el("div", { class: "q", style: "margin-top:10px" }, "What happens at the stop and at the target, after carry and costs?"),
            T.charts.bars([{ label: "Price move to the stop", value: price(st.stop), tone: "down" }, st.target != null ? { label: "Price move to the target", value: price(st.target), tone: "up" } : null,
              i.kind === "fx" ? { label: "Carry over " + st.days + " days (US " + (ru == null ? "–" : fmt(ru, 2)) + "% vs local " + (rl == null ? "–" : fmt(rl, 2)) + "%)", value: carry, tone: carry >= 0 ? "up" : "down" } : null,
              { label: "Round-trip cost (" + i.cost + " " + i.cost_unit + ")", value: -cost, tone: "down" }].filter(Boolean), { fmt: money }),
            el("div", { class: "formula" }, "risk budget = equity $" + fmt(eq, 0) + " × " + st.risk + "% = $" + fmt(riskUsd, 0) + "\n" +
              (i.kind === "fx" ? "loss per $ to stop = |stop − entry| / stop = " + fmt(unitLoss * 100, 3) + "%" : "loss per $ to stop = duration " + fmt(D, 2) + " × |stop − entry| / " + i.scale + " = " + fmt(unitLoss * 100, 3) + "%") +
              "\nnotional = risk budget / (loss per $ + cost per $) = $" + fmt(N, 0)),
            st.risk > b.risk_warning_pct_of_equity ? el("div", { class: "chip warn" }, "⚠ risk above the book's " + b.risk_warning_pct_of_equity + "% warning level") : null,
            el("div", { class: "row", style: "margin-top:10px" }, T.formBtn("Open this trade (GitHub form)", "open-trade", {
              title: "[Open trade] " + st.dir + " " + st.code, instrument: st.code, size: Math.round(N), stop: st.stop, target: st.target, link: st.link,
              horizon: new Date(Date.now() + st.days * 864e5).toISOString().slice(0, 10),
              thesis: "Sized for " + st.risk + "% of equity at risk. Choose direction = " + st.dir + " and size type = Notional (USD)." }, "primary")),
            el("p", { class: "tiny" }, "Pre-filled: instrument, notional, stop, target, horizon and link. GitHub cannot pre-fill dropdowns, so pick the direction (" + st.dir + ") and 'Notional (USD)' on the form. Entry will be the next close after you submit, not the level here."),
            meta({ source: "book settings and " + (inst().series || ""), as_of: inst().date, evidence: { badge: "context", reason: "Arithmetic with the book's own P&L rules." }, degraded: inst().degraded }, { noId: true })));
        });
      }
      const num = (label, key, step) => el("label", {}, label, el("input", { type: "number", step: step || "any", inputmode: "decimal", value: st[key] == null ? "" : String(st[key]), oninput: (e) => { st[key] = e.target.value === "" ? null : parseFloat(e.target.value); compute(); } }));
      function build() {
        const i = inst(); st.entry = i.value;
        const sel = el("select", { onchange: (e) => { st.code = e.target.value; st.stop = null; st.target = null; build(); } }, ...codes.map((k) => { const o = el("option", { value: k }, k + " · " + b.instruments[k].name); if (k === st.code) o.selected = true; return o; }));
        const dir = el("select", { onchange: (e) => { st.dir = e.target.value; compute(); } }, ...["long", "short"].map((k) => { const o = el("option", { value: k }, k + (i.kind === "fx" ? (k === "long" ? " (USD up)" : " (USD down)") : (k === "long" ? " (gains if the yield falls)" : " (gains if the yield rises)"))); if (k === st.dir) o.selected = true; return o; }));
        form.replaceChildren(...nn(el("label", {}, "instrument", sel), el("label", {}, "direction", dir), num("entry (latest close " + fmt(i.value, i.kind === "fx" ? 4 : 2) + ")", "entry"),
          num("stop", "stop"), num("target", "target"), num("risk, % of equity", "risk", "0.25"), num("holding period, days", "days", "1")));
        compute();
      }
      body.replaceWith(el("article", { class: "card" }, el("h2", {}, "How big should this trade be, and what do I make or lose at the stop and the target?"),
        el("p", { class: "small" }, "Choose how much of the book you are willing to lose if the stop is hit. The size follows from the distance to the stop, the instrument's sensitivity and the cost."),
        form, out, b.instruments[st.code].kind === "fx" ? T.how("how a currency trade makes money", () => T.need("teach").then(() => T.teach.fxTrade(st.code === "USDMXN" ? "USDMXN" : "USDBRL")))
          : T.how("how a spread trade makes money", () => T.need("teach").then(() => T.teach.spreadTrade()))));
      build();
    }).catch((err) => body.replaceWith(el("div", { class: "err" }, String(err.message || err))));
    return f;
  };

  function calibration(cal) {
    const NS = "http://www.w3.org/2000/svg", W = 300, H = 280, P = 34;
    const ns = (t, a) => { const n = document.createElementNS(NS, t); for (const [k, v] of Object.entries(a || {})) n.setAttribute(k, v); return n; };
    const svg = ns("svg", { viewBox: `0 0 ${W} ${H}`, style: "max-width:360px;width:100%" });
    const X = (v) => P + v * (W - 2 * P), Y = (v) => H - P - v * (H - 2 * P);
    const g = ns("g", { class: "gridl" }); for (let i = 0; i <= 4; i++) { g.appendChild(ns("line", { x1: X(i / 4), x2: X(i / 4), y1: Y(0), y2: Y(1) })); g.appendChild(ns("line", { x1: X(0), x2: X(1), y1: Y(i / 4), y2: Y(i / 4) })); }
    svg.append(...nn(g, ns("line", { x1: X(0), y1: Y(0), x2: X(1), y2: Y(1), stroke: "var(--axis)", "stroke-width": 1.5 })));
    const ax = ns("g", { class: "axis" }); for (let i = 0; i <= 4; i++) { const a = ns("text", { x: X(i / 4), y: H - P + 16, "text-anchor": "middle" }); a.textContent = i * 25 + "%"; ax.appendChild(a); const b = ns("text", { x: P - 6, y: Y(i / 4) + 4, "text-anchor": "end" }); b.textContent = i * 25 + "%"; ax.appendChild(b); }
    svg.appendChild(ax);
    const maxN = Math.max(...cal.map((c) => c.n));
    cal.forEach((c) => { const d = ns("circle", { cx: X(c.mean_forecast), cy: Y(c.observed), r: 4 + 8 * Math.sqrt(c.n / maxN), fill: "var(--cat-1)", class: "dotm" }); const t = ns("title"); t.textContent = c.bin + ": n=" + c.n + ", forecast " + pctS(c.mean_forecast) + ", observed " + pctS(c.observed); d.appendChild(t); svg.appendChild(d); });
    return el("div", { class: "chart" }, svg);
  }

  function judgements() {
    const j = R.judge, s = j.summary, f = el("div");
    f.append(...nn(el("div", { class: "row" }, T.formBtn("Full call", "full-call", {}, "primary"), T.formBtn("Quick update", "quick-update", {}), T.formBtn("Resolve", "resolve-question", {}))));
    const m = { source: "judgement records (data/judgements)", as_of: (j.generated_at || "").slice(0, 10), evidence: { badge: "context", reason: "Your own scores." } };
    const vs = (pair, d) => pair ? fmt(pair[0], d) + " vs " + fmt(pair[1], d) + " market" : "–";
    f.append(...nn(el("article", { class: "card", style: "margin-top:10px" }, el("div", { class: "hero" },
      stat("questions · resolved", s.n_questions + " · " + s.n_resolved, m),
      stat("Brier (lower is better)", s.brier_mine == null ? "–" : fmt(s.brier_mine, 3), m), stat("Brier vs market at entry (n=" + s.n_with_market + ")", vs(s.brier_mine_vs_market, 3), m),
      stat("log score (higher is better)", s.log_mine == null ? "–" : fmt(s.log_mine, 3), m), stat("log vs market at entry", vs(s.log_mine_vs_market, 3), m)),
      el("div", { class: "tiny" }, "Scored on the last forecast before resolution, against the market-implied probability recorded when it was submitted. Log score is ln(probability given to the outcome), clipped at 1%."),
      s.calibration ? el("div", {}, el("h3", {}, "Calibration"), calibration(s.calibration)) :
        el("p", { class: "small muted" }, "The calibration chart appears after " + s.calibration_min + " resolved questions (" + s.n_resolved + " so far)."))));
    f.append(...nn(el("div", { style: "margin-top:12px" }, brierCard(j))));
    const qs = j.questions || [];
    f.append(...nn(el("div", { class: "sec" }, el("h2", {}, "Calls"))));
    if (!qs.length) f.append(...nn(el("div", { class: "empty" }, "No calls yet. Use Full call, or Make a call on a calendar event or market.")));
    qs.slice().reverse().forEach((q) => {
      const rows = q.forecasts.map((fc) => el("tr", {}, el("td", { class: "small" }, fc.record + " · " + fc.submitted_at.slice(0, 10)),
        el("td", { class: "r num" }, el("b", {}, pctS(fc.prob))), el("td", { class: "r num" }, fc.market ? pctS(fc.market.prob) : "–", fc.market ? el("div", { class: "tiny" }, fc.market.source) : null),
        el("td", { class: "r num" }, fc.ai ? pctS(fc.ai.prob) : "–"), el("td", { class: "r num" }, fc.brier == null ? "–" : fmt(fc.brier, 3) + (fc.market_brier != null ? " / " + fmt(fc.market_brier, 3) : "")),
        el("td", { class: "small" }, fc.what_changed || "")));
      f.append(...nn(el("article", { class: "card", style: "margin-bottom:8px" }, el("div", { class: "row", style: "justify-content:space-between" },
        el("div", {}, el("b", {}, q.question), el("div", { class: "tiny" }, q.key + (q.question_id ? " · " + q.question_id : "") + " · resolves " + (q.resolution_date || "–"))),
        q.resolution ? el("span", { class: "chip" }, "resolved " + (q.resolution.outcome ? "YES" : "NO")) : T.formBtn("Quick update", "quick-update", { target: q.key, title: "[Quick update] " + q.key }, "small")),
        tableOf(["record", { t: "mine", r: 1 }, { t: "market at entry", r: 1 }, { t: "AI", r: 1 }, { t: "Brier mine / mkt", r: 1 }, "what changed"], rows),
        q.call ? el("details", {}, el("summary", {}, "call details"), el("div", { class: "small" },
          el("div", {}, "Base rate: " + (q.call.base_rate || "–")), el("div", {}, "Factors: " + q.call.factors.map((x) => x.factor + " (" + x.direction + ", " + x.size + ")").join("; ")),
          el("div", {}, "Scenarios: " + q.call.scenarios.map((x) => x.scenario + " " + x.pct + "%").join(", ")), el("div", {}, "Change my mind: " + q.call.change_mind),
          el("div", {}, "Pre-mortem: " + q.call.premortem), el("div", {}, "Confidence: " + q.call.confidence + (q.call.linked_trade ? " · trade " + q.call.linked_trade : "")))) : null)));
    });
    return f;
  }

  function journal() {
    const items = (R.journal && R.journal.items) || [], f = el("div");
    f.append(...nn(el("p", { class: "small muted" }, items.length + " entries, newest first. Every trade, fill, close request with post-mortem, exit, call, update and resolution; records are never edited after submission.")));
    if (!items.length) f.append(...nn(el("div", { class: "empty" }, "Nothing yet.")));
    const list = el("div", { class: "evlist" });
    items.slice().reverse().forEach((i) => list.appendChild(el("div", { class: "ev" + (i.rejected ? " under" : "") },
      el("div", { class: "date" }, i.at.slice(5, 10), el("small", {}, i.at.slice(0, 4) + " " + i.at.slice(11, 16))),
      el("div", {}, el("div", { class: "title" }, i.kind.replace(/-/g, " ") + " · " + i.id + (i.rejected ? " (rejected)" : "")), el("div", { class: "small" }, i.text),
        i.detail ? el("div", { class: "small muted", style: "white-space:pre-line" }, i.detail) : null,
        i.errors ? el("div", { class: "err" }, i.errors.join("; ")) : null,
        i.market || i.ai ? el("div", { class: "tiny" }, "at entry: market " + (i.market ? pctS(i.market.prob) : "–") + " · AI " + (i.ai ? pctS(i.ai.prob) : "–")) : null),
      el("div", { class: "att" }, i.issue ? el("a", { class: "small", href: "https://github.com/" + ((R.book && R.book.repo) || "EthanC100/forecast-panel") + "/issues/" + i.issue, target: "_blank", rel: "noopener" }, "#" + i.issue) : null))));
    f.appendChild(list);
    return f;
  }


  // ---------------- track record (Phase 5) ----------------
  const withN = (v, n, d) => el("span", { class: "num" }, v == null ? "–" : fmt(v, d == null ? 3 : d), el("span", { class: "tiny" }, " n=" + (n || 0)));
  const NAMES = { me: "Me", ai: "AI (blind)", market: "Market at entry", no_change: "No-change (my first forecast, never updated)", ai_all: "AI on every question it judged" };
  function noisyChip(q) { return q.noisy ? el("span", { class: "chip warn", title: "Fewer than " + q.min_overall + " resolved questions: differences are mostly luck." }, "noisy: " + q.n_resolved + " of " + q.min_overall + " resolved") : null; }
  function groupTable(rows, label) {
    return tableOf([label, { t: "n", r: 1 }, { t: "Brier me", r: 1 }, { t: "market", r: 1 }, { t: "AI", r: 1 }],
      rows.map((g) => el("tr", {}, el("td", {}, g.group), el("td", { class: "r num" }, String(g.n)),
        ...(g.insufficient ? [el("td", { class: "r tiny", colspan: "3" }, "insufficient data (under 10)")] :
          ["me", "market", "ai"].map((w) => el("td", { class: "r" }, withN(g[w].brier, g[w].n)))))));
  }
  function trackRecord() {
    const f = el("div"), body = el("div", {}, T.skel("lines"), T.skel("block")); f.appendChild(body);
    getJSON("data/book/record.json").then((rec) => {
      const q = rec.questions, tr = rec.trades, out = el("div");
      // side by side
      const side = q.side_by_side;
      out.append(...nn(el("article", { class: "card feature" }, el("div", { class: "lbl" }, el("h2", { style: "margin:0" }, "Who forecasts better?"), noisyChip(q)),
        tableOf(["forecaster", { t: "Brier (lower better)", r: 1 }, { t: "log score (higher better)", r: 1 }],
          ["me", "ai", "market", "no_change", "ai_all"].map((w) => el("tr", { class: w === "me" ? "me-row" : "" }, el("td", {}, NAMES[w]),
            el("td", { class: "r" }, withN(side[w].brier, side[w].n)), el("td", { class: "r" }, withN(side[w].log, side[w].n))))),
        q.shared.n ? el("div", { class: "small" }, "On the " + q.shared.n + " questions where all three exist: me " + fmt(q.shared.scores.me.brier, 3) + ", AI " + fmt(q.shared.scores.ai.brier, 3) + ", market " + fmt(q.shared.scores.market.brier, 3) + ".") : null,
        el("div", { class: "tiny" }, "Every probability is scored the same way, on my last forecast before resolution: the AI's blind probability and the market's were recorded at that same moment. " + q.definitions.no_change + " shows whether updating helps. Trades: the systematic algorithm is compared below."),
        q.n_resolved ? null : el("p", { class: "small muted" }, "Nothing has resolved yet. Scores appear as questions resolve (Resolve form, or automatically for markets)."))));
      // skill
      const sk = q.skill;
      out.append(...nn(el("article", { class: "card" }, el("h2", {}, "Skill: telling outcomes apart vs getting the odds right"),
        tableOf(["", { t: "discrimination ↑", r: 1 }, { t: "calibration error ↓", r: 1 }, { t: "AUC", r: 1 }, { t: "n", r: 1 }],
          ["me", "ai", "market"].map((w) => el("tr", {}, el("td", {}, NAMES[w]), el("td", { class: "r num" }, sk[w].n ? fmt(sk[w].discrimination, 3) : "–"),
            el("td", { class: "r num" }, sk[w].n ? fmt(sk[w].calibration_error, 3) : "–"), el("td", { class: "r num" }, sk[w].auc == null ? "–" : fmt(sk[w].auc, 2)), el("td", { class: "r num" }, String(sk[w].n || 0))))),
        el("div", { class: "tiny" }, "Brier = calibration error − discrimination + uncertainty (ten probability bins). Discrimination: how far apart your forecasts are for things that happened and things that did not. Calibration error: how far your 70% calls are from happening 70% of the time. AUC 0.5 = no better than a coin."))));
      out.append(...nn(el("article", { class: "card" }, el("h2", {}, "Where am I good?"),
        el("h3", {}, "By catalyst type"), groupTable(q.by_type, "type"), el("h3", {}, "By my stated confidence"), groupTable(q.by_confidence, "confidence"),
        el("h3", {}, "By lead time (last forecast to resolution)"), groupTable(q.by_lead, "lead time"),
        el("div", { class: "tiny" }, "Groups with fewer than " + q.min_group + " resolved questions show \"insufficient data\"."))));
      const bl = q.blend;
      out.append(...nn(el("article", { class: "card" }, el("h2", {}, "Would a 50/50 blend of me and the AI do better?"),
        bl.ready ? el("div", {}, tableOf(["", { t: "Brier", r: 1 }], ["me", "ai", "blend"].map((w) => el("tr", {}, el("td", {}, w === "blend" ? "50/50 blend" : NAMES[w]), el("td", { class: "r" }, withN(bl[w].brier, bl[w].n))))),
          el("p", { class: "small" }, el("b", {}, "Verdict: "), bl.verdict + "."))
          : el("p", { class: "small" }, "Shown once " + bl.min + " questions that both of us forecast have resolved (" + bl.n_shared + " so far)."))));
      // trades
      const c = tr.closed, o = tr.open;
      const rRow = (lab, x) => el("tr", {}, el("td", {}, lab), el("td", { class: "r" }, withN(x.total_r, x.n, 2)), el("td", { class: "r num" }, x.per_trade_r == null ? "–" : signed(x.per_trade_r, 2)),
        el("td", { class: "r num small" }, ["price", "carry", "cost"].map((k) => (x[k + "_r"] == null ? "–" : signed(x[k + "_r"], 2))).join(" / ")),
        el("td", { class: "r num" }, money(x.total_usd)));
      out.append(...nn(el("article", { class: "card" }, el("h2", {}, "Trades: P&L per unit of risk, after costs"),
        tableOf(["", { t: "total R", r: 1 }, { t: "per trade", r: 1 }, { t: "price / carry / cost (R)", r: 1 }, { t: "$", r: 1 }], [rRow("closed", c), rRow("open (unrealised)", o)]),
        el("div", { class: "tiny" }, "R = P&L ÷ the risk to the stop at entry (costs included). +1R means you made what you had at risk."))));
      const vs = tr.versus;
      out.append(...nn(el("article", { class: "card" }, el("h2", {}, "My book vs the systematic algorithm vs buy-and-hold, since " + tr.start_date),
        tableOf(["", { t: "return", r: 1 }, "detail"], [
          el("tr", {}, el("td", {}, "My book"), el("td", { class: "r num" }, vs.book.return_pct == null ? "–" : signed(vs.book.return_pct, 2) + "%"), el("td", { class: "small" }, vs.book.n_trades + " trades · " + (vs.book.total_r == null ? "–" : signed(vs.book.total_r, 2) + "R"))),
          el("tr", {}, el("td", {}, "Systematic (em-macro)"), el("td", { class: "r num" }, vs.systematic.return_pct == null ? "–" : signed(vs.systematic.return_pct, 2) + "%"), el("td", { class: "small" }, vs.systematic.return_pct == null ? vs.systematic.note : vs.systematic.n_months + " months to " + vs.systematic.to)),
          el("tr", {}, el("td", {}, "Buy-and-hold (equal weight)"), el("td", { class: "r num" }, vs.buy_and_hold.equal_weight_return_pct == null ? "–" : signed(vs.buy_and_hold.equal_weight_return_pct, 2) + "%"), el("td", { class: "small" }, vs.buy_and_hold.n_instruments + " instruments"))]),
        el("details", {}, el("summary", {}, "buy-and-hold by instrument"), tableOf(["instrument", { t: "return", r: 1 }, "from"], vs.buy_and_hold.rows.map((r) => el("tr", {}, el("td", {}, r.code + " (" + r.description + ")"), el("td", { class: "r num" }, r.return_pct == null ? "–" : signed(r.return_pct, 2) + "%"), el("td", { class: "tiny" }, r.from || "–"))))),
        el("div", { class: "tiny" }, vs.note))));
      const hitT = (rows, label) => rows.length ? tableOf([label, { t: "n", r: 1 }, { t: "hit rate", r: 1 }, { t: "avg win", r: 1 }, { t: "avg loss", r: 1 }, { t: "avg R", r: 1 }],
        rows.map((g) => el("tr", {}, el("td", {}, g.group), el("td", { class: "r num" }, String(g.n)), ...(g.insufficient ? [el("td", { class: "r tiny", colspan: "4" }, "insufficient data (under 10)")] :
          [el("td", { class: "r num" }, g.hit_rate_pct + "%"), el("td", { class: "r num" }, money(g.avg_win_usd)), el("td", { class: "r num" }, money(g.avg_loss_usd)), el("td", { class: "r num" }, signed(g.avg_r, 2))]))))
        : el("p", { class: "small muted" }, "No closed trades yet.");
      out.append(...nn(el("article", { class: "card" }, el("h2", {}, "Hit rate and average win/loss"),
        el("div", { class: "small" }, "All closed trades: ", withN(tr.overall.hit_rate_pct, tr.overall.n, 1), tr.overall.hit_rate_pct == null ? "" : "% hit rate"),
        el("h3", {}, "By instrument"), hitT(tr.by_instrument, "instrument"), el("h3", {}, "By thesis type"), hitT(tr.by_thesis, "thesis type"))));
      out.append(...nn(el("p", { class: "tiny" }, "Rebuilt " + rec.generated_at.replace("T", " ").slice(0, 16) + " UTC after every data run and form.")));
      body.replaceWith(out);
    }).catch((e) => body.replaceWith(el("div", { class: "err" }, "Track record not built yet (" + e.message + ").")));
    return f;
  }

  // ---------------- monthly reviews ----------------
  function md(text) {
    const box = el("div", { class: "md" }), lines = text.split("\n");
    const inline = (s) => { const span = el("span"); span.innerHTML = s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/\*\*(.+?)\*\*/g, "<b>$1</b>").replace(/(^|\W)_(.+?)_(?=\W|$)/g, "$1<i>$2</i>").replace(/\[(.+?)\]\((https?:[^)]+)\)/g, '<a href="$2" target="_blank" rel="noopener">$1</a>'); return span; };
    let list = null, table = null;
    lines.forEach((ln) => {
      if (/^\|/.test(ln)) { if (/^\|[-| ]+\|$/.test(ln)) return; const cells = ln.split("|").slice(1, -1).map((c) => c.trim()); if (!table) { table = el("table"); box.appendChild(el("div", { class: "scroll" }, table)); table.appendChild(el("tr", {}, ...cells.map((c) => el("th", {}, inline(c))))); } else table.appendChild(el("tr", {}, ...cells.map((c) => el("td", {}, inline(c))))); return; }
      table = null;
      const h = ln.match(/^(#{1,3}) (.*)/), li = ln.match(/^\s*(?:- |\d+\. )(.*)/);
      if (li) { if (!list) { list = el(/^\s*\d/.test(ln) ? "ol" : "ul"); box.appendChild(list); } list.appendChild(el("li", {}, inline(li[1]))); return; }
      list = null;
      if (h) box.appendChild(el("h" + (h[1].length + 1), {}, inline(h[2])));
      else if (ln.trim()) box.appendChild(el("p", { class: "small" }, inline(ln)));
    });
    return box;
  }
  function reviews(month) {
    const f = el("div"), body = el("div", {}, T.skel("lines")); f.appendChild(body);
    const repo = (R.book && R.book.repo) || "EthanC100/forecast-panel";
    getJSON("data/book/reviews/index.json").then((ix) => {
      const list = ix.reviews || [];
      if (!list.length) throw new Error("none yet");
      const cur = list.find((r) => r.month === month) || list[0];
      return fetch("data/book/reviews/" + cur.month + ".md", { cache: "no-cache" }).then((r) => r.text()).then((text) => {
        const sel = el("div", { class: "filters" }, ...list.map((r) => el("button", { type: "button", class: r.month === cur.month ? "on" : "", onclick: () => { location.hash = "#record/reviews/" + r.month; } }, r.month)));
        body.replaceWith(el("div", {}, sel, el("article", { class: "card" }, el("div", { class: "row", style: "justify-content:flex-end" },
          el("a", { class: "btn small", href: "https://github.com/" + repo + "/edit/main/" + cur.file, target: "_blank", rel: "noopener" }, "Edit on GitHub")), md(text))));
      });
    }).catch(() => body.replaceWith(el("article", { class: "card" }, el("p", { class: "small" }, "The first draft review is written on the 1st of next month (data/book/reviews/). It is generated once and never overwritten, so edit it on GitHub from your phone."))));
    return f;
  }
  T.remindersCard = function () {
    return getJSON("data/book/reminders.json").then((r) => {
      const open = r.open || [];
      if (!open.length) return null;
      return el("article", { class: "card" }, el("h2", {}, "Reminders (" + open.length + ")"),
        el("ul", { class: "small" }, ...open.slice(0, 8).map((x) => el("li", {}, x.url ? el("a", { href: x.url, target: "_blank", rel: "noopener" }, x.title) : x.title))),
        el("div", { class: "tiny" }, "GitHub issues assigned to you; each closes itself when its condition clears."));
    }).catch(() => null);
  };

  T.pageRecord = function (sub) {
    const [tab, extra] = (sub || "").split("/");
    if (["portfolio", "judgements", "journal", "track", "reviews"].includes(tab)) R.tab = tab;
    const f = el("div");
    const tabs = el("div", { class: "tabs" });
    [["portfolio", "Portfolio"], ["judgements", "Judgements"], ["track", "Track record"], ["reviews", "Reviews"], ["journal", "Journal"]].forEach(([k, l]) => tabs.appendChild(el("button", { type: "button", class: R.tab === k ? "on" : "", onclick: () => { location.hash = "#record/" + k; } }, l)));
    f.append(...nn(el("div", { class: "sec" }, el("h1", {}, "Record"), tabs)));
    const body = el("div", {}, T.skel("lines"), T.skel("block")); f.appendChild(body);
    load().then(() => {
      if (R.err) { body.replaceWith(el("div", { class: "err" }, "Book data not found: " + R.err)); return; }
      body.replaceWith(R.tab === "judgements" ? judgements() : R.tab === "journal" ? journal() : R.tab === "track" ? trackRecord() : R.tab === "reviews" ? reviews(extra) : portfolio());
    });
    return f;
  };
  T.loadBook = load;
  T.bookState = () => R.book;
})();
