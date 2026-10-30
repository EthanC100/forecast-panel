/* Horizons Home and the brief: the full comprehensive brief (facts and judgement kept apart, every
   fact sourced), country cards for Brazil, Mexico, France and Gold (status, Horizons' view, next event),
   the nearest catalyst without a call from me, open paper trades and reminders. #brief/<date> shows any
   archived brief; #brief lists them. */
(function () {
  "use strict";
  const { el, nn, fmt, card, explain, maybe } = HZ;
  const REGIONS = ["BR", "MX", "FR", "GOLD"];
  const KIND = { political: "Politics", fiscal: "Budget", central_bank: "Central bank", market: "Markets", data: "Data" };
  const TILE = { BR: ["usdbrl", "br10y"], MX: ["usdmxn", "mx10y"], FR: ["eurusd", "oatbund"] };
  const LEAN = { long: "Lean long", short: "Lean short", none: "No view" };

  // ---------------- sources ----------------
  function srcLinks(ids, sources) {
    const xs = (ids || []).map((id) => {
      const s = (sources || {})[id];
      const label = s ? (s.label || id) : id;
      const short = label.length > 46 ? label.slice(0, 44) + "…" : label;
      return s && s.url ? el("a", { href: s.url, target: "_blank", rel: "noopener", title: [s.source, s.date].filter(Boolean).join(" · ") }, short) : el("span", {}, short);
    });
    if (!xs.length) return null;
    const out = el("span", { class: "src" }, " · ");
    xs.forEach((x, i) => { if (i) out.append("; "); out.append(x); });
    return out;
  }
  const bad = (f) => f && f.ok === false ? el("span", { class: "chip warn", title: (f.problems || []).join("; ") }, "failed a check") : null;
  const li = (f, sources, lead) => el("li", {}, lead || null, f.text, " ", bad(f), srcLinks(f.source_ids, sources));

  // ---------------- the brief, per region ----------------
  function regionBlock(code, R, b, opts = {}) {
    const S = b.sources || {};
    const name = HZ.NAMES[code];
    const facts = el("div", {});
    const dev = (R && R.developments) || [];
    const wk = (R && R.week_change) || [];
    const up = (R && R.upcoming) || [];
    facts.append(el("div", { class: "row" }, el("span", { class: "chip fact" }, "Facts"), el("span", { class: "tiny" }, "since the last brief · every line cites its source")));
    if (dev.length) facts.append(el("h3", { style: "margin-top:10px" }, "What happened"), el("ul", { class: "facts" }, ...dev.map((f) => li(f, S, f.kind ? el("b", {}, (KIND[f.kind] || f.kind) + ": ") : null))));
    else facts.append(el("p", { class: "empty" }, "No material development in the data since the last brief."));
    if (wk.length) facts.append(el("h3", {}, "Versus a week ago"), el("ul", { class: "facts" }, ...wk.map((f) => li(f, S))));
    if (up.length) facts.append(el("h3", {}, "Next 30 days"), el("ul", { class: "facts" }, ...up.slice(0, opts.compact ? 4 : 30).map((e) =>
      el("li", {}, el("b", {}, HZ.dateShort(e.date) + " "), e.title, e.importance === 3 ? el("span", { class: "chip c" }, " major") : null, " ", el("span", { class: "tiny" }, HZ.inDays(e.date)), srcLinks(e.source_ids, S)))));
    const J = R && R.judgement;
    const judge = el("div", { class: "judgement" });
    judge.append(el("div", { class: "row" }, el("span", { class: "chip judge" }, "Judgement"), el("span", { class: "tiny" }, J && J.date ? "weekly, " + HZ.dateLong(J.date) + (J.verified === false ? " · some checks failed" : "") : "weekly")));
    if (!J) judge.append(el("p", { class: "empty" }, "The weekly judgement for " + name + " has not run yet. It runs on Mondays and near major catalysts."));
    else {
      const why = J.why_it_matters || [];
      if (why.length) judge.append(el("h3", { style: "margin-top:10px" }, "Why it matters"), el("ul", {}, ...why.map((w) => li(w, S, w.for ? el("b", {}, (w.for === "bonds" ? "Bonds" : w.for === "gold" ? "Gold" : "Currency") + ": ") : null))));
      const watch = J.watch || [];
      if (watch.length) judge.append(el("h3", {}, "What to watch"), el("ul", {}, ...watch.map((w) => el("li", {}, el("b", {}, (w.event || w.title || "") + (w.date ? " (" + HZ.dateShort(w.date) + ")" : "") + ": "), w.what_to_watch || w.text || ""))));
      const risks = J.risks || [];
      if (risks.length) judge.append(el("h3", {}, "Key risks"), el("ul", {}, ...risks.map((r) => li(r, S))));
      if (J.consensus || J.might_be_wrong) judge.append(el("h3", {}, "Consensus, and where it might be wrong"),
        J.consensus ? el("p", {}, el("b", {}, "Consensus: "), J.consensus.view || J.consensus.text || String(J.consensus), srcLinks(J.consensus.source_ids, S)) : null,
        J.might_be_wrong ? el("p", {}, el("b", {}, "Might be wrong because: "), typeof J.might_be_wrong === "string" ? J.might_be_wrong : J.might_be_wrong.text) : null);
      if ((J.problems || []).length) judge.append(el("details", {}, el("summary", { class: "small" }, "Checks that failed"), el("ul", { class: "small" }, ...J.problems.map((p) => el("li", {}, p)))));
    }
    HZ.ctx.add("Brief: " + name + " (" + (b.date || "") + ")", [...dev.map((f) => "Fact: " + f.text), ...wk.map((f) => "Week: " + f.text),
      ...up.slice(0, 6).map((e) => "Upcoming " + e.date + ": " + e.title), ...(J ? [...(J.why_it_matters || []).map((w) => "Judgement: " + w.text), ...(J.risks || []).map((r) => "Risk: " + r.text),
        J.consensus ? "Consensus: " + (J.consensus.view || "") : null, J.might_be_wrong ? "Might be wrong: " + (J.might_be_wrong.text || J.might_be_wrong) : null] : [])]);
    return card({ title: name, cls: "c-" + code + (opts.glow ? " glow" : ""), chips: [el("a", { class: "chip c", href: code === "GOLD" ? "#gold" : "#country/" + code }, "Open " + name + " →")] }, facts, judge);
  }

  function legacyFacts(b, code) {
    const fs = (b.facts || []).filter((f) => code === "GOLD" ? (f.country === "US" || f.country === "GLOBAL") : f.country === code);
    return { developments: fs, week_change: [], upcoming: [], judgement: null };
  }

  function briefSection(b, opts = {}) {
    const out = [];
    if (!b) return [card({ title: "The brief" }, el("p", { class: "empty" }, "No brief yet."))];
    const rep = b.report && b.report.regions;
    const top = b.top && b.top.length ? b.top : (b.facts || []).slice(0, 3);
    const head = card({ title: "Today's brief", cls: "s-home glow", chips: [el("span", { class: "chip" }, HZ.dateLong(b.date)), b.verified === false ? el("span", { class: "chip warn" }, "some checks failed") : el("span", { class: "chip fact" }, "facts checked")] },
      top.length ? el("ul", { class: "facts" }, ...top.map((f) => li(f, b.sources))) : el("p", { class: "empty" }, b.status === "no_ai" ? "The AI brief did not run today: " + ((b.judgement && b.judgement.why) || "") : "Nothing material changed."),
      explain({ what: "A daily brief written in two halves. Facts: what changed in the data, each line with its source, checked so every number matches the data. Judgement: a weekly opinion on why it matters, what to watch and the risks, kept apart from the facts.",
        how: "Read the facts first; they are not opinions. Then read the judgement as one well-informed view, which can be wrong. Tap a source to check it.",
        now: top.length ? "Start with " + (rep ? "the country you hold a view or trade on" : "the first line") + ". " + (b.judgement && b.judgement.ran ? "The judgement was refreshed today." : "The judgement shown is from " + HZ.dateLong((b.judgement && b.judgement.date) || b.date) + ".") : null }),
      el("div", { class: "btns" }, el("a", { class: "btn small", href: "#brief" }, "Archive"), b.cost ? el("span", { class: "tiny" }, "AI cost this month: $" + fmt(b.cost.month_usd, 2) + " of the $" + fmt(b.cost.cap_usd, 0) + " cap") : null));
    out.push(head);
    HZ.ctx.add("Brief headline (" + b.date + ")", top.map((f) => f.text));
    REGIONS.forEach((r) => out.push(regionBlock(r, rep ? rep[r] : legacyFacts(b, r), b, opts)));
    return out;
  }
  HZ.briefSection = briefSection;
  HZ.regionBlock = regionBlock;

  // ---------------- country cards ----------------
  function viewLine(v) {
    if (!v) return el("span", { class: "view" }, "No view yet");
    const parts = Object.entries(v).filter(([, x]) => x && x.lean).map(([asset, x]) => (asset === "bond" ? "Bond: " : asset === "currency" ? "Currency: " : "Gold: ") + (LEAN[x.lean] || x.lean) + (x.p ? " (" + Math.round(x.p * (x.p <= 1 ? 100 : 1)) + "%)" : ""));
    return el("span", { class: "view" }, parts.join(" · ") || "No view");
  }
  function countryCards(summary, views, cal, gold) {
    const tiles = {}; ((summary && summary.tiles) || []).forEach((t) => (tiles[t.key] = t));
    const next = (c) => ((cal && cal.events) || []).filter((e) => e.country === c && e.date >= HZ.today() && e.importance >= 2)[0];
    const cards = REGIONS.map((c) => {
      const v = views && views.views && views.views[c];
      let status = [];
      if (c === "GOLD") {
        const g = gold && gold.prices && gold.prices.gold;
        status = g ? [el("div", { class: "big num" }, "$" + fmt(g.value, 0)), el("div", { class: "small" }, "an ounce · ", HZ.chg(g.chg_1w_pct, 1, "%"), " this week")] : [el("div", { class: "small muted" }, "Gold prices arrive with the next data run.")];
      } else {
        status = (TILE[c] || []).map((k) => tiles[k]).filter(Boolean).map((t) => el("div", { class: "small" }, el("b", {}, t.label + " "), el("span", { class: "num" }, fmt(t.level, t.unit_change === "pct" ? 2 : 2)), " ", HZ.chg(t.chg_1w, t.unit_change === "pct" ? 1 : 0, t.unit_change === "pct" ? "%" : "bp"), el("span", { class: "tiny" }, " 1w")));
      }
      const ev = c === "GOLD" ? ((gold && gold.upcoming) || []).find((e) => e.date >= HZ.today()) : next(c);
      HZ.ctx.add("Status: " + HZ.NAMES[c], [...status.map((s) => s.textContent), v ? "Horizons' view: " + viewLine(v).textContent : null, ev ? "Next: " + ev.title + " on " + ev.date : null]);
      return el("a", { class: "card pop ccard c-" + c, href: c === "GOLD" ? "#gold" : "#country/" + c, style: "margin:0" },
        el("div", { class: "row spread" }, el("h2", { style: "margin:0" }, HZ.NAMES[c]), el("span", { class: "chip c" }, "Open →")),
        el("div", { class: "stack", style: "margin-top:8px" }, ...status, viewLine(v),
          ev ? el("div", { class: "small" }, el("b", {}, "Next: "), ev.title, " · ", HZ.dateShort(ev.date), " (", HZ.inDays(ev.date), ")") : el("div", { class: "tiny" }, "No major event in the calendar yet.")));
    });
    return el("section", {}, el("div", { class: "grid2" }, ...cards),
      explain({ what: "One card per market Horizons follows: the latest levels, Horizons' weekly view and the next important event.",
        how: "Currency pairs read 'how many local units per dollar' (except EUR/USD). A + change in USD/BRL or USD/MXN means the local currency weakened. Bond figures are yields: up means prices fell.",
        now: views && views.date ? "Views were last set on " + HZ.dateLong(views.date) + ". Tap a card for the full story, the history and what each school of economics would say." : "Horizons' first weekly view arrives with the next weekly judgement." }));
  }

  // ---------------- nearest catalyst without a call ----------------
  function nearestUncalled(cal, judg, scen) {
    const called = new Set(((judg && judg.questions) || []).map((q) => q.question_id).filter(Boolean));
    const scByEvent = {}; ((scen && scen.scenarios) || []).forEach((s) => { if (s.event) scByEvent[s.event.id] = s; });
    const ev = ((cal && cal.events) || []).filter((e) => e.date >= HZ.today() && e.importance >= 3 && !called.has(e.id) && !called.has("ev:" + e.id) && !(scByEvent[e.id] && called.has("sc:" + scByEvent[e.id].id)))[0];
    if (!ev) return card({ title: "Your next call", cls: "s-cal" }, el("p", {}, "Every major catalyst in the calendar has a call from you. Nice."));
    const s = scByEvent[ev.id];
    const d = HZ.daysUntil(ev.date);
    HZ.ctx.add("Nearest catalyst without my call", [ev.title + " (" + HZ.NAMES[ev.country] + ") on " + ev.date + ", in " + d + " days", ev.base_rate ? "Base rate: " + ev.base_rate.text : null]);
    return card({ title: "Your next call", cls: "s-cal glow", chips: [el("span", { class: "chip c" }, HZ.NAMES[ev.country] || ev.country)] },
      el("div", { class: "row" }, HZ.ring(Math.max(0, 1 - d / 30), d + "d", { size: 72, title: d + " days to go" }),
        el("div", {}, el("h3", { style: "margin:0" }, ev.title), el("div", { class: "small muted" }, HZ.dateLong(ev.date), " · ", HZ.inDays(ev.date), " · ", ev.status))),
      ev.base_rate ? el("p", { class: "small" }, el("b", {}, "Base rate: "), ev.base_rate.text) : null,
      el("div", { class: "btns" }, s ? el("a", { class: "btn soft", href: "#scenarios/" + s.id }, "See the scenarios") : null,
        HZ.callBtn({ title: ev.title, question: ev.title + ": ", question_id: s ? "sc:" + s.id : ev.id, resolution_date: ev.date, base_rate: ev.base_rate && ev.base_rate.text })),
      explain({ what: "The closest major (importance 3) event you have not made a call on yet.",
        how: "The ring fills as the date gets closer (full = today). A call is a probability with your reasons; it gets scored when the event resolves.",
        now: d <= 3 ? "It is " + HZ.inDays(ev.date) + ": if you want this one on your record, make the call now." : "You have " + d + " days. Start from the base rate, then adjust for what is different this time." }));
  }

  // ---------------- open trades ----------------
  function openTrades(book) {
    const open = ((book && book.trades) || []).filter((t) => t.status === "open" || t.status === "pending");
    const eq = book && book.equity;
    HZ.ctx.add("My open paper trades", open.map((t) => `${t.trade_id}: ${t.open.direction} ${t.open.instrument}` + (t.pnl ? `, P&L $${fmt(t.pnl.total, 0)} (price ${fmt(t.pnl.price, 0)}, carry ${fmt(t.pnl.carry, 0)}, cost ${fmt(t.pnl.cost, 0)})` : ", waiting to fill")));
    return card({ title: "Open paper trades", cls: "s-rec", chips: [eq ? el("span", { class: "chip" }, "Book: ", HZ.pnl(eq.pnl_usd, 0)) : null] },
      open.length ? el("div", { class: "scroll" }, el("table", {}, el("thead", {}, el("tr", {}, el("th", {}, "Trade"), el("th", { class: "r" }, "P&L"), el("th", { class: "r" }, "Price"), el("th", { class: "r" }, "Carry"), el("th", { class: "r" }, "Costs"))),
        el("tbody", {}, ...open.map((t) => el("tr", {}, el("td", {}, el("b", {}, (t.open.direction || "") + " " + t.open.instrument), el("div", { class: "tiny" }, t.trade_id + (t.fill ? " · since " + t.fill.entry_date : " · fills at the next close"))),
          el("td", { class: "r" }, HZ.pnl(t.pnl && t.pnl.total)), el("td", { class: "r" }, HZ.pnl(t.pnl && t.pnl.price)), el("td", { class: "r" }, HZ.pnl(t.pnl && t.pnl.carry)), el("td", { class: "r" }, HZ.pnl(t.pnl && t.pnl.cost)))))))
        : el("p", { class: "empty" }, "No open paper trades. Open one from a country page or the Gold page: it's free, uses real prices and teaches a lot."),
      el("div", { class: "btns" }, el("a", { class: "btn soft", href: "#record" }, "Portfolio and record")),
      explain({ what: "Your paper trades: pretend positions tracked with real prices, interest (carry) and trading costs.",
        how: "P&L is split three ways: price (the market moved), carry (interest earned or paid while holding) and costs (the spread paid to get in and out). Green with + is a gain, red with − a loss.",
        now: open.length ? (open.some((t) => t.pnl && t.pnl.carry < 0) ? "At least one trade is paying carry: it needs the price to move your way to make money." : "Check each thesis still holds; close what no longer makes sense.") : "Try one small trade on your strongest view, with a stop." }));
  }

  function reminders(r) {
    const open = (r && r.open) || [];
    if (!open.length) return null;
    return card({ title: "Reminders (" + open.length + ")", cls: "s-help" }, el("ul", {}, ...open.slice(0, 6).map((x) => el("li", {}, x.url ? el("a", { href: x.url, target: "_blank", rel: "noopener" }, x.title) : x.title))),
      el("p", { class: "tiny" }, "Also in your GitHub notifications. Each closes itself when its condition clears."));
  }

  // ---------------- pages ----------------
  HZ.pageHome = function () {
    HZ.ctx.reset("Home", "Given this brief and my positions, what are the two or three things I should think hardest about this week, and what would change your mind?");
    return Promise.all(["brief/latest.json", "summary.json", "horizons/views.json", "calendar.json", "gold.json", "book/state.json", "book/judgements.json", "scenarios.json", "book/reminders.json"].map(maybe))
      .then(([b, summary, views, cal, gold, book, judg, scen, rem]) => {
        const hello = el("div", { class: "phead s-home" }, el("h1", {}, greeting()), el("p", { class: "sub" }, HZ.dateLong(HZ.today()) + " · Brazil, Mexico, France and gold, explained"));
        return [hello, countryCards(summary, views, cal, gold), el("div", { style: "height:16px" }), nearestUncalled(cal, judg, scen), reminders(rem), openTrades(book), ...briefSection(b),
          el("div", { class: "btns", style: "justify-content:center;margin:8px 0 24px" }, HZ.askBtn("Ask Claude about today"))];
      });
  };
  function greeting() { const h = new Date().getHours(); return h < 5 ? "Good night" : h < 12 ? "Good morning" : h < 18 ? "Good afternoon" : "Good evening"; }

  HZ.pageBrief = function (date) {
    if (!date) {
      HZ.ctx.reset("Brief archive");
      return maybe("brief/index.json").then((ix) => [HZ.pageHead("Brief archive", "Every daily brief, newest first.", "s-home"),
        card({ title: "Briefs" }, (ix || []).length ? el("ul", {}, ...ix.map((e) => el("li", {}, el("a", { href: "#brief/" + e.date }, HZ.dateLong(e.date)), " · ", e.n_facts + " facts", e.judgement ? " · judgement" : "", e.verified === false ? " · some checks failed" : "")))
          : el("p", { class: "empty" }, "No briefs yet."))]);
    }
    HZ.ctx.reset("Brief of " + date);
    return maybe("brief/briefs/" + date + ".json").then((b) => [HZ.pageHead("Brief of " + HZ.dateLong(date), "Facts and judgement, per country and for gold.", "s-home"), ...briefSection(b)]);
  };
})();
