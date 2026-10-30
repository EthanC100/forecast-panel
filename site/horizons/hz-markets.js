/* Horizons: Calendar, Scenarios and Crowd. The same content as Catalyst's pages, read from the same
   files (calendar.json, scenarios.json, crowd.json, lab/crowd_tests.json, consensus.json,
   book/judgements.json), with the same forms, explained per Explain mode. */
(function () {
  "use strict";
  const { el, svg, nn, fmt, pct } = HZ;
  const BADGE = { tested_leads: ["Tested: leads", "Tested in a research repo and found to move before its target."],
    tested_no_lead: ["Tested: no lead", "Tested, and no lead was found (or it failed out of sample). Treat as context."],
    untested: ["Untested", "Not tested as a signal yet: a reading, not a prediction."], context: ["Context", "Background, not meant as a signal."] };
  const TYPE = { rates: "central bank", politics: "politics", election: "election", fiscal: "budget", budget: "budget", rating: "rating", data: "data", survey: "survey", trade: "trade" };
  const INSTR = { BR: "USDBRL", MX: "USDMXN", FR: "OATBUND", GLOBAL: "US10Y", US: "US10Y" };
  const M = { calTab: "2w", calCountry: "ALL", calRoutine: true };

  // ---------------- small pieces ----------------
  HZ.badge = HZ.badge || function (ev) {
    if (!ev || !ev.badge) return null;
    const [lab, base] = BADGE[ev.badge] || [ev.badge, ""];
    return el("button", { type: "button", class: "chip", title: ev.reason || base, onclick: () => HZ.sheet(el("div", {}, el("span", { class: "label" }, "Evidence badge"),
      el("h2", { id: "sheet-title" }, lab), el("p", {}, base), ev.reason ? el("p", { class: "small" }, ev.reason) : null,
      ev.report ? el("a", { class: "btn soft", href: "https://github.com/" + HZ.REPO + "/blob/main/" + ev.report, target: "_blank", rel: "noopener" }, "Read the lab report") : null)) }, "◎ " + lab);
  };
  HZ.ctryChip = HZ.ctryChip || ((c) => el("span", { class: "chip c c-" + c }, HZ.NAMES[c] || c));
  const impDots = (n) => el("span", { class: "num", title: "importance " + n + " of 3", "aria-label": "importance " + n + " of 3", style: "letter-spacing:2px;color:var(--ci,var(--ink-2))" }, "●".repeat(n), el("span", { style: "opacity:.25" }, "●".repeat(3 - n)));
  const statusChip = (s) => el("span", { class: "chip" + (s === "confirmed" ? " fact" : ""), title: s === "confirmed" ? "Date published by the institution or fixed in law" : "Date from a rule or past pattern: check it" }, s === "confirmed" ? "✓ confirmed" : "≈ estimated");
  const table = (head, rows) => el("div", { class: "scroll" }, el("table", {}, el("thead", {}, el("tr", {}, ...head.map((h) => el("th", { class: h.r ? "r" : "" }, h.t || h)))), el("tbody", {}, ...rows)));
  const signed = HZ.signed;
  const revealed = () => { try { return JSON.parse(HZ.store.get("revealed", "{}")) || {}; } catch (e) { return {}; } };
  const reveal = (k) => { const r = revealed(); r[k] = 1; HZ.store.set("revealed", JSON.stringify(r)); HZ.route(); };
  /** A horizontal range with shaded zones, past readings as small dots and current marks. */
  const strip = (o) => {
    const W = 360, H = 52, L = 12, R = 12, x = (v) => L + (Math.max(o.min, Math.min(o.max, v)) - o.min) / (o.max - o.min) * (W - L - R);
    const g = svg("svg", { class: "chart", viewBox: `0 0 ${W} ${H}`, role: "img", "aria-label": o.aria || "range" });
    g.appendChild(svg("rect", { x: L, y: 22, width: W - L - R, height: 8, rx: 4, fill: "var(--bg-2)", stroke: "var(--line)" }));
    (o.zones || []).forEach(([a, b]) => g.appendChild(svg("rect", { x: x(a), y: 22, width: Math.max(2, x(b) - x(a)), height: 8, rx: 4, fill: "var(--c,var(--coral))", opacity: ".45" })));
    (o.history || []).forEach((v) => g.appendChild(svg("circle", { cx: x(v), cy: 26, r: 2.6, fill: "var(--ink-3)", opacity: ".55" })));
    (o.ticks || []).forEach((t) => g.appendChild(svg("text", { class: "lbl", x: x(t), y: H - 4, "text-anchor": "middle" }, o.fmt ? o.fmt(t) : String(t))));
    (o.marks || []).forEach((m) => { g.appendChild(svg("circle", { cx: x(m.v), cy: 26, r: 8, fill: "var(--card-solid)", stroke: "var(--ink)", "stroke-width": 3 }));
      g.appendChild(svg("text", { class: "lbl", x: x(m.v), y: 12, "text-anchor": "middle", style: "font-weight:800;fill:var(--ink)" }, m.label || "")); });
    return g;
  };
  HZ.strip = HZ.strip || strip;
  const myCalls = () => HZ.maybe("book/judgements.json").then((j) => {
    const by = {};
    ((j && j.questions) || []).forEach((q) => { if (q.question_id) by[q.question_id] = q; by[q.key] = q; });
    return by;
  });
  const lastProb = (q) => q && q.forecasts && q.forecasts.length ? q.forecasts[q.forecasts.length - 1].prob : null;

  // =====================================================================
  // Calendar
  // =====================================================================
  function timeline(evs, days) {
    const ctrs = ["BR", "MX", "FR", "GLOBAL"].filter((c) => evs.some((e) => e.country === c));
    if (!ctrs.length) return null;
    const W = 360, RH = 30, T = 22, L = 58, H = T + ctrs.length * RH + 6, t0 = Date.parse(HZ.today()), span = days * 864e5;
    const x = (d) => L + (Date.parse(d) - t0) / span * (W - L - 12);
    const g = svg("svg", { class: "chart", viewBox: `0 0 ${W} ${H}`, role: "img", "aria-label": "Timeline of events by country" });
    const ticks = days <= 14 ? [0, 7, 14] : days <= 92 ? [0, 30, 61, 92] : [0, 91, 182, 274, 366];
    ticks.forEach((d) => { const iso = new Date(t0 + d * 864e5).toISOString().slice(0, 10);
      g.appendChild(svg("line", { class: "ax", x1: x(iso), x2: x(iso), y1: T - 4, y2: H - 4 }));
      g.appendChild(svg("text", { class: "lbl", x: x(iso), y: 12, "text-anchor": d === 0 ? "start" : "middle" }, d === 0 ? "today" : HZ.dateShort(iso))); });
    ctrs.forEach((c, i) => {
      const y = T + i * RH + RH / 2;
      g.appendChild(svg("text", { class: "lbl", x: 4, y: y + 4, style: "font-size:11px;font-weight:800;fill:var(--ink-2)" }, HZ.NAMES[c]));
      g.appendChild(svg("line", { x1: L, x2: W - 12, y1: y, y2: y, stroke: "var(--line)", "stroke-width": 4, "stroke-linecap": "round" }));
      evs.filter((e) => e.country === c).forEach((e) => {
        const dot = svg("circle", { class: "c-" + c, cx: x(e.date), cy: y, r: 2 + 1.6 * e.importance, fill: "var(--c)", "fill-opacity": e.importance === 3 ? ".9" : ".55", stroke: e.importance === 3 ? "var(--ink)" : "none", "stroke-width": 1.5 });
        dot.appendChild(svg("title", {}, e.date + " · " + e.title + " · importance " + e.importance)); g.appendChild(dot);
      });
    });
    return g;
  }
  function eventCard(e, calls, scen) {
    const d = HZ.daysUntil(e.date), att = e.attention, mine = calls[e.id] || calls["ev:" + e.id] || (scen && calls[scen.question_id]);
    const ua = e.under_attended != null ? e.under_attended : (e.importance === 3 && att && att.score < 0.5 && d >= 30);
    const dt = new Date(e.date + "T12:00:00Z");
    return el("article", { class: "card c-" + e.country + (e.importance === 3 ? " pop glow" : ""), id: "ev-" + e.id, style: "padding:14px 16px" },
      el("div", { class: "row", style: "align-items:flex-start;flex-wrap:nowrap" },
        el("div", { style: "flex:0 0 58px;text-align:center;border-radius:16px;padding:6px 0;background:color-mix(in srgb,var(--c) 22%,transparent)" },
          el("div", { style: "font-size:1.5rem;font-weight:800;line-height:1.1" }, String(dt.getUTCDate())),
          el("div", { class: "tiny", style: "color:var(--ink-2);font-weight:700" }, dt.toLocaleDateString("en-GB", { month: "short", timeZone: "UTC" }))),
        el("div", { style: "min-width:0;flex:1" },
          el("h3", { style: "margin:0 0 4px" }, e.title),
          el("div", { class: "row small", style: "gap:6px" }, HZ.ctryChip(e.country), el("span", { class: "chip" }, TYPE[e.type] || e.type), impDots(e.importance), statusChip(e.status),
            el("b", { class: "small" }, HZ.inDays(e.date))),
          el("div", { class: "row small", style: "margin-top:6px;gap:8px" },
            att ? el("span", { title: "News coverage of this event's keywords, last 30 days vs the past year (1.0 = normal)" }, "attention ", el("b", { class: "num" }, "×" + fmt(att.score, 2))) : el("span", { class: "tiny" }, "no attention data"),
            ua ? el("span", { class: "chip warn" }, "⚠ under-attended") : null,
            e.source ? el("a", { href: e.source, target: "_blank", rel: "noopener" }, "source") : null),
          e.base_rate ? el("div", { class: "small", style: "margin-top:4px" }, el("b", {}, "Base rate: "), e.base_rate.text) : null,
          e.note ? el("details", {}, el("summary", { class: "small" }, "note"), el("div", { class: "small muted" }, e.note)) : null,
          scen ? el("div", { class: "small", style: "margin-top:4px" }, el("a", { href: "#scenarios/" + scen.id }, "Scenario page: " + scen.title + " →")) : null,
          mine ? el("div", { class: "small", style: "margin-top:6px" }, el("span", { class: "chip c" }, "my call " + pct(lastProb(mine))), " ", mine.key) : null,
          e.importance >= 2 && d >= 0 ? el("div", { class: "btns" },
            mine ? HZ.formBtn("Quick update", "quick-update", { target: mine.key, title: "[Quick update] " + mine.key }, "soft small")
              : HZ.formBtn("Make a call", "full-call", { question: e.title + ": ", question_id: e.id, resolution_date: e.date, base_rate: e.base_rate ? e.base_rate.text : "", title: "[Full call] " + e.title }, "primary small"),
            HZ.formBtn("Open a paper trade", "open-trade", { title: "[Open trade] " + (INSTR[e.country] || "US10Y"), instrument: INSTR[e.country] || "US10Y", link: e.id, horizon: e.date }, "soft small")) : null)));
  }
  HZ.pageCalendar = function (arg, params) {
    if (["2w", "3m", "12m"].includes(arg)) M.calTab = arg;
    HZ.ctx.reset("Calendar", "Which of these catalysts is the market most likely underestimating, and what should I watch before it?");
    return Promise.all([HZ.json("calendar.json"), HZ.maybe("scenarios.json"), myCalls()]).then(([cal, sc, calls]) => {
      const f = el("div", { class: "s-cal" });
      const lim = { "2w": 14, "3m": 92, "12m": 366 }[M.calTab];
      const win = cal.events.filter((e) => { const d = HZ.daysUntil(e.date); return d >= 0 && d <= lim; });
      let evs = M.calCountry === "ALL" ? win : win.filter((e) => e.country === M.calCountry);
      if (!M.calRoutine) evs = evs.filter((e) => e.importance > 1);
      const scenFor = {}; ((sc && sc.scenarios) || []).forEach((s) => { if (s.event) scenFor[s.event.id] = s; });
      const i3 = evs.filter((e) => e.importance === 3), ua = evs.filter((e) => e.under_attended);
      const noCall = i3.filter((e) => !(calls[e.id] || calls["ev:" + e.id] || (scenFor[e.id] && calls[scenFor[e.id].question_id])));
      f.appendChild(HZ.pageHead("Calendar", "Dated events that can move bonds, currencies and gold: when they are, how much they matter, and whether anyone is paying attention.", "s-cal"));
      const tabs = el("div", { class: "tabs", role: "tablist" }, ...[["2w", "Next 2 weeks"], ["3m", "3 months"], ["12m", "12 months"]].map(([k, l]) =>
        el("a", { href: "#calendar/" + k, role: "tab", "aria-selected": String(M.calTab === k), class: M.calTab === k ? "on" : "" }, l)));
      const fl = el("div", { class: "tabs" }, ...["ALL", "BR", "MX", "FR", "GLOBAL"].map((c) => el("button", { type: "button", class: (M.calCountry === c ? "on " : "") + "c-" + c, onclick: () => { M.calCountry = c; HZ.route(); } }, c === "ALL" ? "All" : HZ.NAMES[c])),
        el("button", { type: "button", class: M.calRoutine ? "on" : "", "aria-pressed": String(M.calRoutine), onclick: () => { M.calRoutine = !M.calRoutine; HZ.route(); } }, M.calRoutine ? "Routine shown" : "Routine hidden"));
      f.append(tabs, fl);
      const first3 = i3[0];
      f.appendChild(HZ.card({ title: "The window at a glance", cls: "s-cal" },
        el("div", { class: "row", style: "gap:18px" },
          el("div", { class: "row" }, HZ.ring(evs.length ? i3.length / evs.length : 0, String(evs.length), { title: evs.length + " events" }), el("div", { class: "small" }, el("b", {}, evs.length + " events"), el("br"), i3.length + " of them importance 3")),
          el("div", { class: "row" }, HZ.ring(i3.length ? (i3.length - noCall.length) / i3.length : 0, (i3.length - noCall.length) + "/" + i3.length, { title: "calls made on importance-3 events" }), el("div", { class: "small" }, el("b", {}, "calls made"), el("br"), "on importance-3 events"))),
        timeline(evs, lim),
        HZ.explain({ what: "Every dot is a dated event in this window, one row per country. Bigger, outlined dots are importance 3: elections, budget votes, rating reviews and central-bank decisions that can move markets a lot.",
          how: "Read left to right from today. Clusters mean several catalysts land close together, so moves can compound. The rings count the events and how many of the big ones already have a call from you.",
          now: (first3 ? "The next importance-3 event is " + first3.title + " (" + HZ.country(first3.country) + ") " + HZ.inDays(first3.date) + ". " : "No importance-3 event in this window. ") +
            (noCall.length ? noCall.length + " of the " + i3.length + " big events have no call from you yet" + (noCall[0] ? ": start with " + noCall[0].title + "." : ".") : i3.length ? "You have a call on every big event here." : "") +
            (ua.length ? " " + ua.length + " flagged as under-attended: the news is quieter than usual about them." : "") })));
      f.append(...HZ.nn(HZ.explain({ what: "The list of events, nearest first.",
        how: "Each card: date, country, type, importance (● to ●●●), whether the date is confirmed by the institution or estimated from a rule, and news attention. Attention ×1.0 is normal coverage of the event's keywords over the last 30 days compared with the past year (GDELT); under ×0.5 is quiet. 'Under-attended' marks an importance-3 event at least 30 days away that the news is ignoring: surprises are likelier when nobody is looking. The base rate says how often this kind of event went each way before.",
        now: evs.length ? "Lowest attention among the big events: " + ((i3.filter((e) => e.attention).sort((a, b) => a.attention.score - b.attention.score)[0] || {}).title || "–") + "." : "Nothing in this window with these filters." })));
      const list = el("div", { style: "margin-top:12px" });
      evs.forEach((e) => list.appendChild(eventCard(e, calls, scenFor[e.id])));
      if (!evs.length) list.appendChild(el("div", { class: "empty" }, "No events in this window with these filters."));
      f.appendChild(list);
      if (cal.notes && cal.notes.length) f.appendChild(HZ.card({ title: "Notes on the calendar", cls: "s-cal" }, el("ul", { class: "small" }, ...cal.notes.map((n) => el("li", {}, n)))));
      f.appendChild(el("p", { class: "tiny" }, "Sources: events.yaml (hand-sourced, each event linked), Federal Reserve and ECB calendars, recurring releases by rule; attention from GDELT. " + (cal.attention_definition || "") + " Calendar built " + (cal.generated_at || "").replace("T", " ").slice(0, 16) + " UTC."));
      HZ.ctx.add("Calendar (" + { "2w": "next 2 weeks", "3m": "next 3 months", "12m": "next 12 months" }[M.calTab] + ", " + (M.calCountry === "ALL" ? "all countries" : HZ.NAMES[M.calCountry]) + ")",
        evs.filter((e) => e.importance >= 2).slice(0, 25).map((e) => e.date + " · " + HZ.NAMES[e.country] + " · " + e.title + " · importance " + e.importance + " · " + e.status +
          (e.attention ? " · attention ×" + fmt(e.attention.score, 2) : "") + (e.under_attended ? " · UNDER-ATTENDED" : "") + (e.base_rate ? " · base rate: " + e.base_rate.text : "") +
          ((calls[e.id] || calls["ev:" + e.id]) ? " · my call " + pct(lastProb(calls[e.id] || calls["ev:" + e.id])) : "")));
      const want = params && params.get("ev");
      if (want) setTimeout(() => { const n = document.getElementById("ev-" + want); if (n) { n.classList.add("glow"); n.scrollIntoView({ block: "center" }); } }, 60);
      return f;
    });
  };
  HZ.country = HZ.country || ((c) => HZ.NAMES[c] || c);

  // =====================================================================
  // Scenarios
  // =====================================================================
  const shown = (s) => !!revealed()["sc:" + s.id] || !!s.mine;
  const aiShown = (s) => !!(s.mine && s.ai && s.ai.available);
  const revealBtn = (s) => el("button", { type: "button", class: "btn small soft", title: "Hidden so it does not anchor your call; shown automatically once you have made one", onclick: () => reveal("sc:" + s.id) }, "Reveal the market");
  const unitOf = (m) => m.unit === "%" ? "%" : " bp";
  const moveText = (m) => m.value == null ? "–" : signed(m.value, m.unit === "%" ? 2 : 1) + unitOf(m);
  function calcState(s) {
    const c = s.calculator || {}, key = "calc." + s.id;
    let saved = null; try { saved = JSON.parse(HZ.store.get(key, "null")); } catch (e) { saved = null; }
    const st = { good: c.good_level, bad: c.bad_level, custom: false };
    if (saved && saved.good != null && saved.bad != null) Object.assign(st, saved, { custom: saved.good !== c.good_level || saved.bad !== c.bad_level });
    return st;
  }
  const impliedGood = (cur, good, bad) => (good == null || bad == null || good === bad) ? null : (cur - bad) / (good - bad);
  function evaluate(s, st, pMine) {
    const c = s.calculator || {}, a = s.asymmetry || {}, R = a.rules || { gap_pp: 15, reward_risk: 2, min_days: 14, max_days: 183 };
    const pg = impliedGood(c.current, st.good, st.bad), pgc = pg == null ? null : Math.min(1, Math.max(0, pg));
    const calcYes = pgc == null ? null : (a.yes_is_good ? pgc : 1 - pgc);
    const mkt = s.markets && s.markets.yes != null ? s.markets.yes : (st.custom ? calcYes : null);
    const src = s.markets && s.markets.yes != null ? "prediction market (" + s.markets.how + ")" : st.custom ? "your calculator levels" : null;
    const out = { pg, calcYes, mkt, src, checks: [] };
    const mine = pMine != null ? pMine : s.mine && s.mine.prob;
    if (mine != null && mkt != null) {
      const gap = 100 * (mine - mkt);
      out.checks.push({ ok: Math.abs(gap) >= R.gap_pp, text: "My P(YES) " + pct(mine) + " vs market " + pct(mkt) + ": " + signed(gap, 0) + " points (needs ±" + R.gap_pp + ")" });
      const favourGood = (mine > mkt) === a.yes_is_good, target = favourGood ? st.good : st.bad, other = favourGood ? st.bad : st.good;
      const rr = Math.abs(c.current - other) ? Math.abs(target - c.current) / Math.abs(c.current - other) : null;
      out.rr = rr; out.favour = favourGood ? "good" : "bad";
      out.checks.push({ ok: rr != null && rr >= R.reward_risk, text: "Reward-to-risk toward the " + out.favour + " outcome " + (rr == null ? "–" : fmt(rr, 2)) + " : 1 (needs " + R.reward_risk + " : 1)" });
    } else {
      out.checks.push({ ok: false, text: mine == null ? "No call yet: make one to test the gap" : "No market probability: no market lists this, so enter your own levels in the calculator" });
      out.checks.push({ ok: false, text: "Reward-to-risk needs the gap first" });
    }
    const d = s.days_to_event;
    out.checks.push({ ok: d != null && d >= R.min_days && d <= R.max_days, text: d == null ? "No linked event date" : "Event in " + d + " days (window " + R.min_days + "–" + R.max_days + ")" });
    out.flag = out.checks.every((x) => x.ok);
    return out;
  }
  const brText = (s) => { const br = s.base_rate || {}; return [br.reference_class, br.headline || br.reason].filter(Boolean).join(" — ").slice(0, 900); };
  const callButton = (s, probs) => HZ.formBtn(probs ? "Make a call with these probabilities" : "Make a call", "full-call", { title: "[Full call] " + s.title, question: s.question, question_id: s.question_id, resolution_date: s.resolution_date,
    base_rate: brText(s), scenarios: s.branches.map((b, i) => b.label + ": " + (probs ? probs[i] : "")).join("\n") }, "primary");

  function scenarioList(sc) {
    const f = el("div", { class: "s-scen" });
    f.appendChild(HZ.pageHead("Scenarios", "One page per big catalyst: the question, how often it went each way before, what each outcome would do to markets, and how your view compares.", "s-scen"));
    f.appendChild(el("div", { class: "tabs" }, el("a", { href: "#scenarios", class: "on" }, "Scenarios"), el("a", { href: "#crowd" }, "Crowd")));
    const list = sc.scenarios.slice().sort((a, b) => (a.event ? a.event.date : "9") < (b.event ? b.event.date : "9") ? -1 : 1);
    const called = list.filter((s) => s.mine).length;
    f.appendChild(HZ.card({ title: "Your coverage", cls: "s-scen" }, el("div", { class: "row" }, HZ.ring(list.length ? called / list.length : 0, called + "/" + list.length, { title: "scenarios with a call" }),
      el("p", { class: "small", style: "margin:0;flex:1" }, called === list.length ? "You have a call on every scenario." : (list.length - called) + " scenario" + (list.length - called === 1 ? "" : "s") + " without a call from you. The AI's view on each stays hidden until you make yours, so it cannot anchor you.")),
      HZ.explain({ what: "Each card is one catalyst turned into a yes/no question with a resolution date.", how: "The base rate is the starting point: how often this kind of event went this way before. The market price stays hidden until you reveal it or make a call, so you form your own view first. An asymmetry flag means your view, the market and the possible moves line up for a trade worth considering.",
        now: (() => { const n = list.find((s) => !s.mine && s.event && s.days_to_event >= 0); return n ? "Nearest scenario without your call: " + n.title + " (" + HZ.inDays(n.event.date) + ")." : "All upcoming scenarios have your call."; })() })));
    list.forEach((s) => {
      const ev = evaluate(s, calcState(s)), open = shown(s);
      f.appendChild(el("a", { href: "#scenarios/" + s.id, class: "ccard" }, HZ.card({ title: s.title, cls: "c-" + s.country, chips: [HZ.ctryChip(s.country)] },
        el("p", { style: "margin:4px 0 8px" }, s.question),
        el("div", { class: "row small" },
          s.event ? el("span", {}, HZ.dateLong(s.event.date) + " · ", el("b", {}, s.days_to_event >= 0 ? HZ.inDays(s.event.date) : "passed")) : el("span", { class: "tiny" }, "no linked event"),
          s.mine ? el("span", { class: "chip c" }, "my call " + pct(s.mine.prob)) : el("span", { class: "chip" }, "no call yet"),
          el("span", {}, "market ", el("b", {}, open ? pct(ev.mkt) : "hidden")),
          open && ev.flag ? el("span", { class: "chip warn" }, "asymmetry") : null),
        el("div", { class: "tiny", style: "margin-top:6px" }, "Base rate: " + ((s.base_rate || {}).headline || (s.base_rate || {}).reason || "–")))));
      HZ.ctx.add(s.title, [s.question, "Resolves " + s.resolution_date, "Base rate: " + ((s.base_rate || {}).headline || (s.base_rate || {}).reason || "–"),
        s.mine ? "My call: " + pct(s.mine.prob) : "No call from me yet", open && ev.mkt != null ? "Market P(YES): " + pct(ev.mkt) : null]);
    });
    return f;
  }

  function treeCard(s) {
    const key = "tree." + s.id, n = s.branches.length;
    let p = null; try { p = JSON.parse(HZ.store.get(key, "null")); } catch (e) { p = null; }
    if (!Array.isArray(p) || p.length !== n) {
      const mine = s.branches.map((b) => b.p_mine);
      p = mine.every((v) => v != null) ? mine.map((v) => Math.round(v * 100)) : s.branches.map((b, i) => Math.floor(100 / n) + (i < 100 % n ? 1 : 0));
    }
    const bars = el("div"), outs = el("div"), sliders = [];
    function setOne(i, v) {
      v = Math.max(0, Math.min(100, v)); const rest = 100 - v, others = p.reduce((a, x, j) => a + (j === i ? 0 : x), 0);
      p = p.map((x, j) => j === i ? v : others > 0 ? Math.round(x * rest / others) : Math.round(rest / (n - 1)));
      const diff = 100 - p.reduce((a, x) => a + x, 0);
      if (diff) { let k = -1; p.forEach((x, j) => { if (j !== i && (k < 0 || x > p[k])) k = j; }); if (k >= 0) p[k] += diff; }
    }
    function draw() {
      sliders.forEach(([inp, lab], i) => { inp.value = p[i]; lab.textContent = p[i] + "%"; });
      const pYes = s.branches.reduce((a, b, i) => a + (s.yes_branches.includes(b.id) ? p[i] : 0), 0) / 100;
      const ev = evaluate(s, calcState(s), pYes), open = shown(s);
      const moves = (s.instruments || []).map((ins) => {
        let e = 0, miss = 0;
        s.branches.forEach((b, i) => { const m = b.moves.find((x) => x.instrument === ins && x.value != null); if (m) e += p[i] / 100 * m.value; else miss++; });
        const unit = (s.branches.flatMap((b) => b.moves).find((m) => m.instrument === ins) || {}).unit;
        return { ins, e, miss, unit };
      });
      outs.replaceChildren(el("div", { class: "row", style: "gap:16px;margin-top:10px" },
        el("div", { style: "text-align:center" }, HZ.ring(pYes, pct(pYes), { title: "my P(YES)" }), el("div", { class: "tiny" }, "my P(YES)")),
        el("div", { style: "text-align:center" }, open && ev.mkt != null ? HZ.ring(ev.mkt, pct(ev.mkt), { title: "market P(YES)" }) : HZ.ring(0, "?", { title: "market hidden" }), el("div", { class: "tiny" }, open ? "market P(YES)" : "market (hidden)")),
        el("div", { class: "small" }, el("b", {}, "Gap to market: "), open && ev.mkt != null ? signed(100 * (pYes - ev.mkt), 0) + " points" : "–", el("br"),
          el("b", {}, "Reward-to-risk toward your view: "), open && ev.rr != null ? fmt(ev.rr, 2) + " : 1" : "–")),
        el("div", { class: "small", style: "margin-top:8px" }, el("b", {}, "Probability-weighted expected move: "),
          moves.map((m) => m.ins + " " + signed(m.e, m.unit === "%" ? 2 : 1) + (m.unit === "%" ? "%" : " bp") + (m.miss ? " (" + m.miss + " branch" + (m.miss > 1 ? "es" : "") + " without an estimate, counted as 0)" : "")).join(" · ") || "–"),
        open ? (ev.flag ? el("span", { class: "chip warn" }, "asymmetry flag at these probabilities") : el("p", { class: "tiny" }, "No asymmetry flag at these probabilities: " + ev.checks.filter((c) => !c.ok).map((c) => c.text).join("; ") + "."))
          : el("div", { class: "small" }, "The market's figures are hidden until you reveal them or make a call. ", revealBtn(s)),
        el("div", { class: "btns" }, callButton(s, p), el("button", { type: "button", class: "btn small", onclick: () => { HZ.store.set(key, "null"); HZ.route(); } }, "Reset")),
        el("p", { class: "tiny" }, "On the form, set 'My probability' to " + Math.round(pYes * 20) * 5 + "% (GitHub cannot pre-fill dropdowns)."));
      bars.replaceChildren(...s.branches.map((b, i) => el("div", { style: "margin:8px 0" },
        el("div", { class: "row spread small" }, el("span", {}, b.label, " ", el("span", { class: "tiny" }, s.yes_branches.includes(b.id) ? "· YES" : "· NO")), el("b", { class: "num" }, p[i] + "%")),
        HZ.meter(p[i] / 100, b.label + " " + p[i] + "%"))));
      HZ.store.set(key, JSON.stringify(p));
    }
    s.branches.forEach((b, i) => {
      const lab = el("b", { class: "num" }), inp = el("input", { type: "range", min: 0, max: 100, step: 5, style: "width:100%;accent-color:var(--cyan)", "aria-label": "My probability: " + b.label, oninput: (e) => { setOne(i, +e.target.value); draw(); } });
      sliders.push([inp, lab]);
    });
    draw();
    return HZ.card({ title: "How likely is each outcome, and what would that mean for markets?", cls: "s-scen glow" },
      bars, el("details", {}, el("summary", {}, "Set your own probabilities"), ...s.branches.map((b, i) => el("label", { class: "small", style: "display:block;margin:8px 0" }, el("span", { class: "row spread" }, b.label, sliders[i][1]), sliders[i][0]))),
      outs,
      HZ.explain({ what: "The possible outcomes (branches) of this catalyst with your probabilities, and what they add up to.", how: "Drag a slider and the others rescale to keep 100%. P(YES) adds up the branches that count as YES. The expected move multiplies each branch's estimated market move by its probability. The gap compares your P(YES) with the market's: a big gap is where you disagree with the crowd.",
        now: s.mine ? "Your latest call is " + pct(s.mine.prob) + " on " + (s.mine.submitted_at || "").slice(0, 10) + "." : "No call yet. The bars start equal (or at your saved sliders) until you make one." }));
  }
  function branchCard(s, b, open) {
    const side = { good: "▲ favourable for the market", bad: "▼ adverse for the market", mixed: "◆ mixed" }[b.side] || b.side;
    const probRing = (p, lab, hid) => el("div", { style: "text-align:center" }, hid ? HZ.ring(0, hid, { size: 56 }) : HZ.ring(p || 0, p == null ? "–" : pct(p), { size: 56, title: lab }), el("div", { class: "tiny" }, lab));
    return HZ.card({ title: b.label, cls: "s-scen", chips: [el("span", { class: "chip" }, side), el("span", { class: "chip" }, s.yes_branches.includes(b.id) ? "YES" : "NO")] },
      el("div", { class: "row", style: "gap:14px" }, probRing(b.p_mine, "mine"),
        aiShown(s) ? probRing(b.p_ai, "AI " + (s.ai.date || "")) : probRing(null, "AI", s.ai && s.ai.available ? "after" : "–"),
        probRing(b.p_market, "market", open ? null : "?")),
      el("div", { class: "label", style: "margin-top:10px" }, "Expected market move"),
      el("ul", { class: "small" }, ...b.moves.map((m) => el("li", {}, el("b", { class: "num" }, m.instrument + " " + moveText(m)),
        m.lo != null ? el("span", { class: "tiny" }, " [" + signed(m.lo, 1) + ", " + signed(m.hi, 1) + "]" + (m.interval ? " " + m.interval : "")) : null,
        m.assumption ? el("span", { class: "chip", style: "margin-left:4px" }, "assumption") : null, el("div", { class: "tiny" }, (m.basis || "") + (m.source ? " · " + m.source : ""))))),
      el("div", { class: "label" }, "Signposts: early signs this branch is unfolding"),
      el("ul", { class: "small" }, ...b.signposts.map((x) => el("li", {}, x))));
  }
  function aiCard(s) {
    const a = s.ai || {};
    if (!a.available) return null;
    if (!aiShown(s)) return HZ.card({ title: "The AI's judgement", cls: "s-scen" }, el("p", { class: "small" }, "The AI has a probability for this question, recorded blind (it never sees your calls). It appears here once you have made your own call, so it cannot anchor you."), callButton(s));
    return HZ.card({ title: "The AI's judgement (" + (a.date || "") + ")", cls: "s-scen", chips: [el("span", { class: "chip judge" }, "judgement, not fact"), a.verified ? el("span", { class: "chip fact" }, "✓ validated") : el("span", { class: "chip warn" }, "check")] },
      el("div", { class: "row" }, HZ.ring(a.p_yes, pct(a.p_yes)), el("div", { class: "small" }, el("b", {}, "P(YES) " + pct(a.p_yes)), " · confidence " + (a.confidence || "–"), el("br"), "You said " + pct(s.mine && s.mine.prob))),
      a.base_rate_used ? el("p", { class: "small" }, el("b", {}, "Started from: "), a.base_rate_used) : null,
      (a.factors || []).length ? el("ul", { class: "small" }, ...a.factors.map((x) => el("li", {}, (x.effect === "raises" ? "▲ raises: " : "▼ lowers: ") + x.text))) : null,
      a.what_would_change_view ? el("p", { class: "small" }, el("b", {}, "Would change its view: "), a.what_would_change_view) : null,
      a.most_likely_wrong ? el("p", { class: "small" }, el("b", {}, "Most likely way it is wrong: "), a.most_likely_wrong) : null,
      (a.problems || []).length ? el("p", { class: "tiny" }, "Validation notes: " + a.problems.join("; ")) : null,
      el("a", { class: "small", href: "#brief" }, "From the brief →"));
  }
  function calculatorCard(s) {
    const c = s.calculator, st = calcState(s);
    if (!c) return null;
    if (c.error) return HZ.card({ title: "Market-implied probability", cls: "s-scen" }, el("div", { class: "err" }, c.instrument + ": " + c.error));
    const dec = c.kind === "fx" ? 4 : c.unit === "bp" ? 1 : 2, out = el("div"), asym = el("div");
    const inp = (v, on, lab) => el("input", { type: "number", step: "any", inputmode: "decimal", "aria-label": lab, style: "width:100%;min-height:44px;border-radius:12px;border:1.5px solid var(--line);padding:6px 10px;background:var(--card-solid);color:var(--ink);font:inherit", value: v == null ? "" : String(+(+v).toFixed(dec + 1)), oninput: (e) => on(parseFloat(e.target.value)) });
    const lvl = (v) => fmt(v, dec).replace(/,/g, "");
    const tradeBtn = (side) => {
      const target = side === "good" ? st.good : st.bad, stop = side === "good" ? st.bad : st.good;
      if (target == null || stop == null) return null;
      const dir = ((target > c.current) === (c.kind === "fx")) ? "long" : "short";
      return HZ.formBtn("Paper trade: " + side + " outcome (" + dir + ")", "open-trade", { title: "[Open trade] " + dir + " " + c.instrument, instrument: c.instrument, stop: lvl(stop), target: lvl(target), link: s.question_id, horizon: s.resolution_date,
        thesis: "Positioned for the " + side + " outcome of " + s.title + ". Choose direction = " + dir + "." }, "soft small");
    };
    function render() {
      const ev = evaluate(s, st), open = shown(s), pg = ev.pg;
      out.replaceChildren(el("div", { class: "row", style: "gap:16px;margin-top:8px" },
        el("div", { style: "text-align:center" }, open && pg != null ? HZ.ring(Math.min(1, Math.max(0, pg)), pct(Math.min(1, Math.max(0, pg)))) : HZ.ring(0, "?"), el("div", { class: "tiny" }, "implied P(good)")),
        el("div", { style: "text-align:center" }, open && ev.calcYes != null ? HZ.ring(ev.calcYes, pct(ev.calcYes)) : HZ.ring(0, "?"), el("div", { class: "tiny" }, "implied P(YES)"))),
        open && pg != null && (pg < 0 || pg > 1) ? el("div", { class: "err" }, "Today's level is beyond the " + (pg < 0 ? "bad" : "good") + "-outcome level: either the levels are off or the instrument is pricing more than this event.") : null,
        !st.custom ? el("p", { class: "tiny" }, "Defaults are " + (c.default_basis || "the branch move estimates") + " (" + c.good_branch + " " + signed(c.good_move, 1) + ", " + c.bad_branch + " " + signed(c.bad_move, 1) + "). With them the result only restates the move estimates, so it is not used as a market probability until you enter your own levels.") : null);
      asym.replaceChildren(el("h3", {}, "Asymmetry check ", open && ev.flag ? el("span", { class: "chip warn" }, "flag") : null),
        !open ? el("div", { class: "small" }, "Hidden until you reveal the market or make a call. ", revealBtn(s))
          : el("ul", { class: "small", style: "list-style:none;padding:0" }, ...ev.checks.map((x) => el("li", {}, (x.ok ? "✓ " : "✗ ") + x.text))),
        el("p", { class: "tiny" }, "Market probability: " + (ev.src || "none") + ". The flag needs all three: a gap of 15+ points, reward-to-risk 2 : 1 or better toward your view, and the event 2 weeks to 6 months away."),
        el("div", { class: "btns" }, tradeBtn("good"), tradeBtn("bad")));
    }
    render();
    return HZ.card({ title: "What is the market pricing?", cls: "s-scen" },
      el("p", { class: "small" }, c.name + " is at ", el("b", { class: "num" }, fmt(c.current, dec)), " " + (c.unit || "") + " (" + (c.as_of || "") + ")", c.proxy ? el("span", { class: "chip", style: "margin-left:4px" }, "proxy") : null),
      el("div", { class: "grid2", style: "gap:10px" },
        el("label", { class: "small" }, "Level if the good outcome happens", inp(st.good, (v) => { st.good = v; st.custom = true; HZ.store.set("calc." + s.id, JSON.stringify({ good: st.good, bad: st.bad })); render(); }, "level if good outcome")),
        el("label", { class: "small" }, "Level if the bad outcome happens", inp(st.bad, (v) => { st.bad = v; st.custom = true; HZ.store.set("calc." + s.id, JSON.stringify({ good: st.good, bad: st.bad })); render(); }, "level if bad outcome"))),
      el("button", { type: "button", class: "btn small", style: "margin-top:8px", onclick: () => { HZ.store.set("calc." + s.id, "null"); HZ.route(); } }, "Reset levels"),
      out, asym,
      HZ.explain({ what: "A way to read a probability out of a market price: if you know where the price would go in the good and the bad outcome, today's price tells you how likely the market thinks each one is.",
        how: "P(good) = (today − bad level) ÷ (good level − bad level). If today's price sits halfway between the two levels, the market is pricing about 50%. Your levels are saved only on this phone.",
        now: c.range_12m ? c.name + " has ranged " + fmt(c.range_12m[0], dec) + " to " + fmt(c.range_12m[1], dec) + " over 12 months; it is at " + fmt(c.current, dec) + " now." : null }),
      HZ.source(c.source, c.source_url, c.as_of));
  }
  function baseRateCard(s) {
    const b = s.base_rate || {};
    const rows = b.rows || b.recent;
    return HZ.card({ title: "How often has this happened before?", cls: "s-scen" },
      b.reference_class ? el("p", { class: "small" }, el("b", {}, "Compared with: "), b.reference_class) : null,
      b.computed ? el("div", {},
        el("p", { style: "font-size:1.125rem;font-weight:800;margin:6px 0" }, b.headline),
        b.p_yes != null ? el("div", { class: "row" }, HZ.ring(b.p_yes, pct(b.p_yes)), el("span", { class: "small" }, "Base-rate P(YES)" + (b.p_yes_low != null && pct(b.p_yes_low) !== pct(b.p_yes) ? ": " + pct(b.p_yes_low) + " to " + pct(b.p_yes) : ""))) : null,
        b.range_note ? el("p", { class: "tiny" }, b.range_note) : null,
        b.counts ? el("p", { class: "small" }, Object.entries(b.counts).map(([k, v]) => k + " " + v).join(" · ")) : null,
        rows && rows.length ? el("details", {}, el("summary", {}, "The cases (" + rows.length + ")"), table(Object.keys(rows[0]).map((k) => k.replace(/_/g, " ")),
          rows.map((r) => el("tr", {}, ...Object.keys(rows[0]).map((k) => el("td", { class: "small" }, r[k] === true ? "yes" : r[k] === false ? "no" : r[k] == null ? "–" : String(r[k]))))))) : null)
        : el("p", { class: "small" }, el("b", {}, "Not computed. "), b.reason || ""),
      ...(b.context || []).map((c) => el("p", { class: "tiny" }, c)),
      b.event_study && b.event_study.rows ? el("details", {}, el("summary", {}, b.event_study.label || "What markets did after similar events"),
        table(["event", "date", { t: "USD/local day 1 (%)", r: 1 }, { t: "10y day 1 (bp)", r: 1 }], b.event_study.rows.map((r) => el("tr", {}, el("td", { class: "small" }, r.event), el("td", {}, r.date),
          el("td", { class: "r num" }, r.usd_fx_pct == null ? "–" : signed(r.usd_fx_pct, 2)), el("td", { class: "r num" }, r.y10_bp == null ? "–" : signed(r.y10_bp, 1)))))) : null,
      HZ.explain({ what: "The base rate: how often events like this one went the YES way in the past.", how: "Start your forecast here, then move up or down only for reasons specific to this time. People tend to ignore base rates and overreact to the story of the moment.",
        now: b.computed ? "The past says " + (b.p_yes != null ? pct(b.p_yes) : b.headline) + "." + (s.mine ? " Your call is " + pct(s.mine.prob) + "." : "") : "No computed base rate for this one: think of the closest past cases yourself." }),
      HZ.source("em-macro", b.source_url));
  }
  function marketsCard(s) {
    const rows = (s.markets && s.markets.rows) || [], open = shown(s);
    if (!rows.length) return HZ.card({ title: "Prediction markets", cls: "s-scen" }, el("p", { class: "small" }, "No prediction market lists this question. The calculator above is the market read."));
    return HZ.card({ title: "What do betting markets say?", cls: "s-scen", chips: [open ? null : revealBtn(s)] },
      table(["market", { t: "P(yes)", r: 1 }, "maps to"], rows.map((r) => el("tr", {},
        el("td", {}, r.url ? el("a", { href: r.url, target: "_blank", rel: "noopener" }, r.question || r.id) : (r.question || r.id), el("div", { class: "tiny" }, r.venue + (r.note ? " · " + r.note : ""))),
        el("td", { class: "r num" }, open ? pct(r.prob, 1) : "hidden"), el("td", { class: "small" }, r.related ? "related only" : (r.branches || []).join(", "))))),
      open && s.markets.yes != null ? el("p", { class: "small" }, "Market P(YES): ", el("b", {}, pct(s.markets.yes, 1)), " (" + s.markets.how + ")") : null,
      HZ.explain({ what: "Prices from Polymarket and Kalshi, where people bet on this question or a related one.", how: "A price of 30¢ reads as a 30% chance. Thin markets (little money traded) can be wrong or easy to push around. 'Related only' means it is a different question that still tells you something.",
        now: open ? (s.markets.yes != null ? "The markets put YES at " + pct(s.markets.yes) + "." : "No market maps exactly to YES.") : "Hidden so it does not anchor your call." }));
  }
  function indicatorsCard(s) {
    if (!s.indicators || !s.indicators.length) return null;
    return HZ.card({ title: "Live signposts", cls: "s-scen" }, ...s.indicators.map((x) => el("div", { style: "margin:8px 0" },
      el("div", { class: "row spread" }, el("b", {}, x.label), el("span", { class: "num" }, fmt(x.value, 2), x.target != null ? el("span", { class: "tiny" }, " vs target " + fmt(x.target, 2)) : null)),
      el("div", { class: "small muted" }, "3 months ago: " + (x.three_months_ago == null ? "–" : fmt(x.three_months_ago, 2))), HZ.source(x.source, x.source_url, x.as_of))),
      HZ.explain({ what: "Data that moves before the catalyst and hints at which branch is unfolding.", how: "Compare today's value with the target and with 3 months ago: the direction of travel matters more than the level.",
        now: s.indicators.map((x) => x.label + " " + fmt(x.value, 2) + (x.three_months_ago != null ? " (" + (x.value > x.three_months_ago ? "up" : x.value < x.three_months_ago ? "down" : "flat") + " from " + fmt(x.three_months_ago, 2) + ")" : "")).join("; ") + "." }));
  }
  function scenarioPage(s) {
    const f = el("div", { class: "s-scen c-" + s.country }), ev = s.event;
    f.appendChild(el("a", { href: "#scenarios", class: "small" }, "← all scenarios"));
    f.appendChild(HZ.pageHead(s.title, null, "s-scen"));
    f.appendChild(HZ.card({ title: "The question", cls: "glow c-" + s.country, chips: [HZ.ctryChip(s.country)] },
      el("p", { style: "font-size:1.1875rem;font-weight:700" }, s.question),
      el("p", { class: "small" }, el("b", {}, "Resolves " + HZ.dateLong(s.resolution_date) + ". "), s.resolution),
      ev ? el("p", { class: "small" }, el("b", {}, "Catalyst: "), el("a", { href: "#calendar?ev=" + ev.id }, ev.title), " · " + HZ.dateLong(ev.date) + " (" + ev.status + ") · ", el("b", {}, s.days_to_event >= 0 ? HZ.inDays(ev.date) : "passed"),
        ev.source ? [" · ", el("a", { href: ev.source, target: "_blank", rel: "noopener" }, "source")] : null) : null,
      el("div", { class: "btns" }, callButton(s), s.mine ? HZ.formBtn("Quick update", "quick-update", { target: s.mine.branches_from || s.question_id, title: "[Quick update] " + s.question_id }, "soft") : null),
      s.mine ? el("p", { class: "small" }, "Your latest: ", el("b", {}, pct(s.mine.prob)), " (" + (s.mine.record || "") + ", " + (s.mine.submitted_at || "").slice(0, 10) + ")") : el("p", { class: "tiny" }, "Question id " + s.question_id + " and the branch names are pre-filled on the form.")));
    f.appendChild(treeCard(s));
    s.branches.forEach((b) => f.appendChild(branchCard(s, b, shown(s))));
    f.append(...HZ.nn(HZ.explain({ what: "One card per outcome: the probabilities from you, the AI and the market; the moves expected in the instruments; and signposts that would show it unfolding.",
      how: "'Favourable/adverse' is from the market's point of view (for example, a downgrade is adverse for French bonds), not a judgement on your position. Moves marked 'assumption' are judgement or rescaling, not a direct historical estimate.",
      now: "The AI's numbers are " + (aiShown(s) ? "shown because you have made a call." : "hidden until you make a call.") })));
    nn(aiCard(s), calculatorCard(s), baseRateCard(s), marketsCard(s), indicatorsCard(s)).forEach((x) => f.appendChild(x));
    const open = shown(s), evv = evaluate(s, calcState(s));
    HZ.ctx.reset("Scenario: " + s.title, "Given the base rate and the branches, what probability would you put on YES, and which signpost would change your mind fastest?");
    HZ.ctx.add("Question", [s.question, "Resolves " + s.resolution_date + ": " + s.resolution, ev ? "Catalyst: " + ev.title + " on " + ev.date + " (" + ev.status + ")" : null]);
    HZ.ctx.add("Base rate", [(s.base_rate || {}).reference_class, (s.base_rate || {}).headline || (s.base_rate || {}).reason]);
    HZ.ctx.add("Branches", s.branches.map((b) => b.label + (s.yes_branches.includes(b.id) ? " (YES)" : " (NO)") + ": mine " + pct(b.p_mine) + (open ? ", market " + pct(b.p_market) : "") + (aiShown(s) ? ", AI " + pct(b.p_ai) : "") +
      "; moves " + b.moves.map((m) => m.instrument + " " + moveText(m)).join(", ") + "; signposts: " + b.signposts.join("; ")));
    HZ.ctx.add("My call", [s.mine ? pct(s.mine.prob) + " on " + (s.mine.submitted_at || "").slice(0, 10) : "None yet"]);
    if (open) HZ.ctx.add("Market", [evv.mkt != null ? "Market P(YES) " + pct(evv.mkt) + " (" + evv.src + ")" : "No market probability"]);
    if (aiShown(s)) HZ.ctx.add("AI judgement (" + s.ai.date + ", a model's view)", ["P(YES) " + pct(s.ai.p_yes) + ", confidence " + s.ai.confidence, s.ai.most_likely_wrong ? "Most likely wrong because: " + s.ai.most_likely_wrong : null]);
    return f;
  }
  HZ.pageScenarios = function (arg) {
    HZ.ctx.reset("Scenarios", "Which scenario has the biggest gap between the base rate and the market, and why might that be?");
    return Promise.all([HZ.json("scenarios.json"), myCalls()]).then(([sc]) => {
      const s = arg && sc.scenarios.find((x) => x.id === arg);
      return s ? scenarioPage(s) : scenarioList(sc);
    });
  };

  // =====================================================================
  // Crowd
  // =====================================================================
  const GQ = { a: "Do polls and prediction markets disagree about the next vote?", b: "Are pollsters herding or concentrated?", c: "Do forecasters disagree more than usual before the next decision?",
    d: "How much rosier is the official fiscal forecast than independent ones?", e: "Is speculative positioning crowded before a catalyst?", f: "How close is a rating threshold that forces buying or selling?" };
  const EXTREME = { a: "Extreme when the gap is 25+ points: one of the two crowds is badly wrong.",
    b: "Extreme when the herding ratio is below 0.5 (polls agree more than random sampling allows) or one pollster dominates: shared errors are likelier.",
    c: "Extreme in the top fifth of dispersion: the decision is more likely to surprise the survey median (tested on Copom meetings).",
    d: "Extreme when the gap is above 1 point of GDP: the official plan is likely to be revised.",
    e: "Extreme below the 10th or above the 90th percentile with a catalyst within 30 days: little room left to add to the same bet.",
    f: "Extreme one notch from a threshold with a negative outlook: a single action forces index or mandate flows." };
  const HOW = { a: "Polls are turned into a win probability using how wrong polls have been in past elections; the market price is the betting odds. The dots are past elections.",
    b: "The herding ratio compares how much final polls spread with how much random sampling alone would make them spread. Below 1, pollsters agree suspiciously; the 'miss' is how far the final average was from the result.",
    c: "Dispersion is the spread (standard deviation) of forecasters' expectations; the percentile ranks it against past meetings. High disagreement means a bigger chance the decision surprises.",
    d: "Official = the government's own forecast; independent = the median of fiscal councils, the IMF and others. A positive gap means the government is more optimistic.",
    e: "Net positioning of leveraged funds as a share of open interest, ranked against the past three years. Extreme readings mean the trade is crowded.",
    f: "Where each agency's rating sits relative to the line that forces some funds to buy or sell; 'near' means one notch away." };
  function lab(id, L) {
    const t = L && L.tests && L.tests[id];
    if (!t) return null;
    return el("details", {}, el("summary", { class: "small" }, "Lab test: " + (BADGE[t.badge] || [t.badge])[0]),
      el("p", { class: "small" }, t.name), el("p", { class: "small" }, t.reason || ""), t.method ? el("p", { class: "tiny" }, t.method) : null,
      el("a", { class: "small", href: "https://github.com/" + HZ.REPO + "/blob/main/reports/crowd_lab.md", target: "_blank", rel: "noopener" }, "Full lab report"));
  }
  function gaugeCard(g, body, now, L) {
    return HZ.card({ title: GQ[g.id] || g.title, cls: "s-crowd", chips: [HZ.badge(g.evidence)] },
      el("div", { class: "tiny" }, "(" + g.id + ") " + g.title),
      g.error ? el("div", { class: "err" }, g.error) : null, body,
      HZ.explain({ what: g.what || g.title, how: HOW[g.id] + " " + EXTREME[g.id], now }), lab(g.id, L));
  }
  HZ.pageCrowd = function () {
    HZ.ctx.reset("Crowd", "Where could forecasters, pollsters and positioning all be wrong together in the next six months?");
    return Promise.all([HZ.json("crowd.json"), HZ.maybe("scenarios.json"), HZ.maybe("lab/crowd_tests.json"), HZ.maybe("consensus.json")]).then(([C, sc, L, cons]) => {
      const f = el("div", { class: "s-crowd" }), G = {};
      (C.gauges || []).forEach((g) => { G[g.id] = g; });
      const scs = {}; ((sc && sc.scenarios) || []).forEach((s) => { scs[s.id] = s; });
      f.appendChild(HZ.pageHead("Crowd", "Where the crowd (forecasters, pollsters, markets, positioning) could be wrong together. Shared mistakes cause the biggest surprises.", "s-crowd"));
      f.appendChild(el("div", { class: "tabs" }, el("a", { href: "#scenarios" }, "Scenarios"), el("a", { href: "#crowd", class: "on" }, "Crowd")));
      // ranked shared errors
      const se = C.shared_errors || [];
      f.appendChild(HZ.card({ title: "Most likely shared errors in the next 6 months", cls: "s-crowd glow" },
        el("ol", { style: "padding-left:1.2rem" }, ...se.map((it) => { const s = scs[it.scenario], open = s ? shown(s) : false;
          return el("li", { style: "margin-bottom:12px" }, el("div", { class: "row spread" }, el("a", { href: "#scenarios/" + it.scenario }, el("b", {}, it.title)), el("span", { class: "row" }, HZ.ring(Math.min(1, it.score), fmt(it.score, 2), { size: 48, title: "score " + fmt(it.score, 2) }))),
            el("div", { class: "tiny" }, (it.date ? HZ.dateLong(it.date) : "") + " · " + HZ.inDays(it.date || HZ.today())),
            it.signals.length ? el("ul", { class: "small" }, ...it.signals.map((x) => el("li", {}, el("b", {}, x.signal + ": "), x.hidden_market && !open ? "hidden until you reveal the market on the scenario page" : x.detail, " ", el("span", { class: "tiny" }, "strength " + fmt(x.strength, 2)), " ", HZ.badge({ badge: x.badge }))))
              : el("div", { class: "tiny" }, "No signal applies yet")); })),
        el("p", { class: "tiny" }, C.ranking_method || ""),
        HZ.explain({ what: "Upcoming catalysts ranked by how many crowd-error signals point at them at once.", how: "Each signal is one way the crowd could be wrong (markets far from history, a crowded trade, a rating near a forced-selling line). The score adds their strengths, 0 to about 1 each. It is a heuristic, not a tested model.",
          now: se[0] ? "Top of the list: " + se[0].title + " (score " + fmt(se[0].score, 2) + ", " + se[0].signals.length + " signals)." : "No ranked items." })));
      // consensus gaps (my view vs economists)
      const gaps = (cons && (cons.gaps || cons.consensus_gaps)) || [];
      if (gaps.length) f.appendChild(HZ.card({ title: "My view against the economist consensus", cls: "s-crowd" },
        table(["question", { t: "gap (sd)", r: 1 }, "flag"], gaps.map((g) => el("tr", {}, el("td", { class: "small" }, g.label || g.name || g.question_id), el("td", { class: "r num" }, g.gap_in_sd == null ? "–" : signed(g.gap_in_sd, 2)), el("td", {}, g.flagged ? el("span", { class: "chip warn" }, "far from consensus") : "")))),
        HZ.explain({ what: "Where your point forecasts or probabilities sit relative to the median economist.", how: "The gap is in standard deviations of forecasters' disagreement: beyond about 1.5 you are on your own, which is fine if you have a reason.", now: gaps.filter((g) => g.flagged).length + " of your views are flagged as far from consensus." })));
      // (a)
      const a = G.a || {}, ar = a.readings || [], hist = ((L && L.tests.a && L.tests.a.result) || {}).elections || [];
      f.appendChild(gaugeCard(a, el("div", {},
        hist.length ? el("div", {}, el("div", { class: "tiny" }, "Market minus poll-implied probability (points), " + hist.length + " past elections; latest marked"),
          strip({ min: -1, max: 1, ticks: [-1, -0.25, 0, 0.25, 1], fmt: (v) => signed(100 * v, 0), zones: [[-1, -0.25], [0.25, 1]], history: hist.map((x) => x.gap),
            marks: a.latest_resolved ? [{ v: a.latest_resolved.gap, label: signed(100 * a.latest_resolved.gap, 0) }] : [] })) : null,
        ar.length ? table(["contest", { t: "polls", r: 1 }, { t: "market", r: 1 }, { t: "gap", r: 1 }], ar.map((r) => { const op = scs[r.scenario] && shown(scs[r.scenario]);
          return el("tr", {}, el("td", { class: "small" }, r.label, el("div", { class: "tiny" }, "lead " + signed(r.poll_margin_pp, 1) + " pp, σ " + r.sigma_pp + " pp, " + r.poll_date)),
            el("td", { class: "r num" }, pct(r.p_poll)), el("td", { class: "r num" }, op ? pct(r.p_market) : "hidden"), el("td", { class: "r num" }, op && r.gap != null ? signed(100 * r.gap, 0) : "–")); }))
          : el("p", { class: "small" }, a.note || "No current readings."),
        a.latest_resolved ? el("p", { class: "small" }, el("b", {}, "Latest resolved: "), a.latest_resolved.election + ": polls " + pct(a.latest_resolved.p_poll_a) + ", market " + pct(a.latest_resolved.p_market_a) + " for candidate A; A " + (a.latest_resolved.a_won ? "won" : "lost") + ".") : null),
        ar.length ? ar.length + " live contest" + (ar.length > 1 ? "s" : "") + " tracked." : (a.note || "No current polls entered.") + (a.latest_resolved ? " Last time (" + a.latest_resolved.election + ") the gap was " + signed(100 * a.latest_resolved.gap, 0) + " points." : ""), L));
      // (b)
      const b = G.b || {}, hr = (b.elections || []).filter((r) => r.herding_ratio != null);
      f.appendChild(gaugeCard(b, el("div", {},
        hr.length ? el("div", {}, el("div", { class: "tiny" }, "Herding ratio for " + hr.length + " elections; latest marked"), strip({ min: 0, max: 5, ticks: [0, 0.5, 1, 2, 5], fmt: (v) => fmt(v, v < 1 ? 1 : 0), zones: [[0, 0.5]], history: hr.map((r) => r.herding_ratio), marks: [{ v: hr[0].herding_ratio, label: fmt(hr[0].herding_ratio, 2) }] })) : null,
        table(["election", { t: "polls", r: 1 }, { t: "pollsters", r: 1 }, { t: "top share", r: 1 }, { t: "herding", r: 1 }, { t: "miss (pp)", r: 1 }], (b.elections || []).slice(0, 8).map((r) => el("tr", {},
          el("td", { class: "small" }, r.election), el("td", { class: "r num" }, String(r.n_polls)), el("td", { class: "r num" }, String(r.n_pollsters)), el("td", { class: "r num", title: r.top_pollster }, pct(r.top_share)),
          el("td", { class: "r num" }, r.herding_ratio == null ? "–" : fmt(r.herding_ratio, 2)), el("td", { class: "r num" }, r.miss == null ? "–" : signed(r.miss, 1))))),
        (b.elections || [])[0] ? el("details", {}, el("summary", { class: "small" }, "House effects, " + b.elections[0].election), el("p", { class: "small" }, Object.entries(b.elections[0].house_effects || {}).map(([k, v]) => k + " " + signed(v, 1)).join(" · "))) : null,
        b.upcoming ? el("p", { class: "tiny" }, b.upcoming) : null),
        hr.length ? "Latest: " + hr[0].election + ", herding ratio " + fmt(hr[0].herding_ratio, 2) + (hr[0].herding_ratio < 0.5 ? " (suspiciously tight)" : hr[0].herding_ratio < 1 ? " (somewhat tight)" : " (normal spread)") + (hr[0].miss != null ? ", polls missed by " + signed(hr[0].miss, 1) + " pp." : ".") : "No pollster data yet.", L));
      // (c)
      const c = G.c || {}, cr = c.readings || [];
      f.appendChild(gaugeCard(c, el("div", {},
        ...cr.filter((r) => r.percentile != null).map((r) => el("div", {}, el("div", { class: "small" }, r.label + ": ", el("b", { class: "num" }, "sd " + fmt(r.value, 3) + ", percentile " + fmt(r.percentile, 0)), " ", HZ.badge(r.evidence)),
          strip({ min: 0, max: 100, ticks: [0, 50, 80, 100], zones: [[80, 100]], marks: [{ v: r.percentile, label: fmt(r.percentile, 0) + "th" }] }))),
        table(["survey", { t: "sd", r: 1 }, { t: "percentile", r: 1 }, "next decision"], cr.map((r) => el("tr", {}, el("td", { class: "small" }, r.label, el("div", { class: "tiny" }, "median " + fmt(r.median, 2) + " · " + r.as_of)),
          el("td", { class: "r num" }, fmt(r.value, 3)), el("td", { class: "r num" }, r.percentile == null ? "–" : fmt(r.percentile, 0), r.extreme ? el("span", { class: "chip warn", style: "margin-left:4px" }, "wide") : null), el("td", { class: "small" }, r.event ? r.event.date : "–"))))),
        cr.filter((r) => r.extreme).length ? "Disagreement is unusually wide for: " + cr.filter((r) => r.extreme).map((r) => r.label).join(", ") + "." : cr.length ? "No survey shows unusually wide disagreement right now." : "No readings.", L));
      // (d)
      const d = G.d || {}, dr = d.rows || [], big = dr.filter((r) => r.gap != null).sort((x, y) => Math.abs(y.gap) - Math.abs(x.gap))[0];
      f.appendChild(gaugeCard(d, table(["country", "year", "measure", { t: "official", r: 1 }, { t: "independent", r: 1 }, { t: "gap", r: 1 }], dr.map((r) => el("tr", {},
        el("td", {}, HZ.NAMES[r.country] || r.country), el("td", {}, String(r.year)), el("td", { class: "small" }, r.measure), el("td", { class: "r num" }, r.official == null ? "–" : fmt(r.official, 2)),
        el("td", { class: "r num" }, r.independent_median == null ? "not entered" : fmt(r.independent_median, 2)), el("td", { class: "r num" }, r.gap == null ? "–" : el("b", {}, signed(r.gap, 2)))))),
        big ? "Largest gap: " + (HZ.NAMES[big.country] || big.country) + " " + big.year + " " + big.measure + ", " + signed(big.gap, 2) + " points" + (Math.abs(big.gap) > 1 ? " (above 1 point: revision risk)." : ".") : "No gap computed yet.", L));
      // (e)
      const e = G.e || {}, er = e.readings || [];
      f.appendChild(gaugeCard(e, el("div", {}, ...er.map((r) => r.error ? el("div", { class: "err" }, r.country + ": " + r.error) : el("div", { style: "margin:10px 0" },
        el("div", { class: "row spread" }, el("b", {}, r.label), r.flag ? el("span", { class: "chip warn" }, "crowded before a catalyst") : el("span", { class: "chip" }, (r.catalysts_30d || []).length ? "no extreme" : "no catalyst within 30 days")),
        el("div", { class: "small" }, "Net " + fmt(r.net, 0) + " contracts = " + fmt(r.net_pct_oi, 1) + "% of open interest · percentile ", el("b", { class: "num" }, fmt(r.percentile, 0))),
        strip({ min: 0, max: 100, ticks: [0, 10, 50, 90, 100], zones: [[0, 10], [90, 100]], marks: [{ v: r.percentile, label: fmt(r.percentile, 0) + "th" }] }),
        (r.catalysts_30d || []).length ? el("div", { class: "tiny" }, "Catalysts: " + r.catalysts_30d.map((x) => x.date + " " + x.title).join("; ")) : null,
        r.meta ? HZ.source(r.meta.source, r.meta.source_url, r.meta.as_of) : null))),
        er.filter((r) => r.flag).length ? "Crowded: " + er.filter((r) => r.flag).map((r) => r.label).join(", ") + "." : er.length ? "No positioning extreme with a catalyst near." : "No readings.", L));
      // (f)
      const ff = G.f || {}, fi = ff.items || [];
      f.appendChild(gaugeCard(ff, el("ul", { style: "padding-left:1rem" }, ...fi.map((it) => el("li", { style: "margin-bottom:10px" },
        el("div", {}, HZ.ctryChip(it.country), " ", el("b", {}, it.threshold), it.near ? el("span", { class: "chip warn", style: "margin-left:4px" }, "near") : null),
        el("div", { class: "small" }, it.distance), el("div", { class: "tiny" }, it.why),
        it.ratings ? el("div", { class: "tiny" }, it.ratings.map((x) => x.agency + " " + x.rating + " " + (x.outlook || "") + " (" + x.date + ")").join(" · ")) : null))),
        fi.filter((x) => x.near).length ? "Near a threshold: " + fi.filter((x) => x.near).map((x) => HZ.NAMES[x.country] + " (" + x.threshold + ")").join(", ") + "." : "No country is one notch from a forced-flow threshold.", L));
      HZ.ctx.add("Ranked shared errors", se.map((it) => it.title + " (" + it.date + ", score " + fmt(it.score, 2) + "): " + it.signals.map((x) => x.signal + (x.hidden_market ? "" : " — " + x.detail)).join("; ")));
      HZ.ctx.add("Gauges", (C.gauges || []).map((g) => "(" + g.id + ") " + g.title + " · badge " + ((g.evidence || {}).badge || "–")));
      return f;
    });
  };
})();
