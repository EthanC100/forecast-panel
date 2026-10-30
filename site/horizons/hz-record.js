/* Horizons: Record. Paper book (Portfolio), my calls, the track record (incl. Horizons' view as a
   forecaster), monthly reviews, the journal and reminders, read from data/book/*.json. Same content
   and forms as Catalyst's Record, explained per Explain mode. */
(function () {
  "use strict";
  const { el, svg, nn, fmt, pct } = HZ;
  const signed = HZ.signed;
  const money = (v) => v == null ? "–" : (v < 0 ? "−$" : "$") + fmt(Math.abs(v), 0);
  const table = (head, rows) => el("div", { class: "scroll" }, el("table", {}, el("thead", {}, el("tr", {}, ...head.map((h) => el("th", { class: h.r ? "r" : "" }, h.t || h)))), el("tbody", {}, ...rows)));
  const withN = (v, n, d) => el("span", { class: "num" }, v == null ? "–" : fmt(v, d == null ? 3 : d), el("span", { class: "tiny" }, " n=" + (n || 0)));
  const TABS = [["portfolio", "Portfolio"], ["calls", "My calls"], ["track", "Track record"], ["reviews", "Reviews"], ["journal", "Journal"]];
  const NAMES = { me: "Me", ai: "AI (blind)", market: "Market at entry", no_change: "No-change (my first forecast, never updated)", ai_all: "AI on every question it judged", horizons: "Horizons' view" };
  const stat = (label, value, sub) => el("div", { style: "min-width:120px;flex:1" }, el("div", { class: "label" }, label), el("div", { style: "font-size:1.375rem;font-weight:800" }, value), sub ? el("div", { class: "tiny" }, sub) : null);

  // ---------------- reminders ----------------
  function remindersCard(r) {
    const open = (r && r.open) || [];
    return HZ.card({ title: "Reminders" + (open.length ? " (" + open.length + ")" : ""), cls: "s-rec" },
      open.length ? el("ul", { class: "small" }, ...open.slice(0, 10).map((x) => el("li", {}, el("span", { class: "chip" }, x.kind || "reminder"), " ", x.url ? el("a", { href: x.url, target: "_blank", rel: "noopener" }, x.title) : x.title)))
        : el("p", { class: "small" }, "Nothing due. Reminders arrive as GitHub issues assigned to you when a call goes 14 days without an update, a signpost date arrives, a trade passes its horizon or moves more than 2 standard deviations, or a big catalyst is 3 days away without a call."),
      HZ.explain({ what: "Your open reminders: each is a GitHub issue, so it reaches your phone as a notification.", how: "Tap one to open it; it carries the right form (quick update, make a call, close trade). It closes itself once the condition clears.",
        now: open.length ? open.length + " open: " + open.slice(0, 3).map((x) => x.title).join("; ") + "." : "Nothing due today." }));
  }

  // ---------------- Portfolio ----------------
  function portfolio(b, rem) {
    const f = el("div"), e = b.equity || {}, s = b.stats || {}, dd = e.worst_drawdown || {};
    const trades = b.trades || [], open = trades.filter((t) => t.status === "open"), pending = trades.filter((t) => t.status === "pending"), closed = trades.filter((t) => t.status === "closed");
    f.appendChild(el("div", { class: "btns" }, HZ.formBtn("Open a paper trade", "open-trade", { title: "[Open trade] " }, "primary"), HZ.formBtn("Close a trade", "close-trade", {}, "soft")));
    f.appendChild(remindersCard(rem));
    const hit = s.hit_rate_pct;
    f.appendChild(HZ.card({ title: "The paper book", cls: "s-rec glow" },
      el("div", { class: "row", style: "gap:16px;align-items:flex-start" },
        stat("Equity", money(e.current), "started at " + money(b.starting_capital_usd) + " on " + b.start_date),
        stat("P&L since start", HZ.pnl(e.pnl_usd), e.return_pct == null ? null : HZ.signed(e.return_pct, 2, "%")),
        stat("Worst drawdown", fmt(dd.pct, 2) + "%", dd.to ? "to " + dd.to : null),
        stat("Risk to stops now", money(b.risk_at_stake_usd), b.risk_at_stake_pct != null ? fmt(b.risk_at_stake_pct, 2) + "% of equity" : null)),
      el("div", { class: "row", style: "gap:18px;margin-top:12px" },
        el("div", { style: "text-align:center" }, HZ.ring(hit == null ? 0 : hit / 100, hit == null ? "–" : fmt(hit, 0) + "%", { title: "hit rate" }), el("div", { class: "tiny" }, "hit rate")),
        el("div", { class: "small" }, "Average win ", HZ.pnl(s.avg_win_usd), " · average loss ", HZ.pnl(s.avg_loss_usd), el("br"), (s.n_open || 0) + " open · " + (s.n_pending || 0) + " pending · " + (s.n_closed || 0) + " closed")),
      HZ.explain({ what: "Your pretend trading account: $" + fmt(b.starting_capital_usd, 0) + " of paper money, marked to real closing prices every day, with carry and trading costs included.",
        how: "Equity is what the account is worth now. Drawdown is the biggest fall from a previous high: it tells you how painful the worst stretch was. Risk to stops is what you would lose if every open trade hit its stop. Hit rate is the share of closed trades that made money; it only means something next to the average win and loss.",
        now: open.length ? open.length + " open trade" + (open.length > 1 ? "s" : "") + ", " + money(b.risk_at_stake_usd) + " at risk to the stops." : "No open trades: the book is flat. Open one from a calendar event, a scenario or a country page." })));
    // equity curve
    const curve = e.curve || [];
    f.appendChild(HZ.card({ title: "How has the book's equity moved?", cls: "s-rec" },
      curve.length >= 2 ? HZ.lineChart(curve, { unit: "USD", decimals: 0, noRanges: true, name: "Equity" }) : el("p", { class: "small" }, "The curve appears after the second daily mark."),
      HZ.explain({ what: "The value of the paper book each day since " + b.start_date + ".", how: "A steady upward line is the goal; deep dips are drawdowns. Touch the chart to read any day.",
        now: curve.length ? "Now " + money(curve[curve.length - 1][1]) + " after " + curve.length + " daily marks; worst drawdown " + fmt(dd.pct, 2) + "%." : null })));
    // open positions
    f.appendChild(HZ.card({ title: "Open positions", cls: "s-rec" },
      open.length ? el("div", {}, ...open.map((t) => el("div", { style: "padding:10px 0;border-bottom:1px solid var(--line)" },
        el("div", { class: "row spread" }, el("b", {}, t.open.direction + " " + t.open.instrument), el("span", { style: "font-size:1.25rem" }, HZ.pnl(t.pnl.total))),
        el("div", { class: "small" }, "Entry " + t.fill.entry_value + " on " + t.fill.entry_date + " · now " + t.mark.value + " (" + t.mark.date + ") · notional " + money(t.fill.notional_usd)),
        el("div", { class: "small" }, "Price ", HZ.pnl(t.pnl.price), " · carry ", HZ.pnl(t.pnl.carry), " · costs ", HZ.pnl(t.pnl.cost)),
        el("div", { class: "tiny" }, "Stop " + t.open.stop + " · target " + (t.open.target ?? "–") + " · horizon " + t.open.horizon + " · risk to stop " + money(t.risk_to_stop_now)),
        (t.flags || []).length ? el("div", {}, ...t.flags.map((x) => el("span", { class: "chip warn", style: "margin-right:4px" }, x))) : null,
        el("div", { class: "btns" }, t.open.issue_url ? el("a", { class: "btn small", href: t.open.issue_url, target: "_blank", rel: "noopener" }, t.trade_id) : null,
          t.close_request ? el("span", { class: "chip" }, "closing at the next close") : HZ.formBtn("Close", "close-trade", { trade_id: t.trade_id, title: "[Close trade] " + t.trade_id }, "soft small")))))
        : el("p", { class: "empty" }, "No open positions."),
      HZ.explain({ what: "Each open trade with its profit or loss so far, split into where it came from.", how: "Price = the market move; carry = interest earned or paid for holding it; costs = the round-trip spread, charged at entry. Green with + is a gain, red with − is a loss. Flags warn about a passed horizon or a stop nearly hit.",
        now: open.length ? (() => { const w = open.slice().sort((a, c) => a.pnl.total - c.pnl.total)[0]; return "Weakest: " + w.trade_id + " (" + w.open.instrument + ") at " + money(w.pnl.total) + "."; })() : "Nothing open." })));
    if (pending.length) f.appendChild(HZ.card({ title: "Waiting for the next close", cls: "s-rec" }, el("ul", { class: "small" }, ...pending.map((t) => el("li", {}, t.trade_id + ": " + t.open.direction + " " + t.open.instrument + ", submitted " + t.open.submitted_at.slice(0, 16).replace("T", " ") + (t.open.warnings || []).map((w) => " ⚠ " + w).join(""))))));
    f.appendChild(HZ.card({ title: "Closed trades", cls: "s-rec" },
      closed.length ? table(["trade", "entry → exit", "reason", { t: "P&L", r: 1 }, "post-mortem"], closed.map((t) => el("tr", {}, el("td", {}, t.open.issue_url ? el("a", { href: t.open.issue_url, target: "_blank", rel: "noopener" }, t.trade_id) : t.trade_id, el("div", { class: "tiny" }, t.open.direction + " " + t.open.instrument)),
        el("td", { class: "small num" }, t.fill.entry_value + " → " + t.exit.exit_value, el("div", { class: "tiny" }, t.fill.entry_date + " → " + t.exit.exit_date)), el("td", { class: "small" }, t.exit.reason),
        el("td", { class: "r" }, HZ.pnl(t.pnl.total)), el("td", { class: "small" }, ((t.close_request || {}).postmortem || []).join(" / "))))) : el("p", { class: "empty" }, "None yet.")));
    const rej = trades.filter((t) => t.status === "rejected");
    if (rej.length) f.appendChild(el("details", {}, el("summary", { class: "small" }, rej.length + " rejected trade forms"), el("ul", { class: "small" }, ...rej.map((t) => el("li", {}, t.trade_id + ": " + (t.open.errors || []).join("; "))))));
    // systematic and buy-and-hold
    const sy = b.systematic || {};
    f.appendChild(HZ.card({ title: "The systematic algorithm (em-macro)", cls: "s-rec" },
      !sy.available ? el("p", { class: "small" }, sy.message || "Not available.") : el("div", {},
        el("div", { class: "row", style: "gap:16px" }, stat("Cumulative since 2006", fmt(sy.full_history[sy.full_history.length - 1][1], 3) + "×"),
          stat("Since your start", sy.since_start && sy.since_start.length ? money(sy.since_start[sy.since_start.length - 1][1]) : "no month yet", "scaled to $" + fmt(b.starting_capital_usd / 1000, 0) + "k"), stat("Latest sample", sy.latest_sample || "–")),
        HZ.lineChart(sy.full_history.map((r) => [r[0] + "-01", r[1]]), { unit: "×", decimals: 2, range: 0, ranges: [["5Y", 1826], ["All", 0]], name: "Systematic cumulative return" }),
        el("p", { class: "tiny" }, sy.note || "")),
      HZ.explain({ what: "A rules-based currency strategy (carry, trend and value across 10 currencies), designed on 2005–2019 data and then frozen. It is the benchmark your own trades should beat.",
        how: "The line is how $1 invested in 2006 would have grown (1.5× = +50%). It runs monthly at its own risk level, so compare direction with your book more than size.",
        now: sy.available ? "Latest month " + sy.full_history[sy.full_history.length - 1][0] + ": " + fmt(sy.full_history[sy.full_history.length - 1][1], 3) + "× since 2006." : null }),
      HZ.source("em-macro results/systematic", "https://github.com/EthanC100/em-macro/tree/main/results/systematic", sy.as_of)));
    const bh = b.benchmarks || [];
    f.appendChild(HZ.card({ title: "Buy-and-hold of each instrument", cls: "s-rec" },
      table(["instrument", { t: "since " + b.start_date, r: 1 }, { t: "last 12 months", r: 1 }], bh.map((r) => el("tr", {}, el("td", {}, r.name, el("div", { class: "tiny" }, r.description)),
        el("td", { class: "r" }, r.since_start ? HZ.pnl(r.since_start.return_pct, 2, "") : "–", r.since_start ? el("span", { class: "tiny" }, "%") : null),
        el("td", { class: "r" }, r.last_12m ? HZ.pnl(r.last_12m.return_pct, 2, "") : "–", r.last_12m ? el("span", { class: "tiny" }, "%") : null)))),
      HZ.explain({ what: "What you would have made simply holding $100,000 long each instrument as quoted, with carry and no costs.", how: "If buy-and-hold beats your trades, your timing is costing you. 'Long USD/BRL' gains when the real weakens; 'long' a yield instrument means owning the bond, gaining when yields fall.",
        now: (() => { const v = bh.filter((r) => r.last_12m); if (!v.length) return null; const best = v.sort((a, c) => c.last_12m.return_pct - a.last_12m.return_pct)[0]; return "Best over 12 months: " + best.name + " " + signed(best.last_12m.return_pct, 2) + "%."; })() })));
    f.appendChild(el("details", {}, el("summary", { class: "small" }, "Assumptions and costs (data/book/config.yaml)"), el("ul", { class: "small" }, ...(b.assumptions || []).map((a) => el("li", {}, a))),
      table(["code", "instrument", "round-trip cost", "close (UTC)"], Object.entries(b.instruments || {}).map(([k, i]) => el("tr", {}, el("td", {}, k), el("td", { class: "small" }, i.name + (i.proxy ? " (proxy)" : "")), el("td", { class: "small" }, i.cost + " " + i.cost_unit), el("td", { class: "small" }, i.close_utc || "–"))))));
    HZ.ctx.add("Paper book (as of " + b.as_of + ")", ["Equity " + money(e.current) + ", P&L " + money(e.pnl_usd) + " (" + signed(e.return_pct, 2) + "%) since " + b.start_date, "Worst drawdown " + fmt(dd.pct, 2) + "%, risk to stops " + money(b.risk_at_stake_usd),
      "Hit rate " + (hit == null ? "–" : hit + "%") + ", avg win " + money(s.avg_win_usd) + ", avg loss " + money(s.avg_loss_usd)]);
    HZ.ctx.add("Open trades", open.map((t) => t.trade_id + ": " + t.open.direction + " " + t.open.instrument + " entry " + t.fill.entry_value + " (" + t.fill.entry_date + "), now " + t.mark.value + ", P&L " + money(t.pnl.total) + " (price " + money(t.pnl.price) + ", carry " + money(t.pnl.carry) + ", cost " + money(t.pnl.cost) + "), stop " + t.open.stop + ", target " + (t.open.target ?? "–") + ", horizon " + t.open.horizon + ", thesis: " + (t.open.thesis || "")));
    HZ.ctx.ask("Looking at my open trades and the book, what is the biggest risk I'm carrying and is any trade's thesis looking broken?");
    return f;
  }

  // ---------------- My calls ----------------
  function calibrationSvg(cal) {
    const W = 300, H = 280, P = 34, X = (v) => P + v * (W - 2 * P), Y = (v) => H - P - v * (H - 2 * P);
    const g = svg("svg", { class: "chart", viewBox: `0 0 ${W} ${H}`, style: "max-width:360px", role: "img", "aria-label": "calibration chart" });
    for (let i = 0; i <= 4; i++) { g.appendChild(svg("line", { class: "ax", x1: X(i / 4), x2: X(i / 4), y1: Y(0), y2: Y(1) })); g.appendChild(svg("line", { class: "ax", x1: X(0), x2: X(1), y1: Y(i / 4), y2: Y(i / 4) }));
      g.appendChild(svg("text", { class: "lbl", x: X(i / 4), y: H - P + 16, "text-anchor": "middle" }, i * 25 + "%")); g.appendChild(svg("text", { class: "lbl", x: P - 6, y: Y(i / 4) + 4, "text-anchor": "end" }, i * 25 + "%")); }
    g.appendChild(svg("line", { x1: X(0), y1: Y(0), x2: X(1), y2: Y(1), stroke: "var(--ink-3)", "stroke-dasharray": "4 4" }));
    const maxN = Math.max(...cal.map((c) => c.n));
    cal.forEach((c) => { const d = svg("circle", { cx: X(c.mean_forecast), cy: Y(c.observed), r: 4 + 8 * Math.sqrt(c.n / maxN), fill: "var(--plum)", "fill-opacity": ".7" }); d.appendChild(svg("title", {}, c.bin + ": n=" + c.n + ", forecast " + pct(c.mean_forecast) + ", happened " + pct(c.observed))); g.appendChild(d); });
    return g;
  }
  function calls(j) {
    const s = j.summary || {}, f = el("div"), qs = j.questions || [];
    f.appendChild(el("div", { class: "btns" }, HZ.formBtn("Make a call", "full-call", {}, "primary"), HZ.formBtn("Quick update", "quick-update", {}, "soft"), HZ.formBtn("Resolve a question", "resolve-question", {}, "soft")));
    const vs = (pair) => pair ? fmt(pair[0], 3) + " vs " + fmt(pair[1], 3) + " market" : "–";
    f.appendChild(HZ.card({ title: "How good are my calls?", cls: "s-rec glow" },
      el("div", { class: "row", style: "gap:16px;align-items:flex-start" },
        el("div", { style: "text-align:center" }, HZ.ring(s.n_questions ? s.n_resolved / s.n_questions : 0, (s.n_resolved || 0) + "/" + (s.n_questions || 0), { title: "resolved of all questions" }), el("div", { class: "tiny" }, "resolved")),
        stat("Brier (lower is better)", s.brier_mine == null ? "–" : fmt(s.brier_mine, 3), "vs market at entry (n=" + (s.n_with_market || 0) + "): " + vs(s.brier_mine_vs_market)),
        stat("Log score (higher is better)", s.log_mine == null ? "–" : fmt(s.log_mine, 3), "vs market: " + vs(s.log_mine_vs_market))),
      s.calibration ? el("div", {}, el("h3", {}, "Calibration: do my 70% calls happen 70% of the time?"), calibrationSvg(s.calibration),
        HZ.explain({ what: "Each bubble groups calls with similar probabilities: across is what you said, up is how often it happened.", how: "Bubbles on the dashed line are well calibrated. Bubbles below the line mean you were too confident; above means too timid. Bigger bubbles hold more calls.", now: null }))
        : el("p", { class: "small muted" }, "The calibration chart appears after " + (s.calibration_min || 30) + " resolved questions (" + (s.n_resolved || 0) + " so far)."),
      HZ.explain({ what: "Your forecasting scores so far, against the market price recorded when you made each call.", how: "Brier: 0 is perfect, 0.25 is what always saying 50% scores. Log score punishes confident misses hard; closer to 0 is better. Both are on your last forecast before each question resolved.",
        now: s.n_resolved ? "After " + s.n_resolved + " resolved questions your Brier is " + fmt(s.brier_mine, 3) + (s.brier_mine_vs_market ? (s.brier_mine_vs_market[0] < s.brier_mine_vs_market[1] ? ": better than the market." : ": the market has been better.") : ".") : "Nothing has resolved yet: " + (s.n_questions || 0) + " open question" + (s.n_questions === 1 ? "" : "s") + "." })));
    // running Brier
    const res = qs.filter((q) => q.resolution).map((q) => { const fc = q.forecasts[q.forecasts.length - 1]; return { d: q.resolution.date, me: fc.brier }; }).filter((x) => x.me != null).sort((a, b) => a.d < b.d ? -1 : 1);
    if (res.length >= 2) { let sm = 0; f.appendChild(HZ.card({ title: "Are my calls getting better?", cls: "s-rec" }, HZ.lineChart(res.map((r, i) => [r.d, (sm += r.me) / (i + 1)]), { decimals: 3, noRanges: true, name: "Running Brier" }),
      HZ.explain({ what: "Your average Brier score as questions resolve, in date order.", how: "A falling line means you are improving. Early on it jumps around: a few questions are mostly luck.", now: "Latest running average " + fmt(sm / res.length, 3) + " over " + res.length + " questions." }))); }
    if (!qs.length) f.appendChild(HZ.card({ title: "No calls yet", cls: "s-rec" }, el("p", { class: "small" }, "Make your first call from a calendar event, a scenario page, a country page or the button above. You give a probability; Horizons scores it when the question resolves.")));
    qs.slice().reverse().forEach((q) => {
      const last = q.forecasts[q.forecasts.length - 1];
      f.appendChild(HZ.card({ title: q.question, cls: "s-rec", chips: [q.resolution ? el("span", { class: "chip" }, "resolved " + (q.resolution.outcome ? "YES" : "NO")) : el("span", { class: "chip c" }, "open")] },
        el("div", { class: "tiny" }, q.key + (q.question_id ? " · " + q.question_id : "") + " · resolves " + (q.resolution_date || "–")),
        el("div", { class: "row", style: "margin:8px 0" }, HZ.ring(last.prob, pct(last.prob), { size: 56, title: "my latest" }), el("div", { class: "small" }, "Market at entry " + (last.market ? pct(last.market.prob) : "–") + " · AI " + (last.ai ? pct(last.ai.prob) : "–") + (last.brier != null ? " · Brier " + fmt(last.brier, 3) : ""))),
        q.forecasts.length > 1 ? table(["record", { t: "mine", r: 1 }, { t: "market", r: 1 }, { t: "AI", r: 1 }, "what changed"], q.forecasts.map((fc) => el("tr", {}, el("td", { class: "small" }, fc.record + " · " + fc.submitted_at.slice(0, 10)),
          el("td", { class: "r num" }, pct(fc.prob)), el("td", { class: "r num" }, fc.market ? pct(fc.market.prob) : "–"), el("td", { class: "r num" }, fc.ai ? pct(fc.ai.prob) : "–"), el("td", { class: "small" }, fc.what_changed || ""))))
          : null,
        q.call ? el("details", {}, el("summary", { class: "small" }, "The call in full"), el("div", { class: "small" },
          el("p", {}, el("b", {}, "Base rate: "), q.call.base_rate || "–"), el("p", {}, el("b", {}, "Factors: "), (q.call.factors || []).map((x) => x.factor + " (" + x.direction + ", " + x.size + ")").join("; ") || "–"),
          el("p", {}, el("b", {}, "Scenarios: "), (q.call.scenarios || []).map((x) => x.scenario + " " + x.pct + "%").join(", ") || "–"), el("p", {}, el("b", {}, "Would change my mind: "), q.call.change_mind || "–"),
          el("p", {}, el("b", {}, "Pre-mortem: "), q.call.premortem || "–"), el("p", {}, el("b", {}, "Confidence: "), (q.call.confidence || "–") + (q.call.linked_trade ? " · trade " + q.call.linked_trade : "")))) : null,
        q.resolution ? null : el("div", { class: "btns" }, HZ.formBtn("Quick update", "quick-update", { target: q.key, title: "[Quick update] " + q.key }, "soft small"),
          HZ.formBtn("Resolve", "resolve-question", { target: q.key, title: "[Resolve] " + q.key }, "small"))));
    });
    HZ.ctx.add("My calls", qs.map((q) => { const l = q.forecasts[q.forecasts.length - 1]; return q.key + ": " + q.question + " → " + pct(l.prob) + " (" + l.submitted_at.slice(0, 10) + ")" + (l.market ? ", market " + pct(l.market.prob) : "") + (q.resolution ? ", resolved " + (q.resolution.outcome ? "YES" : "NO") + (l.brier != null ? ", Brier " + fmt(l.brier, 3) : "") : ", resolves " + (q.resolution_date || "–")); }));
    HZ.ctx.add("Scores", ["Resolved " + (s.n_resolved || 0) + " of " + (s.n_questions || 0), "Brier " + (s.brier_mine == null ? "–" : fmt(s.brier_mine, 3)), "Log " + (s.log_mine == null ? "–" : fmt(s.log_mine, 3))]);
    HZ.ctx.ask("Which of my open calls is most likely wrong, and what evidence should make me update it this week?");
    return f;
  }

  // ---------------- Track record ----------------
  function noisyChip(q) { return q.noisy ? el("span", { class: "chip warn", title: "Fewer than " + q.min_overall + " resolved questions: differences are mostly luck." }, "noisy: " + q.n_resolved + " of " + q.min_overall) : null; }
  function groupTable(rows, label) {
    return table([label, { t: "n", r: 1 }, { t: "Brier me", r: 1 }, { t: "market", r: 1 }, { t: "AI", r: 1 }], (rows || []).map((g) => el("tr", {}, el("td", {}, g.group), el("td", { class: "r num" }, String(g.n)),
      ...(g.insufficient ? [el("td", { class: "r tiny", colspan: "3" }, "insufficient data (under 10)")] : ["me", "market", "ai"].map((w) => el("td", { class: "r" }, withN((g[w] || {}).brier, (g[w] || {}).n)))))));
  }
  const num = (x) => typeof x === "number";
  function horizonsCard(h) {
    if (!h) return HZ.card({ title: "Horizons' view as a forecaster", cls: "s-rec" }, el("p", { class: "small" }, "Horizons' weekly views (lean long, lean short or no view on each bond, currency and gold) are scored here like any forecaster once they reach their horizon date."));
    const top = h.overall || h.score || h;
    const n = top.n ?? top.n_resolved ?? 0;
    const hr = top.hit_rate_pct ?? (num(top.hit_rate) ? 100 * top.hit_rate : null);
    const rows = h.by_region || h.by_asset || h.rows || [];
    const vsMe = h.vs_me || h.side_by_side || null;
    return HZ.card({ title: "Horizons' view as a forecaster", cls: "s-rec glow", chips: [el("span", { class: "chip view" }, "Horizons' view, not financial advice")] },
      el("div", { class: "row", style: "gap:16px" },
        el("div", { style: "text-align:center" }, HZ.ring(hr == null ? 0 : hr / 100, hr == null ? "–" : fmt(hr, 0) + "%", { title: "hit rate" }), el("div", { class: "tiny" }, "direction right")),
        stat("Brier", top.brier == null ? "–" : fmt(top.brier, 3), "n=" + n), stat("Log score", top.log == null ? "–" : fmt(top.log, 3), "n=" + n),
        num(h.n_open) || num(h.open) ? stat("Still open", String(h.n_open ?? h.open)) : null),
      Array.isArray(rows) && rows.length ? table(Object.keys(rows[0]).filter((k) => typeof rows[0][k] !== "object").map((k) => ({ t: k.replace(/_/g, " "), r: typeof rows[0][k] === "number" })),
        rows.map((r) => el("tr", {}, ...Object.keys(rows[0]).filter((k) => typeof rows[0][k] !== "object").map((k) => el("td", { class: typeof r[k] === "number" ? "r num" : "small" }, typeof r[k] === "number" ? fmt(r[k], Math.abs(r[k]) < 1 ? 3 : 1) : (r[k] == null ? "–" : String(r[k]))))))) : null,
      vsMe && typeof vsMe === "object" ? el("p", { class: "small" }, el("b", {}, "On the same questions: "), Object.entries(vsMe).filter(([, v]) => v && typeof v === "object" && "brier" in v).map(([k, v]) => (NAMES[k] || k) + " " + (v.brier == null ? "–" : fmt(v.brier, 3)) + " (n=" + (v.n || 0) + ")").join(" · ") || "no shared questions yet") : null,
      HZ.explain({ what: "Every weekly Horizons view is a probability that a bond, currency or gold moves its way by a set date. When the date passes, it is scored exactly like your calls.",
        how: "Hit rate: how often the lean was the right direction. Brier and log score also reward the right confidence. Under 100 resolved views, treat it as noisy.",
        now: n ? n + " views scored so far" + (hr != null ? ", " + fmt(hr, 0) + "% right on direction." : ".") : "No view has reached its horizon date yet." }));
  }
  function track(rec) {
    const q = rec.questions, tr = rec.trades, f = el("div"), side = q.side_by_side;
    const who = ["me", "ai", "market", "no_change", "ai_all", "horizons"].filter((w) => side[w]);
    const briers = who.map((w) => side[w].brier).filter((v) => v != null), maxB = Math.max(0.25, ...briers);
    f.appendChild(HZ.card({ title: "Who forecasts better?", cls: "s-rec glow", chips: [noisyChip(q)] },
      ...who.map((w) => el("div", { style: "margin:10px 0" + (w === "me" ? ";font-weight:800" : "") },
        el("div", { class: "row spread small" }, el("span", {}, NAMES[w] || w), el("span", {}, "Brier ", withN(side[w].brier, side[w].n), " · log ", withN(side[w].log, side[w].n))),
        HZ.meter(side[w].brier == null ? 0 : side[w].brier / maxB, (NAMES[w] || w) + " Brier"))),
      q.shared && q.shared.n ? el("p", { class: "small" }, "On the " + q.shared.n + " questions where all three exist: me " + fmt(q.shared.scores.me.brier, 3) + ", AI " + fmt(q.shared.scores.ai.brier, 3) + ", market " + fmt(q.shared.scores.market.brier, 3) + ".") : null,
      HZ.explain({ what: "Your scores side by side with the AI (which never sees your calls), the market price at the moment you called, and 'no-change' (your first forecast, never updated).",
        how: "Shorter bars are better (Brier: 0 perfect, 0.25 a coin flip). n is how many resolved questions sit behind each number: below 100 everything is labelled noisy. If no-change beats you, your updates are hurting.",
        now: q.n_resolved ? (side.me.brier != null && side.market.brier != null ? (side.me.brier < side.market.brier ? "You are ahead of the market so far" : "The market is ahead of you so far") + " (" + fmt(side.me.brier, 3) + " vs " + fmt(side.market.brier, 3) + ", n=" + side.me.n + ")." : "Too few shared questions to compare.") : "Nothing has resolved yet: scores appear as questions resolve." })));
    f.appendChild(horizonsCard(rec.horizons || q.horizons || null));
    const sk = q.skill || {};
    f.appendChild(HZ.card({ title: "Skill: telling outcomes apart vs getting the odds right", cls: "s-rec" },
      table(["", { t: "discrimination ↑", r: 1 }, { t: "calibration error ↓", r: 1 }, { t: "AUC", r: 1 }, { t: "n", r: 1 }], ["me", "ai", "market"].filter((w) => sk[w]).map((w) => el("tr", {}, el("td", {}, NAMES[w]),
        el("td", { class: "r num" }, sk[w].n ? fmt(sk[w].discrimination, 3) : "–"), el("td", { class: "r num" }, sk[w].n ? fmt(sk[w].calibration_error, 3) : "–"), el("td", { class: "r num" }, sk[w].auc == null ? "–" : fmt(sk[w].auc, 2)), el("td", { class: "r num" }, String(sk[w].n || 0))))),
      sk.me && sk.me.auc != null ? el("div", { class: "row", style: "margin-top:8px" }, HZ.ring((sk.me.auc - 0.5) * 2, fmt(sk.me.auc, 2), { title: "my AUC" }), el("span", { class: "small" }, "Your AUC: 0.5 is a coin flip, 1.0 is perfect separation.")) : null,
      HZ.explain({ what: "Your Brier score split into two skills.", how: "Discrimination (higher is better): are your forecasts higher for things that happened than for things that didn't? That is the real skill. Calibration error (lower is better): do your 70% calls happen 70% of the time? You can fix that by shading. AUC 0.5 = no better than a coin.",
        now: sk.me && sk.me.n ? "Discrimination " + fmt(sk.me.discrimination, 3) + ", calibration error " + fmt(sk.me.calibration_error, 3) + " over " + sk.me.n + " questions." : "Needs resolved questions." })));
    f.appendChild(HZ.card({ title: "Where am I good?", cls: "s-rec" },
      el("h3", {}, "By catalyst type"), groupTable(q.by_type, "type"), el("h3", {}, "By my stated confidence"), groupTable(q.by_confidence, "confidence"),
      el("h3", {}, "By lead time (last forecast to resolution)"), groupTable(q.by_lead, "lead time"),
      HZ.explain({ what: "Your scores split by the kind of event, how confident you said you were, and how far ahead you called it.", how: "Groups under " + q.min_group + " resolved questions say 'insufficient data': a handful of questions is mostly luck. Look for groups where you beat the market and focus there.",
        now: (() => { const ok = (q.by_type || []).filter((g) => !g.insufficient); return ok.length ? "Enough data for: " + ok.map((g) => g.group).join(", ") + "." : "No group has 10 resolved questions yet."; })() })));
    const bl = q.blend || {};
    f.appendChild(HZ.card({ title: "Would a 50/50 blend of me and the AI do better?", cls: "s-rec" },
      bl.ready ? el("div", {}, table(["", { t: "Brier", r: 1 }], ["me", "ai", "blend"].map((w) => el("tr", {}, el("td", {}, w === "blend" ? "50/50 blend" : NAMES[w]), el("td", { class: "r" }, withN(bl[w].brier, bl[w].n))))), el("p", { class: "small" }, el("b", {}, "Verdict: "), bl.verdict + "."))
        : el("div", { class: "row" }, HZ.ring((bl.n_shared || 0) / (bl.min || 20), (bl.n_shared || 0) + "/" + (bl.min || 20), { title: "shared resolved questions" }), el("p", { class: "small", style: "flex:1;margin:0" }, "Shown once " + (bl.min || 20) + " questions that both of you forecast have resolved.")),
      HZ.explain({ what: "Whether averaging your probability with the AI's would have scored better than either alone.", how: "Averaging two independent forecasters often beats both. If it does here, a simple rule follows: average with the AI before you submit.", now: bl.ready ? "Verdict: " + bl.verdict + "." : (bl.n_shared || 0) + " of " + (bl.min || 20) + " shared questions resolved." })));
    const c = tr.closed || {}, o = tr.open || {};
    const rRow = (lab, x) => el("tr", {}, el("td", {}, lab), el("td", { class: "r" }, withN(x.total_r, x.n, 2)), el("td", { class: "r num" }, x.per_trade_r == null ? "–" : signed(x.per_trade_r, 2)),
      el("td", { class: "r num small" }, ["price", "carry", "cost"].map((k) => (x[k + "_r"] == null ? "–" : signed(x[k + "_r"], 2))).join(" / ")), el("td", { class: "r" }, HZ.pnl(x.total_usd)));
    f.appendChild(HZ.card({ title: "Trades: profit per unit of risk, after costs", cls: "s-rec" },
      table(["", { t: "total R", r: 1 }, { t: "per trade", r: 1 }, { t: "price / carry / cost (R)", r: 1 }, { t: "$", r: 1 }], [rRow("closed", c), rRow("open (unrealised)", o)]),
      HZ.explain({ what: "Trade results in R: 1R is the loss you accepted to your stop. +2R means you made twice what you risked.", how: "R makes small and big trades comparable. The split shows whether profits came from market moves (price), interest (carry) or were eaten by costs.",
        now: c.n ? c.n + " closed trades, " + signed(c.total_r, 2) + "R in total." : "No closed trades yet." })));
    const vs = tr.versus || {};
    f.appendChild(HZ.card({ title: "My book vs the systematic algorithm vs buy-and-hold, since " + tr.start_date, cls: "s-rec" },
      table(["", { t: "return", r: 1 }, "detail"], [
        el("tr", {}, el("td", {}, "My book"), el("td", { class: "r" }, vs.book && vs.book.return_pct != null ? HZ.pnl(vs.book.return_pct, 2, "") : "–"), el("td", { class: "small" }, vs.book ? vs.book.n_trades + " trades · " + (vs.book.total_r == null ? "–" : signed(vs.book.total_r, 2) + "R") : "")),
        el("tr", {}, el("td", {}, "Systematic (em-macro)"), el("td", { class: "r num" }, vs.systematic && vs.systematic.return_pct != null ? signed(vs.systematic.return_pct, 2) + "%" : "–"), el("td", { class: "small" }, vs.systematic ? (vs.systematic.return_pct == null ? vs.systematic.note : vs.systematic.n_months + " months to " + vs.systematic.to) : "")),
        el("tr", {}, el("td", {}, "Buy-and-hold (equal weight)"), el("td", { class: "r num" }, vs.buy_and_hold && vs.buy_and_hold.equal_weight_return_pct != null ? signed(vs.buy_and_hold.equal_weight_return_pct, 2) + "%" : "–"), el("td", { class: "small" }, vs.buy_and_hold ? vs.buy_and_hold.n_instruments + " instruments" : ""))]),
      el("p", { class: "tiny" }, vs.note || ""),
      HZ.explain({ what: "Your book's return next to two benchmarks over the same period.", how: "Beating buy-and-hold means your choices added value over simply holding. Beating the systematic algorithm means you beat a disciplined rules-based approach. The book's return is in green or red because it is your gain or loss; the benchmarks are neutral.",
        now: vs.book && vs.book.return_pct != null ? "Book " + signed(vs.book.return_pct, 2) + "%" + (vs.systematic && vs.systematic.return_pct != null ? ", systematic " + signed(vs.systematic.return_pct, 2) + "%" : "") + (vs.buy_and_hold && vs.buy_and_hold.equal_weight_return_pct != null ? ", buy-and-hold " + signed(vs.buy_and_hold.equal_weight_return_pct, 2) + "%." : ".") : null })));
    const hitT = (rows, label) => rows && rows.length ? table([label, { t: "n", r: 1 }, { t: "hit rate", r: 1 }, { t: "avg win", r: 1 }, { t: "avg loss", r: 1 }, { t: "avg R", r: 1 }], rows.map((g) => el("tr", {}, el("td", {}, g.group), el("td", { class: "r num" }, String(g.n)),
      ...(g.insufficient ? [el("td", { class: "r tiny", colspan: "4" }, "insufficient data (under 10)")] : [el("td", { class: "r num" }, g.hit_rate_pct + "%"), el("td", { class: "r" }, HZ.pnl(g.avg_win_usd)), el("td", { class: "r" }, HZ.pnl(g.avg_loss_usd)), el("td", { class: "r num" }, signed(g.avg_r, 2))]))))
      : el("p", { class: "empty" }, "No closed trades yet.");
    const ov = tr.overall || {};
    f.appendChild(HZ.card({ title: "Hit rate and average win or loss", cls: "s-rec" },
      el("div", { class: "row" }, HZ.ring(ov.hit_rate_pct == null ? 0 : ov.hit_rate_pct / 100, ov.hit_rate_pct == null ? "–" : fmt(ov.hit_rate_pct, 0) + "%", { title: "hit rate" }), el("span", { class: "small" }, "All closed trades, n=" + (ov.n || 0))),
      el("h3", {}, "By instrument"), hitT(tr.by_instrument, "instrument"), el("h3", {}, "By thesis type"), hitT(tr.by_thesis, "thesis type"),
      HZ.explain({ what: "How often your trades win, and how big wins and losses are, by instrument and by the kind of idea behind them.", how: "A 40% hit rate is fine if wins are twice the size of losses. Groups under 10 trades say 'insufficient data'.", now: ov.n ? (ov.n + " closed trades, " + fmt(ov.hit_rate_pct, 0) + "% winners.") : "No closed trades yet." })));
    f.appendChild(el("p", { class: "tiny" }, "Rebuilt " + (rec.generated_at || "").replace("T", " ").slice(0, 16) + " UTC after every data run and form."));
    HZ.ctx.add("Track record (" + (q.noisy ? "noisy: " + q.n_resolved + " resolved" : q.n_resolved + " resolved") + ")", who.map((w) => (NAMES[w] || w) + ": Brier " + (side[w].brier == null ? "–" : fmt(side[w].brier, 3)) + ", log " + (side[w].log == null ? "–" : fmt(side[w].log, 3)) + ", n=" + side[w].n));
    HZ.ctx.add("Trades", ["Closed: " + (c.n || 0) + " trades, total " + (c.total_r == null ? "–" : signed(c.total_r, 2) + "R"), "Book return " + (vs.book && vs.book.return_pct != null ? signed(vs.book.return_pct, 2) + "%" : "–")]);
    HZ.ctx.ask("Based on my track record so far, where am I adding value and where should I defer to the market or the AI?");
    return f;
  }

  // ---------------- Reviews ----------------
  function md(text) {
    const box = el("div", { class: "md" }), lines = text.split("\n");
    const inline = (s) => { const span = el("span"); span.innerHTML = s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/\*\*(.+?)\*\*/g, "<b>$1</b>").replace(/(^|\W)_(.+?)_(?=\W|$)/g, "$1<i>$2</i>").replace(/\[(.+?)\]\((https?:[^)\s"]+)\)/g, '<a href="$2" target="_blank" rel="noopener">$1</a>'); return span; };
    let list = null, tbl = null;
    lines.forEach((ln) => {
      if (/^\|/.test(ln)) { if (/^\|[-| :]+\|$/.test(ln)) return; const cells = ln.split("|").slice(1, -1).map((c) => c.trim());
        if (!tbl) { tbl = el("table"); box.appendChild(el("div", { class: "scroll" }, tbl)); tbl.appendChild(el("tr", {}, ...cells.map((c) => el("th", {}, inline(c))))); } else tbl.appendChild(el("tr", {}, ...cells.map((c) => el("td", {}, inline(c))))); return; }
      tbl = null;
      const h = ln.match(/^(#{1,3}) (.*)/), li = ln.match(/^\s*(?:- |\d+\. )(.*)/);
      if (li) { if (!list) { list = el(/^\s*\d/.test(ln) ? "ol" : "ul"); box.appendChild(list); } list.appendChild(el("li", {}, inline(li[1]))); return; }
      list = null;
      if (h) box.appendChild(el("h" + h[1].length, {}, inline(h[2])));
      else if (ln.trim()) box.appendChild(el("p", { class: "small" }, inline(ln)));
    });
    return box;
  }
  function reviews(month) {
    return HZ.maybe("book/reviews/index.json").then((ix) => {
      const list = (ix && ix.reviews) || [];
      if (!list.length) return HZ.card({ title: "Monthly reviews", cls: "s-rec" }, el("p", { class: "small" }, "The first draft review is written on the 1st of next month. It is generated once and never overwritten, so you can edit it on GitHub from your phone."),
        HZ.explain({ what: "A monthly look back: calls made and resolved, scores against the market and the AI, best and worst calls, trades and P&L, and lessons from your post-mortems.", how: "Read the draft, then tap Edit on GitHub and write three lessons in your own words.", now: "No review yet." }));
      const cur = list.find((r) => r.month === month) || list[0];
      return HZ.text("book/reviews/" + cur.month + ".md").then((text) => {
        HZ.ctx.add("Monthly review " + cur.month, text.split("\n").filter((l) => l.trim()).slice(0, 60));
        HZ.ctx.ask("Read my monthly review: what pattern in my mistakes should I fix first?");
        return el("div", {}, el("div", { class: "tabs" }, ...list.map((r) => el("a", { href: "#record/reviews/" + r.month, class: r.month === cur.month ? "on" : "" }, r.month + (r.edited ? " ✎" : "")))),
          HZ.card({ title: cur.title || cur.month, cls: "s-rec" }, el("div", { class: "btns", style: "margin-top:0" }, el("a", { class: "btn primary small", href: "https://github.com/" + HZ.REPO + "/edit/main/" + cur.file, target: "_blank", rel: "noopener" }, "Edit on GitHub")), md(text),
            HZ.explain({ what: "This month's review, drafted automatically on the 1st from your record.", how: "The numbers are filled in for you; the lessons are yours to write. Edits on GitHub are kept: the file is never regenerated.", now: cur.edited ? "You have edited this review." : "Still the untouched draft: add your three lessons." })));
      });
    });
  }

  // ---------------- Journal ----------------
  function journal(jn) {
    const items = (jn && jn.items) || [];
    HZ.ctx.add("Journal (latest 20)", items.slice(-20).reverse().map((i) => i.at.slice(0, 10) + " " + i.kind + " " + i.id + ": " + i.text));
    return HZ.card({ title: "Journal", cls: "s-rec", sub: items.length + " entries, newest first. Every trade, fill, close with post-mortem, exit, call, update and resolution; records are never edited after submission." },
      items.length ? el("div", {}, ...items.slice().reverse().map((i) => el("div", { style: "padding:10px 0;border-bottom:1px solid var(--line)" },
        el("div", { class: "row spread" }, el("b", {}, i.kind.replace(/-/g, " ") + " · " + i.id + (i.rejected ? " (rejected)" : "")), el("span", { class: "tiny" }, i.at.slice(0, 16).replace("T", " "))),
        el("div", { class: "small" }, i.text), i.detail ? el("div", { class: "small muted", style: "white-space:pre-line" }, i.detail) : null, i.errors ? el("div", { class: "err" }, i.errors.join("; ")) : null,
        i.market || i.ai ? el("div", { class: "tiny" }, "At entry: market " + (i.market ? pct(i.market.prob) : "–") + " · AI " + (i.ai ? pct(i.ai.prob) : "–")) : null,
        i.issue ? el("a", { class: "small", href: "https://github.com/" + HZ.REPO + "/issues/" + i.issue, target: "_blank", rel: "noopener" }, "#" + i.issue) : null)))
        : el("p", { class: "empty" }, "Nothing yet."),
      HZ.explain({ what: "Everything you have done, in order: your decision diary.", how: "Read it back before a big catalyst: what did you think last time, and what happened?", now: items.length ? "Latest: " + items[items.length - 1].text : "Empty so far." }));
  }

  HZ.pageRecord = function (arg) {
    const [tab0, extra] = (arg || "").split("/");
    const tab = TABS.some(([k]) => k === tab0) ? tab0 : tab0 === "judgements" ? "calls" : "portfolio";
    HZ.ctx.reset("Record: " + TABS.find(([k]) => k === tab)[1]);
    const f = el("div", { class: "s-rec" });
    f.appendChild(HZ.pageHead("Record", "Your paper trades, your calls and how they score against the market, the AI and Horizons.", "s-rec"));
    f.appendChild(el("div", { class: "tabs", role: "tablist" }, ...TABS.map(([k, l]) => el("a", { href: "#record/" + k, role: "tab", "aria-selected": String(k === tab), class: k === tab ? "on" : "" }, l))));
    let body;
    if (tab === "portfolio") body = Promise.all([HZ.json("book/state.json"), HZ.maybe("book/reminders.json")]).then(([b, r]) => portfolio(b, r));
    else if (tab === "calls") body = HZ.json("book/judgements.json").then(calls);
    else if (tab === "track") body = HZ.json("book/record.json").then(track).catch((e) => HZ.card({ title: "Track record", cls: "s-rec" }, el("p", { class: "small" }, "Not built yet (" + e.message + ").")));
    else if (tab === "reviews") body = reviews(extra);
    else body = HZ.maybe("book/journal.json").then(journal);
    return body.then((n) => { f.appendChild(n); return f; });
  };
})();
