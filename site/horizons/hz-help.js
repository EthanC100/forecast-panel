/* Horizons Help: the first-open walkthrough (shown once, then from the menu), short lessons tied to live
   data, each ending with one question to check understanding, and the glossary. Never shown on main
   pages after the first open. */
(function () {
  "use strict";
  const { el, fmt, card, maybe } = HZ;

  // live numbers used by the walkthrough and lessons; every one degrades to a plain example if missing
  const live = () => Promise.all(["summary.json", "gold.json", "calendar.json", "book/config.json", "teach.json", "book/record.json", "book/state.json"].map(maybe))
    .then(([summary, gold, cal, , teach, record, book]) => {
      const t = {}; ((summary && summary.tiles) || []).forEach((x) => (t[x.key] = x));
      return { summary, t, gold, cal, teach, record, book };
    });
  const lvl = (D, k, d, fb) => D.t[k] ? fmt(D.t[k].level, d) : fb;
  const asOf = (D, k) => D.t[k] ? " (" + HZ.dateShort(D.t[k].as_of) + ")" : "";
  const seriesLast = (id) => HZ.series(id).then((s) => { const h = s.history || []; return h.length ? { v: +h[h.length - 1][1], d: h[h.length - 1][0] } : null; }).catch(() => null);

  // ---------------- quiz ----------------
  function quiz(q) {
    const box = el("div", { class: "quiz" }, el("b", {}, "Check your understanding"), el("p", {}, q.q));
    const fb = el("p", { class: "small", "aria-live": "polite" });
    q.options.forEach((o, i) => box.appendChild(el("button", { type: "button", class: "opt", onclick: (e) => {
      box.querySelectorAll(".opt").forEach((b) => b.classList.remove("right", "wrong"));
      e.currentTarget.classList.add(i === q.answer ? "right" : "wrong");
      fb.textContent = (i === q.answer ? "Right. " : "Not quite. ") + q.why;
      if (i === q.answer) { HZ.store.set("quiz." + q.id, "1"); }
    } }, o)));
    box.appendChild(fb);
    return box;
  }

  // ---------------- lessons ----------------
  const LESSONS = [
    { id: "bonds", title: "What a bond is, and how it makes or loses money", c: "c-FR", body: (D) => [
      el("p", {}, "A bond is a loan to a government. You pay, say, 100 today; the government pays interest every year and returns 100 at the end."),
      el("p", {}, "Bonds trade every day. If new bonds pay more interest than yours, nobody pays full price for yours, so its price falls. That is why ", HZ.term("yield"), " and price move in opposite directions."),
      el("p", {}, el("b", {}, "Live: "), "Mexico's 10-year yield is ", el("b", {}, lvl(D, "mx10y", 2, "about 9") + "%"), asOf(D, "mx10y"), ". If it rises one percentage point, a 10-year bond loses roughly its ", HZ.term("duration"), " in percent, about 7%."),
      el("p", {}, el("b", {}, "You make money on a bond "), "when its yield falls (price up) and from the interest you collect. ", el("b", {}, "You lose "), "when its yield rises faster than the interest you collect.")],
      quiz: { id: "bonds", q: "A country's 10-year yield jumps from 9% to 10%. What happened to the price of its existing bonds?", options: ["It rose", "It fell", "It didn't change"], answer: 1, why: "Yields and prices move in opposite directions: a higher yield means a lower price." } },
    { id: "currencies", title: "Currencies: how to read them and how they move", c: "c-MX", body: (D) => [
      el("p", {}, "An ", HZ.term("currency", "exchange rate"), " is a price. ", HZ.term("usdbrl", "USD/BRL"), " is how many reais one dollar buys: ", el("b", {}, lvl(D, "usdbrl", 3, "5.4")), asOf(D, "usdbrl"), ". If it rises, the real has weakened."),
      el("p", {}, "EUR/USD is quoted the other way round: dollars per euro (", el("b", {}, lvl(D, "eurusd", 4, "1.10")), asOf(D, "eurusd"), "). Up means the euro is stronger."),
      el("p", {}, "Currencies move on interest rates (higher rates attract money), inflation, the budget, politics and global fear. You make money being long a currency when it strengthens, plus the interest gap (", HZ.term("carry"), ")."),
      D.t.usdbrl ? el("p", {}, el("b", {}, "This week: "), "USD/BRL moved ", HZ.chg(D.t.usdbrl.chg_1w, 1, "%"), ", so the real ", D.t.usdbrl.chg_1w > 0 ? "weakened." : "strengthened.") : null],
      quiz: { id: "currencies", q: "USD/MXN goes from 18.5 to 19.5. Did the peso strengthen or weaken?", options: ["Strengthened", "Weakened"], answer: 1, why: "It now takes more pesos to buy one dollar, so each peso is worth less." } },
    { id: "gold", title: "Gold: what moves it", c: "c-GOLD", body: (D) => {
      const g = D.gold && D.gold.prices && D.gold.prices.gold;
      const ry = D.gold && (D.gold.drivers || []).find((x) => x.id === "real_yield");
      return [el("p", {}, HZ.term("gold", "Gold"), " pays no interest. So it competes with safe bonds: when the ", HZ.term("real yield"), " (interest after inflation) rises, holding gold costs you more in lost interest, and gold tends to fall."),
        el("p", {}, "It is priced in dollars, so a stronger dollar tends to push it down. Fear (war, political crises) and steady ", HZ.term("central-bank buying"), " push it up."),
        g ? el("p", {}, el("b", {}, "Live: "), "gold is $", fmt(g.value, 0), " an ounce (", HZ.dateShort(g.date), "), ", HZ.chg(g.chg_1m_pct, 1, "%"), " over a month.", ry ? [" The US 10-year real yield is ", fmt(ry.value, 2), "%."] : null) : null,
        el("p", {}, "You make money long gold when it rises; you pay the interest you could have earned on dollars (negative carry).")];
    }, quiz: { id: "gold", q: "US real interest rates rise sharply. What usually happens to gold?", options: ["It tends to rise", "It tends to fall", "No relationship"], answer: 1, why: "Gold pays nothing, so higher real rates make holding it more expensive compared with bonds." } },
    { id: "carry", title: "Carry: getting paid to wait", c: "c-BR", body: (D) => Promise.all([seriesLast("br.selic.target"), seriesLast("us.fedfunds")]).then(([s, f]) => [
      el("p", {}, HZ.term("carry", "Carry"), " is what a position earns if prices don't move. Holding reais pays Brazil's rate; funding it in dollars costs the US rate."),
      s && f ? el("p", {}, el("b", {}, "Live: "), "the Selic target is ", el("b", {}, fmt(s.v, 2) + "%"), " and US fed funds ", el("b", {}, fmt(f.v, 2) + "%"), ". The gap is about ", el("b", {}, fmt(s.v - f.v, 1) + " points a year"), ": $100,000 long reais against dollars earns about $", fmt((s.v - f.v) * 1000, 0), " a year if USD/BRL doesn't move.") : null,
      el("p", {}, "The catch: currencies with high carry can fall fast in a crisis, wiping out a year of carry in days. Carry is a cushion, not a guarantee.")]),
      quiz: { id: "carry", q: "You are long the real with 10 points of carry a year. After a month USD/BRL is unchanged. Roughly what have you made?", options: ["Nothing", "About 0.8% of the position", "About 10%"], answer: 1, why: "10% a year is roughly 0.8% a month, earned even though the price didn't move." } },
    { id: "spreads", title: "Spreads: France versus Germany", c: "c-FR", body: (D) => [
      el("p", {}, "A ", HZ.term("spread"), " is the gap between two yields. France's OAT-Bund spread is the French 10-year yield minus Germany's: what investors charge France extra over the euro area's safest borrower."),
      el("p", {}, el("b", {}, "Live: "), "the spread is ", el("b", {}, lvl(D, "oatbund", 0, "about 80") + " basis points"), asOf(D, "oatbund"), ". One ", HZ.term("bp", "basis point"), " is 0.01 percentage points."),
      el("p", {}, "It widens when investors worry about France's budget, politics or credit rating, and narrows when those fears ease.")],
      quiz: { id: "spreads", q: "France's spread widens from 70bp to 90bp. What does that tell you?", options: ["Investors are less worried about France", "Investors want more to hold French debt instead of German", "German yields fell 20bp"], answer: 1, why: "A wider spread means more extra yield demanded for French risk (it could come from either yield moving)." } },
    { id: "duration", title: "Duration: how much a bond moves", c: "c-FR", body: (D) => {
      const dur = 8, y = D.t.br10y ? D.t.br10y.level : 13;
      return [el("p", {}, HZ.term("duration", "Duration"), " says how sensitive a bond's price is to its yield. Duration 8 means about 8% price change for each 1 percentage point of yield."),
        el("p", {}, el("b", {}, "Worked example: "), "Brazil's 10-year proxy yields ", el("b", {}, fmt(y, 2) + "%"), asOf(D, "br10y"), ". If it rises 0.5 points with a duration of about ", dur, ", the price falls about ", fmt(dur * .5, 1), "%. On $100,000 that's about −$", fmt(dur * 500, 0), ", partly offset by the interest earned."),
        el("p", {}, "Longer bonds have higher duration: more gain if yields fall, more loss if they rise.")];
    }, quiz: { id: "duration", q: "A bond has duration 5. Its yield falls 1 percentage point. Its price…", options: ["rises about 5%", "falls about 5%", "rises about 1%"], answer: 0, why: "Price moves opposite to yield, by about duration × the yield change." } },
    { id: "crisis", title: "Why currencies fall in crises", c: "c-MX", body: (D) => HZ.series("br.usdbrl.ptax").then((s) => {
      const h = s.history || [];
      const at = (d) => { let v = null; for (const r of h) { if (r[0] <= d) v = r[1]; else break; } return v; };
      const a = at("2020-02-20"), b = at("2020-05-13"), c = at("2008-08-01"), d = at("2008-12-05");
      return [el("p", {}, "In a scare, investors sell what feels risky and buy ", HZ.term("safe haven"), "s: the dollar, US Treasuries, gold. Emerging-market currencies like the real and the peso are sold, so they fall, often far more than the news alone justifies."),
        a && b ? el("p", {}, el("b", {}, "From the data: "), "USD/BRL went from ", fmt(a, 2), " on 20 Feb 2020 to ", fmt(b, 2), " on 13 May 2020 (", HZ.chg(100 * (b / a - 1), 0, "%"), "), as Covid hit.", c && d ? [" In 2008 it went from ", fmt(c, 2), " (1 Aug) to ", fmt(d, 2), " (5 Dec), ", HZ.chg(100 * (d / c - 1), 0, "%"), "."] : null) : null,
        el("p", {}, "That's why high carry isn't free: you are paid to take the risk of these sudden falls. Watch the ", HZ.term("volatility", "VIX"), " and the ", HZ.term("dollar", "dollar index"), " as early warnings.")];
    }).catch(() => [el("p", {}, "In a scare, investors sell emerging-market currencies and buy the dollar, Treasuries and gold.")]),
      quiz: { id: "crisis", q: "Global fear spikes. Which usually happens?", options: ["The peso strengthens", "The peso weakens and the dollar strengthens", "Nothing changes"], answer: 1, why: "In risk-off episodes money flows to safe havens such as the dollar, so emerging-market currencies weaken." } },
    { id: "elections", title: "How elections move markets", c: "c-BR", body: (D) => {
      const g = D.teach && D.teach.event_study && D.teach.event_study.groups && (D.teach.event_study.groups.BR || []).find((x) => x.event_type === "election");
      const p20 = g && (g.path || []).find((x) => x.day === 20);
      return [el("p", {}, "Markets care about who wins only through policy: the budget, the central bank's independence, trade. When the likely winners differ on those, prices move before and after the vote."),
        g ? el("p", {}, el("b", {}, "From the data: "), "after ", g.n, " past Brazilian elections, USD/BRL moved on average ", HZ.chg(p20 ? p20.mean : null, 1, "%"), " over the 20 trading days that followed (range ", fmt(p20 && p20.lo, 1), "% to ", fmt(p20 && p20.hi, 1), "%). Averages hide big differences between elections.") : null,
        el("p", {}, "The surprise matters more than the result: if markets expected the winner, the move is small. Compare ", HZ.term("prediction market"), " odds with polls before the vote.")];
    }, quiz: { id: "elections", q: "The candidate markets expected wins comfortably. What is the most likely market reaction?", options: ["A very large move", "A small move, since it was already priced", "Always a rally"], answer: 1, why: "Prices already reflect expected outcomes; big moves come from surprises." } },
    { id: "fiscal", title: "Fiscal policy and markets", c: "c-BR", body: (D) => {
      const f = D.summary && D.summary.countries && D.summary.countries.BR && (D.summary.countries.BR.fiscal_gap || [])[0];
      return [el("p", {}, HZ.term("fiscal", "Fiscal policy"), " is the government's budget. A bigger ", HZ.term("deficit"), " means more borrowing: more bonds to sell, so yields may need to rise to find buyers. If investors doubt debt is under control, the currency can fall too."),
        f ? el("p", {}, el("b", {}, "Live: "), f.metric, " for ", f.year, ": official target ", fmt(f.official && f.official.value, 2), "%", f.independent && f.independent.value != null ? [", independent estimate ", fmt(f.independent.value, 2), "%"] : null, ". The gap between them is what markets watch.") : null,
        el("p", {}, "Central banks react too: loose budgets can keep interest rates higher for longer.")];
    }, quiz: { id: "fiscal", q: "A government announces a much bigger deficit than expected. What is the usual first reaction?", options: ["Yields rise", "Yields fall", "The currency always strengthens"], answer: 0, why: "More borrowing and more doubt about debt usually mean investors demand higher yields." } },
    { id: "catalysts", title: "Catalysts and scenarios", c: "c-GOLD", body: (D) => {
      const ev = ((D.cal && D.cal.events) || []).filter((e) => e.importance === 3 && e.date >= HZ.today())[0];
      return [el("p", {}, "A ", HZ.term("catalyst"), " is a dated event that can move prices: an election, a budget vote, a rating review, a central-bank decision. Because it has a date you can prepare."),
        ev ? el("p", {}, el("b", {}, "Next major one: "), ev.title, " on ", HZ.dateLong(ev.date), " (", HZ.inDays(ev.date), ").") : null,
        el("p", {}, "Scenario pages split a catalyst into a few outcomes, give each a probability and estimate the market move in each. ", HZ.term("signpost", "Signposts"), " are early clues to which one is unfolding.")];
    }, quiz: { id: "catalysts", q: "Which is a catalyst?", options: ["A central bank meeting on a set date", "A long-term trend in productivity", "A currency's 10-year average"], answer: 0, why: "A catalyst is a dated event that can move markets." } },
    { id: "scores", title: "Reading the scores", c: "s-rec", body: (D) => {
      const q = D.record && D.record.questions;
      return [el("p", {}, "Horizons scores every probability you give with the ", HZ.term("brier", "Brier score"), ": (probability − outcome)², averaged. 0 is perfect; always saying 50% scores 0.25. Lower is better."),
        el("p", {}, "Example: you say 80% and it happens: (0.8 − 1)² = 0.04. It doesn't happen: (0.8 − 0)² = 0.64. Confident misses hurt."),
        el("p", {}, HZ.term("calibration", "Calibration"), " asks whether your 70%s happen 70% of the time. ", HZ.term("discrimination", "Discrimination"), " asks whether you give higher numbers to things that happen. The second is the real skill."),
        q ? el("p", {}, el("b", {}, "Your record: "), q.n_resolved, " resolved questions so far. Below 100, every statistic is ", el("b", {}, "noisy"), ": read the direction, not the decimals.") : null];
    }, quiz: { id: "scores", q: "You said 90% and it didn't happen. Your Brier score on that question is…", options: ["0.01", "0.81", "0.09"], answer: 1, why: "(0.9 − 0)² = 0.81: confident misses cost a lot." } },
    { id: "calls", title: "Making a call (worked example)", c: "s-cal", body: (D) => {
      const ev = ((D.cal && D.cal.events) || []).find((e) => e.base_rate && e.date >= HZ.today());
      return [el("p", {}, "A call is a probability plus your reasons. Horizons sends you to a short GitHub form; a robot records it, adds the market's and the AI's numbers at that moment, and scores it when the event resolves."),
        el("ol", {}, el("li", {}, "Start from the ", HZ.term("base rate"), ".", ev ? [" For ", ev.title, ": ", ev.base_rate.text, "."] : null),
          el("li", {}, "Adjust for up to three things that are different now, each up or down."),
          el("li", {}, "Write the scenarios (they must add up to 100) and your probability."),
          el("li", {}, "Say what would change your mind, with a date (you'll get a reminder), and a one-line pre-mortem: how could this be wrong?"),
          el("li", {}, "Submit. The market's and the AI's probabilities stay hidden until you have.")),
        ev ? el("div", { class: "btns" }, HZ.callBtn({ title: ev.title, question: ev.title + ": ", question_id: ev.id, resolution_date: ev.date, base_rate: ev.base_rate.text }, "Try it on " + ev.title)) : null];
    }, quiz: { id: "calls", q: "What should a call start from?", options: ["Your gut feeling", "The base rate: how often this happened before", "The market price"], answer: 1, why: "Starting from the base rate anchors you to history before adjusting for what's different." } },
    { id: "trades", title: "Making a paper trade (worked example)", c: "s-rec", body: (D) => {
      const x = D.t.usdbrl ? D.t.usdbrl.level : 5.4, stop = x * 1.03;
      return [el("p", {}, "A ", HZ.term("paper trade"), " is pretend money, real prices. Example: you think the real will strengthen over two months."),
        el("ol", {}, el("li", {}, "Short USD/BRL (that's ", HZ.term("long", "long"), " the real). Today: ", fmt(x, 3), "."),
          el("li", {}, "Stop at ", fmt(stop, 3), " (3% against you). Size by risk: risk $1,000, so the position is about $33,000 (3% of $33,000 ≈ $1,000)."),
          el("li", {}, "Target, horizon date, one-line thesis, thesis type."),
          el("li", {}, "Submit: it fills at the next published close. You earn the interest gap (carry) while you wait.")),
        el("p", {}, "Closing: tap Close and write two lines: what happened against your thesis, and what you'd do differently. Results are measured in ", HZ.term("R", "units of risk"), ": +1.5R means you made 1.5 times what you risked."),
        el("div", { class: "btns" }, HZ.tradeBtn("USDBRL", { thesis: "" }, "Open a paper trade"))];
    }, quiz: { id: "trades", q: "You risk $1,000 to your stop and the trade makes $2,000. In units of risk that is…", options: ["+0.5R", "+2R", "+1R"], answer: 1, why: "2,000 ÷ 1,000 = 2R." } },
    { id: "charts", title: "How to read each chart", c: "s-help", body: () => [
      el("p", {}, el("b", {}, "Line charts: "), "time runs left to right; the line is the level. The dot is the latest value. Touch anywhere to read that day. Use 1Y / 5Y / All to zoom out: a big move on 1Y can look small over 5 years."),
      el("p", {}, el("b", {}, "Shaded bands: "), "a normal range (for example the past year). Outside it means unusual."),
      el("p", {}, el("b", {}, "Rings: "), "how full something is: days to an event, a probability, a hit rate."),
      el("p", {}, el("b", {}, "Scales: "), "a pin on a line between two ends, such as interventionist ↔ orthodox policy."),
      el("p", {}, el("b", {}, "Tables: "), "every statistic shows n, how many items it is based on. Small n means luck matters a lot."),
      el("p", {}, el("b", {}, "Colours: "), "each country has its own colour. Green with + and red with − are used only for your gains and losses; market moves are shown with a sign in neutral ink.")],
      quiz: { id: "charts", q: "A hit rate shows 80% with n = 5. How much should you trust it?", options: ["A lot: 80% is high", "Little: 5 items is mostly luck", "Completely"], answer: 1, why: "With only 5 items, one more win or loss changes the rate by 20 points." } },
    { id: "crowd", title: "Reading crowd signals", c: "s-crowd", body: () => [
      el("p", {}, "Prices can be wrong when everyone makes the same mistake. Horizons watches for this: polls versus prediction markets, forecasters who all agree (low ", HZ.term("dispersion"), "), and speculators all on one side (", HZ.term("positioning"), ")."),
      el("p", {}, "Each signal carries a badge saying whether it has been tested. Untested signals are context, not proof.")],
      quiz: { id: "crowd", q: "All forecasters agree closely. Why might that be a warning sign?", options: ["It never is", "If they are wrong together, the surprise is bigger", "It means the forecast is certain"], answer: 1, why: "Low disagreement means a shared error would hit everyone at once." } },
    { id: "schools", title: "Economic schools, in one page", c: "s-help", body: () => [
      el("p", {}, "Economists disagree about what drives growth and inflation. Horizons shows each school's strongest case on current policy, so you can test your own view against all of them."),
      el("ul", {}, el("li", {}, el("b", {}, "Keynesian: "), "demand drives output in the short run; deficits can help in a slump."),
        el("li", {}, el("b", {}, "Monetarist (Friedman): "), "inflation is about money; prefer stable rules."),
        el("li", {}, el("b", {}, "Austrian (Hayek, Mises): "), "cheap credit causes booms that end in busts; distorted prices misallocate capital."),
        el("li", {}, el("b", {}, "Supply-side: "), "growth comes from incentives: taxes and regulation."),
        el("li", {}, el("b", {}, "Modern Monetary Theory: "), "a country borrowing in its own currency is limited by inflation, not debt.")),
      el("p", {}, "History rarely proves one school right: country pages show what followed past episodes, including ones that cut against each school.")],
      quiz: { id: "schools", q: "Which school would most worry that a long period of very cheap credit creates a bust?", options: ["Austrian", "MMT", "Keynesian"], answer: 0, why: "The Austrian school argues artificially cheap credit misallocates capital and ends in a bust." } },
  ];
  HZ.LESSONS = LESSONS;

  function lessonNode(L, D, short) {
    const body = Promise.resolve(L.body(D));
    const holder = el("div", {}, HZ.skel("lines"));
    body.then((b) => { holder.replaceChildren(...HZ.nn(b)); HZ.glossarize(holder); }).catch((e) => holder.replaceChildren(HZ.err(e)));
    return el("div", {}, holder, short ? null : quiz(L.quiz));
  }

  HZ.pageHelp = function (id) {
    return live().then((D) => {
      const L = LESSONS.find((x) => x.id === id);
      if (L) {
        HZ.ctx.reset("Lesson: " + L.title, "Explain this lesson's idea using today's numbers, and give me one harder follow-up question.");
        HZ.ctx.add("Lesson", [L.title]);
        const i = LESSONS.indexOf(L), nx = LESSONS[i + 1];
        return [HZ.pageHead(L.title, "A short lesson with today's numbers.", L.c), card({ cls: L.c }, lessonNode(L, D)),
          el("div", { class: "btns" }, el("a", { class: "btn", href: "#help" }, "All lessons"), nx ? el("a", { class: "btn primary " + nx.c, href: "#help/" + nx.id }, "Next: " + nx.title) : null)];
      }
      HZ.ctx.reset("Help", "I'm learning to read bond, currency and gold markets. What should I learn next, given what's happening this week?");
      const done = LESSONS.filter((x) => HZ.store.get("quiz." + x.id, "") === "1").length;
      return [HZ.pageHead("Help and lessons", "Short lessons that use today's data. Each ends with one question.", "s-help"),
        card({ title: "Your progress", cls: "s-help glow" }, el("div", { class: "row" }, HZ.ring(done / LESSONS.length, done + "/" + LESSONS.length, { size: 76, title: done + " of " + LESSONS.length + " lessons answered correctly" }),
          el("div", {}, el("p", { style: "margin:0" }, done ? "You've answered " + done + " lesson question" + (done === 1 ? "" : "s") + " correctly." : "Start anywhere. Each lesson takes about two minutes."),
            el("button", { type: "button", class: "btn soft", onclick: () => HZ.walkthrough(true) }, "Replay the welcome tour")))),
        el("div", { class: "grid2" }, ...LESSONS.map((x) => el("a", { class: "card pop ccard " + x.c, href: "#help/" + x.id, style: "margin:0" },
          el("div", { class: "row spread" }, el("h3", { style: "margin:0" }, x.title), HZ.store.get("quiz." + x.id, "") === "1" ? el("span", { class: "chip c" }, "✓ done") : null)))),
        el("div", { class: "btns" }, el("a", { class: "btn", href: "#glossary" }, "Glossary of every term"))];
    });
  };

  HZ.pageGlossary = function () {
    HZ.ctx.reset("Glossary");
    const list = Object.entries(HZ.TERMS).sort((a, b) => a[1].t.localeCompare(b[1].t));
    const box = el("div", {});
    const draw = (q) => box.replaceChildren(...list.filter(([, t]) => !q || (t.t + " " + (t.aka || []).join(" ") + " " + t.short).toLowerCase().includes(q.toLowerCase()))
      .map(([k, t]) => el("div", { style: "padding:10px 0;border-bottom:1px solid var(--line)" }, el("button", { type: "button", class: "term noterm", "data-term": k }, el("b", {}, t.t)), el("div", { class: "small muted noterm" }, t.short))));
    const input = el("input", { type: "search", placeholder: "Search terms", "aria-label": "Search terms", style: "width:100%;font:inherit;padding:12px 14px;border-radius:14px;border:1.5px solid var(--line);background:var(--card-solid);color:var(--ink)" });
    input.addEventListener("input", () => draw(input.value));
    draw("");
    return [HZ.pageHead("Glossary", list.length + " terms. Tap one for its full meaning.", "s-help"), card({ cls: "s-help" }, input, box)];
  };

  // ---------------- welcome walkthrough ----------------
  HZ.walkthrough = function (force) {
    if (!force && HZ.store.get("welcomed", "") === "1") return;
    live().then((D) => {
      const g = D.gold && D.gold.prices && D.gold.prices.gold;
      const ev = ((D.cal && D.cal.events) || []).filter((e) => e.importance === 3 && e.date >= HZ.today())[0];
      const steps = [
        ["Welcome to Horizons", [el("p", {}, "Horizons follows Brazil, Mexico and France (their government bonds and currencies) and gold. It shows everything, and explains it."),
          el("p", {}, "Under each chart you'll see what it shows, how to read it and what to look for right now. Change that any time in the menu (☰): Explain mode Full, Light or Off. Dotted words can be tapped for their meaning.")]],
        ["Bonds", [el("p", {}, "A bond is a loan to a government. Its yield is the return at today's price. Yields up = prices down."),
          el("p", {}, "You make money when yields fall, plus the interest. You lose when yields rise. Brazil's 10-year proxy yields ", el("b", {}, lvl(D, "br10y", 2, "about 13") + "%"), " today.")]],
        ["Currencies", [el("p", {}, "USD/BRL ", el("b", {}, lvl(D, "usdbrl", 3, "")), " means one dollar buys that many reais. Up = the real is weaker. EUR/USD is the other way round: up = the euro is stronger."),
          el("p", {}, "You make money long a currency when it strengthens, and from the interest gap (carry). You lose when it weakens, which can happen fast in a crisis.")]],
        ["Gold", [el("p", {}, "Gold pays nothing, is priced in dollars, and is bought in fear.", g ? [" Today: $", fmt(g.value, 0), " an ounce."] : null),
          el("p", {}, "It tends to fall when real interest rates and the dollar rise, and to rise with war, political tension and central-bank buying.")]],
        ["Catalysts", [el("p", {}, "A catalyst is a dated event that can move prices: an election, a budget vote, a rating review, a central-bank decision."),
          ev ? el("p", {}, "Next major one: ", el("b", {}, ev.title), ", ", HZ.inDays(ev.date), ".") : null]],
        ["Reading the scores", [el("p", {}, "You give probabilities, not yes/no. They are scored with the Brier score: 0 is perfect, 0.25 is a coin flip, lower is better."),
          el("p", {}, "Every statistic shows n, how many items it rests on. Under 100 resolved questions it's labelled noisy.")]],
        ["Make a call: an example", [el("p", {}, ev && ev.base_rate ? ["Take ", ev.title, ". Base rate: ", ev.base_rate.text, ". "] : "Start from the base rate: how often this happened before. ",
          "Adjust for what's different now, write the scenarios and your probability, what would change your mind, and how you could be wrong."),
          el("p", {}, "Tap Make a call; GitHub opens a short form. A robot records it and scores it later.")]],
        ["Make a paper trade: an example", [el("p", {}, "Think the peso will strengthen? Short USD/MXN (now ", lvl(D, "usdmxn", 3, "about 18.8"), "). Put a stop 3% away and risk $1,000, so the size is about $33,000."),
          el("p", {}, "It fills at the next close. You earn the interest gap while you wait. Close it with a two-line post-mortem. Results are counted in units of the risk you took.")]],
        ["Ask Claude", [el("p", {}, "The Ask Claude button (bottom right, and on every page) copies what you're looking at (data with dates, the brief, Horizons' view, your calls) and opens Claude so you can paste and ask, using your own Claude subscription."),
          el("p", {}, "Help and short lessons are in the menu (☰). This tour won't show again unless you ask for it.")]],
      ];
      let i = 0;
      const render = () => {
        const [title, body] = steps[i];
        const dots = el("div", { class: "steps", "aria-hidden": "true" }, ...steps.map((_, k) => el("i", { class: k === i ? "on" : "" })));
        HZ.sheet(el("div", {}, el("span", { class: "label" }, "Welcome · " + (i + 1) + " of " + steps.length), el("h2", { id: "sheet-title" }, title), ...HZ.nn(body), dots,
          el("div", { class: "btns", style: "justify-content:space-between" },
            i ? el("button", { type: "button", class: "btn", onclick: () => { i--; render(); } }, "Back") : el("button", { type: "button", class: "btn", onclick: finish }, "Skip"),
            i < steps.length - 1 ? el("button", { type: "button", class: "btn primary", onclick: () => { i++; render(); } }, "Next") : el("button", { type: "button", class: "btn primary", onclick: finish }, "Start exploring"))), ["s-home", "c-BR", "c-MX", "c-GOLD", "s-cal", "s-rec", "s-cal", "s-rec", "s-home"][i]);
      };
      const finish = () => { HZ.store.set("welcomed", "1"); HZ.closeSheet(); };
      render();
    });
  };
})();
