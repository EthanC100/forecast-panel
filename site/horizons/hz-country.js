/* Horizons country pages (Brazil, Mexico, France): the full policy playbook. The story now (the
   brief, facts apart from judgement), the government's approach, what happened last time, what each
   school would say, everything Catalyst shows for the country (each explained), and Horizons' view.
   Shared helpers (HZ.cx) are also used by hz-gold.js. */
(function () {
  "use strict";
  const { el, fmt } = HZ;
  const nn = HZ.nn;

  // ---------------- shared helpers ----------------
  const cx = HZ.cx = {};
  const INSTR = {
    BR: { fx: "USDBRL", fxTile: "usdbrl", bond: "BR10Y", bondTile: "br10y", cur: "real", pair: "USD/BRL", inverted: false },
    MX: { fx: "USDMXN", fxTile: "usdmxn", bond: "MX10Y", bondTile: "mx10y", cur: "peso", pair: "USD/MXN", inverted: false },
    FR: { fx: "EURUSD", fxTile: "eurusd", bond: "OATBUND", bondTile: "oatbund", cur: "euro", pair: "EUR/USD", inverted: true },
  };
  cx.INSTR = INSTR;
  const ISO3 = { BR: "BRA", MX: "MEX", FR: "FRA" };
  cx.sources = {};
  /** Source links for a list of ids, looked up in the brief's (or views') source map. */
  cx.src = (ids, map) => {
    const list = nn(ids).filter((v, i, a) => a.indexOf(v) === i);
    if (!list.length) return null;
    const m = map || cx.sources;
    return el("div", { class: "src" }, "Sources: ", ...list.map((id, i) => {
      const s = m[id];
      const lab = s ? (s.label || id) + (s.date ? " (" + String(s.date).slice(0, 10) + ")" : "") : id;
      return [i ? " · " : "", s && s.url ? el("a", { href: s.url, target: "_blank", rel: "noopener" }, lab) : el("span", {}, lab)];
    }));
  };
  /** A citation list: [{label|author,title,year,url,date}]. */
  cx.cites = (list, lead) => {
    const xs = nn(list);
    if (!xs.length) return null;
    return el("div", { class: "src" }, (lead || "Sources") + ": ", ...xs.map((c, i) => {
      if (typeof c === "string") return [i ? " · " : "", /^https?:/.test(c) ? el("a", { href: c, target: "_blank", rel: "noopener" }, c.replace(/^https?:\/\/(www\.)?/, "").slice(0, 48)) : c];
      const lab = c.label || nn([c.author, c.title ? "“" + c.title + "”" : null, c.year]).join(", ") || c.url;
      const tail = c.date && !c.label ? "" : c.date ? " (" + c.date + ")" : "";
      return [i ? " · " : "", c.url ? el("a", { href: c.url, target: "_blank", rel: "noopener" }, lab + tail) : lab + tail];
    }));
  };
  cx.factChip = () => el("span", { class: "chip fact", title: "A sourced fact, checked against its source" }, "Fact");
  cx.judgeChip = () => el("span", { class: "chip judge", title: "A model's judgement, not a fact" }, "Judgement");
  cx.viewChip = () => el("span", { class: "chip view", title: "Horizons' view, not financial advice" }, "Horizons' view");
  cx.kindChip = (k) => k ? el("span", { class: "chip" }, String(k).replace(/_/g, " ")) : null;
  cx.list = (items, render, empty) => items && items.length ? el("ul", { class: "facts" }, ...items.map((x) => el("li", {}, render(x)))) : el("p", { class: "empty" }, empty || "Nothing new.");
  cx.factItem = (f, map) => [f.text, " ", cx.kindChip(f.kind), f.ok === false ? el("span", { class: "chip warn" }, "unverified") : null, cx.src(f.source_ids, map)];
  cx.tileBy = (summary, key) => (summary && summary.tiles || []).find((t) => t.key === key);
  cx.anchor = (id) => { const t = document.getElementById(id); if (t) { t.scrollIntoView({ behavior: "smooth", block: "start" }); t.classList.add("glow"); setTimeout(() => t.classList.remove("glow"), 2400); } };
  cx.jump = (items) => el("nav", { class: "tabs", "aria-label": "On this page" }, ...items.map(([id, lab]) => el("button", { type: "button", onclick: () => cx.anchor(id) }, lab)));
  /** "Will X be lower/higher on D than V?" for a view, so my probability and Horizons' are on the same question. */
  cx.viewQuestion = (v, label, wantUp) => {
    const dir = wantUp ? "higher" : "lower";
    return `Will ${label} be ${dir} on ${v.horizon_end || "the horizon date"} than ${v.entry_value != null ? fmt(v.entry_value, Math.abs(v.entry_value) < 20 ? 4 : 2) : "at the view date"}?`;
  };
  /** My latest probability on a question id (book/judgements.json), or null. */
  cx.myCall = (judg, qid) => {
    const q = (judg && judg.questions || []).find((x) => x.question_id === qid || x.key === qid);
    if (!q || !q.forecasts || !q.forecasts.length) return null;
    const f = q.forecasts[q.forecasts.length - 1];
    return { prob: f.prob, date: (f.submitted_at || "").slice(0, 10), q };
  };
  /** The lean in plain words, e.g. "Lean long the real" / "No view". */
  cx.leanText = (v, asset, code) => {
    if (!v || !v.lean || v.lean === "none") return "No view";
    const what = asset === "gold" ? "gold" : asset === "bond" ? (code === "FR" ? "French bonds (vs Germany)" : "the bond") : "the " + (INSTR[code] ? INSTR[code].cur : "currency");
    return "Lean " + v.lean + " " + what;
  };
  /** Horizons' view card for one asset (bond, currency or gold). */
  cx.viewBox = (o) => {
    const { v, asset, code, date, judg, label, wantUp, srcMap, tradeInstr, episodeLink } = o;
    if (!v) return el("div", { class: "viewbox" }, el("div", { class: "lean" }, "No view yet"), el("p", { class: "small muted" }, "Horizons writes a view every week with the judgement. The first one appears after the next weekly run."));
    const qid = "hz:" + code + "." + asset + "." + date;
    const mine = cx.myCall(judg, qid);
    const p = v.p != null ? (v.p > 1 ? v.p / 100 : v.p) : null;
    const rings = el("div", { class: "row" },
      p != null ? el("div", { style: "text-align:center" }, HZ.ring(p, HZ.pct(p), { size: 72, title: "Horizons: " + HZ.pct(p) + " chance it moves the leaned way" }), el("div", { class: "tiny" }, "Horizons")) : null,
      mine ? el("div", { style: "text-align:center" }, HZ.ring(mine.prob, HZ.pct(mine.prob), { size: 72, cls: "s-rec", title: "You: " + HZ.pct(mine.prob) }), el("div", { class: "tiny" }, "You (" + mine.date + ")")) : null,
      el("div", { class: "small", style: "flex:1;min-width:160px" },
        p != null ? ["Horizons gives ", el("b", {}, HZ.pct(p)), " that ", label, " moves the leaned way by ", el("b", {}, v.horizon_end || "–"), ". "] : null,
        v.confidence ? ["Confidence: ", el("b", {}, v.confidence), ". "] : null,
        v.horizon_weeks ? ["Horizon: about " + v.horizon_weeks + " weeks."] : null));
    const box = el("div", { class: "viewbox" },
      el("div", { class: "row spread" }, el("div", { class: "lean" }, cx.leanText(v, asset, code)), cx.viewChip()),
      v.meaning ? el("p", { class: "small muted" }, v.meaning) : null,
      rings,
      v.reasons && v.reasons.length ? [el("h3", { style: "margin-top:12px" }, "Why"), el("ul", {}, ...v.reasons.map((r) => el("li", {}, typeof r === "string" ? r : r.text, typeof r === "string" ? null : cx.src(r.source_ids, srcMap))))] : null,
      v.resembles && (v.resembles.episode_id || v.resembles.why) ? el("p", { class: "small" }, el("b", {}, "Most resembles: "),
        v.resembles.episode_id ? (episodeLink ? episodeLink(v.resembles.episode_id) : v.resembles.episode_id) : "", v.resembles.why ? " — " + v.resembles.why : "") : null,
      v.main_risk ? el("p", { class: "small" }, el("b", {}, "Main risk: "), v.main_risk) : null,
      v.would_change ? el("p", { class: "small" }, el("b", {}, "What would change it: "), v.would_change) : null,
      v.ok === false ? el("p", { class: "tiny" }, el("span", { class: "chip warn" }, "check"), " This view failed a validation check: ", (v.problems || []).join("; ")) : null,
      el("div", { class: "btns" },
        HZ.callBtn({ title: (mine ? "Update: " : "") + cx.viewQuestion(v, label, wantUp), question: cx.viewQuestion(v, label, wantUp), question_id: qid, resolution_date: v.horizon_end,
          base_rate: p != null ? "Horizons' view: " + HZ.pct(p) + " (" + date + ")" : null }, mine ? "Update my call" : "Make a call on this"),
        tradeInstr ? HZ.tradeBtn(tradeInstr, { link: qid, horizon: v.horizon_end, thesis: cx.leanText(v, asset, code) + " (Horizons' view " + date + ")" }) : null),
      el("p", { class: "disclaim" }, "Horizons' view, not financial advice. Written by a model from the sourced facts, checked by the brief's rules, and scored in the track record like any forecaster."));
    return box;
  };
  cx.ctxView = (v, asset, code, label) => v ? cx.leanText(v, asset, code) + (v.p != null ? `, ${HZ.pct(v.p > 1 ? v.p / 100 : v.p)} that ${label} moves that way by ${v.horizon_end}` : "") + (v.confidence ? ` (confidence ${v.confidence})` : "") + (v.main_risk ? `. Main risk: ${v.main_risk}` : "") : null;
  /** Value of an outcome cell, tolerating {value, source} objects. */
  const cell = (x) => x == null ? null : typeof x === "object" ? x.value : x;
  cx.cell = cell;

  /** Series chart card with what/how/now. */
  cx.seriesCard = (o) => HZ.lazy(() => HZ.series(o.series).then((s) => {
    const rows = s.history.map((r) => [r[0], r[1]]);
    const st = HZ.stats(rows);
    const unit = o.unit || s.unit || "";
    const d = o.decimals != null ? o.decimals : (st && Math.abs(st.last) < 20 ? 3 : 2);
    const nowTxt = st ? `${o.name} is ${fmt(st.last, d)} ${unit} (${HZ.dateLong(st.date)}): ${st.m1 != null ? (st.last >= st.m1 ? "up " : "down ") + fmt(Math.abs(st.last - st.m1), d) + " in a month, " : ""}${HZ.zWords(st.z)}` +
      ` (z-score ${HZ.signed(st.z, 1)}). Over the past year it ranged ${fmt(st.lo, d)} to ${fmt(st.hi, d)}. ${o.nowExtra ? o.nowExtra(st) : ""}` : "No data yet.";
    HZ.ctx.add("Key data", st ? `${o.name}: ${fmt(st.last, d)} ${unit} on ${st.date}; 1 month ago ${st.m1 != null ? fmt(st.m1, d) : "–"}; 1-year z-score ${HZ.signed(st.z, 1)}` : null);
    return HZ.card({ title: o.title || o.name, cls: o.cls || "" },
      HZ.lineChart(rows, { unit, decimals: d, name: o.name, events: o.events }),
      o.note ? el("details", { class: "tiny" }, el("summary", {}, "About this series"), el("p", {}, o.note)) : null,
      HZ.explain({ what: o.what || `${s.name}, ${unit}, from ${s.source}${s.first ? " since " + s.first.slice(0, 4) : ""}.`, how: o.how, now: nowTxt }),
      HZ.source(s.source + (s.source_id ? " · " + s.source_id : ""), s.source_url, s.last));
  }));
  cx.howFor = (series, unit, code) => {
    const u = (unit || "").toLowerCase();
    if (/brl per usd|mxn per usd/.test(u)) return `Up means one dollar buys more ${INSTR[code] ? INSTR[code].cur + "s" : "local currency"}: the local currency is weaker. Down means it is stronger.`;
    if (/usd per eur|eur\/usd/.test(u) || series === "eu.eurusd") return "Up means the euro is stronger against the dollar.";
    if (/bp/.test(u)) return "This is a gap between two yields in basis points. Up means investors demand more extra yield: more worry. Down means less.";
    if (/%|p\.a\./.test(u)) return "This is a yield or rate. Up means borrowing is more expensive and existing bond prices fell; down means the reverse.";
    return "Read the line left to right; touch it to see any day's value. The dot is the latest reading.";
  };

  // ---------------- the page ----------------
  HZ.pageCountry = function (code) {
    code = (code || "BR").toUpperCase();
    if (!INSTR[code]) code = "BR";
    const I = INSTR[code], name = HZ.NAMES[code];
    HZ.ctx.reset(name, `Given ${name}'s situation on this page, what is the strongest case for and against Horizons' view on the ${I.cur} and the bond over the next 1-3 months?`);
    return Promise.all([HZ.json("summary.json"), HZ.maybe("brief/latest.json"), HZ.maybe("horizons/views.json"), HZ.maybe("book/judgements.json"), HZ.maybe("playbook.json")])
      .then(([summary, brief, views, judg, pb]) => {
        cx.sources = Object.assign({}, brief && brief.sources || {}, views && views.sources || {});
        const C = summary.countries[code] || {};
        const page = el("div", { class: "c-" + code });
        page.appendChild(hero(code, summary, C, views, brief));
        page.appendChild(cx.jump([["sec-story", "The story"], ["sec-approach", "Approach"], ["sec-history", "Last time"], ["sec-schools", "Schools"], ["sec-markets", "Markets"],
          ["sec-econ", "Economists"], ["sec-drivers", "Drivers"], ["sec-scen", "Scenarios"], ["sec-view", "Horizons' view"]]));
        page.appendChild(story(code, brief));
        page.appendChild(approach(code, pb));
        page.appendChild(history(code, pb, views));
        page.appendChild(schools(code, pb));
        page.appendChild(el("h2", { id: "sec-markets", style: "margin:26px 0 10px" }, "Everything on ", name));
        page.appendChild(el("p", { class: "muted small noterm" }, "Markets, economists, drivers, scenarios and crowd signals: the same data as the Catalyst app, explained."));
        (C.charts || []).forEach((c) => page.appendChild(cx.seriesCard({ series: c.series, name: c.name, unit: c.unit, how: cx.howFor(c.series, c.unit, code),
          note: c.proxy_note ? "Proxy: " + c.proxy_note : null, what: `${c.name} (${c.unit}). ${c.proxy ? "This is a proxy: a close stand-in for the real market rate." : ""}` })));
        page.appendChild(HZ.lazy(() => fiscalGap(code, C)));
        if (code === "FR" && C.ratings) page.appendChild(ratings(C.ratings));
        page.appendChild(HZ.lazy(() => surveysCot(code, C)));
        page.appendChild(el("div", { id: "sec-econ" }));
        page.appendChild(HZ.lazy(() => HZ.maybe("consensus.json").then((cs) => consensus(code, cs, judg))));
        page.appendChild(HZ.lazy(() => Promise.all([HZ.maybe("assessments.json"), HZ.maybe("consensus.json")]).then(([a, cs]) => assessments(code, a || (cs && cs.assessments)))));
        page.appendChild(HZ.lazy(() => HZ.maybe("consensus.json").then((cs) => policies(code, cs))));
        page.appendChild(el("div", { id: "sec-drivers" }));
        page.appendChild(HZ.lazy(() => HZ.maybe("drivers.json").then((d) => drivers(code, d))));
        page.appendChild(HZ.lazy(() => HZ.maybe("teach.json").then((t) => emModel(code, t))));
        page.appendChild(HZ.lazy(() => HZ.maybe("teach.json").then((t) => whatIf(code, t))));
        page.appendChild(HZ.lazy(() => HZ.maybe("teach.json").then((t) => eventStudy(code, t))));
        page.appendChild(el("div", { id: "sec-scen" }));
        page.appendChild(HZ.lazy(() => HZ.maybe("scenarios.json").then((s) => scenarios(code, s))));
        page.appendChild(HZ.lazy(() => crowd(code, summary)));
        page.appendChild(markets(code, C));
        page.appendChild(viewSection(code, views, judg, summary, pb));
        myCalls(code, judg);
        page.appendChild(el("div", { class: "btns", style: "margin:8px 0 20px" }, HZ.askBtn("Ask Claude about " + name)));
        return page;
      });
  };

  function hero(code, summary, C, views, brief) {
    const I = INSTR[code];
    const fx = cx.tileBy(summary, I.fxTile), bond = cx.tileBy(summary, I.bondTile);
    const tile = (t) => t ? el("div", { class: "card", style: "margin:0;padding:14px" },
      el("div", { class: "label noterm" }, t.label), el("div", { class: "num", style: "font-size:1.5rem;font-weight:800" }, fmt(t.level, t.decimals != null ? Math.min(t.decimals, 4) : 2)),
      el("div", { class: "small" }, "1 week ", HZ.chg(t.chg_1w, t.unit_change === "pct" ? 2 : 0, t.unit_change === "pct" ? "%" : "bp"), " · 1 month ", HZ.chg(t.chg_1m, t.unit_change === "pct" ? 2 : 0, t.unit_change === "pct" ? "%" : "bp")),
      el("div", { class: "tiny noterm" }, t.unit, " · ", t.as_of)) : null;
    const v = views && views.views && views.views[code] || {};
    const today = HZ.today();
    const evs = (C.events || []).filter((e) => e.date >= today).sort((a, b) => (b.importance - a.importance) || a.date.localeCompare(b.date));
    const next = evs.filter((e) => e.importance === 3)[0] || evs[0];
    if (fx) HZ.ctx.add("Key data", `${fx.label}: ${fx.level} (${fx.unit}) on ${fx.as_of}; 1 week ${HZ.signed(fx.chg_1w, 2)}%, 1 month ${HZ.signed(fx.chg_1m, 2)}%`);
    if (bond) HZ.ctx.add("Key data", `${bond.label}: ${bond.level} (${bond.unit}) on ${bond.as_of}; 1 week ${HZ.signed(bond.chg_1w, 2)}, 1 month ${HZ.signed(bond.chg_1m, 2)}`);
    if (next) HZ.ctx.add("Key data", `Next catalyst: ${next.title} on ${next.date} (importance ${next.importance})`);
    const status = brief && brief.report && brief.report.regions && brief.report.regions[code] && brief.report.regions[code].judgement && brief.report.regions[code].judgement.status;
    return el("div", {},
      HZ.pageHead(HZ.NAMES[code], `Its ${I.cur}, its government bonds and the policies behind them, explained.`, "c-" + code),
      status ? el("p", { class: "small" }, el("b", {}, "Status: "), status) : null,
      el("div", { class: "row", style: "margin-bottom:12px" },
        el("a", { class: "chip view", href: "#", onclick: (e) => { e.preventDefault(); cx.anchor("sec-view"); } }, "Bond: ", cx.leanText(v.bond, "bond", code)),
        el("a", { class: "chip view", href: "#", onclick: (e) => { e.preventDefault(); cx.anchor("sec-view"); } }, "Currency: ", cx.leanText(v.currency, "currency", code))),
      el("div", { class: "grid2" }, tile(fx), tile(bond)),
      next ? el("article", { class: "card pop glow", style: "margin-top:14px" }, el("div", { class: "label" }, "Next big event"), el("h3", { style: "margin:4px 0" }, next.title),
        el("p", { class: "small", style: "margin:0" }, HZ.dateLong(next.date), " · ", HZ.inDays(next.date), " · importance ", next.importance, " of 3", next.status === "estimated" ? " · date estimated" : ""),
        HZ.callBtn({ title: next.title, question: next.title + ": ", question_id: next.id, resolution_date: next.date, base_rate: next.base_rate && next.base_rate.text }, "Make a call", "primary small")) : null);
  }

  function story(code, brief) {
    const R = brief && brief.report && brief.report.regions && brief.report.regions[code];
    const map = cx.sources;
    const body = [];
    if (R) {
      const J = R.judgement || {};
      const watchFor = (u) => (J.watch || []).find((w) => (w.event || "").includes(u.title) || (w.event || "").includes(u.date) || (u.event_id && w.event_id === u.event_id));
      body.push(el("div", { class: "row" }, cx.factChip(), el("span", { class: "tiny" }, "From the daily brief, " + (brief.report.date || brief.date) + ". Every fact is checked against its source.")));
      body.push(el("h3", { style: "margin-top:10px" }, "What happened"), cx.list(R.developments, (f) => cx.factItem(f, map), "No material development since the last brief."));
      body.push(el("h3", {}, "Versus a week ago"), cx.list(R.week_change, (f) => cx.factItem(f, map), "No week-on-week comparison yet."));
      body.push(el("h3", {}, "Next 30 days"), cx.list(R.upcoming, (u) => { const w = watchFor(u); return [el("b", {}, HZ.dateShort(u.date)), " ", u.title, u.importance ? " · importance " + u.importance : "", w ? el("div", { class: "small" }, cx.judgeChip(), " Watch for: ", w.what_to_watch) : null]; }, "No dated events in the next 30 days."));
      body.push(el("hr", { class: "soft" }), el("div", { class: "row" }, cx.judgeChip(), el("span", { class: "tiny" }, J.date ? "Weekly judgement, " + J.date + (J.verified === false ? " (some checks failed)" : "") : "No judgement yet")));
      if (J.why_it_matters && J.why_it_matters.length) body.push(el("div", { class: "judgement" }, el("h3", {}, "Why it matters"), el("ul", {}, ...J.why_it_matters.map((w) => el("li", {}, w.for ? el("b", {}, "For " + w.for + ": ") : null, w.text, cx.src(w.source_ids, map))))));
      if (J.risks && J.risks.length) body.push(el("div", { class: "judgement" }, el("h3", {}, "Key risks"), el("ul", {}, ...J.risks.map((w) => el("li", {}, w.text || w, cx.src(w.source_ids, map))))));
      if (J.consensus || J.might_be_wrong) body.push(el("div", { class: "judgement" }, el("h3", {}, "Consensus, and where it might be wrong"),
        J.consensus ? el("p", {}, el("b", {}, "Consensus: "), J.consensus.view || J.consensus, cx.src(J.consensus.source_ids, map)) : null,
        J.might_be_wrong ? el("p", {}, el("b", {}, "Where it might be wrong: "), J.might_be_wrong) : null));
      (R.developments || []).slice(0, 8).forEach((f) => HZ.ctx.add("Brief: what happened (facts)", f.text));
      (R.week_change || []).slice(0, 5).forEach((f) => HZ.ctx.add("Brief: versus a week ago (facts)", f.text));
      (J.why_it_matters || []).forEach((w) => HZ.ctx.add("Brief: why it matters (judgement)", (w.for ? w.for + ": " : "") + w.text));
      (J.risks || []).forEach((w) => HZ.ctx.add("Brief: key risks (judgement)", w.text || w));
      if (J.might_be_wrong) HZ.ctx.add("Brief: where consensus might be wrong (judgement)", J.might_be_wrong);
    } else {
      const facts = (brief && brief.facts || []).filter((f) => f.country === code);
      body.push(el("div", { class: "row" }, cx.factChip(), el("span", { class: "tiny" }, brief ? "From the brief of " + brief.date : "No brief yet")));
      body.push(cx.list(facts, (f) => cx.factItem(f, map), "The full country section of the brief appears after its next run."));
      facts.forEach((f) => HZ.ctx.add("Brief (facts)", f.text));
    }
    const n = R ? (R.developments || []).length : 0;
    const up = R && (R.upcoming || [])[0];
    return HZ.card({ title: "The story: politics and economy now", id: "sec-story", cls: "c-" + code }, ...body,
      HZ.explain({ what: "The country's section of the daily brief: what changed, how it compares with a week ago and what is coming, then a weekly judgement on why it matters.",
        how: "Blue “Fact” items are checked against the source linked under each one; nothing is written from memory. Violet “Judgement” items are a model's reading of those facts: useful, but opinion.",
        now: R ? `${n} development${n === 1 ? "" : "s"} in the latest brief.${up ? ` Next on the calendar: ${up.title} on ${HZ.dateLong(up.date)} (${HZ.inDays(up.date)}).` : ""}` : "The comprehensive section has not run yet; showing the short brief." }));
  }

  function approach(code, pb) {
    const A = pb && pb.countries && pb.countries[code] && pb.countries[code].approach;
    if (!A) return HZ.card({ title: "The government's approach", id: "sec-approach" }, el("p", { class: "empty" }, "The policy playbook is built with the next data run."));
    const pols = A.policies || [];
    pols.forEach((p) => HZ.ctx.add("Government approach", `${p.name}: position ${p.position}/100 (0 interventionist/Keynesian, 100 orthodox/monetarist). ${p.why || ""}`));
    const avg = pols.length ? pols.reduce((s, p) => s + (+p.position || 0), 0) / pols.length : null;
    return HZ.card({ title: "The government's approach", id: "sec-approach", cls: "c-" + code },
      A.summary ? el("p", {}, A.summary) : null,
      ...pols.map((p) => el("div", { style: "margin:14px 0 6px" },
        el("h3", { style: "margin-bottom:2px" }, p.name),
        el("div", { class: "scale noterm", role: "img", "aria-label": `${p.name}: ${p.position} on a 0 (interventionist, Keynesian) to 100 (orthodox, monetarist) scale` },
          el("div", { class: "track" }), el("div", { class: "pin", style: `left:${Math.max(0, Math.min(100, +p.position || 0))}%` }),
          el("div", { class: "ends" }, el("span", {}, "Interventionist / Keynesian"), el("span", {}, "Orthodox / monetarist"))),
        p.why ? el("p", { class: "small" }, p.why) : null, cx.cites(p.sources))),
      HZ.explain({ what: "The main live policies and where each sits between two broad approaches: the state steering demand and prices (left) and rules-based, market-led policy (right).",
        how: "The pin's place is a characterisation, sourced underneath. Neither end is “right”: each school below argues for its side. Look at whether policies point the same way or pull against each other.",
        now: avg != null ? `Across ${pols.length} policies the average sits at ${fmt(avg, 0)} of 100: ${avg < 40 ? "leaning interventionist" : avg > 60 ? "leaning orthodox" : "a mix of the two"}.${pols.length > 1 ? ` The most orthodox is “${pols.slice().sort((a, b) => b.position - a.position)[0].name}”, the most interventionist “${pols.slice().sort((a, b) => a.position - b.position)[0].name}”.` : ""}` : null }));
  }

  function outcomeTable(ep) {
    const O = ep.outcomes || {}, S = ep.outcome_sources || {};
    const rows = [["inflation", "Inflation", "%", false], ["growth", "Growth", "%", false], ["fx_pct", "Currency vs USD", "%", true], ["y10_bp", "10-year yield", "bp", true]];
    const fmtCell = (k, unit, signed, m) => {
      const v = cell(O[m] && O[m][k]);
      const srcRaw = (S[m] && S[m][k]) || S[k] || (O[m] && O[m][k] && O[m][k].source);
      const val = v == null ? el("span", { class: "tiny" }, (O[m] && O[m][k] && O[m][k].note) || "no free data") : el("span", { class: "num" }, signed ? HZ.signed(v, unit === "bp" ? 0 : 1, unit === "bp" ? "bp" : "%") : fmt(v, 1) + "%");
      const src = typeof srcRaw === "string" ? (/^https?:/.test(srcRaw) ? el("a", { href: srcRaw, target: "_blank", rel: "noopener", class: "tiny", title: srcRaw }, " ↗") : el("span", { class: "tiny", title: srcRaw }, " ·" + srcRaw.replace(/^series:/, ""))) : srcRaw && srcRaw.url ? el("a", { href: srcRaw.url, target: "_blank", rel: "noopener", class: "tiny", title: srcRaw.label || srcRaw.url }, " ↗") : null;
      return el("td", { class: "r" }, val, src);
    };
    return el("div", { class: "scroll" }, el("table", {}, el("thead", {}, el("tr", {}, el("th", {}, "What followed"), el("th", { class: "r" }, "After 6 months"), el("th", { class: "r" }, "After 24 months"))),
      el("tbody", {}, ...rows.map(([k, lab, unit, signed]) => el("tr", {}, el("td", {}, lab), fmtCell(k, unit, signed, "m6"), fmtCell(k, unit, signed, "m24"))))));
  }
  cx.outcomeTable = outcomeTable;
  function episodeCard(ep) {
    return el("article", { class: "card", id: "ep-" + ep.id, style: "box-shadow:none" },
      el("div", { class: "row spread" }, el("h3", { style: "margin:0" }, ep.name), el("span", { class: "chip c" }, ep.kind || "episode")),
      el("div", { class: "tiny" }, nn([ep.country && HZ.NAMES[ep.country] || ep.country, ep.start && (ep.start.slice(0, 7) + (ep.end ? " to " + ep.end.slice(0, 7) : ""))]).join(" · ")),
      ep.summary ? el("p", { class: "small" }, ep.summary) : null,
      outcomeTable(ep),
      ep.against && (!Array.isArray(ep.against) || ep.against.length) ? el("div", { class: "small" }, el("b", {}, "Cuts against: "),
        Array.isArray(ep.against) ? el("ul", {}, ...ep.against.map((a) => el("li", {}, typeof a === "string" ? a : [el("b", {}, (a.school || "") + ": "), a.why || ""]))) : String(ep.against)) : null,
      ep.outcome_note ? el("p", { class: "tiny" }, ep.outcome_note) : null,
      cx.cites(ep.cites));
  }
  cx.episodeCard = episodeCard;

  function history(code, pb, views) {
    const P = pb && pb.countries && pb.countries[code];
    if (!P) return HZ.card({ title: "What happened last time", id: "sec-history" }, el("p", { class: "empty" }, "Past episodes appear with the next data run."));
    const eps = P.episodes || [];
    const regional = code === "FR" ? [] : (pb.regional || []);
    const v = views && views.views && views.views[code] || {};
    const res = [v.bond, v.currency].filter((x) => x && x.resembles && x.resembles.episode_id).map((x) => x.resembles.episode_id);
    const resEp = eps.concat(regional).find((e) => res.includes(e.id));
    eps.forEach((e) => HZ.ctx.add("Past episodes (what followed, not proof of cause)", `${e.name} (${e.start}): ${e.summary || ""}`.slice(0, 300)));
    const showReg = el("details", {}, el("summary", {}, "Regional reference: Argentina (" + regional.length + " episodes)"), ...regional.map(episodeCard));
    return HZ.card({ title: "What happened last time", id: "sec-history", cls: "c-" + code },
      el("p", { class: "small" }, el("b", {}, pb.disclaimer || "These show what followed, not proof of cause.")),
      ...eps.map(episodeCard),
      regional.length ? showReg : null,
      HZ.explain({ what: `Past policy episodes in ${HZ.NAMES[code]}${regional.length ? " and Argentina" : ""}, with what followed for inflation, growth, the currency and 10-year yields 6 and 24 months after each began.`,
        how: "Read across a row to see how things moved later. Cells link to their source: stored data where Horizons has it, otherwise a cited figure, otherwise “no free data”. Many other things changed at the same time, so treat these as what followed, not what caused it. Episodes are picked to include ones that cut against each school.",
        now: resEp ? `Horizons' current view says today most resembles “${resEp.name}”.` : `${eps.length} episodes for ${HZ.NAMES[code]}${regional.length ? ", " + regional.length + " regional" : ""}.` }));
  }

  function schools(code, pb) {
    const S = pb && pb.countries && pb.countries[code] && pb.countries[code].schools || [];
    if (!S.length) return HZ.card({ title: "What each school would say", id: "sec-schools" }, el("p", { class: "empty" }, "School perspectives appear with the next data run."));
    const TERMKEY = { Keynesian: "keynesian", Monetarist: "monetarist", Austrian: "austrian", "Supply-side": "supply-side", MMT: "mmt", "Modern Monetary Theory": "mmt" };
    S.forEach((s) => HZ.ctx.add("School perspectives (labelled, cited)", `${s.school}: ${s.view}`.slice(0, 400)));
    return HZ.card({ title: "What each school would say", id: "sec-schools", cls: "c-" + code },
      el("p", { class: "small muted" }, "Each view is a school perspective in its strongest terms, paraphrased from its published writing (cited). None is Horizons' view."),
      ...S.map((s) => el("div", { style: "margin:14px 0" }, el("div", { class: "row" }, el("span", { class: "label" }, "School perspective"), TERMKEY[s.school] ? HZ.term(TERMKEY[s.school], s.school) : el("b", {}, s.school)),
        el("p", { style: "margin:4px 0" }, s.view), s.applies_to ? el("p", { class: "tiny" }, "On: ", s.applies_to) : null, cx.cites(s.cites, "Published writing"))),
      HZ.explain({ what: "How five schools of economics would judge the current policy.",
        how: "Read them as arguments, not facts. Where they agree, the case is stronger; where they split, look at the episodes above for what followed similar choices.",
        now: `${S.length} schools on ${HZ.NAMES[code]}'s current policy.` }));
  }

  function fiscalGap(code, C) {
    const rows = C.fiscal_gap || [];
    if (!rows.length) return null;
    return HZ.card({ title: "Fiscal optimism gap" },
      ...rows.map((r) => el("div", { style: "margin:10px 0" }, el("h3", {}, r.metric, " · ", r.year),
        el("p", { class: "small" }, "Government: ", el("b", { class: "num" }, r.official && r.official.value != null ? fmt(r.official.value, 2) + "% of GDP" : "–"), " ",
          r.official && r.official.verified === false ? el("span", { class: "chip warn", title: r.official.check || "" }, "not confirmed in the law") : null),
        el("ul", { class: "small" }, ...(r.independent || []).map((i) => el("li", {}, i.name, ": ", i.value != null ? el("b", { class: "num" }, fmt(i.value, 2)) : el("span", { class: "tiny" }, "not entered"), " ", i.source ? el("a", { href: i.source, target: "_blank", rel: "noopener", class: "tiny" }, "source") : null))),
        r.gap != null ? el("p", { class: "small" }, "Gap: ", el("b", {}, HZ.signed(r.gap, 2)), " points") : null,
        r.official && r.official.source ? HZ.source(r.official.label, r.official.source) : null)),
      HZ.explain({ what: "The government's own budget target next to independent estimates of the same number.",
        how: "A positive gap means the government is more optimistic than independent forecasters. Persistent optimism tends to end in missed targets, which bond investors notice.",
        now: rows.some((r) => r.gap != null) ? rows.filter((r) => r.gap != null).map((r) => `${r.metric} ${r.year}: gap ${HZ.signed(r.gap, 2)} points`).join("; ") + "." : "Independent estimates are not entered yet for every row, so the gap cannot be computed." }));
  }

  function ratings(R) {
    const rows = R.rows || [];
    HZ.ctx.add("Credit ratings", rows.map((r) => `${r.agency}: ${(r.cells || []).slice(0, 2).join(", ")}`));
    const neg = rows.filter((r) => /neg/i.test((r.cells || [])[1] || "")).length;
    return HZ.card({ title: "Credit ratings" },
      el("div", { class: "scroll" }, el("table", {}, el("thead", {}, el("tr", {}, el("th", {}, "Agency"), el("th", {}, "Rating"), el("th", {}, "Outlook"), el("th", {}, "Date"))),
        el("tbody", {}, ...rows.map((r) => el("tr", {}, el("td", {}, r.agency), el("td", {}, el("b", {}, (r.cells || [])[0])), el("td", {}, (r.cells || [])[1]), el("td", { class: "tiny" }, (r.cells || [])[2])))))),
      HZ.explain({ what: "France's credit ratings from each agency, as listed by the French Treasury (AFT).", how: "Ratings run AAA, AA+, AA, AA−, A+… The outlook hints at the next move. A downgrade is often priced in before it happens, so watch the spread around review dates.",
        now: `${neg} of ${rows.length} agencies have a negative outlook.` }),
      R.meta ? HZ.source(R.meta.source, R.meta.source_url, R.meta.as_of) : null);
  }

  function surveysCot(code, C) {
    const out = [];
    const SV = C.surveys || [];
    if (SV.length) {
      const nowBits = [];
      SV.forEach((sv) => { const r = (sv.rows || [])[0]; if (r && r.sd_pct_10y != null) nowBits.push([sv.label, r, r.sd_pct_10y]); });
      const tight = nowBits.filter((x) => x[2] < 20).map((x) => x[0]), wide = nowBits.filter((x) => x[2] > 80).map((x) => x[0]);
      SV.forEach((sv) => (sv.rows || []).forEach((x) => HZ.ctx.add("Forecaster surveys", `${sv.label} ${x.ref}: median ${fmt(x.median, 2)} (range ${fmt(x.min, 2)}-${fmt(x.max, 2)}), disagreement percentile ${fmt(x.sd_pct_10y, 0)} of 10 years`)));
      out.push(HZ.card({ title: "What forecasters expect, and how much they disagree" },
        ...SV.map((sv) => el("div", { style: "margin:12px 0" }, el("h3", { style: "margin-bottom:4px" }, sv.label),
          el("table", {}, el("thead", {}, el("tr", {}, el("th", {}, "For"), el("th", { class: "r" }, "Median and range"), el("th", { class: "r" }, "Disagreement"))),
            el("tbody", {}, ...(sv.rows || []).map((x) => el("tr", {}, el("td", {}, x.ref), el("td", { class: "r" }, el("b", { class: "num" }, fmt(x.median, 2), sv.unit === "%" ? "%" : ""), el("div", { class: "tiny num" }, fmt(x.min, 2), " to ", fmt(x.max, 2))),
              el("td", { class: "r" }, x.sd_pct_10y != null ? HZ.ring(x.sd_pct_10y / 100, fmt(x.sd_pct_10y, 0), { size: 46, title: "disagreement percentile " + fmt(x.sd_pct_10y, 0) + " of 10 years" }) : "–"))))),
          sv.meta ? HZ.source(sv.meta.source, sv.meta.source_url, sv.meta.as_of) : null)),
        HZ.explain({ what: "The median of professional forecasts for each measure, the range from lowest to highest, and how much forecasters disagree.",
          how: "The ring shows where today's disagreement sits against 10 years of readings at the same horizon: 100 means more disagreement than ever, 0 less than ever. When everyone agrees, a surprise catches most people at once, so the market move can be bigger.",
          now: (tight.length ? "Unusually tight (crowd aligned): " + tight.join(", ") + ". " : "") + (wide.length ? "Unusually wide (views split): " + wide.join(", ") + ". " : "") + (!tight.length && !wide.length ? "Disagreement is within its normal range on every measure." : "") })));
    }
    if (C.cot && C.cot.rows) {
      const lev = C.cot.rows[0];
      out.push(HZ.card({ title: "Positioning: who is betting which way" },
        el("div", { class: "scroll" }, el("table", {}, el("thead", {}, el("tr", {}, el("th", {}, "Group"), el("th", { class: "r" }, "Net contracts"), el("th", { class: "r" }, "Percentile, 3 years"))),
          el("tbody", {}, ...C.cot.rows.map((x) => el("tr", {}, el("td", {}, x.label), el("td", { class: "r num" }, HZ.signed(x.value, 0)), el("td", { class: "r" }, HZ.ring(x.pct_3y / 100, fmt(x.pct_3y, 0), { size: 44 }))))))),
        HZ.explain({ what: `Net futures positions in the ${INSTR[code].cur} held by big speculators, from the US regulator's weekly report.`, how: "Positive means betting on the local currency rising. A percentile near 100 means more crowded than almost any time in 3 years: crowded trades can unwind fast if news disappoints.",
          now: lev ? `${lev.label}: ${HZ.signed(lev.value, 0)} contracts, ${fmt(lev.pct_3y, 0)}th percentile of 3 years${lev.pct_3y > 90 ? " (crowded)" : lev.pct_3y < 10 ? " (crowded the other way)" : ""}. Positions as of ${C.cot.as_of}.` : null }),
        C.cot.meta ? HZ.source(C.cot.meta.source, C.cot.meta.source_url, C.cot.meta.as_of) : null));
    }
    return out;
  }

  function consensus(code, cs, judg) {
    const rows = cs && cs.forecasts && cs.forecasts[code] || [];
    if (!rows.length) return null;
    const moved = rows.filter((r) => r.change_3m != null).sort((a, b) => Math.abs(b.change_3m) - Math.abs(a.change_3m))[0];
    const gaps = (cs.gaps || []).filter((g) => (g.question_id || "").includes(code) || g.country === code);
    rows.slice(0, 8).forEach((r) => HZ.ctx.add("Economists' consensus", `${r.label} ${r.year}: median ${r.median}${r.unit === "%" ? "%" : " " + (r.unit || "")} (range ${r.min}–${r.max}, ${r.respondents || "?"} forecasters, ${r.source}, ${r.as_of})`));
    return HZ.card({ title: "What economists expect", chips: [el("span", { class: "chip c" }, cs.year || "")] },
      el("div", { class: "scroll" }, el("table", {}, el("thead", {}, el("tr", {}, el("th", {}, "Forecast"), el("th", { class: "r" }, "Median"), el("th", { class: "r" }, "Range"), el("th", { class: "r" }, "3-month change"), el("th", {}, ""))),
        el("tbody", {}, ...rows.map((r) => el("tr", {}, el("td", {}, r.label, " ", el("span", { class: "tiny" }, r.year)), el("td", { class: "r num" }, fmt(r.median, 2)),
          el("td", { class: "r num tiny" }, r.min != null ? fmt(r.min, 1) + "–" + fmt(r.max, 1) : "–"), el("td", { class: "r" }, r.change_3m != null ? HZ.chg(r.change_3m, 2) : el("span", { class: "tiny" }, "–")),
          el("td", {}, HZ.callBtn({ title: `${r.label} ${r.year} above ${r.median}?`, question: `Will ${r.label} for ${r.year} come in above the consensus median of ${r.median}?`, question_id: r.id, resolution_date: (r.year + 1) + "-03-31", base_rate: `Consensus median ${r.median} (${r.source}, ${r.as_of})` }, cx.myCall(judg, r.id) ? "Update" : "My view", "small soft"))))))),
      gaps.length ? el("p", { class: "small" }, el("span", { class: "chip warn" }, "gap"), " Your view differs from consensus by more than one standard deviation on ", gaps.map((g) => g.question_id).join(", ")) : null,
      HZ.explain({ what: "The middle (median) of professional forecasts for inflation, growth, the budget and rates, the range, and how the median moved in three months.",
          how: "Markets already price the consensus; prices move when outcomes surprise it. Tap “My view” to record whether you expect above or below the median; Horizons flags when you differ by more than the usual disagreement.",
          now: moved ? `The biggest 3-month move: ${moved.label} ${moved.year} median ${moved.change_3m > 0 ? "up" : "down"} ${fmt(Math.abs(moved.change_3m), 2)} to ${fmt(moved.median, 2)}.` : "No 3-month comparison stored yet." }),
      HZ.source(rows[0].source, rows[0].source_url, rows[0].as_of));
  }

  function assessments(code, A) {
    const items = (A && A.items || []).filter((x) => x.country === code);
    if (!items.length) return null;
    const ok = items.filter((x) => x.status === "ok");
    ok.forEach((x) => HZ.ctx.add("Independent fiscal assessments", `${x.name} (${x.date}): ${x.summary}`));
    return HZ.card({ title: "Independent fiscal watchdogs" },
      ...items.map((x) => el("div", { style: "margin:12px 0" }, el("h3", { style: "margin:0" }, x.name),
        x.status === "ok" ? [el("p", { class: "small" }, x.summary), x.stance ? el("span", { class: "chip c" }, x.stance) : null, x.key_number ? el("p", { class: "small" }, el("b", {}, "Key number: "), x.key_number.value, " ", x.key_number.what) : null,
          x.verified === false ? el("span", { class: "chip warn" }, "unverified") : null, HZ.source(x.title, x.url, x.date)]
          : el("p", { class: "tiny" }, "Unavailable: ", x.note || "no recent publication found."))),
      HZ.explain({ what: "Summaries of the latest reports by the country's independent budget watchdogs, checked number by number against the report.",
        how: "Watchdogs are paid to be sceptical. When they call the government's plan optimistic, bond investors often agree; the stance chip says which way.",
        now: ok.length ? ok.map((x) => `${x.name.split(" (")[0]}: ${x.stance || "see summary"}`).join("; ") + "." : "No current summary." }));
  }

  function policies(code, cs) {
    const P = cs && cs.policies && cs.policies[code] || [];
    if (!P.length) return null;
    return HZ.card({ title: "Policy tracker: claims versus independent checks" },
      ...P.map((p) => el("details", { style: "margin:10px 0" }, el("summary", {}, p.name),
        el("p", { class: "small" }, p.what),
        p.claim ? el("p", { class: "small" }, el("b", {}, "The government says: "), p.claim.text, p.claim.source ? HZ.source(p.claim.source.label, p.claim.source.url, p.claim.source.date) : null) : null,
        p.assessment ? el("p", { class: "small" }, el("b", {}, (p.assessment.by || "Independent check") + ": "), p.assessment.text, p.assessment.source ? HZ.source(p.assessment.source.label, p.assessment.source.url, p.assessment.source.date) : null) : null,
        p.effects ? el("ul", { class: "small" }, ...Object.entries(p.effects).map(([k, e]) => el("li", {}, el("b", {}, k + ": "), e.text))) : null,
        p.status ? el("p", { class: "tiny" }, "Status: ", p.status) : null,
        p.next ? el("p", { class: "tiny" }, "Next: ", p.next.title || p.next.label, " · ", p.next.date) : null,
        p.view && p.view.question ? HZ.callBtn({ title: p.view.question, question: p.view.question, question_id: "pol:" + p.id, resolution_date: p.view.resolution_date }, "My view", "small soft") : null)),
      HZ.explain({ what: "The government's main live policies, what it claims for each, and what an independent body says about the same claim.",
        how: "Compare the two lines: when an independent check is much less optimistic, the policy may need a correction later (spending freezes, tax rises) that markets will react to.",
        now: `${P.length} policies tracked; the next dated step is ${P.map((p) => p.next).filter((n) => n && n.date).sort((a, b) => a.date.localeCompare(b.date)).map((n) => (n.title || n.label) + " on " + n.date)[0] || "not set"}.` }));
  }

  function drivers(code, D) {
    if (!D || !D.instruments) return null;
    const ins = Object.entries(D.instruments).filter(([, i]) => i.country === code && i.available);
    if (!ins.length) return null;
    return ins.map(([k, i]) => {
      const rows = (i.univariate || []).filter((u) => u.available && u["3y"]);
      const strongest = rows.slice().sort((a, b) => (b["3y"].r2 || 0) - (a["3y"].r2 || 0))[0];
      const att = (i.attribution || []).slice(-1)[0];
      const opts = rows.map((u) => [u.driver, D.drivers[u.driver]]);
      const sel = el("select", { "aria-label": "Driver", style: "font:inherit;font-size:1rem;padding:8px;border-radius:12px;border:1.5px solid var(--line);background:var(--card-solid);color:var(--ink);max-width:100%" }, ...opts.map(([d, dd]) => el("option", { value: d }, dd.label)));
      const slider = el("input", { type: "range", min: -3, max: 3, step: 0.5, value: 1, "aria-label": "Driver move", style: "flex:1;min-width:140px" });
      const out = el("p", { class: "small", "aria-live": "polite" });
      const upd = () => {
        const u = rows.find((r) => r.driver === sel.value); const dd = D.drivers[sel.value]; if (!u || !dd) return;
        const move = +slider.value * dd.unit_move, b = u["3y"].beta, se = u["3y"].se;
        const unit = dd.unit === "pct" ? "%" : dd.unit === "bp" ? "bp" : " " + dd.unit;
        const iu = i.unit === "pct" ? "%" : "bp";
        out.replaceChildren("If ", el("b", {}, dd.label), " moves ", el("b", {}, HZ.signed(move, dd.unit === "pct" ? 1 : 0, unit)), ", ", i.label, " has typically moved ",
          el("b", {}, HZ.signed(b * move, 2, iu)), " (90% range ", HZ.signed((b - 1.645 * se) * move, 2, iu), " to ", HZ.signed((b + 1.645 * se) * move, 2, iu), ").");
      };
      sel.addEventListener("change", upd); slider.addEventListener("input", upd); upd();
      if (att) HZ.ctx.add("External drivers", `${i.label}, week to ${att.end}: ${att.reading}`);
      return HZ.card({ title: "What moves " + i.label + " from outside" },
        el("ul", { class: "small" }, ...rows.map((u) => el("li", {}, u.sentence, el("span", { class: "tiny" }, ` (3 years, ${u["3y"].n} weeks, fit ${fmt(100 * u["3y"].r2, 0)}%)`)))),
        el("h3", {}, "Try it"), el("div", { class: "row" }, sel, slider), out,
        att ? el("p", { class: "small" }, el("b", {}, "Last week: "), att.reading) : null,
        HZ.explain({ what: `How ${i.label} has moved alongside global forces (the dollar, US yields, risk appetite, commodities) over the past 3 years.`,
          how: "Each line is a sensitivity (a beta): a rough rule of thumb from the past, not a forecast. The slider applies it to a move you choose and shows the usual range. The “fit” says how much of the weekly moves the driver alone explains.",
          now: [strongest ? `The strongest link is ${D.drivers[strongest.driver].label} (fit ${fmt(100 * strongest["3y"].r2, 0)}%).` : "", att ? ` In the latest week ${fmt(Math.abs(att.explained), 2)} of the ${fmt(Math.abs(att.move), 2)} move was explained by global drivers; the rest (${HZ.signed(att.local, 2)}) was local.` : ""].join("") }));
    });
  }

  function emModel(code, T) {
    const Cn = T && T.countries && T.countries[code];
    if (!Cn || !Cn.drivers) return null;
    return Cn.drivers.map((d) => {
      const rows = (d.rows || []).filter((r) => r.contribution_now != null).sort((a, b) => Math.abs(b.contribution_now) - Math.abs(a.contribution_now)).slice(0, 8);
      const top = rows[0];
      return HZ.card({ title: "What the research model says drives the " + d.kind },
        el("p", { class: "tiny" }, d.model, " · as of ", d.as_of),
        el("div", { class: "scroll" }, el("table", {}, el("thead", {}, el("tr", {}, el("th", {}, "Factor"), el("th", { class: "r" }, "Pushing now"), el("th", { class: "r" }, "Change in 12 months"))),
          el("tbody", {}, ...rows.map((r) => el("tr", {}, el("td", {}, r.plain || r.label, r.significant ? null : el("span", { class: "tiny" }, " (weak)")), el("td", { class: "r" }, HZ.chg(r.contribution_now, 1)), el("td", { class: "r" }, HZ.chg(r.change_12m, 1))))))),
        HZ.explain({ what: `em-macro's model of the ${d.target}: how much each economic or political factor is pushing it now, in ${d.unit}.`,
          how: "Positive numbers push the " + (d.kind === "spread" ? "spread wider (worse)" : "currency weaker") + ", negative ones the other way. “Weak” factors are not statistically clear. It is a model of averages across many countries.",
          now: top ? `The biggest push now: ${top.plain || top.label} (${HZ.signed(top.contribution_now, 1)} ${d.unit.split(" ")[0]}).` : null }),
        d.source_url ? HZ.source("em-macro", d.source_url) : null);
    });
  }

  function whatIf(code, T) {
    const W = T && T.what_if && T.what_if.countries && T.what_if.countries[code];
    if (!W || !W.length) return null;
    const out = el("div", { class: "stack" });
    const vals = {};
    const res = el("p", { "aria-live": "polite" });
    const upd = () => {
      let sp = 0, spv = 0, fx = 0, fxv = 0;
      W.forEach((w) => { const x = vals[w.key] || 0; const e = w.effects || {}; if (e.spread_bp) { sp += x * e.spread_bp.per_unit; spv += (x * e.spread_bp.se_per_unit) ** 2; } if (e.fx_pct) { fx += x * e.fx_pct.per_unit; fxv += (x * e.fx_pct.se_per_unit) ** 2; } });
      res.replaceChildren("Spread: ", el("b", {}, HZ.signed(sp, 0, "bp")), " (±", fmt(1.645 * Math.sqrt(spv), 0), "bp) · Currency: ", el("b", {}, HZ.signed(fx, 1, "%")), " (±", fmt(1.645 * Math.sqrt(fxv), 1), "%)");
    };
    W.forEach((w) => {
      vals[w.key] = 0;
      const lab = el("span", { class: "num" }, "0");
      const s = el("input", { type: "range", min: w.min, max: w.max, step: w.step, value: 0, "aria-label": w.label, style: "width:100%" });
      s.addEventListener("input", () => { vals[w.key] = +s.value; lab.textContent = HZ.signed(+s.value, 2); upd(); });
      out.appendChild(el("div", {}, el("div", { class: "row spread small" }, el("span", {}, w.label), lab), s, w.now != null ? el("div", { class: "tiny" }, "Now: ", fmt(w.now, 2)) : null));
    });
    upd();
    return HZ.card({ title: "What if…?" }, out, res,
      el("p", { class: "tiny" }, T.what_if.currency_note || "", " ", T.what_if.band || ""),
      HZ.explain({ what: "Move the sliders to see how the research model says the bond spread and the currency would respond if one of these changed, everything else equal.",
        how: "Positive currency numbers mean a weaker currency against the dollar (as the model defines it). The ± range covers only the model's statistical uncertainty: reality is noisier.", now: T.what_if.caveat }));
  }

  function eventStudy(code, T) {
    const G = T && T.event_study && T.event_study.groups && T.event_study.groups[code];
    if (!G || !G.length) return null;
    const last = (p) => p[p.length - 1];
    const rows = G.map((g) => ({ g, d: last(g.path || []) })).filter((x) => x.d);
    const big = rows.slice().sort((a, b) => Math.abs(b.d.mean) - Math.abs(a.d.mean))[0];
    return HZ.card({ title: "What usually followed past events" },
      el("div", { class: "scroll" }, el("table", {}, el("thead", {}, el("tr", {}, el("th", {}, "Event"), el("th", {}, "Asset"), el("th", { class: "r" }, "n"), el("th", { class: "r" }, "After ~1 month: average"), el("th", { class: "r" }, "Range"))),
        el("tbody", {}, ...rows.map(({ g, d }) => el("tr", {}, el("td", {}, g.group), el("td", {}, g.asset), el("td", { class: "r" }, g.n), el("td", { class: "r" }, HZ.chg(d.mean, 2, g.unit === "%" ? "%" : "bp")),
          el("td", { class: "r tiny" }, HZ.signed(d.lo, 1), " to ", HZ.signed(d.hi, 1))))))),
      HZ.explain({ what: "How the currency and the 10-year yield moved in the 20 trading days after past elections and rate decisions in this country (an event study).",
        how: `The average hides a wide range (${G[0].range}): use the range to see how often the move went either way. Few events (small n) make averages unreliable.`,
        now: big ? `The largest average follow-through is after ${big.g.group.toLowerCase()} for ${big.g.asset}: ${HZ.signed(big.d.mean, 2)} on average across ${big.g.n} events.` : null }),
      T.event_study.source_url ? HZ.source("em-macro event study", T.event_study.source_url) : null);
  }

  function scenarios(code, S) {
    const list = (S && S.scenarios || []).filter((s) => s.country === code);
    if (!list.length) return null;
    list.forEach((s) => HZ.ctx.add("Scenarios", `${s.title}: ${s.question} (resolves ${s.resolution_date})${s.mine ? "; my probability " + HZ.pct(s.mine.p_yes != null ? s.mine.p_yes : s.mine.prob) : ""}`));
    return HZ.card({ title: "Scenarios for " + HZ.NAMES[code], cls: "s-scen" },
      ...list.map((s) => el("a", { href: "#scenarios/" + s.id, class: "card", style: "display:block;text-decoration:none;color:inherit;box-shadow:none;margin:10px 0" },
        el("div", { class: "row spread" }, el("b", {}, s.title), s.days_to_event != null ? el("span", { class: "chip c" }, HZ.inDays(s.event ? s.event.date : s.resolution_date)) : null),
        el("p", { class: "small", style: "margin:4px 0" }, s.question),
        s.base_rate && s.base_rate.headline ? el("p", { class: "tiny", style: "margin:0" }, "Base rate: ", s.base_rate.headline) : null)),
      HZ.explain({ what: "The big dated questions for this country, each split into outcomes with probabilities and market moves.",
        how: "Open one to see the base rate, the outcome tree and what markets would do in each branch. The AI's and the market's probabilities stay hidden until you make your own call, so they don't anchor you.",
        now: `Next to resolve: ${list.slice().sort((a, b) => a.resolution_date.localeCompare(b.resolution_date))[0].title}.` }));
  }

  function crowd(code, summary) {
    return HZ.maybe("crowd.json").then((Cr) => {
      if (!Cr) return null;
      const scen = HZ.maybe("scenarios.json");
      return scen.then((S) => {
        const ids = new Set((S && S.scenarios || []).filter((s) => s.country === code).map((s) => s.id));
        const shared = (Cr.shared_errors || []).filter((x) => ids.has(x.scenario));
        const sig = [];
        (Cr.gauges || []).forEach((g) => {
          (g.readings || []).filter((r) => r.country === code).forEach((r) => sig.push({ g, text: r.label + (r.percentile != null ? ` — ${fmt(r.percentile, 0)}th percentile` : "") + (r.crowded ? ` (crowded ${r.crowded})` : "") + (r.extreme ? " · extreme" : ""), r }));
          (g.rows || []).filter((r) => r.country === code).forEach((r) => sig.push({ g, text: `${r.measure} ${r.year}: official ${r.official}, independent ${r.independent_median != null ? r.independent_median : "not entered"}` }));
          (g.items || []).filter((r) => r.country === code).forEach((r) => sig.push({ g, text: r.threshold + ": " + (r.ratings || []).map((x) => x.agency + " " + x.rating).join(", ") }));
          (g.elections || []).filter((r) => r.iso3 === ISO3[code]).slice(0, 1).forEach((r) => sig.push({ g, text: `${r.election}: ${r.n_polls} polls from ${r.n_pollsters} pollsters; herding ratio ${fmt(r.herding_ratio, 2)}` }));
        });
        if (!shared.length && !sig.length) return null;
        sig.forEach((s) => HZ.ctx.add("Crowd signals", s.g.title + ": " + s.text));
        const BADGE = { tested_leads: "tested: it led", tested_no_lead: "tested: no lead found", untested: "untested", context: "context" };
        return HZ.card({ title: "Where the crowd might be wrong", cls: "s-crowd" },
          shared.length ? [el("h3", {}, "Shared-error watch"), el("ul", {}, ...shared.map((x) => el("li", {}, el("a", { href: "#scenarios/" + x.scenario }, x.title), " · score ", fmt(x.score, 1),
            el("ul", { class: "small" }, ...(x.signals || []).map((s) => el("li", {}, s.signal, ": ", s.hidden_market ? "market price hidden until you call" : s.detail, " ", el("span", { class: "chip" }, BADGE[s.badge] || s.badge)))))))] : null,
          sig.length ? [el("h3", {}, "Crowd gauges"), el("ul", { class: "small" }, ...sig.map((s) => el("li", {}, el("b", {}, s.g.title + ": "), s.text, " ", el("span", { class: "chip" }, BADGE[s.g.evidence && s.g.evidence.badge] || "")))) ] : null,
          el("a", { class: "btn soft small", href: "#crowd" }, "All crowd gauges"),
          HZ.explain({ what: "Signs that forecasters, pollsters, traders or the government may all be making the same mistake.",
            how: "Each signal has a badge: “tested: it led” means research found it predicted outcomes; “no lead found” or “untested” means treat it as background. Several signals on one question deserve a closer look.",
            now: shared.length ? `${shared[0].title} has the highest shared-error score (${fmt(shared[0].score, 1)}).` : `${sig.length} gauge readings for ${HZ.NAMES[code]}; ${sig.filter((s) => s.r && (s.r.extreme || s.r.flag)).length} flagged as extreme.` }));
      });
    });
  }

  function markets(code, C) {
    const M = (C.markets || []).slice().sort((a, b) => (b.volume || 0) - (a.volume || 0)).slice(0, 8);
    if (!M.length) return el("div");
    const key = "revealed." + code;
    const shown = HZ.store.get(key, "") === "1";
    const body = el("div");
    const render = (on) => body.replaceChildren(el("div", { class: "scroll" }, el("table", {}, el("thead", {}, el("tr", {}, el("th", {}, "Question"), el("th", { class: "r" }, "Market odds"), el("th", { class: "r" }, "Volume"))),
      el("tbody", {}, ...M.map((m) => el("tr", {}, el("td", {}, el("a", { href: m.url, target: "_blank", rel: "noopener" }, m.question), el("div", { class: "tiny" }, m.venue, " · ends ", (m.end_date || "").slice(0, 10))),
        el("td", { class: "r num" }, on ? el("b", {}, HZ.pct(m.prob)) : el("span", { class: "tiny" }, "hidden")), el("td", { class: "r num tiny" }, "$" + fmt(m.volume, 0))))))),
      on ? null : el("button", { type: "button", class: "btn soft small", onclick: () => { HZ.store.set(key, "1"); render(true); } }, "Show the odds (after you've thought about it)"));
    render(shown);
    if (shown) M.forEach((m) => HZ.ctx.add("Prediction markets", `${m.question}: ${HZ.pct(m.prob)} (${m.venue})`));
    return HZ.card({ title: "Prediction markets" }, body,
      HZ.explain({ what: "The most traded prediction-market questions about this country, with what traders' prices imply.", how: "A price of 30 cents on a $1 contract reads as a 30% chance. Odds start hidden so you can form your own view first. Small markets can be wrong or pushed around.",
        now: `${M.length} markets; the most traded is “${M[0].question}”.` }));
  }

  function viewSection(code, views, judg, summary, pb) {
    const I = INSTR[code];
    const v = views && views.views && views.views[code] || {};
    const date = views && views.date || HZ.today();
    const bondLabel = (cx.tileBy(summary, I.bondTile) || {}).label || I.bond;
    const epLink = (id) => el("a", { href: "#", onclick: (e) => { e.preventDefault(); cx.anchor("ep-" + id); } }, ((pb && pb.countries && pb.countries[code] && pb.countries[code].episodes || []).concat(pb && pb.regional || []).find((x) => x.id === id) || {}).name || id);
    // the question for a call: the leaned way (bond: yields/spread lower; currency: local currency stronger)
    const bondUp = v.bond && v.bond.lean === "short";
    const fxLocalStrong = !(v.currency && v.currency.lean === "short");
    const fxUp = I.inverted ? fxLocalStrong : !fxLocalStrong;
    HZ.ctx.add("Horizons' view (" + date + ", not financial advice)", [cx.ctxView(v.bond, "bond", code, bondLabel), cx.ctxView(v.currency, "currency", code, I.pair)]);
    return el("div", { id: "sec-view" }, HZ.card({ title: "Horizons' view", cls: "c-GOLD glow", sub: "For the next 1–3 months. " + (views ? "Written " + HZ.dateLong(date) + "." : "") },
      el("h3", {}, "The bond"), cx.viewBox({ v: v.bond, asset: "bond", code, date, judg, label: bondLabel, wantUp: bondUp, srcMap: cx.sources, tradeInstr: I.bond, episodeLink: epLink }),
      el("h3", { style: "margin-top:16px" }, "The " + I.cur), cx.viewBox({ v: v.currency, asset: "currency", code, date, judg, label: I.pair, wantUp: fxUp, srcMap: cx.sources, tradeInstr: I.fx, episodeLink: epLink }),
      HZ.explain({ what: "What Horizons would do with this country's bond and currency over the next one to three months, and why.",
        how: "“Lean long the bond” means expecting yields to fall (bond prices to rise); “lean long the " + I.cur + "” means expecting it to strengthen" + (I.inverted ? " (EUR/USD up)" : " (" + I.pair + " down)") + ". The ring is the probability it moves that way by the horizon date. Make your own call on the same question to compare: both are scored in the Record.",
        now: v.bond || v.currency ? `${cx.leanText(v.bond, "bond", code)}; ${cx.leanText(v.currency, "currency", code)}.` : "No view yet: the first weekly view comes with the next judgement run." })));
  }

  function myCalls(code, judg) {
    const qs = (judg && judg.questions || []).filter((q) => (q.question_id || "").includes(code + ".") || (q.question_id || "").includes("-" + code.toLowerCase() + "-") || (q.question_id || "").startsWith("sc:" + code.toLowerCase()));
    qs.forEach((q) => { const f = q.forecasts[q.forecasts.length - 1]; HZ.ctx.add("My calls", `${q.question}: ${HZ.pct(f.prob)} on ${(f.submitted_at || "").slice(0, 10)}${q.resolution ? " (resolved " + (q.resolution.outcome ? "YES" : "NO") + ")" : ""}`); });
    if (!qs.length) HZ.ctx.add("My calls", "No calls on this country yet.");
  }
})();
