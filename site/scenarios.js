/* Scenarios (list and one page per scenario) and Crowd. Loaded after terminal.js and record.js;
   uses their helpers via window.TERM. Market prices stay hidden until revealed, or until you have
   made a call on that scenario. */
(function () {
  "use strict";
  const T = window.TERM;
  const { el, fmt, signed, meta, badge, getJSON } = T;
  const D = { sc: null, crowd: null, err: null, loading: null };
  const REPO = "https://github.com/EthanC100/forecast-panel/blob/main/";
  const pct = (p, d = 0) => p == null ? "–" : fmt(100 * p, d) + "%";
  const SIDE = { good: ["good", "conf"], bad: ["bad", "flag"], mixed: ["mixed", "est"] };
  const DESCRIPTIVE = { badge: "context", reason: "Base rates and scenario trees are descriptive, not tested signals." };

  function load() {
    if (D.sc || D.err) return Promise.resolve();
    if (!D.loading) D.loading = Promise.all([getJSON("data/scenarios.json"), getJSON("data/crowd.json").catch(() => null)])
      .then(([s, c]) => { D.sc = s; D.crowd = c; })
      .catch((e) => { D.err = String(e); });
    return D.loading;
  }
  // calendar rows link to scenario pages once the data is in
  T.scenarioFor = (eventId) => D.sc && D.sc.scenarios.find((s) => s.event && s.event.id === eventId);
  load().then(() => { if (/^#(calendar|country)/.test(location.hash || "")) T.route(); });

  const shown = (s) => T.isRevealed("sc:" + s.id) || !!s.mine;
  const revealBtn = (s) => el("button", { type: "button", class: "btn small", title: "Hidden so it does not anchor your call; shown automatically once you have made one",
    onclick: () => T.reveal("sc:" + s.id) }, "reveal");
  const unitOf = (m) => m.unit === "%" ? "%" : " bp";
  const moveText = (m) => m.value == null ? "–" : signed(m.value, m.unit === "%" ? 2 : 1) + unitOf(m);

  // ---------------- calculator state (per viewer, in this browser) ----------------
  function calcState(s) {
    const c = s.calculator, key = "terminal.calc." + s.id;
    let saved = null; try { saved = JSON.parse(T.store.get(key, "null")); } catch (e) { saved = null; }
    const st = { good: c.good_level, bad: c.bad_level, custom: false };
    if (saved && saved.good != null && saved.bad != null) Object.assign(st, saved, { custom: saved.good !== c.good_level || saved.bad !== c.bad_level });
    return st;
  }
  function saveCalc(s, st) { T.store.set("terminal.calc." + s.id, JSON.stringify({ good: st.good, bad: st.bad })); }
  const impliedGood = (cur, good, bad) => (good == null || bad == null || good === bad) ? null : (cur - bad) / (good - bad);

  function evaluate(s, st) {
    const c = s.calculator, a = s.asymmetry, R = a.rules;
    const pg = impliedGood(c.current, st.good, st.bad);
    const pgc = pg == null ? null : Math.min(1, Math.max(0, pg));
    const calcYes = pgc == null ? null : (a.yes_is_good ? pgc : 1 - pgc);
    const mkt = s.markets.yes != null ? s.markets.yes : (st.custom ? calcYes : null);
    const src = s.markets.yes != null ? "prediction market (" + s.markets.how + ")" : st.custom ? "your calculator levels" : null;
    const out = { pg, calcYes, mkt, src, checks: [] };
    const mine = s.mine && s.mine.prob;
    if (mine != null && mkt != null) {
      const gap = 100 * (mine - mkt);
      out.checks.push({ k: "gap", ok: Math.abs(gap) >= R.gap_pp, text: "my P(YES) " + pct(mine) + " vs market " + pct(mkt) + ": " + signed(gap, 0) + " points (need ±" + R.gap_pp + ")" });
      const favourGood = (mine > mkt) === a.yes_is_good;
      const target = favourGood ? st.good : st.bad, other = favourGood ? st.bad : st.good;
      const rr = Math.abs(c.current - other) ? Math.abs(target - c.current) / Math.abs(c.current - other) : null;
      out.favour = favourGood ? "good" : "bad"; out.target = target; out.stop = other;
      out.checks.push({ k: "rr", ok: rr != null && rr >= R.reward_risk, text: "reward:risk toward the " + out.favour + " outcome " + (rr == null ? "–" : fmt(rr, 2)) + ":1 (need " + R.reward_risk + ":1)" });
    } else {
      out.checks.push({ k: "gap", ok: false, text: mine == null ? "no call yet: make one to test the gap" : "no market probability: link a market or enter your own levels below" });
      out.checks.push({ k: "rr", ok: false, text: "reward:risk needs the gap first" });
    }
    const d = s.days_to_event;
    out.checks.push({ k: "time", ok: d != null && d >= R.min_days && d <= R.max_days, text: d == null ? "no linked event date" : "event in " + d + " days (window " + R.min_days + "–" + R.max_days + ")" });
    out.flag = out.checks.every((x) => x.ok);
    return out;
  }

  // ---------------- form links ----------------
  function callButton(s) {
    const br = s.base_rate || {};
    return T.formBtn("Make a call", "full-call", {
      title: "[Full call] " + s.title, question: s.question, question_id: s.question_id, resolution_date: s.resolution_date,
      base_rate: [br.reference_class, br.headline || br.reason].filter(Boolean).join(" — ").slice(0, 900),
      scenarios: s.branches.map((b) => b.label + ": ").join("\n") }, "primary");
  }
  function tradeButton(s, side, st) {
    const c = s.calculator, target = side === "good" ? st.good : st.bad, stop = side === "good" ? st.bad : st.good;
    if (target == null) return null;
    const up = target > c.current, fx = c.kind === "fx";
    const dir = (up === fx) ? "long" : "short";
    const lvl = (v) => fmt(v, c.kind === "fx" ? 4 : c.unit === "bp" ? 1 : 2).replace(/,/g, "");
    return T.formBtn("Open trade: " + side + " outcome", "open-trade", {
      title: "[Open trade] " + c.instrument + " " + dir + " (" + s.id + ", " + side + ")", instrument: c.instrument, link: s.question_id,
      horizon: s.resolution_date, target: lvl(target), stop: lvl(stop),
      thesis: "Scenario " + s.title + ": positioned for the " + side + " outcome. Choose direction = " + dir + "." }, "small");
  }

  // ---------------- list ----------------
  function list() {
    const f = el("div");
    f.append(el("div", { class: "sec" }, el("h1", {}, "Scenarios"), el("span", { class: "tiny" }, "updated " + (D.sc.generated_at || "").replace("T", " ").slice(0, 16) + " UTC")));
    f.append(el("p", { class: "small muted" }, "One page per catalyst: a dated question, a base rate from em-macro's history, a branch tree with expected moves, signposts, a market-implied-probability calculator and the asymmetry check."));
    const g = el("div", { class: "grid" });
    D.sc.scenarios.slice().sort((a, b) => (a.event ? a.event.date : "9") < (b.event ? b.event.date : "9") ? -1 : 1).forEach((s) => {
      const st = calcState(s), ev = evaluate(s, st), open = shown(s);
      g.appendChild(el("article", { class: "card sccard" },
        el("div", { class: "lbl" }, el("a", { href: "#scenarios/" + s.id }, el("b", {}, s.title)), T.ctryChip(s.country)),
        el("div", { class: "small", style: "margin:6px 0" }, s.question),
        el("div", { class: "row small" },
          s.event ? el("span", {}, s.event.date + " · " + (s.days_to_event >= 0 ? "in " + s.days_to_event + "d" : "passed")) : el("span", { class: "tiny" }, "no linked event"),
          s.mine ? el("span", { class: "chip conf" }, "my call " + pct(s.mine.prob)) : el("span", { class: "chip est" }, "no call yet"),
          el("span", {}, "market ", open ? el("b", {}, pct(ev.mkt)) : revealBtn(s)),
          open && ev.flag ? el("span", { class: "chip flag" }, "asymmetry") : null),
        el("div", { class: "tiny", style: "margin-top:6px" }, "Base rate: " + ((s.base_rate || {}).headline || (s.base_rate || {}).reason || "–"))));
    });
    f.append(g);
    return f;
  }

  // ---------------- one scenario ----------------
  function baseRateBox(s) {
    const b = s.base_rate || {}, box = el("article", { class: "card" }, el("h2", {}, "Base rate"));
    if (b.reference_class) box.append(el("div", { class: "small" }, el("b", {}, "Reference class: "), b.reference_class));
    if (b.computed) {
      box.append(el("div", { class: "big", style: "margin:8px 0" }, b.headline));
      if (b.p_yes != null || b.p_yes_low != null) box.append(el("div", { class: "small" }, "Base-rate P(YES): ", el("b", {}, b.p_yes_low != null && pct(b.p_yes_low) !== pct(b.p_yes) ? pct(b.p_yes_low) + " to " + pct(b.p_yes) : pct(b.p_yes))));
      if (b.range_note) box.append(el("div", { class: "tiny" }, b.range_note));
      if (b.counts) box.append(el("div", { class: "small" }, Object.entries(b.counts).map(([k, v]) => k + " " + v).join(" · ")));
      if (b.subset) box.append(el("div", { class: "small", style: "margin-top:6px" }, el("b", {}, "Subset " + b.subset.label + ": "),
        b.subset.on_time + " of " + b.subset.n + " on time; special law " + b.subset.special_law + "; Article 49.3 used " + b.subset.art_49_3 + " times"));
      if (b.own) box.append(el("div", { class: "small" }, "This country: " + b.own.n + " elections, final-poll leader won " + b.own.leader_won + ", RMS error " + b.own.rms_error_pp + " pp",
        b.pooled ? "; all 13 countries: " + b.pooled.n + " elections, leader won " + b.pooled.leader_won + ", RMS error " + b.pooled.rms_error_pp + " pp" : ""));
      const rows = b.rows || b.recent;
      if (rows && rows.length) {
        const keys = Object.keys(rows[0]);
        box.append(el("details", {}, el("summary", {}, "rows (" + rows.length + ")"), el("div", { class: "scroll" }, el("table", {},
          el("thead", {}, el("tr", {}, ...keys.map((k) => el("th", {}, k.replace(/_/g, " "))))),
          el("tbody", {}, ...rows.map((r) => el("tr", {}, ...keys.map((k) => el("td", { class: "small" }, r[k] === true ? "yes" : r[k] === false ? "no" : r[k] == null ? "–" : String(r[k]))))))))));
      }
    } else {
      box.append(el("div", { class: "small", style: "margin:8px 0" }, el("b", {}, "Not computed. "), b.reason || ""));
    }
    (b.context || []).forEach((c) => box.append(el("div", { class: "tiny" }, c)));
    if (b.event_study && b.event_study.rows) box.append(el("details", {}, el("summary", {}, b.event_study.label || "event study"),
      el("div", { class: "scroll" }, el("table", {}, el("thead", {}, el("tr", {}, el("th", {}, "event"), el("th", {}, "date"), el("th", { class: "r" }, "USD/local, day 1 (%)"), el("th", { class: "r" }, "10y, day 1 (bp)"))),
        el("tbody", {}, ...b.event_study.rows.map((r) => el("tr", {}, el("td", { class: "small" }, r.event), el("td", {}, r.date), el("td", { class: "r num" }, r.usd_fx_pct == null ? "–" : signed(r.usd_fx_pct, 2)), el("td", { class: "r num" }, r.y10_bp == null ? "–" : signed(r.y10_bp, 1)))))))));
    box.append(meta({ source: "em-macro", source_url: b.source_url, as_of: D.sc.generated_at, evidence: DESCRIPTIVE }, { noId: true }));
    return box;
  }

  function branchCard(s, b, open) {
    const [lab, cls] = SIDE[b.side] || [b.side, "est"];
    return el("article", { class: "card branch " + b.side },
      el("div", { class: "lbl" }, el("b", {}, b.label), el("span", { class: "chip " + cls }, lab + (s.yes_branches.includes(b.id) ? " · YES" : " · NO"))),
      el("div", { class: "probs" },
        el("div", {}, el("div", { class: "k" }, "mine"), el("div", { class: "v num" }, pct(b.p_mine))),
        el("div", { title: "AI probabilities arrive in Phase 4" }, el("div", { class: "k" }, "AI"), el("div", { class: "v num muted" }, "Phase 4")),
        el("div", {}, el("div", { class: "k" }, "market"), el("div", { class: "v num" }, open ? pct(b.p_market) : "hidden"))),
      el("div", { class: "k small", style: "margin-top:8px" }, "Expected move"),
      el("ul", { class: "moves" }, ...b.moves.map((m) => el("li", {},
        el("b", {}, m.instrument + " " + moveText(m)),
        m.lo != null ? el("span", { class: "tiny" }, " [" + signed(m.lo, 1) + ", " + signed(m.hi, 1) + "]" + (m.interval ? " " + m.interval : "")) : null,
        m.assumption ? el("span", { class: "chip est", style: "margin-left:4px", title: "A judgement or a rescaling, not a direct em-macro estimate" }, "assumption") : null,
        m.error ? el("span", { class: "err" }, " " + m.error) : null,
        el("div", { class: "tiny" }, m.basis || "", m.source ? " · " + m.source : "")))),
      el("div", { class: "k small" }, "Signposts"),
      el("ul", { class: "small" }, ...b.signposts.map((x) => el("li", {}, x))));
  }

  function calculatorCard(s) {
    const c = s.calculator, st = calcState(s), box = el("article", { class: "card" });
    if (c.error) { box.append(el("h2", {}, "Market-implied probability"), el("div", { class: "err" }, c.instrument + ": " + c.error)); return box; }
    const out = el("div"), asym = el("div");
    const dec = c.kind === "fx" ? 4 : c.unit === "bp" ? 1 : 2;
    const inp = (v, on) => el("input", { type: "number", step: "any", inputmode: "decimal", value: v == null ? "" : String(+(+v).toFixed(dec + 1)), oninput: (e) => on(parseFloat(e.target.value)) });
    function render() {
      const ev = evaluate(s, st), open = shown(s);
      out.textContent = "";
      const pg = ev.pg;
      out.append(el("div", { class: "hero" },
        el("div", { class: "h" }, el("div", { class: "v num" }, open ? pct(pg == null ? null : Math.min(1, Math.max(0, pg))) : "hidden"), el("div", { class: "k" }, "implied P(good outcome)")),
        el("div", { class: "h" }, el("div", { class: "v num" }, open ? pct(ev.calcYes) : "hidden"), el("div", { class: "k" }, "implied P(YES)"))));
      if (open && pg != null && (pg < 0 || pg > 1)) out.append(el("div", { class: "note err" }, "Today's level is beyond the " + (pg < 0 ? "bad" : "good") + "-outcome level: either the levels are off or the instrument is pricing more than this event."));
      if (!st.custom) out.append(el("div", { class: "tiny" }, "Defaults are " + c.default_basis + " (" + c.good_branch + " " + signed(c.good_move, 1) + ", " + c.bad_branch + " " + signed(c.bad_move, 1) + "). With them the result only restates the move estimates, so it is not used as a market probability until you enter your own levels."));
      asym.textContent = "";
      asym.append(el("h2", {}, "Asymmetry check ", open && ev.flag ? el("span", { class: "chip flag" }, "flag") : null));
      if (!open) asym.append(el("div", { class: "small" }, "Hidden until you reveal the market or make a call. ", revealBtn(s)));
      else {
        asym.append(el("ul", { class: "checks" }, ...ev.checks.map((x) => el("li", { class: x.ok ? "ok" : "no" }, (x.ok ? "✓ " : "✗ ") + x.text))));
        asym.append(el("div", { class: "tiny" }, "Market probability: " + (ev.src || "none") + ". Flag = all three: gap of 15+ points, reward:risk 2:1 or better toward my view, event 2 weeks to 6 months away."));
      }
      asym.append(el("div", { class: "row", style: "margin-top:8px" }, tradeButton(s, "good", st), tradeButton(s, "bad", st)));
    }
    box.append(el("h2", {}, "Market-implied probability"),
      el("div", { class: "small" }, c.name + " now ", el("b", { class: "num" }, fmt(c.current, dec)), " " + (c.unit || ""), c.proxy ? el("span", { class: "chip est", style: "margin-left:4px" }, "proxy") : null),
      el("div", { class: "calc" },
        el("label", {}, "level if good outcome", inp(st.good, (v) => { st.good = v; st.custom = true; saveCalc(s, st); render(); })),
        el("label", {}, "level if bad outcome", inp(st.bad, (v) => { st.bad = v; st.custom = true; saveCalc(s, st); render(); })),
        el("button", { type: "button", class: "btn small", onclick: () => { T.store.set("terminal.calc." + s.id, "null"); T.route(); } }, "reset")),
      el("div", { class: "tiny" }, "P(good) = (now − bad level) / (good level − bad level). Levels are saved in this browser only."),
      out, meta({ source: c.source, source_url: c.source_url, as_of: c.as_of, series: c.series, evidence: DESCRIPTIVE, degraded: c.degraded }, { noId: true }));
    render();
    return [box, el("article", { class: "card" }, asym)];
  }

  function marketsCard(s) {
    const rows = s.markets.rows || [], open = shown(s);
    if (!rows.length) return el("article", { class: "card" }, el("h2", {}, "Prediction markets"), el("div", { class: "small muted" }, "No market lists this question. The calculator is the market read."));
    const t = el("table", {}, el("thead", {}, el("tr", {}, el("th", {}, "market"), el("th", { class: "r" }, "P(yes)"), el("th", {}, "maps to"))));
    t.appendChild(el("tbody", {}, ...rows.map((r) => el("tr", {},
      el("td", {}, r.url ? el("a", { href: r.url, target: "_blank", rel: "noopener" }, r.question || r.id) : (r.question || r.id), el("div", { class: "tiny" }, r.venue + " " + r.id + (r.note ? " · " + r.note : ""))),
      el("td", { class: "r num" }, open ? pct(r.prob, 1) : "hidden"),
      el("td", { class: "small" }, r.related ? el("span", { class: "chip est" }, "related only") : (r.branches || []).join(", "))))));
    return el("article", { class: "card" }, el("h2", {}, "Prediction markets ", open ? null : revealBtn(s)), el("div", { class: "scroll" }, t),
      s.markets.yes != null && open ? el("div", { class: "small" }, "Market P(YES): ", el("b", {}, pct(s.markets.yes, 1)), " (" + s.markets.how + ")") : null,
      meta({ source: "Polymarket / Kalshi snapshots", as_of: (rows.find((r) => r.as_of) || {}).as_of, evidence: { badge: "untested", reason: "Prediction-market prices; their accuracy here is what the Lab and Record pages score." } }, { noId: true }));
  }

  function page(s) {
    const f = el("div"), open = shown(s);
    f.append(el("div", { class: "small" }, el("a", { href: "#scenarios" }, "← all scenarios")));
    f.append(el("div", { class: "sec" }, el("h1", {}, s.title), T.ctryChip(s.country)));
    const ev = s.event;
    f.append(el("article", { class: "card" },
      el("div", { class: "big" }, s.question),
      el("div", { class: "small", style: "margin-top:6px" }, el("b", {}, "Resolves "), s.resolution_date + ". ", s.resolution),
      ev ? el("div", { class: "small", style: "margin-top:6px" }, el("b", {}, "Catalyst: "), el("a", { href: "#calendar" }, ev.title), " · " + ev.date + " (" + ev.status + ") · ",
        el("b", {}, s.days_to_event >= 0 ? "in " + s.days_to_event + " days" : "passed"), ev.source ? [" · ", el("a", { href: ev.source, target: "_blank", rel: "noopener" }, "source")] : null) : null,
      el("div", { class: "row", style: "margin-top:10px" }, callButton(s),
        s.mine ? el("span", { class: "small" }, "My latest: ", el("b", {}, pct(s.mine.prob)), " (" + s.mine.record + ", " + s.mine.submitted_at.slice(0, 10) + ")",
          T.formBtn("Quick update", "quick-update", { target: s.mine.branches_from || s.question_id, title: "[Quick update] " + s.question_id }, "small")) : el("span", { class: "tiny" }, "Question id " + s.question_id + " is pre-filled; branch names are pre-filled in the scenarios box."))));
    f.append(el("div", { class: "sec" }, el("h2", {}, "Scenario tree"), el("span", { class: "tiny" }, "mine = from my latest Full call · AI from Phase 4 · market " + (open ? "shown" : "hidden until revealed"))));
    const g = el("div", { class: "grid" }); s.branches.forEach((b) => g.appendChild(branchCard(s, b, open))); f.append(g);
    f.append(el("div", { class: "sec" }, el("h2", {}, "Market read")));
    const g2 = el("div", { class: "grid wide" }); calculatorCard(s).forEach((x) => g2.appendChild(x)); f.append(g2);
    const g3 = el("div", { class: "grid wide", style: "margin-top:12px" }); g3.append(baseRateBox(s), marketsCard(s)); f.append(g3);
    if (s.indicators && s.indicators.length) {
      f.append(el("div", { class: "sec" }, el("h2", {}, "Live signposts")));
      const g4 = el("div", { class: "grid" });
      s.indicators.forEach((x) => g4.appendChild(el("article", { class: "card" }, el("div", { class: "lbl" }, x.label),
        el("div", { class: "lvl" }, fmt(x.value, 2), x.target != null ? el("span", { class: "tiny" }, " vs target " + fmt(x.target, 2)) : null),
        el("div", { class: "small" }, "3 months ago " + (x.three_months_ago == null ? "–" : fmt(x.three_months_ago, 2))),
        meta({ source: x.source, source_url: x.source_url, as_of: x.as_of, series: x.series, evidence: { badge: "untested", reason: "Shown as a signpost; not tested as a predictor." } }, { noId: true }))));
      f.append(g4);
    }
    return f;
  }

  T.pageScenarios = function (arg) {
    const f = el("div"), body = el("div", { class: "empty" }, "Loading…"); f.appendChild(body);
    load().then(() => {
      if (D.err) { body.replaceWith(el("div", { class: "err" }, "Scenario data not found: " + D.err)); return; }
      const s = arg && D.sc.scenarios.find((x) => x.id === arg);
      body.replaceWith(s ? page(s) : list());
    });
    return f;
  };

  // ---------------- crowd ----------------
  function gaugeCard(g, body) {
    return el("article", { class: "card gauge" }, el("div", { class: "lbl" }, el("b", {}, "(" + g.id + ") " + g.title), badge(g.evidence)),
      g.error ? el("div", { class: "err" }, g.error) : null,
      el("div", { class: "tiny", style: "margin:4px 0 8px" }, g.what || ""), body || null,
      g.evidence && g.evidence.reason ? el("details", {}, el("summary", {}, "evidence"), el("div", { class: "tiny" }, g.evidence.reason,
        g.evidence.report ? [" · ", el("a", { href: REPO + g.evidence.report, target: "_blank", rel: "noopener" }, "lab report")] : null)) : null);
  }
  const tbl = (head, rows) => el("div", { class: "scroll" }, el("table", {}, el("thead", {}, el("tr", {}, ...head.map((h) => el("th", { class: h.r ? "r" : "" }, h.t || h)))), el("tbody", {}, ...rows)));
  const pbar = (p) => p == null ? el("span", { class: "tiny" }, "–") : el("span", { class: "pbar", title: "percentile " + p }, el("span", { class: "track" }, el("i", { style: "width:" + Math.max(2, p) + "%" })), el("b", { class: "num" }, fmt(p, 0)));

  function crowdPage() {
    const C = D.crowd, f = el("div"), G = {};
    (C.gauges || []).forEach((g) => { G[g.id] = g; });
    f.append(el("div", { class: "sec" }, el("h1", {}, "Crowd"), el("span", { class: "tiny" }, "updated " + (C.generated_at || "").replace("T", " ").slice(0, 16) + " UTC")));
    f.append(el("p", { class: "small muted" }, "Where forecasters, pollsters and positioning could be wrong together. Badges come from the lab tests on em-macro's 13-country history: ",
      el("a", { href: REPO + "reports/crowd_lab.md", target: "_blank", rel: "noopener" }, "report"), "."));
    // ranked list
    const scs = {}; (D.sc ? D.sc.scenarios : []).forEach((s) => { scs[s.id] = s; });
    const rl = el("ol", { class: "ranked" });
    (C.shared_errors || []).forEach((it) => {
      const s = scs[it.scenario], open = s ? shown(s) : false;
      rl.appendChild(el("li", { class: "card" },
        el("div", { class: "lbl" }, el("a", { href: "#scenarios/" + it.scenario }, el("b", {}, it.title)), el("span", { class: "num small" }, "score " + fmt(it.score, 2))),
        el("div", { class: "tiny" }, (it.date || "") + " · in " + it.days + " days"),
        it.signals.length ? el("ul", { class: "small" }, ...it.signals.map((x) => el("li", {}, el("b", {}, x.signal + ": "),
          x.hidden_market && !open ? "hidden until revealed on the scenario page" : x.detail, " ", el("span", { class: "tiny" }, "strength " + fmt(x.strength, 2)), " ", badge({ badge: x.badge, reason: "" }))))
          : el("div", { class: "tiny" }, "no signal applies yet")));
    });
    f.append(el("div", { class: "sec" }, el("h2", {}, "Most likely shared errors in the next 6 months")), rl,
      el("div", { class: "tiny" }, C.ranking_method));
    const g = el("div", { class: "grid wide", style: "margin-top:12px" });
    // (a)
    const a = G.a || {}, ar = a.readings || [];
    g.appendChild(gaugeCard(a, el("div", {},
      ar.length ? tbl(["contest", { t: "polls", r: 1 }, { t: "market", r: 1 }, { t: "gap", r: 1 }], ar.map((r) => el("tr", {}, el("td", { class: "small" }, r.label, el("div", { class: "tiny" }, "lead " + signed(r.poll_margin_pp, 1) + " pp, σ " + r.sigma_pp + " pp, " + r.poll_date)),
        el("td", { class: "r num" }, pct(r.p_poll)), el("td", { class: "r num" }, scs[r.scenario] && shown(scs[r.scenario]) ? pct(r.p_market) : "hidden"), el("td", { class: "r num" }, scs[r.scenario] && shown(scs[r.scenario]) && r.gap != null ? signed(100 * r.gap, 0) : "–"))))
        : el("div", { class: "small" }, a.note || "no readings"),
      a.latest_resolved ? el("div", { class: "small", style: "margin-top:8px" }, el("b", {}, "Latest resolved: "), a.latest_resolved.election + " — polls " + pct(a.latest_resolved.p_poll_a) + ", market " + pct(a.latest_resolved.p_market_a) +
        " for candidate A; A " + (a.latest_resolved.a_won ? "won" : "lost") + ".") : null)));
    // (b)
    const b = G.b || {};
    g.appendChild(gaugeCard(b, el("div", {}, tbl(["election", { t: "polls", r: 1 }, { t: "pollsters", r: 1 }, { t: "top share", r: 1 }, { t: "herding", r: 1 }, { t: "miss (pp)", r: 1 }],
      (b.elections || []).slice(0, 8).map((r) => el("tr", {}, el("td", { class: "small" }, r.election), el("td", { class: "r num" }, r.n_polls), el("td", { class: "r num" }, r.n_pollsters),
        el("td", { class: "r num", title: r.top_pollster }, pct(r.top_share)), el("td", { class: "r num", title: "sd of final polls / sd expected from sampling alone" }, r.herding_ratio == null ? "–" : fmt(r.herding_ratio, 2)),
        el("td", { class: "r num" }, r.miss == null ? "–" : signed(r.miss, 1))))),
      (b.elections || [])[0] ? el("details", {}, el("summary", {}, "house effects, " + b.elections[0].election), el("div", { class: "small" },
        Object.entries(b.elections[0].house_effects || {}).map(([k, v]) => k + " " + signed(v, 1)).join(" · "))) : null,
      b.upcoming ? el("div", { class: "tiny" }, b.upcoming) : null)));
    // (c)
    const c = G.c || {};
    g.appendChild(gaugeCard(c, tbl(["survey", { t: "sd", r: 1 }, "percentile", "next decision", "evidence"], (c.readings || []).map((r) => el("tr", {},
      el("td", { class: "small" }, r.label, el("div", { class: "tiny" }, "median " + fmt(r.median, 2) + " · " + r.as_of)), el("td", { class: "r num" }, fmt(r.value, 3)),
      el("td", { title: r.percentile_basis }, pbar(r.percentile), r.extreme ? el("span", { class: "chip flag", style: "margin-left:4px" }, "wide") : null),
      el("td", { class: "small" }, r.event ? r.event.date : "–"), el("td", {}, badge(r.evidence)))))));
    // (d)
    const d = G.d || {};
    g.appendChild(gaugeCard(d, tbl(["country", "year", "measure", { t: "official", r: 1 }, { t: "independent", r: 1 }, { t: "gap", r: 1 }], (d.rows || []).map((r) => el("tr", {},
      el("td", {}, r.country), el("td", {}, r.year), el("td", { class: "small" }, r.measure), el("td", { class: "r num" }, r.official == null ? "–" : fmt(r.official, 2)),
      el("td", { class: "r num" }, r.independent_median == null ? "not entered" : fmt(r.independent_median, 2)), el("td", { class: "r num" }, r.gap == null ? "–" : el("b", {}, signed(r.gap, 2))))))));
    // (e)
    const e = G.e || {};
    g.appendChild(gaugeCard(e, el("div", {}, ...(e.readings || []).map((r) => r.error ? el("div", { class: "err" }, r.country + ": " + r.error) : el("div", { class: "posrow" },
      el("div", { class: "lbl" }, el("b", {}, r.label), r.flag ? el("span", { class: "chip flag" }, "crowded " + r.crowded.split(" ")[1] + " before a catalyst") : el("span", { class: "chip est" }, r.catalysts_30d.length ? "no extreme" : "no catalyst within 30 days")),
      el("div", { class: "small" }, "net " + fmt(r.net, 0) + " contracts = " + fmt(r.net_pct_oi, 1) + "% of open interest · percentile ", pbar(r.percentile)),
      r.catalysts_30d.length ? el("div", { class: "tiny" }, "catalysts: " + r.catalysts_30d.map((x) => x.date + " " + x.title).join("; ")) : null,
      meta(r.meta, { noId: true }))))));
    // (f)
    const ff = G.f || {};
    g.appendChild(gaugeCard(ff, el("ul", { class: "thresholds" }, ...(ff.items || []).map((it) => el("li", {},
      el("div", {}, T.ctryChip(it.country), " ", el("b", {}, it.threshold), it.near ? el("span", { class: "chip flag", style: "margin-left:4px" }, "near") : null),
      el("div", { class: "small" }, it.distance), el("div", { class: "tiny" }, it.why),
      it.ratings ? el("div", { class: "tiny" }, it.ratings.map((x) => x.agency + " " + x.rating + " " + (x.outlook || "") + " (" + x.date + ")").join(" · ")) : null)))));
    f.append(el("div", { class: "sec" }, el("h2", {}, "Gauges")), g);
    return f;
  }

  T.pageCrowd = function () {
    const f = el("div"), body = el("div", { class: "empty" }, "Loading…"); f.appendChild(body);
    load().then(() => {
      if (D.err || !D.crowd) { body.replaceWith(el("div", { class: "err" }, "Crowd data not found" + (D.err ? ": " + D.err : ""))); return; }
      body.replaceWith(crowdPage());
    });
    return f;
  };
})();
