/* AI brief: the card on Today (three lines), the full brief per region (#brief/<date>), the archive
   (#brief) and the AI judgement card on scenario pages. Facts and judgement are kept visibly apart, and the judgement on a question
   stays hidden until you have made your own call on it. */
(function () {
  "use strict";
  const T = window.TERM;
  const { el, nn, json, getJSON } = T;
  const pctInt = (p) => p == null ? "–" : Math.round(p) + "%";
  const scen = () => json("data/scenarios.json").catch(() => ({ scenarios: [] }));
  const mineOn = (sc, id) => { const s = (sc.scenarios || []).find((x) => x.id === id); return !!(s && s.mine); };
  const CONF = { low: "low confidence", medium: "medium confidence", high: "high confidence" };

  function srcChips(ids, sources) {
    return el("span", { class: "srcs" }, ...(ids || []).map((id) => {
      const s = (sources || {})[id], label = s ? s.label : id;
      const short = label.length > 42 ? label.slice(0, 40) + "…" : label;
      const title = id + (s ? " · " + [s.source, s.date].filter(Boolean).join(" · ") : " · not in the snapshot");
      return s && s.url ? el("a", { class: "src", href: s.url, target: "_blank", rel: "noopener", title }, short)
        : el("span", { class: "src" + (s ? "" : " missing"), title }, short);
    }));
  }

  function banner(b) {
    if (b.verified !== false) return null;
    return el("div", { class: "unverified", role: "alert" },
      el("div", {}, el("b", {}, "Unverified. "), (b.problems || []).length + " check" + ((b.problems || []).length === 1 ? "" : "s") +
        " failed. Shown exactly as the model wrote it; the failing lines are marked ✕."),
      el("details", {}, el("summary", {}, "what failed"), el("ul", { class: "small" }, ...(b.problems || []).map((p) => el("li", {}, p)))));
  }

  function factsBlock(b, limit) {
    const box = el("section", { class: "facts" },
      el("div", { class: "bhead" }, el("h3", {}, "Facts"), el("span", { class: "tiny" }, "what changed since " + (b.snapshot && b.snapshot.prev_date || "the last brief") + " · every line cites the snapshot")));
    if (b.status === "no_ai") { box.append(...nn(el("p", { class: "small muted" }, "No AI brief: " + (b.judgement && b.judgement.why || "not run") + "."))); return box; }
    const facts = b.facts || [];
    if (!facts.length) box.append(...nn(el("p", { class: "small muted" }, b.status === "failed" ? "Extraction failed; see the problems above." : "Nothing changed that the snapshot shows.")));
    const ul = el("ul", { class: "factlist" });
    facts.slice(0, limit || facts.length).forEach((f) => ul.appendChild(el("li", { class: f.ok === false ? "bad-line" : "" },
      f.ok === false ? el("span", { class: "x", title: (f.problems || []).join("; ") }, "✕ ") : null,
      T.ctryChip(f.country === "GLOBAL" ? "GLOBAL" : f.country), " ", f.text, " ", srcChips(f.source_ids, b.sources),
      f.ok === false ? el("div", { class: "tiny" }, (f.problems || []).join("; ")) : null)));
    box.append(...nn(ul));
    if (limit && facts.length > limit) box.append(...nn(el("a", { class: "small", href: "#brief/" + b.date }, (facts.length - limit) + " more →")));
    return box;
  }

  const REGION = { BR: "Brazil", MX: "Mexico", FR: "France", GOLD: "Gold" };
  const KIND = { political: "politics", fiscal: "fiscal", central_bank: "central bank", market: "markets", data: "data" };
  const chipFor = (r) => T.ctryChip(r === "GOLD" ? "GLOBAL" : r);

  function factLi(f, sources, extra) {
    return el("li", { class: f.ok === false ? "bad-line" : "" },
      f.ok === false ? el("span", { class: "x", title: (f.problems || []).join("; ") }, "✕ ") : null,
      extra || null, f.text, " ", srcChips(f.source_ids, sources),
      f.ok === false ? el("div", { class: "tiny" }, (f.problems || []).join("; ")) : null);
  }

  function topBlock(b) {
    const top = (b.top && b.top.length ? b.top : (b.facts || []).slice(0, 3));
    const box = el("section", { class: "facts" },
      el("div", { class: "bhead" }, el("h3", {}, "In three lines"), el("span", { class: "tiny" }, "facts only · every line cites the snapshot")));
    if (b.status === "no_ai") { box.append(...nn(el("p", { class: "small muted" }, "No AI brief: " + (b.judgement && b.judgement.why || "not run") + "."))); return box; }
    if (!top.length) { box.append(...nn(el("p", { class: "small muted" }, b.status === "failed" ? "Extraction failed; see the problems above." : "Nothing changed that the snapshot shows."))); return box; }
    box.append(...nn(el("ul", { class: "factlist" }, ...top.map((f) => factLi(f, b.sources)))));
    return box;
  }

  function regionBlock(r, x, sources) {
    const j = x.judgement || null;
    const facts = el("section", { class: "facts" },
      el("div", { class: "bhead" }, el("h3", {}, "Facts"), el("span", { class: "tiny" }, "since the last brief · validated")));
    const dev = x.developments || [], wk = x.week_change || [], up = x.upcoming || [];
    facts.append(...nn(dev.length ? el("ul", { class: "factlist" }, ...dev.map((f) => factLi(f, sources, el("span", { class: "chip" }, KIND[f.kind] || f.kind)))) :
      el("p", { class: "small muted" }, "No material change."),
      wk.length ? el("div", { class: "small" }, el("b", {}, "Against a week ago")) : null,
      wk.length ? el("ul", { class: "factlist" }, ...wk.map((f) => factLi(f, sources))) : null,
      el("div", { class: "small" }, el("b", {}, "Next 30 days")),
      up.length ? el("ul", { class: "factlist" }, ...up.map((e) => {
        const w = j && (j.watch || []).find((v) => v.event_id === e.event_id);
        return el("li", {}, el("b", { class: "num" }, e.date), " ", e.title, e.importance ? " " : null, e.importance ? T.imp(e.importance) : null,
          w ? el("div", { class: "tiny" }, el("b", {}, "Watch: "), w.what_to_watch) : null);
      })) : el("p", { class: "small muted" }, "No scheduled events.")));
    const judge = el("section", { class: "judge" },
      el("div", { class: "bhead" }, el("h3", {}, "Judgement"), el("span", { class: "tiny" }, "the model's opinion, not fact" + (j && j.date ? " · " + j.date : ""))));
    if (!j || j.ok === false && !j.why_it_matters) judge.append(...nn(el("p", { class: "small muted" }, j && j.problems ? "✕ " + j.problems.join("; ") : "No judgement yet; it runs weekly.")));
    else {
      const list = (title, items, fn) => items && items.length ? [el("div", { class: "small" }, el("b", {}, title)), el("ul", { class: "factors" }, ...items.map(fn))] : [];
      judge.append(...nn(
        ...list("Why it matters", j.why_it_matters, (w) => el("li", {}, el("span", { class: "chip" }, w.for), " ", w.text, " ", srcChips(w.source_ids, sources))),
        ...list("Key risks", j.risks, (w) => el("li", {}, w.text, " ", srcChips(w.source_ids, sources))),
        j.consensus ? el("div", { class: "small" }, el("b", {}, "Consensus: "), j.consensus.view, " ", srcChips(j.consensus.source_ids, sources)) : null,
        j.might_be_wrong ? el("div", { class: "small" }, el("b", {}, "Where it might be wrong: "), j.might_be_wrong) : null,
        j.verified === false ? el("div", { class: "tiny bad-line" }, "✕ " + (j.problems || []).join("; ")) : null));
    }
    return el("section", { class: "region" }, el("div", { class: "sec", style: "margin:14px 0 6px" }, el("h2", { style: "margin:0" }, REGION[r] || r), chipFor(r)), facts, judge);
  }

  function questionView(q, open, sources, compact) {
    const head = el("div", { class: "qhead" }, el("a", { href: "#scenarios/" + q.scenario_id }, q.title || q.question_id),
      open && q.p_yes != null ? el("span", { class: "pbig num" }, pctInt(q.p_yes)) : null,
      open && q.confidence ? el("span", { class: "chip est" }, CONF[q.confidence] || q.confidence) : null);
    if (!open) return el("div", { class: "q hidden-q" }, head, el("div", { class: "tiny" }, "Hidden until you make a call on this question, so it cannot anchor yours. ",
      el("a", { href: "#scenarios/" + q.scenario_id }, "Make a call →")));
    if (q.p_yes == null) return el("div", { class: "q bad-line" }, head, el("div", { class: "tiny" }, "✕ " + (q.problems || []).join("; ")));
    const body = [el("div", { class: "small" }, el("b", {}, "Start: "), q.base_rate_used)];
    if (!compact) {
      body.push(el("ul", { class: "factors" }, ...(q.factors || []).map((f) => el("li", {}, el("span", { class: "eff", title: f.effect }, f.effect === "raises" ? "↑" : "↓"), " ", f.text, " ", srcChips(f.source_ids, sources)))));
      body.push(el("div", { class: "small" }, el("b", {}, "Would change the view: "), q.what_would_change_view));
      body.push(el("div", { class: "small" }, el("b", {}, "Most likely way this is wrong: "), q.most_likely_wrong));
      if (q.branches && q.branches.length) body.push(el("div", { class: "tiny" }, "Branches: " + q.branches.map((b) => b.id + " " + b.p + "%").join(" · ")));
    }
    if (q.ok === false) body.push(el("div", { class: "tiny bad-line" }, "✕ " + (q.problems || []).join("; ")));
    return el("div", { class: "q" + (q.ok === false ? " bad-line" : "") }, head, ...body);
  }

  function judgementBlock(b, sc, compact) {
    const j = b.judgement || {};
    const box = el("section", { class: "judge" },
      el("div", { class: "bhead" }, el("h3", {}, "Judgement"), el("span", { class: "tiny" }, "the model's opinion, not fact" +
        (j.date ? " · " + (j.carried ? "from " + j.date : "today") : "") + (j.why ? " · " + j.why : ""))));
    (b.moved_to_judgement || []).length && box.append(...nn(el("div", { class: "small" }, el("b", {}, "Claims moved here from the facts (no source cited):"),
      el("ul", {}, ...b.moved_to_judgement.map((m) => el("li", {}, m.text))))));
    const qs = j.questions || [];
    if (!qs.length) { box.append(...nn(el("p", { class: "small muted" }, j.ran === false && !j.carried ? "No judgement yet." : "No open questions."))); return box; }
    qs.forEach((q) => box.append(...nn(questionView(q, mineOn(sc, q.scenario_id), b.sources, compact))));
    return box;
  }

  function costLine(b) {
    const c = b.cost || {};
    return el("div", { class: "tiny" }, "AI spend: $" + (c.today_usd || 0).toFixed(3) + " today, $" + (c.month_usd || 0).toFixed(2) + " in " + (c.month || "this month") +
      " of a $" + Number(c.cap_usd || 15).toFixed(2) + " cap" + (c.expected_month_usd != null ? " · expected about $" + Number(c.expected_month_usd).toFixed(2) + " a month" : "") +
      (b.mode === "extraction_only" ? " · extraction only (cap reached)" : ""));
  }

  function howBody() {
    return el("div", { class: "small" },
      el("p", {}, "Each evening a job writes a snapshot: the latest data points, the next 90 days of events, the scenario pages (without your own probabilities), prediction-market odds, CFTC positioning, survey dispersion and 20 to 40 headlines from GDELT and official press pages. Every item has an id."),
      el("p", {}, el("b", {}, "Facts (daily): "), "a cost-efficient Claude model reports, for Brazil, Mexico, France and gold, every material political, fiscal, central-bank and market development since the last brief, what changed against a week ago, and the three facts that matter most, citing ids. The next 30 days of events come straight from the calendar. ",
        el("b", {}, "Judgement (weekly): "), "a stronger Claude model writes, per region, why the developments matter for bonds and the currency (or gold), what to watch at each event, key risks, and the consensus against where it might be wrong; it also gives a probability for each open scenario question in 5% steps, starting from the page's base rate. Within 3 days of an importance-3 catalyst it re-runs for that catalyst's region only. It never sees your calls."),
      el("p", {}, el("b", {}, "Checks: "), "every number must match a snapshot value within rounding and every cited id must exist. Facts without a source move to the judgement side. Anything else that fails is published as written under a red Unverified banner, never quietly corrected."),
      el("p", {}, el("b", {}, "Cost: "), "Batch API (half price) with prompt caching; spend is counted in data/terminal/brief/spend.json with the expected monthly cost, and above the $15 monthly cap only the facts step runs."));
  }

  function briefArticle(b, sc, compact) {
    return el("article", { class: "card brief" + (b.verified === false ? " is-unverified" : "") },
      el("div", { class: "sec", style: "margin:0 0 8px" }, el("h2", { style: "margin:0" }, "AI brief"), el("span", { class: "tiny" }, b.date + " · built " + (b.generated_at || "").slice(11, 16) + " UTC")),
      banner(b), ...(b.report ? [topBlock(b), ...(compact ? [] : Object.keys(REGION).filter((r) => b.report.regions && b.report.regions[r])
        .map((r) => regionBlock(r, b.report.regions[r], b.sources)))] : [factsBlock(b, compact ? 8 : 0)]),
      judgementBlock(b, sc, compact),
      el("div", { class: "row bfoot" }, costLine(b), el("span", { class: "small" }, compact ? el("a", { href: "#brief/" + b.date }, "full brief") : null, compact ? " · " : null, el("a", { href: "#brief" }, "archive →"))),
      T.how("the AI brief", howBody));
  }

  function card() {
    return Promise.all([getJSON("data/brief/latest.json"), scen()]).then(([b, sc]) => briefArticle(b, sc, true))
      .catch(() => el("article", { class: "card brief" }, el("h2", {}, "AI brief"), el("p", { class: "small muted" }, "No brief yet. It is built each evening after the data run.")));
  }

  function pageBrief(arg) {
    const f = el("div"), body = el("div", {}, T.skel("lines"), T.skel("block"));
    f.append(...nn(el("div", { class: "small" }, el("a", { href: "#today" }, "← Today")), el("div", { class: "sec" }, el("h1", {}, arg ? "AI brief " + arg : "AI brief archive")), body));
    if (arg) {
      Promise.all([getJSON("data/brief/briefs/" + arg + ".json"), scen()]).then(([b, sc]) => body.replaceWith(briefArticle(b, sc, false)))
        .catch((e) => body.replaceWith(el("div", { class: "err" }, "No brief for " + arg + " (" + e.message + ").")));
    } else {
      getJSON("data/brief/index.json").then((idx) => {
        const t = el("table", {}, el("thead", {}, el("tr", {}, el("th", {}, "date"), el("th", {}, "checks"), el("th", { class: "r" }, "facts"), el("th", {}, "judgement"))),
          el("tbody", {}, ...idx.map((e) => el("tr", {}, el("td", {}, el("a", { href: "#brief/" + e.date }, e.date)),
            el("td", {}, e.verified === false ? el("span", { class: "chip flag-red" }, "✕ unverified") : e.verified ? el("span", { class: "chip" }, "✓ verified") : el("span", { class: "tiny" }, e.status || "–")),
            el("td", { class: "r num" }, String(e.n_facts)), el("td", {}, e.judgement ? "ran" : e.mode === "extraction_only" ? "skipped (cap)" : "–")))));
        body.replaceWith(el("article", { class: "card" }, el("div", { class: "scroll" }, t), el("p", { class: "tiny" }, "Every brief is kept in data/terminal/brief/briefs/ with the ids it cites.")));
      }).catch((e) => body.replaceWith(el("div", { class: "err" }, "No archive yet (" + e.message + ").")));
    }
    return f;
  }

  function scenarioCard(s, open) {
    const a = s.ai;
    const box = el("article", { class: "card judge-card" },
      el("div", { class: "bhead" }, el("h2", { style: "margin:0" }, "AI judgement"), el("span", { class: "tiny" }, "the model's opinion, not fact · " + a.date + " · ", el("a", { href: a.brief }, "brief"))));
    if (!open) {
      box.append(...nn(el("p", { class: "small" }, "Hidden until you make a call on this question, so it cannot anchor yours. It appears here, and in the AI column above, once your call is recorded.")));
      return box;
    }
    box.append(...nn(
      el("div", { class: "qhead" }, el("span", {}, "P(yes)"), el("span", { class: "pbig num" }, pctInt(100 * a.p_yes)), a.confidence ? el("span", { class: "chip est" }, CONF[a.confidence]) : null,
        a.verified === false ? el("span", { class: "chip flag-red", title: (a.problems || []).join("; ") }, "✕ unverified") : null),
      el("div", { class: "small" }, el("b", {}, "Start: "), a.base_rate_used),
      el("ul", { class: "factors" }, ...(a.factors || []).map((f) => el("li", {}, el("span", { class: "eff" }, f.effect === "raises" ? "↑" : "↓"), " ", f.text, el("span", { class: "tiny" }, " [" + (f.source_ids || []).join(", ") + "]")))),
      el("div", { class: "small" }, el("b", {}, "Would change the view: "), a.what_would_change_view),
      el("div", { class: "small" }, el("b", {}, "Most likely way this is wrong: "), a.most_likely_wrong),
      a.verified === false ? el("div", { class: "tiny bad-line" }, "✕ " + (a.problems || []).join("; ")) : null));
    return box;
  }

  T.brief = { card, scenarioCard };
  T.pageBrief = pageBrief;
})();
