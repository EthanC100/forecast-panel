/* Terminal core: routing, Today, Calendar, country pages and Status. Everything heavier loads on
   demand: charts.js (every chart), teach.js (How-this-works cards, calculators, overview visuals),
   record.js (Record and trade sizing), scenarios.js (Scenarios and Crowd), glossary.js. Data:
   data/summary.json first; calendar, series and teaching data only when a page needs them. */
(function () {
  "use strict";
  const app = document.getElementById("app");
  const S = { summary: null, calendar: null, calP: null, series: {}, calTab: "2w", calCountry: "ALL", calRoutine: true, mods: {}, json: {} };
  const store = {
    get(k, d) { try { const v = localStorage.getItem(k); return v === null ? d : v; } catch (e) { return d; } },
    set(k, v) { try { localStorage.setItem(k, v); } catch (e) { /* private mode */ } },
  };
  const COUNTRY = { FR: "France", BR: "Brazil", MX: "Mexico", US: "United States", GLOBAL: "Global", DE: "Germany" };
  const BADGE = { tested_leads: "Tested-leads", tested_no_lead: "Tested-no-lead", untested: "Untested", context: "Context" };

  // ---------------- helpers ----------------
  const el = (tag, attrs, ...kids) => {
    const n = document.createElement(tag);
    if (attrs) for (const [k, v] of Object.entries(attrs)) {
      if (v == null || v === false) continue;
      if (k === "class") n.className = v; else if (k === "text") n.textContent = v;
      else if (k.startsWith("on")) n.addEventListener(k.slice(2), v); else n.setAttribute(k, v);
    }
    for (const kid of kids.flat()) if (kid != null && kid !== false) n.appendChild(typeof kid === "string" || typeof kid === "number" ? document.createTextNode(String(kid)) : kid);
    return n;
  };
  const nn = (...a) => a.flat().filter((x) => x != null && x !== false);
  const fmt = (v, d = 2) => v == null || Number.isNaN(v) ? "–" : Number(v).toLocaleString("en-US", { minimumFractionDigits: d, maximumFractionDigits: d });
  const signed = (v, d = 1) => v == null ? "–" : (v > 0 ? "+" : v < 0 ? "−" : "") + fmt(Math.abs(v), d);
  const getJSON = (p) => fetch(p, { cache: "no-cache" }).then((r) => { if (!r.ok) throw new Error(p + ": HTTP " + r.status); return r.json(); });
  const todayISO = () => new Date().toISOString().slice(0, 10);
  const daysUntil = (iso) => Math.round((Date.parse(iso + "T12:00:00Z") - Date.parse(todayISO() + "T12:00:00Z")) / 864e5);
  const weekday = (iso) => new Date(iso + "T12:00:00Z").toLocaleDateString("en-GB", { weekday: "short", timeZone: "UTC" });
  const json = (p) => (S.json[p] = S.json[p] || getJSON(p));

  // modules and lazy mounting
  function need(name) {
    if (!S.mods[name]) S.mods[name] = new Promise((res, rej) => {
      const s = el("script", { src: name + ".js" }); s.onload = () => res(TERM); s.onerror = () => rej(new Error(name + ".js failed to load")); document.head.appendChild(s);
    });
    return S.mods[name];
  }
  const io = "IntersectionObserver" in window ? new IntersectionObserver((ents) => ents.forEach((e) => {
    if (e.isIntersecting) { io.unobserve(e.target); const f = e.target._mount; e.target._mount = null; if (f) f(); }
  }), { rootMargin: "300px 0px" }) : null;
  /** A placeholder that builds its content when it scrolls near the viewport. `build` returns a node or a promise of one. */
  function lazy(kind, build) {
    const holder = el("div", { class: "lazy" }, skel(kind));
    holder._mount = () => Promise.resolve().then(build).then((n) => { if (n) { holder.replaceWith(n); if (TERM.glossarize) TERM.glossarize(n.parentNode || n); } else holder.remove(); })
      .catch((err) => holder.replaceWith(el("div", { class: "err" }, String(err.message || err))));
    if (io) io.observe(holder); else setTimeout(holder._mount, 0);
    return holder;
  }
  function skel(kind) {
    if (kind === "lines") return el("div", { "aria-hidden": "true" }, el("div", { class: "skel line" }), el("div", { class: "skel line w60" }), el("div", { class: "skel line w40" }));
    return el("div", { "aria-hidden": "true" }, el("div", { class: "skel line w40" }), el("div", { class: "skel block" }));
  }
  function calendar() { return S.calendar ? Promise.resolve(S.calendar) : (S.calP = S.calP || getJSON("data/calendar.json").then((c) => (S.calendar = c))); }

  // ---------------- freshness + evidence + source meta ----------------
  function ageDays(asOf) {
    if (!asOf) return null;
    const t = /T/.test(asOf) ? Date.parse(asOf) : Date.parse(String(asOf).slice(0, 10) + "T23:59:59Z");
    return Number.isNaN(t) ? null : (Date.now() - t) / 864e5;
  }
  function freshness(asOf) {
    const a = ageDays(asOf);
    if (a == null) return { cls: "none", label: "no date" };
    if (a < 1) return { cls: "fresh", label: "under 1 day old" };
    if (a < 7) return { cls: "aging", label: "under 1 week old" };
    return { cls: "stale", label: "older than 1 week" };
  }
  function badge(ev) {
    const b = (ev && ev.badge) || "untested";
    return el("span", { class: "badge " + b, title: (ev && ev.reason) || "", tabindex: "0" }, BADGE[b] || b);
  }
  function meta(m, opts) {
    m = m || {};
    const f = freshness(m.as_of);
    const asOf = m.as_of ? String(m.as_of).replace("T", " ").replace("Z", " UTC").slice(0, 20) : "no date";
    const srcText = m.source || "source unknown";
    const src = m.source_url ? el("a", { href: m.source_url, target: "_blank", rel: "noopener", title: m.source_id || "" }, srcText)
      : el("span", { title: m.source_id || "" }, srcText);
    return el("div", { class: "meta" },
      el("span", { class: "dot " + f.cls, role: "img", "aria-label": "freshness: " + f.label, title: "Freshness: " + f.label }),
      src, m.source_id && !(opts && opts.noId) ? el("span", { class: "tiny" }, m.source_id.length > 60 ? m.source_id.slice(0, 57) + "…" : m.source_id) : null,
      el("span", {}, "as of " + asOf), m.evidence === null ? null : badge(m.evidence), degradedChip(m.degraded));
  }
  function degradedChip(d) {
    return d ? el("a", { class: "chip deg", href: "#status", title: d.effect + " Fix: " + d.upgrade }, "degraded") : null;
  }
  const hasSeries = (id) => !S.summary || !S.summary.series_index || S.summary.series_index.includes(id);
  function loadSeries(id) {
    if (!hasSeries(id)) return Promise.reject(new Error("series " + id + " is not stored"));
    if (!S.series[id]) S.series[id] = getJSON("data/series/" + id + ".json");
    return S.series[id];
  }
  /** A card whose title is the question the visual answers. */
  function vizCard(question, ...body) { return el("article", { class: "card" }, el("h2", {}, question), ...body); }
  /** An expandable "How this works" card; the body is built the first time it opens. */
  function how(title, build) {
    const d = el("details", { class: "how" }, el("summary", {}, "How this works: " + title));
    const body = el("div", {}, skel("lines")); d.appendChild(body);
    d.addEventListener("toggle", () => {
      if (!d.open || d._built) return; d._built = true;
      Promise.resolve().then(build).then((n) => { body.replaceChildren(...nn(n)); if (TERM.glossarize) TERM.glossarize(d); }).catch((err) => body.replaceChildren(...nn(el("div", { class: "err" }, String(err.message || err)))));
    });
    return d;
  }

  const INSTRUMENTS = { BR: ["USDBRL", "BR10Y", "DI27", "DI29", "DI31"], MX: ["USDMXN", "MX10Y"], FR: ["OATBUND"], GLOBAL: ["US10Y"], US: ["US10Y"] };
  const TERM = window.TERM = { nn, el, fmt, signed, meta, badge, getJSON, json, need, lazy, skel, calendar, loadSeries, hasSeries, vizCard, how, S,
    freshness: (a) => freshness(a), todayISO };
  const formBtn = (...a) => (TERM.formBtn ? TERM.formBtn(...a) : null);
  const blindKey = "terminal.revealed";
  let revealed = {}; try { revealed = JSON.parse(store.get(blindKey, "{}")) || {}; } catch (e) { revealed = {}; }
  Object.assign(TERM, { store, COUNTRY, INSTRUMENTS, daysUntil, weekday, imp: (n) => imp(n), ctryChip: (c) => ctryChip(c), route: () => route(),
    isRevealed: (k) => !!revealed[k], reveal: (k) => { revealed[k] = 1; store.set(blindKey, JSON.stringify(revealed)); route(); } });
  // the issue-form helpers live here so country and calendar pages need no other module
  TERM.issueUrl = function (template, params) {
    const repo = "EthanC100/forecast-panel";
    const q = new URLSearchParams({ template: template + ".yml" });
    for (const [k, v] of Object.entries(params || {})) if (v != null && v !== "") q.set(k, String(v));
    return "https://github.com/" + repo + "/issues/new?" + q.toString();
  };
  TERM.formBtn = function (label, template, params, cls) {
    return el("a", { class: "btn " + (cls || ""), href: TERM.issueUrl(template, params), target: "_blank", rel: "noopener" }, label);
  };
  const tradeLink = (instr, extra, label, cls) => el("a", { class: "btn " + (cls || "small"), href: "#trade/" + instr + (extra ? "?" + new URLSearchParams(extra).toString() : "") }, label || instr);
  TERM.tradeLink = tradeLink;

  // ---------------- shared pieces ----------------
  const ctryChip = (c) => el("span", { class: "chip ctry", title: COUNTRY[c] || c }, c === "GLOBAL" ? "GL" : c);
  const statusChip = (s) => el("span", { class: "chip " + (s === "confirmed" ? "conf" : "est"), title: s === "confirmed" ? "Date published by the institution or fixed in law" : "Date from a rule or past pattern; check it" }, s);
  const imp = (n) => el("span", { class: "imp", title: "importance " + n + " of 3", "aria-label": "importance " + n + " of 3" }, "●".repeat(n), el("i", {}, "●".repeat(3 - n)));
  const unitSuffix = (u) => (u === "pct" ? "%" : " bp");
  function underAttended(e) { return e.importance === 3 && e.attention && e.attention.score < 0.5 && daysUntil(e.date) >= 30; }
  TERM.underAttended = underAttended;
  function countdown(iso) {
    const d = daysUntil(iso);
    if (d <= 0) return { n: d === 0 ? "0" : String(d), u: d === 0 ? "today" : "days ago" };
    if (d === 1) { const h = Math.max(1, Math.round((Date.parse(iso + "T12:00:00Z") - Date.now()) / 36e5)); return { n: String(h), u: "hours" }; }
    return { n: String(d), u: "days" };
  }

  function tile(t) {
    const go = ["FR", "BR", "MX"].includes(t.country) ? "#country/" + t.country : null;
    const head = el("div", { class: "lbl" }, go ? el("a", { href: go }, t.label) : el("span", {}, t.label), ctryChip(t.country));
    if (t.missing) {
      return el("article", { class: "card tile missing" }, head, el("div", { class: "lvl" }, "unavailable"),
        el("div", { class: "note err" }, (t.reason || "").slice(0, 160), " · ", el("a", { href: "#status" }, "details")),
        el("div", { class: "meta" }, el("span", { class: "dot stale", title: "Source failing" }), el("a", { href: "#status" }, (t.meta && t.meta.source) || "see status"), badge(t.meta && t.meta.evidence)));
    }
    const u = unitSuffix(t.unit_change), d = t.unit_change === "pct" ? 2 : 0;
    const dir = (v) => v == null || v === 0 ? "" : v > 0 ? "▲ " : "▼ ";
    return el("article", { class: "card tile" }, head,
      el("div", { class: "lvl" }, fmt(t.level, t.decimals), el("span", { class: "tiny" }, " " + (t.unit || ""))),
      el("div", { class: "chg" },
        el("span", { title: t.chg_1w_from ? "vs " + t.chg_1w_from : "no observation a week earlier" }, "1w ", el("b", {}, t.chg_1w == null ? "–" : dir(t.chg_1w) + signed(t.chg_1w, d) + u)),
        el("span", { title: t.chg_1m_from ? "vs " + t.chg_1m_from : "no observation a month earlier" }, "1m ", el("b", {}, t.chg_1m == null ? "–" : dir(t.chg_1m) + signed(t.chg_1m, d) + u)),
        el("span", { title: "level vs the past year: (level − mean) / sd over " + t.n_1y + " observations" }, "z-score 1y ", el("b", {}, t.z_1y == null ? "–" : signed(t.z_1y, 2)))),
      t.meta.note ? el("div", { class: "note" }, t.meta.note) : null, meta(t.meta));
  }

  function eventRow(e, calGenerated) {
    const d = daysUntil(e.date), ua = underAttended(e);
    const att = e.attention;
    const attCell = el("div", { class: "att" },
      att ? el("div", { class: "v", title: "GDELT coverage of this event's keywords: last 30 days vs the past 12 months (1.0 = normal)" }, "×" + fmt(att.score, 2)) : el("div", { class: "tiny" }, "no attention data"),
      ua ? el("span", { class: "chip warn", title: "Importance 3, attention under half the country's normal, 30+ days away" }, "⚠ under-attended") : null,
      att ? meta({ source: "GDELT", source_url: "https://api.gdeltproject.org/api/v2/doc/doc?query=" + encodeURIComponent(att.query) + "&mode=timelinevolraw&timespan=12m",
        source_id: att.query, as_of: att.as_of, evidence: (S.summary && S.summary.evidence_defaults.attention) }, { noId: true }) : null);
    const sc = TERM.scenarioFor && TERM.scenarioFor(e.id);
    return el("div", { class: "ev" + (ua ? " under" : ""), id: "ev-" + e.id },
      el("div", { class: "date" }, e.date.slice(5), el("small", {}, weekday(e.date) + " · " + (d === 0 ? "today" : d > 0 ? "in " + d + "d" : -d + "d ago"))),
      el("div", {},
        el("div", { class: "title" }, e.title),
        el("div", { class: "row2" }, ctryChip(e.country), el("span", {}, e.type), imp(e.importance), statusChip(e.status),
          e.source ? el("a", { href: e.source, target: "_blank", rel: "noopener" }, "source") : null),
        e.note ? el("details", {}, el("summary", {}, "note"), el("div", { class: "small muted" }, e.note)) : null,
        sc ? el("div", { class: "small" }, el("a", { href: "#scenarios/" + sc.id }, "Scenario page: " + sc.title + " →")) : null,
        meta({ source: "calendar", as_of: calGenerated, evidence: S.summary && S.summary.evidence_defaults.countdown, source_url: e.source }, { noId: true }),
        e.importance >= 2 && d >= 0 ? el("div", { class: "row", style: "margin-top:6px" },
          tradeLink((INSTRUMENTS[e.country] || ["US10Y"])[0], { link: e.id, horizon: e.date }, "Size and open a trade"),
          formBtn("Make a call", "full-call", { question: e.title + ": ", question_id: e.id, resolution_date: e.date, base_rate: e.base_rate ? e.base_rate.text : "", title: "[Full call] " + e.title }, "small")) : null),
      attCell);
  }
  TERM.eventRow = eventRow;

  // ---------------- pages ----------------
  function pageToday() {
    const s = S.summary, f = el("div");
    f.append(...nn(el("div", { class: "sec" }, el("h1", {}, "Today"), el("span", { class: "tiny" }, "summary built " + s.generated_at.replace("T", " ").replace("Z", " UTC")))));
    const cats = el("div", { class: "grid" });
    (s.next_catalysts || []).forEach((e) => {
      const c = countdown(e.date);
      cats.appendChild(el("article", { class: "card cat" },
        el("div", { class: "cd", title: "countdown to " + e.date }, el("div", { class: "n" }, c.n), el("div", { class: "u" }, c.u)),
        el("div", { style: "min-width:0" }, el("div", { class: "t" }, e.title),
          el("div", { class: "d" }, ctryChip(e.country), " ", e.date + " (" + weekday(e.date) + ") ", imp(e.importance), " ", statusChip(e.status)),
          meta({ source: "source", source_url: e.source, as_of: s.generated_at, evidence: s.evidence_defaults.countdown }))));
    });
    f.append(...nn(el("div", { class: "sec" }, el("h2", {}, "Next catalysts"), el("a", { href: "#calendar", class: "small" }, "full calendar →")), cats));
    const g = el("div", { class: "grid" }); s.tiles.forEach((t) => g.appendChild(tile(t)));
    f.append(...nn(el("div", { class: "sec" }, el("h2", {}, "Instruments"), el("span", { class: "tiny" }, "1w / 1m change; z-score = level vs the past year")), g));
    const ov = el("div", { class: "grid wide" });
    ov.append(...nn(lazy("block", () => need("teach").then(() => TERM.teach.mapCard())), lazy("block", () => need("teach").then(() => TERM.teach.heatmapCard()))));
    f.append(...nn(el("div", { class: "sec" }, el("h2", {}, "Overview")), ov));
    const st = Object.values(s.status.sources || {}), bad = st.filter((x) => ["error", "missing_secret"].includes(x.state));
    f.append(...nn(el("p", { class: "small muted", style: "margin-top:14px" }, st.length + " sources tracked, ", el("b", {}, String(bad.length)), " failing or missing a secret. ", el("a", { href: "#status" }, "Status page →"))));
    return f;
  }

  function pageCalendar() {
    const f = el("div"), body = el("div", {}, skel("lines"), skel("lines"));
    const tabs = el("div", { class: "tabs", role: "tablist" });
    [["2w", "Next 2 weeks"], ["3m", "3 months"], ["12m", "12 months"]].forEach(([k, l]) => tabs.appendChild(el("button", { class: S.calTab === k ? "on" : "", role: "tab", "aria-selected": String(S.calTab === k), type: "button", onclick: () => { S.calTab = k; location.hash = "#calendar/" + k; } }, l)));
    f.append(...nn(el("div", { class: "sec" }, el("h1", {}, "Calendar"), tabs), body));
    Promise.all([calendar(), need("scenarios").catch(() => null)]).then(([cal]) => {
      const lim = { "2w": 14, "3m": 92, "12m": 366 }[S.calTab];
      let evs = cal.events.filter((e) => { const d = daysUntil(e.date); return d >= 0 && d <= lim; });
      if (S.calCountry !== "ALL") evs = evs.filter((e) => e.country === S.calCountry);
      if (!S.calRoutine) evs = evs.filter((e) => e.importance > 1);
      const ua = evs.filter(underAttended).length;
      const fl = el("div", { class: "filters" });
      ["ALL", "FR", "BR", "MX", "GLOBAL"].forEach((c) => fl.appendChild(el("button", { type: "button", class: S.calCountry === c ? "on" : "", onclick: () => { S.calCountry = c; route(); } }, c === "ALL" ? "All" : c === "GLOBAL" ? "Global" : COUNTRY[c])));
      fl.appendChild(el("button", { type: "button", class: S.calRoutine ? "on" : "", onclick: () => { S.calRoutine = !S.calRoutine; route(); }, title: "Weekly/monthly surveys (importance 1)" }, S.calRoutine ? "Routine shown" : "Routine hidden"));
      const out = el("div", {}, fl,
        lazy("block", () => need("teach").then(() => TERM.teach.timelineCard(cal))),
        el("p", { class: "small muted" }, evs.length + " events in this window · " + ua + " under-attended. Attention = news coverage of the event's keywords over the last 30 days relative to their normal level over the past year (GDELT); ×1.0 is normal."));
      const list = el("div", { class: "evlist" });
      evs.forEach((e) => list.appendChild(eventRow(e, cal.generated_at)));
      if (!evs.length) list.appendChild(el("div", { class: "empty" }, "No events in this window."));
      out.appendChild(list);
      if (cal.notes && cal.notes.length) out.appendChild(el("div", { class: "card", style: "margin-top:14px" }, el("h3", { style: "margin-top:0" }, "Notes"), el("ul", { class: "small muted" }, ...cal.notes.map((n) => el("li", {}, n)))));
      out.appendChild(el("p", { class: "tiny" }, "Definition: " + (cal.attention_definition || "") + ". Sources: events.yaml (hand-sourced), Federal Reserve and ECB calendars (scraped daily), recurring releases by rule, em-macro for " + cal.past_events.length + " past events."));
      body.replaceWith(out);
      if (TERM.glossarize) TERM.glossarize(out);
      const want = (location.hash.split("?")[1] || "").match(/ev=([^&]+)/);
      if (want) { const n = document.getElementById("ev-" + decodeURIComponent(want[1])); if (n) { n.classList.add("hl"); n.scrollIntoView({ block: "center" }); } }
    }).catch((err) => body.replaceWith(el("div", { class: "err" }, String(err))));
    return f;
  }

  const CHART_INSTRUMENT = { "br.usdbrl.ptax": "USDBRL", "mx.usdmxn.fix": "USDMXN", "fr.spread.oat_bund": "OATBUND", "fr.spread.oat_bund.ecb_m": "OATBUND",
    "br.di.f27": "DI27", "br.di.f27.proxy": "DI27", "br.di.f29": "DI29", "br.di.f29.proxy": "DI29", "br.di.f31": "DI31", "br.di.f31.proxy": "DI31",
    "br.td.pre_longest": "BR10Y", "mx.mbono10y.auction": "MX10Y", "mx.10y.oecd_m": "MX10Y" };
  function chartCard(item, code, all) {
    if (item.missing) {
      return el("article", { class: "card" }, el("h2", {}, item.name), el("div", { class: "empty" }, "Not available yet — see the status page."), el("div", { class: "meta" }, el("span", { class: "dot stale" }), el("a", { href: "#status" }, "status"), badge(item.meta && item.meta.evidence)));
    }
    const instr = CHART_INSTRUMENT[item.series];
    const card = el("article", { class: "card" });
    card.append(...nn(lazy("block", () => need("charts").then(() => TERM.charts.seriesCard(item, { country: code, compareWith: all.filter((x) => !x.missing && x.series !== item.series) })))));
    if (item.series === "br.usdbrl.ptax" || item.series === "mx.usdmxn.fix") card.append(...nn(how("how a currency trade makes money", () => need("teach").then(() => TERM.teach.fxTrade(instr)))));
    if (item.series.startsWith("fr.spread.oat_bund")) card.append(...nn(how("how a spread trade makes money", () => need("teach").then(() => TERM.teach.spreadTrade()))));
    if (instr) card.append(...nn(el("div", { class: "row", style: "margin-top:8px" }, tradeLink(instr, null, "Size a " + instr + " trade"))));
    return card;
  }

  function cellVal(v, d) { return v == null ? el("span", { class: "tiny" }, "not entered") : el("b", { class: "num" }, fmt(v, d)); }

  function fiscalTable(rows, ev) {
    if (!rows.length) return el("div", { class: "empty" }, "No rows. Add them in data/terminal/inputs/fiscal_gap.yaml.");
    const wrap = el("div");
    rows.forEach((r) => {
      const t = el("table", {}, el("thead", {}, el("tr", {}, el("th", {}, "estimate"), el("th", { class: "r" }, "% of GDP"), el("th", {}, "source"))));
      const tb = el("tbody");
      const o = r.official || {};
      tb.appendChild(el("tr", {}, el("td", {}, el("b", {}, "Official: "), o.label || "", o.check ? el("details", {}, el("summary", {}, o.verified ? "how it was checked" : "why it is not confirmed"), el("div", { class: "small muted" }, o.check)) : null),
        el("td", { class: "r" }, cellVal(o.value, 2)),
        el("td", {}, o.source ? el("a", { href: o.source, target: "_blank", rel: "noopener" }, "source") : "–", " ", o.verified ? el("span", { class: "chip conf" }, "verified") : el("span", { class: "chip est" }, "to verify"))));
      (r.independent || []).forEach((i) => tb.appendChild(el("tr", {}, el("td", {}, i.name, i.note ? el("div", { class: "tiny" }, i.note) : null),
        el("td", { class: "r" }, cellVal(i.value, 2), i.as_of ? el("div", { class: "tiny" }, el("span", { class: "dot " + freshness(i.as_of).cls }), " " + i.as_of) : null),
        el("td", {}, i.source ? el("a", { href: i.source, target: "_blank", rel: "noopener" }, i.source_label || "source") : "–", " ", i.value == null ? null : i.verified ? (i.auto ? null : el("span", { class: "chip conf" }, "verified")) : el("span", { class: "chip est" }, "to verify")))));
      t.appendChild(tb);
      wrap.append(...nn(el("h3", {}, r.metric + ", " + r.year),
        el("div", { class: "small" }, "Optimism gap (official − median independent): ", el("b", { class: "num" }, r.gap == null ? "–" : signed(r.gap, 2) + " pp"), " ", badge(ev)),
        el("div", { class: "scroll" }, t)));
    });
    wrap.appendChild(el("p", { class: "tiny" }, "Balances in % of GDP (deficit negative). A positive gap means the official number is more optimistic. Edit data/terminal/inputs/fiscal_gap.yaml."));
    return wrap;
  }

  function surveyCard(b) {
    const t = el("table", {}, el("thead", {}, el("tr", {}, el("th", {}, "year"), el("th", { class: "r" }, "median"), el("th", { class: "r" }, "sd"), el("th", { class: "r", title: "percentile of the current standard deviation among readings at the same horizon over 10 years" }, "dispersion pct (10y)"), el("th", { class: "r" }, "resp."))));
    const tb = el("tbody");
    b.rows.forEach((r) => tb.appendChild(el("tr", {}, el("td", {}, r.ref), el("td", { class: "r num" }, fmt(r.median, 2)), el("td", { class: "r num" }, fmt(r.sd, 2)), el("td", { class: "r num" }, r.sd_pct_10y == null ? "–" : fmt(r.sd_pct_10y, 0) + "th"), el("td", { class: "r num" }, r.respondents == null ? "–" : fmt(r.respondents, 0)))));
    t.appendChild(tb);
    return el("article", { class: "card" }, el("h2", {}, b.label, el("span", { class: "tiny" }, " " + (b.unit || ""))), el("div", { class: "scroll" }, t), meta(b.meta));
  }

  function cotCard(c, country) {
    const t = el("table", {}, el("thead", {}, el("tr", {}, el("th", {}, "group"), el("th", { class: "r" }, "net contracts"), el("th", { class: "r" }, "3y percentile"))));
    const tb = el("tbody");
    c.rows.forEach((r) => tb.appendChild(el("tr", {}, el("td", {}, r.label), el("td", { class: "r num" }, r.value == null ? "–" : signed(r.value, 0)), el("td", { class: "r num" }, r.pct_3y == null ? "–" : fmt(r.pct_3y, 0) + "th"))));
    t.appendChild(tb);
    return el("article", { class: "card" }, el("h2", {}, "CFTC positioning: " + (country === "BR" ? "BRL" : "MXN") + " futures"),
      el("div", { class: "scroll" }, t),
      el("div", { class: "tiny" }, "CME contracts are priced in USD per " + (country === "BR" ? "BRL" : "MXN") + ", so net long = long the " + (country === "BR" ? "real" : "peso") + ". Open interest " + fmt(c.open_interest, 0) + "."),
      meta(c.meta));
  }

  function pageCountry(code) {
    const c = S.summary.countries[code]; if (!c) return el("div", { class: "empty" }, "Unknown country.");
    const f = el("div");
    const sub = el("div", { class: "filters" });
    ["FR", "BR", "MX"].forEach((k) => sub.appendChild(el("button", { type: "button", class: k === code ? "on" : "", onclick: () => { location.hash = "#country/" + k; } }, COUNTRY[k])));
    f.append(...nn(sub, el("div", { class: "sec" }, el("h1", {}, c.name))));
    if (c.events && c.events.length) {
      const l = el("div", { class: "evlist" }); c.events.filter((e) => e.importance >= 2).slice(0, 4).forEach((e) => l.appendChild(eventRow(e, S.summary.generated_at)));
      f.append(...nn(el("div", { class: "sec" }, el("h2", {}, "Next catalysts"), el("a", { class: "small", href: "#calendar" }, "calendar →")), l));
    }
    const g = el("div", { class: "grid wide" }); c.charts.forEach((it) => g.appendChild(chartCard(it, code, c.charts)));
    f.append(...nn(el("div", { class: "sec" }, el("h2", {}, "Markets"), el("span", { class: "tiny" }, "tap or drag a chart for values; numbered markers explain the largest moves")), g));
    const mdl = el("div", { class: "grid wide" });
    mdl.append(...nn(lazy("block", () => need("teach").then(() => TERM.teach.driversCard(code))),
      lazy("block", () => need("teach").then(() => TERM.teach.waterfallCard(code))),
      lazy("block", () => need("teach").then(() => TERM.teach.whatIfCard(code)))));
    if (code !== "FR") mdl.append(...nn(lazy("block", () => need("teach").then(() => TERM.teach.eventStudyCard(code)))));
    f.append(...nn(el("div", { class: "sec" }, el("h2", {}, "What drives it (em-macro risk model)")), mdl));
    f.append(...nn(el("div", { class: "sec" }, el("h2", {}, "Fiscal optimism gap")), el("article", { class: "card" }, fiscalTable(c.fiscal_gap || [], S.summary.evidence_defaults.fiscal_gap))));
    const ex = el("div", { class: "grid wide" });
    (c.surveys || []).forEach((b) => ex.appendChild(surveyCard(b)));
    if (c.cot) ex.appendChild(cotCard(c.cot, code));
    if (!c.surveys.length && !c.cot) ex.appendChild(el("article", { class: "card" }, el("div", { class: "empty" }, "No survey or futures-positioning source for " + c.name + " (no Focus- or Banxico-style survey with a public API; no CFTC-listed euro sovereign contract).")));
    f.append(...nn(el("div", { class: "sec" }, el("h2", {}, "Expectations and positioning")), ex));
    if (c.ratings) {
      const r = c.ratings, t = el("table", {}, el("thead", {}, el("tr", {}, el("th", {}, "agency"), el("th", {}, "rating"), el("th", {}, "outlook"), el("th", {}, "last action"), el("th", {}, "next review"))));
      const tb = el("tbody");
      r.rows.forEach((x) => tb.appendChild(r.origin === "aft" ? el("tr", {}, el("td", {}, x.agency), el("td", {}, el("b", {}, (x.cells || [])[0] || "–")), el("td", {}, (x.cells || [])[1] || "–"), el("td", { class: "small" }, (x.cells || [])[2] || "–"), el("td", {}, (x.cells || [])[3] || "–"))
        : el("tr", {}, el("td", {}, x.agency), el("td", {}, el("b", {}, x.rating)), el("td", {}, x.outlook || "–"), el("td", { class: "small" }, x.last_action || "–"), el("td", {}, x.next_review || "–", x.verified ? null : el("span", { class: "chip est", style: "margin-left:4px" }, "to verify")))));
      t.appendChild(tb);
      f.append(...nn(el("div", { class: "sec" }, el("h2", {}, "Credit ratings")), el("article", { class: "card" }, el("div", { class: "scroll" }, t), meta(r.meta))));
    }
    if (c.markets && c.markets.length) {
      const t = el("table", {}, el("thead", {}, el("tr", {}, el("th", {}, "market"), el("th", { class: "r" }, "P(yes)"), el("th", { class: "r" }, "volume"), el("th", {}, ""))));
      const tb = el("tbody");
      c.markets.forEach((m) => {
        const key = m.meta.source_id, qid = m.venue === "Polymarket" ? "pm:" + String(key).replace("market ", "") : "ks:" + key;
        const show = !!revealed[qid];
        const cell = el("td", { class: "r num" }, show ? fmt(100 * m.prob, 0) + "%" : el("button", { type: "button", class: "btn small", title: "Hidden so it does not anchor a call; recorded with any call you submit",
          onclick: () => { revealed[qid] = 1; store.set(blindKey, JSON.stringify(revealed)); route(); } }, "reveal"));
        tb.appendChild(el("tr", {}, el("td", {}, el("a", { href: m.url, target: "_blank", rel: "noopener" }, m.question), el("div", { class: "tiny" }, m.venue + (m.end_date ? " · ends " + m.end_date : ""))), cell,
          el("td", { class: "r num" }, m.volume == null ? "–" : "$" + fmt(m.volume / 1000, 0) + "k"),
          el("td", {}, formBtn("Make a call", "full-call", { question: m.question, question_id: qid, resolution_date: m.end_date || "", title: "[Full call] " + m.question }, "small"))));
      });
      t.appendChild(tb);
      f.append(...nn(el("div", { class: "sec" }, el("h2", {}, "Prediction markets"), el("span", { class: "tiny" }, "Prices hidden until you reveal them; a call records the price at submission.")),
        el("article", { class: "card" }, el("div", { class: "scroll" }, t), meta(c.markets[0].meta, { noId: true }))));
    }
    return f;
  }

  function pageStatus() {
    const st = S.summary.status.sources || {}, f = el("div");
    f.append(...nn(el("div", { class: "sec" }, el("h1", {}, "Source status"), el("span", { class: "tiny" }, "updated " + (S.summary.status.updated_at || "")))));
    const deg = S.summary.degraded || [];
    f.append(...nn(el("article", { class: "card" }, el("h2", {}, "Running on substitute data (" + deg.length + ")"),
      deg.length ? el("div", {}, ...deg.map((d) => el("div", { class: "degrow" },
        el("div", {}, el("span", { class: "chip deg" }, "degraded"), " ", el("b", {}, d.features)),
        el("div", { class: "small" }, "Using " + (d.fallback_name || "a fallback") + " because " + d.primary + " is " + String(d.primary_state).replace("_", " ") + ". " + d.effect),
        el("div", { class: "small" }, el("b", {}, "To upgrade: "), d.upgrade + "."))))
        : el("p", { class: "small" }, "Every feature is on its preferred source."),
      el("p", { class: "tiny" }, "Features list their sources best-first, so they switch to the better data on the first run after it appears; nothing needs editing."))));
    const rows = Object.entries(st).sort((a, b) => (a[1].country || "").localeCompare(b[1].country || "") || a[0].localeCompare(b[0]));
    const t = el("table", {}, el("thead", {}, el("tr", {}, el("th", {}, "source"), el("th", {}, "state"), el("th", {}, "last success"), el("th", {}, "last attempt"), el("th", {}, "detail"))));
    const tb = el("tbody");
    const cls = { ok: "fresh", standby: "none", partial: "aging", error: "stale", missing_secret: "stale" };
    const lbl = { ok: "OK", standby: "standby (fallback not needed)", partial: "partial", error: "error", missing_secret: "missing secret" };
    rows.forEach(([k, s]) => tb.appendChild(el("tr", {},
      el("td", {}, el("b", {}, s.name || k), el("div", { class: "tiny" }, k + " · " + (s.country || "") + (s.release ? " · releases: " + s.release : ""))),
      el("td", {}, el("span", { class: "state" }, el("span", { class: "dot " + (cls[s.state] || "none") }), lbl[s.state] || s.state || "never run")),
      el("td", { class: "small" }, (s.last_success || "never").replace("T", " ").replace("Z", "")),
      el("td", { class: "small" }, (s.last_attempt || "–").replace("T", " ").replace("Z", "")),
      el("td", {}, s.secret ? el("div", { class: "tiny" }, "needs " + s.secret + (s.secret_present ? " (set)" : " (not set)")) : null,
        s.fallback_for ? el("div", { class: "tiny" }, "fallback for " + s.fallback_for) : null,
        s.error ? el("div", { class: "err" }, s.error) : null, s.note ? el("div", { class: "tiny" }, s.note) : null,
        s.n_series ? el("div", { class: "tiny" }, s.n_series + " series written") : null))));
    t.appendChild(tb);
    f.append(...nn(el("article", { class: "card" }, el("div", { class: "scroll" }, t)),
      el("p", { class: "small muted" }, "Green: succeeded on the last run. Red: failed or a secret is missing; it is skipped and everything else keeps working. Grey: a fallback that was not needed. Amber: partial.")));
    return f;
  }

  // module pages: a skeleton until the module arrives
  function modPage(mod, fn, ...args) {
    const holder = el("div", {}, skel("lines"), skel("block"));
    need(mod).then(() => holder.replaceWith(TERM[fn](...args))).catch((err) => holder.replaceWith(el("div", { class: "err" }, String(err.message || err))));
    return holder;
  }

  // ---------------- routing ----------------
  function route() {
    const full = (location.hash || "#today").slice(1), h = full.split("?")[0], [page, arg] = h.split("/");
    if (page === "calendar" && ["2w", "3m", "12m"].includes(arg)) S.calTab = arg;
    document.querySelectorAll("[data-r]").forEach((a) => a.classList.toggle("on", a.dataset.r === page || a.dataset.r === h));
    app.textContent = "";
    if (!S.summary) { app.appendChild(el("div", {}, skel("lines"), el("div", { class: "grid" }, skel("block"), skel("block"), skel("block")))); return; }
    let node;
    if (page === "calendar") node = pageCalendar();
    else if (page === "country") node = pageCountry((arg || "BR").toUpperCase());
    else if (page === "status") node = pageStatus();
    else if (page === "scenarios") node = modPage("scenarios", "pageScenarios", arg);
    else if (page === "crowd") node = modPage("scenarios", "pageCrowd");
    else if (page === "record") node = modPage("record", "pageRecord", arg);
    else if (page === "trade") node = modPage("record", "pageTrade", arg, new URLSearchParams(full.split("?")[1] || ""));
    else if (page === "glossary") node = modPage("glossary", "pageGlossary");
    else node = pageToday();
    app.appendChild(node);
    if (TERM.glossarize) requestAnimationFrame(() => TERM.glossarize(app));
  }

  // theme
  const btn = document.getElementById("theme");
  const apply = (t) => { if (t) document.documentElement.setAttribute("data-theme", t); else document.documentElement.removeAttribute("data-theme"); btn.textContent = t === "dark" ? "☾" : t === "light" ? "☀" : "◐"; btn.title = "Theme: " + (t || "auto"); };
  let theme = store.get("terminal.theme", ""); apply(theme);
  btn.addEventListener("click", () => { theme = theme === "" ? "light" : theme === "light" ? "dark" : ""; store.set("terminal.theme", theme); apply(theme); });

  // offline: the service worker serves the last data it saw
  const off = document.getElementById("offline");
  const net = () => off && off.classList.toggle("on", navigator.onLine === false);
  window.addEventListener("online", net); window.addEventListener("offline", net); net();
  if ("serviceWorker" in navigator && location.protocol !== "file:") navigator.serviceWorker.register("sw.js").catch(() => { /* not fatal */ });

  window.addEventListener("hashchange", () => { route(); window.scrollTo(0, 0); });
  route();
  getJSON("data/summary.json").then((s) => { S.summary = s; route(); })
    .then(() => (window.requestIdleCallback || setTimeout)(() => need("glossary").then(() => TERM.glossarize(app)).catch(() => null)))
    .catch((err) => { app.textContent = ""; app.appendChild(el("div", { class: "ph" }, el("h1", {}, "Data not found"), el("p", {}, String(err)), el("p", { class: "small" }, "Locally: run `python -m terminal.run site` and serve the site folder with `python -m http.server`."))); });
})();
