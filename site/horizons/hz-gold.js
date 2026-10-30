/* Horizons gold page: gold and silver prices, the forces behind them (real interest rates, the
   dollar, war and political tension, central-bank buying), the frozen gold-events model's weekly
   expected move, past episodes, upcoming US political and Fed events, the brief, Horizons' view,
   and buttons to make a gold call or open a paper trade. Data: gold.json and the stored series. */
(function () {
  "use strict";
  const { el, fmt } = HZ;
  const nn = HZ.nn;

  HZ.pageGold = function () {
    HZ.ctx.reset("Gold", "Given the readings on this page, what is the strongest case for and against Horizons' view on gold over the next 1-3 months, and which upcoming event matters most?");
    return HZ.need("hz-country").then(() => Promise.all([HZ.maybe("gold.json"), HZ.maybe("brief/latest.json"), HZ.maybe("horizons/views.json"), HZ.maybe("book/judgements.json")]))
      .then(([G, brief, views, judg]) => {
        const cx = HZ.cx;
        cx.sources = Object.assign({}, brief && brief.sources || {}, views && views.sources || {});
        const page = el("div", { class: "c-GOLD" });
        const P = G && G.prices || {};
        const v = views && views.views && views.views.GOLD && views.views.GOLD.gold;
        const vdate = views && views.date || HZ.today();
        page.appendChild(HZ.pageHead("Gold", "The metal that pays no interest but holds its value in fear: what is moving it now, explained."));
        page.appendChild(el("div", { class: "row", style: "margin-bottom:12px" },
          el("a", { class: "chip view", href: "#", onclick: (e) => { e.preventDefault(); cx.anchor("sec-view"); } }, "Horizons: ", cx.leanText(v, "gold", "GOLD"))));
        if (!G) page.appendChild(HZ.card({ title: "Gold data is on its way" }, el("p", { class: "small" }, "The gold file (prices, drivers, the model and events) is built by the next data run. Charts below use whatever series are already stored.")));
        page.appendChild(prices(P));
        page.appendChild(cx.jump([["sec-gstory", "The story"], ["sec-drivers", "Drivers"], ["sec-model", "Model"], ["sec-eps", "Last time"], ["sec-events", "Coming up"], ["sec-view", "Horizons' view"]]));
        page.appendChild(story(brief));
        const gsid = P.gold && P.gold.series || "gl.gold", ssid = P.silver && P.silver.series || "gl.silver";
        page.appendChild(cx.seriesCard({ series: gsid, name: "Gold", unit: "USD per ounce", decimals: 0, how: "Up means gold costs more dollars per ounce. Touch the line to read any day; switch 1Y, 5Y, All to see the long climb and its pullbacks.",
          note: P.gold && P.gold.degraded, what: "The gold price in US dollars per troy ounce." }));
        page.appendChild(cx.seriesCard({ series: ssid, name: "Silver", unit: "USD per ounce", decimals: 2, how: "Silver follows gold but swings more, because industry also uses it.", note: P.silver && P.silver.degraded, what: "The silver price in US dollars per troy ounce." }));
        page.appendChild(ratio(P));
        page.appendChild(drivers(G));
        page.appendChild(model(G));
        page.appendChild(episodes(G, v));
        page.appendChild(events(G));
        page.appendChild(view(v, vdate, judg, P));
        page.appendChild(el("div", { class: "btns", style: "margin:8px 0 20px" }, HZ.askBtn("Ask Claude about gold")));
        (judg && judg.questions || []).filter((q) => /gold|GOLD/.test(q.question_id || "")).forEach((q) => { const f = q.forecasts[q.forecasts.length - 1]; HZ.ctx.add("My calls", `${q.question}: ${HZ.pct(f.prob)} on ${(f.submitted_at || "").slice(0, 10)}`); });
        return page;
      });
  };

  function priceTile(p, name, d) {
    if (!p) return HZ.card({ title: name }, el("p", { class: "empty" }, "No price stored yet."));
    HZ.ctx.add("Key data", `${name}: $${fmt(p.value, d)} per ounce on ${p.date}; 1 week ${HZ.signed(p.chg_1w_pct, 1)}%, 1 month ${HZ.signed(p.chg_1m_pct, 1)}%, 1 year ${HZ.signed(p.chg_1y_pct, 1)}%`);
    return el("article", { class: "card pop", style: "margin:0;padding:14px" }, el("div", { class: "label" }, name),
      el("div", { class: "num", style: "font-size:1.6rem;font-weight:800" }, "$" + fmt(p.value, d)),
      el("div", { class: "small" }, "1 week ", HZ.chg(p.chg_1w_pct, 1, "%"), " · 1 month ", HZ.chg(p.chg_1m_pct, 1, "%"), " · 1 year ", HZ.chg(p.chg_1y_pct, 1, "%")),
      el("div", { class: "tiny" }, "per ounce · ", p.date, p.degraded ? " · monthly average" : ""));
  }
  function prices(P) {
    const g = P.gold;
    return el("div", {}, el("div", { class: "grid2" }, priceTile(P.gold, "Gold", 0), priceTile(P.silver, "Silver", 2)),
      g ? HZ.explain({ what: "Today's gold and silver prices and how they changed over a week, a month and a year.", how: "These are market moves, not your gains or losses, so they're shown with a sign but no colour.",
        now: `Gold is ${HZ.zWords(g.z_1y)}${g.z_1y != null ? " (z-score " + HZ.signed(g.z_1y, 1) + ")" : ""}${g.high_1y ? `, in a 1-year range of $${fmt(g.low_1y, 0)} to $${fmt(g.high_1y, 0)}` : ""}.` }) : null,
      g ? HZ.source(g.source + (g.source_id ? " · " + g.source_id : ""), g.url, g.date) : null);
  }
  function ratio(P) {
    const r = P.ratio;
    if (!r) return el("div");
    HZ.ctx.add("Key data", `Gold/silver ratio: ${r.value} (${r.date})`);
    return HZ.card({ title: "Gold-to-silver ratio" }, el("div", { class: "row" }, HZ.ring(Math.min(1, r.value / 120), fmt(r.value, 0), { size: 76, title: "ratio " + r.value }), el("p", { class: "small", style: "flex:1" }, r.meaning)),
      HZ.explain({ what: "How many ounces of silver one ounce of gold buys.", how: "A high ratio means gold is expensive relative to silver: usually a sign investors want safety more than growth. The ring fills toward 120, near the extremes of recent decades.",
        now: `One ounce of gold buys ${fmt(r.value, 1)} ounces of silver (${r.date}).` }));
  }
  function story(brief) {
    const cx = HZ.cx;
    const R = brief && brief.report && brief.report.regions && brief.report.regions.GOLD;
    const J = R && R.judgement || {};
    const map = cx.sources;
    if (R) {
      (R.developments || []).forEach((f) => HZ.ctx.add("Brief: gold (facts)", f.text));
      (J.why_it_matters || []).forEach((w) => HZ.ctx.add("Brief: why it matters (judgement)", w.text));
      (J.risks || []).forEach((w) => HZ.ctx.add("Brief: key risks (judgement)", w.text || w));
    }
    return HZ.card({ title: "The story: gold now", id: "sec-gstory" },
      R ? [el("div", { class: "row" }, cx.factChip(), el("span", { class: "tiny" }, "From the daily brief, " + (brief.report.date || brief.date))),
        el("h3", { style: "margin-top:10px" }, "What happened"), cx.list(R.developments, (f) => cx.factItem(f, map), "No material development since the last brief."),
        el("h3", {}, "Versus a week ago"), cx.list(R.week_change, (f) => cx.factItem(f, map), "No week-on-week comparison yet."),
        el("h3", {}, "Next 30 days"), cx.list(R.upcoming, (u) => [el("b", {}, HZ.dateShort(u.date)), " ", u.title], "Nothing dated in the next 30 days."),
        el("hr", { class: "soft" }), el("div", { class: "row" }, cx.judgeChip(), el("span", { class: "tiny" }, J.date ? "Weekly judgement, " + J.date : "No judgement yet")),
        J.why_it_matters && J.why_it_matters.length ? el("div", { class: "judgement" }, el("h3", {}, "Why it matters for gold"), el("ul", {}, ...J.why_it_matters.map((w) => el("li", {}, w.text, cx.src(w.source_ids, map))))) : null,
        J.risks && J.risks.length ? el("div", { class: "judgement" }, el("h3", {}, "Key risks"), el("ul", {}, ...J.risks.map((w) => el("li", {}, w.text || w, cx.src(w.source_ids, map))))) : null,
        J.consensus || J.might_be_wrong ? el("div", { class: "judgement" }, el("h3", {}, "Consensus, and where it might be wrong"),
          J.consensus ? el("p", {}, el("b", {}, "Consensus: "), J.consensus.view || J.consensus) : null, J.might_be_wrong ? el("p", {}, el("b", {}, "Where it might be wrong: "), J.might_be_wrong) : null) : null]
        : el("p", { class: "empty" }, "The gold section of the brief appears after its next run."),
      HZ.explain({ what: "Gold's section of the daily brief: what changed, against a week ago, what's coming, and the weekly judgement.",
        how: "Blue “Fact” items are checked against their linked source. Violet “Judgement” items are a model's reading: opinion, not fact.",
        now: R ? `${(R.developments || []).length} gold developments in the latest brief.` : "Not run yet." }));
  }
  function drivers(G) {
    const D = G && G.drivers || [];
    const cx = HZ.cx;
    const SERIES = { real_yield: ["us.tips10", "%", 2, "Up means safe money pays more after inflation, which makes holding gold (which pays nothing) more costly."],
      dollar: ["us.usd.broad", "index", 1, "Up means a stronger dollar. Gold is priced in dollars, so a stronger dollar usually weighs on it."],
      gpr: ["gl.gpr", "index (100 = 1985-2019 average)", 0, "Spikes mark wars, attacks and political crises. Gold often rallies with them, though the effect fades."],
      cb_buying: ["gl.cbgold", "tonnes per month", 1, "Bars above zero are months when central banks added gold to reserves."] };
    const TERM = { real_yield: "real yield", dollar: "dollar", gpr: "gpr", cb_buying: "central-bank buying" };
    D.forEach((d) => HZ.ctx.add("Gold drivers", `${d.name}: ${d.value} ${d.unit || ""} on ${d.date}. ${d.reading || ""}`));
    const wrap = el("div", { id: "sec-drivers" }, el("h2", { style: "margin:24px 0 10px" }, "What moves gold"));
    if (!D.length) wrap.appendChild(el("p", { class: "empty" }, "Driver readings appear with the next data run."));
    D.forEach((d) => {
      const s = SERIES[d.id] || [d.series];
      wrap.appendChild(HZ.card({ title: d.name, chips: [TERM[d.id] ? el("span", { class: "small" }, HZ.term(TERM[d.id], "what is this?")) : null] },
        el("div", { class: "row" }, el("div", { class: "num", style: "font-size:1.4rem;font-weight:800" }, fmt(d.value, s[2] != null ? s[2] : 2), " ", el("span", { class: "small" }, d.unit || "")),
          d.chg_1m != null ? el("span", { class: "small" }, "1 month ", HZ.chg(d.chg_1m, d.chg_unit === "bp" ? 0 : 1, d.chg_unit === "bp" ? "bp" : d.chg_unit === "%" ? "%" : " " + (d.chg_unit || ""))) : null,
          d.percentile_10y != null ? HZ.ring(d.percentile_10y / 100, fmt(d.percentile_10y, 0), { size: 48, title: "10-year percentile " + fmt(d.percentile_10y, 0) }) : null),
        HZ.lazy(() => HZ.series(d.series || s[0]).then((ser) => HZ.lineChart(ser.history.map((r) => [r[0], r[1]]), { unit: s[1] || d.unit, decimals: s[2] != null ? s[2] : 2, name: d.name })).catch(() => null)),
        HZ.explain({ what: d.name + ".", how: s[3] || "Touch the chart to read any day.", now: d.reading }),
        d.finding_url ? el("p", { class: "tiny" }, el("a", { href: d.finding_url, target: "_blank", rel: "noopener" }, "What gold-events found about this driver")) : null,
        HZ.source(d.source + (d.source_id ? " · " + d.source_id : ""), d.url, d.date)));
    });
    return wrap;
  }
  function model(G) {
    const M = G && G.model;
    const box = el("div", { id: "sec-model" });
    if (!M) return box;
    if (!M.available) { box.appendChild(HZ.card({ title: "The gold model's weekly expected move" }, el("p", { class: "small" }, M.note || "Not available."), M.source_url ? HZ.source("gold-events", M.source_url) : null)); return box; }
    HZ.ctx.add("Frozen gold-events model (research prediction)", `Logged ${M.log_date} (${M.version}): expected gold move over 5 trading days ${HZ.signed(M.pred_gold_5d_pct, 2)}%, silver ${HZ.signed(M.pred_silver_5d_pct, 2)}%`);
    const recent = (M.recent || []).slice().reverse();
    box.appendChild(HZ.card({ title: "The gold model's weekly expected move", cls: "glow" },
      el("div", { class: "grid2" },
        el("div", {}, el("div", { class: "label" }, "Gold, next 5 trading days"), el("div", { class: "num", style: "font-size:1.6rem;font-weight:800" }, HZ.signed(M.pred_gold_5d_pct, 2, "%"))),
        el("div", {}, el("div", { class: "label" }, "Silver, next 5 trading days"), el("div", { class: "num", style: "font-size:1.6rem;font-weight:800" }, HZ.signed(M.pred_silver_5d_pct, 2, "%")))),
      el("p", { class: "small" }, "Logged ", HZ.dateLong(M.log_date), " · model ", M.version || "", M.data_as_of ? " · data to " + M.data_as_of : ""),
      M.n_scored ? el("div", { class: "row" }, HZ.ring(M.direction_hits / M.n_scored, M.direction_hits + "/" + M.n_scored, { size: 60, title: "direction right in " + M.direction_hits + " of " + M.n_scored + " scored weeks" }), el("span", { class: "small" }, "weeks where it got the direction right so far")) : null,
      recent.length ? el("details", {}, el("summary", {}, "Recent weeks"), el("div", { class: "scroll" }, el("table", {}, el("thead", {}, el("tr", {}, el("th", {}, "Week of"), el("th", { class: "r" }, "Expected"), el("th", { class: "r" }, "What happened"))),
        el("tbody", {}, ...recent.map((r) => el("tr", {}, el("td", {}, r.log_date), el("td", { class: "r" }, HZ.chg(r.pred_gold_5d_pct, 2, "%")), el("td", { class: "r" }, r.realised_gold_5d_pct != null ? HZ.chg(r.realised_gold_5d_pct, 2, "%") : el("span", { class: "tiny" }, "pending")))))))) : null,
      el("p", { class: "small" }, el("b", {}, "Plainly: "), "this is a frozen research model's prediction, not Horizons' view and not advice. Its coefficients were fixed in the gold-events project and are not tuned to recent weeks, so its live record is an honest test. ", M.note || ""),
      HZ.explain({ what: "The expected gold and silver move over the next 5 trading days from the frozen regression model in the gold-events project, using last week's changes in real yields, the dollar, volatility and geopolitical risk.",
        how: "Weekly gold moves are mostly noise: a prediction of +0.3% is small next to typical weekly swings of a couple of percent. Watch the direction and the running scorecard, not the decimals.",
        now: `For the week from ${M.log_date}, the model expects gold ${M.pred_gold_5d_pct >= 0 ? "up" : "down"} ${fmt(Math.abs(M.pred_gold_5d_pct), 2)}%.${M.n_scored ? ` So far it called the direction right in ${M.direction_hits} of ${M.n_scored} weeks.` : " No week has been scored yet."}` }),
      el("div", { class: "src" }, el("a", { href: M.source_url, target: "_blank", rel: "noopener" }, "Forward log"), " · ", M.scorecard_url ? el("a", { href: M.scorecard_url, target: "_blank", rel: "noopener" }, "Scorecard") : null)));
    return box;
  }
  function episodes(G, v) {
    const E = G && G.episodes || [];
    const wrap = el("div", { id: "sec-eps" });
    if (!E.length) return wrap;
    const res = v && v.resembles && v.resembles.episode_id;
    const resEp = E.find((e) => e.id === res);
    E.forEach((e) => HZ.ctx.add("Past gold episodes (what followed, not proof of cause)", `${e.name} (${e.start}): gold ${HZ.signed(e.moves && e.moves.gold_pct_6m, 1)}% after 6 months`));
    const cellv = (x, unit, d) => x == null ? el("span", { class: "tiny" }, "–") : el("span", { class: "num" }, HZ.signed(x, d != null ? d : 1, unit));
    wrap.appendChild(HZ.card({ title: "What happened last time" },
      el("p", { class: "small" }, el("b", {}, "These show what followed, not proof of cause.")),
      ...E.map((e) => { const m = e.moves || {}; return el("article", { class: "card", id: "ep-" + e.id, style: "box-shadow:none" },
        el("div", { class: "row spread" }, el("h3", { style: "margin:0" }, e.name), el("span", { class: "chip c" }, e.start)),
        el("p", { class: "small" }, e.summary),
        el("div", { class: "scroll" }, el("table", {}, el("thead", {}, el("tr", {}, el("th", {}, "After"), el("th", { class: "r" }, "1 month"), el("th", { class: "r" }, "6 months"), el("th", { class: "r" }, "24 months"))),
          el("tbody", {}, el("tr", {}, el("td", {}, "Gold"), el("td", { class: "r" }, cellv(m.gold_pct_1m, "%")), el("td", { class: "r" }, cellv(m.gold_pct_6m, "%")), el("td", { class: "r" }, cellv(m.gold_pct_24m, "%"))),
            el("tr", {}, el("td", {}, "Silver"), el("td", { class: "r" }, cellv(m.silver_pct_1m, "%")), el("td", { class: "r" }, cellv(m.silver_pct_6m, "%")), el("td", { class: "r" }, cellv(m.silver_pct_24m, "%")))))),
        el("p", { class: "tiny" }, nn([m.real_yield_bp_6m != null ? "Real yield over 6 months: " + HZ.signed(m.real_yield_bp_6m, 0, "bp") : null, m.dollar_pct_6m != null ? "Dollar over 6 months: " + HZ.signed(m.dollar_pct_6m, 1, "%") : null,
          m.cb_tonnes_12m != null ? "Central-bank buying in the next 12 months: " + fmt(m.cb_tonnes_12m, 0) + " t" : null, e.basis ? "Prices from " + e.basis : null]).join(" · ")),
        HZ.cx.cites(e.cites)); }),
      HZ.explain({ what: "Past moments that mattered for gold, including the 2024 US election and the 2025 rally, and how gold, silver, real yields and the dollar moved afterwards.",
        how: "Compare the drivers' moves with gold's: when gold rose while real yields also rose, something else (fear, central-bank buying) was doing the lifting. A dash means the period hasn't finished or no free data covers it.",
        now: resEp ? `Horizons' current view says today most resembles “${resEp.name}”.` : `${E.length} episodes; the most recent began ${E.slice().sort((a, b) => b.start.localeCompare(a.start))[0].start}.` })));
    return wrap;
  }
  function events(G) {
    const U = G && G.upcoming || [];
    const wrap = el("div", { id: "sec-events" });
    if (!U.length) return wrap;
    U.slice(0, 6).forEach((u) => HZ.ctx.add("Upcoming US political and Fed events", `${u.date}: ${u.title}. Watch: ${u.what_to_watch || ""}`));
    wrap.appendChild(HZ.card({ title: "Coming up: US politics and the Fed", cls: "c-US" },
      ...U.map((u) => el("div", { style: "margin:12px 0" },
        el("div", { class: "row spread" }, el("h3", { style: "margin:0" }, u.title), el("span", { class: "chip c" }, HZ.dateShort(u.date), " · ", HZ.inDays(u.date))),
        u.summary ? el("p", { class: "small" }, u.summary) : null,
        u.what_to_watch ? el("p", { class: "small" }, el("b", {}, "What to watch: "), u.what_to_watch) : null,
        u.study ? el("p", { class: "tiny" }, "After past midterms (", u.study.n, " since 2002) gold moved on average ", HZ.signed(u.study.raw_20d, 2, "%"), " over 20 days (", HZ.signed(u.study.net_20d, 2, "%"), " after removing the dollar and real yields). ", u.study.note, " ", el("a", { href: u.study.url, target: "_blank", rel: "noopener" }, "Study")) : null,
        el("div", { class: "btns" }, HZ.callBtn({ title: "Gold after " + u.title, question: `Will gold be higher 20 trading days after ${u.title} (${u.date}) than on the day before?`, question_id: "gold:" + (u.kind || "event") + "." + u.date, resolution_date: u.date, base_rate: u.study ? `${u.study.n} past midterms, average 20-day move ${u.study.raw_20d}%` : null }, "Make a gold call", "soft small")),
        u.source_url ? HZ.source(u.kind === "fed" ? "Federal Reserve" : "Official source", u.source_url) : null)),
      G.not_included && G.not_included.length ? el("p", { class: "tiny" }, "Not included: ", G.not_included.join(" ")) : null,
      HZ.explain({ what: "Dated US political and Federal Reserve events in the coming months that can move the dollar, real yields and so gold.",
        how: "Fed decisions matter through real yields and the dollar. Elections matter through spending, tariffs and pressure on the Fed. Prepare a view before the date; that's what the call button is for.",
        now: `Next: ${U[0].title} on ${HZ.dateLong(U[0].date)} (${HZ.inDays(U[0].date)}).` })));
    return wrap;
  }
  function view(v, date, judg, P) {
    const cx = HZ.cx;
    HZ.ctx.add("Horizons' view (" + date + ", not financial advice)", cx.ctxView(v, "gold", "GOLD", "gold"));
    const wantUp = !(v && v.lean === "short");
    return el("div", { id: "sec-view" }, HZ.card({ title: "Horizons' view on gold", cls: "glow", sub: "For the next 1–3 months." },
      cx.viewBox({ v, asset: "gold", code: "GOLD", date, judg, label: "gold (XAU/USD)", wantUp, srcMap: cx.sources, tradeInstr: "XAUUSD", episodeLink: (id) => el("a", { href: "#", onclick: (e) => { e.preventDefault(); cx.anchor("ep-" + id); } }, id) }),
      el("div", { class: "btns" },
        HZ.callBtn({ title: "Gold higher in 3 months?", question: `Will gold (XAU/USD) be higher on ${addDays(91)} than ${P.gold ? "$" + fmt(P.gold.value, 0) + " (" + P.gold.date + ")" : "today"}?`, question_id: "gold:price." + addDays(91), resolution_date: addDays(91) }, "Make a gold call", "primary"),
        HZ.tradeBtn("XAUUSD", { thesis: "" }, "Paper trade gold"), HZ.tradeBtn("XAGUSD", { thesis: "" }, "Paper trade silver")),
      HZ.explain({ what: "What Horizons would do with gold over the next one to three months, and why.",
        how: "“Lean long gold” means expecting the price to rise. The ring is the probability it moves that way by the horizon date. Your own call on the same question is shown next to it once you've made one; both are scored in the Record.",
        now: v ? cx.leanText(v, "gold", "GOLD") + (v.p != null ? `, ${HZ.pct(v.p > 1 ? v.p / 100 : v.p)} by ${v.horizon_end}.` : ".") : "No view yet: the first weekly view comes with the next judgement run." })));
  }
  function addDays(n) { const d = new Date(Date.now() + n * 864e5); return d.toISOString().slice(0, 10); }
})();
