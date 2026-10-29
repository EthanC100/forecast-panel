/* Macro Terminal (Phase 1). Static: reads data/summary.json, data/calendar.json and data/series/<id>.json. */
(function () {
  "use strict";
  const app = document.getElementById("app");
  const S = { summary: null, calendar: null, series: {}, range: "1y", calTab: "2w", calCountry: "ALL", calRoutine: true };
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
  const fmt = (v, d = 2) => v == null || Number.isNaN(v) ? "–" : Number(v).toLocaleString("en-US", { minimumFractionDigits: d, maximumFractionDigits: d });
  const signed = (v, d = 1) => v == null ? "–" : (v > 0 ? "+" : v < 0 ? "−" : "") + fmt(Math.abs(v), d);
  const getJSON = (p) => fetch(p, { cache: "no-cache" }).then((r) => { if (!r.ok) throw new Error(p + ": HTTP " + r.status); return r.json(); });
  const todayISO = () => new Date().toISOString().slice(0, 10);
  const daysUntil = (iso) => Math.round((Date.parse(iso + "T12:00:00Z") - Date.parse(todayISO() + "T12:00:00Z")) / 864e5);
  const weekday = (iso) => new Date(iso + "T12:00:00Z").toLocaleDateString("en-GB", { weekday: "short", timeZone: "UTC" });

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
      el("span", {}, "as of " + asOf), badge(m.evidence));
  }

  // ---------------- chart (SVG line, crosshair tooltip, data table) ----------------
  function lineChart(points, opts) {
    opts = opts || {};
    const wrap = el("div", { class: "chart" });
    const pts = points.filter((p) => p[1] != null);
    if (pts.length < 2) { wrap.appendChild(el("div", { class: "empty", text: "Not enough data yet." })); return wrap; }
    const fmtV = opts.fmt || ((v) => fmt(v, 2));
    const H = opts.height || 190, P = { t: 10, r: 10, b: 24, l: 48 };
    const xs = pts.map((p) => Date.parse(p[0])), ys = pts.map((p) => p[1]);
    const x0 = xs[0], x1 = xs[xs.length - 1];
    let y0 = Math.min(...ys), y1 = Math.max(...ys); const pad = (y1 - y0) * 0.08 || Math.abs(y1) * 0.02 || 1; y0 -= pad; y1 += pad;
    const NS = "http://www.w3.org/2000/svg";
    const svg = document.createElementNS(NS, "svg"); const tip = el("div", { class: "tip" });
    wrap.append(svg, tip);
    const ns = (t, a) => { const n = document.createElementNS(NS, t); for (const [k, v] of Object.entries(a || {})) n.setAttribute(k, v); return n; };
    function render() {
      const W = Math.max(260, wrap.clientWidth || 560);
      svg.setAttribute("viewBox", `0 0 ${W} ${H}`); svg.textContent = "";
      const X = (t) => P.l + ((t - x0) / (x1 - x0 || 1)) * (W - P.l - P.r);
      const Y = (v) => P.t + (1 - (v - y0) / (y1 - y0)) * (H - P.t - P.b);
      const g = ns("g", { class: "gridl" }), ax = ns("g", { class: "axis" });
      for (let i = 0; i <= 4; i++) {
        const v = y0 + ((y1 - y0) * i) / 4, y = Y(v);
        g.appendChild(ns("line", { x1: P.l, x2: W - P.r, y1: y, y2: y }));
        const t = ns("text", { x: P.l - 6, y: y + 4, "text-anchor": "end" }); t.textContent = fmtV(v); ax.appendChild(t);
      }
      const nx = W < 420 ? 3 : 5, span = x1 - x0;
      for (let i = 0; i <= nx; i++) {
        const t = x0 + (span * i) / nx, d = new Date(t).toISOString();
        const tx = ns("text", { x: X(t), y: H - 6, "text-anchor": i === 0 ? "start" : i === nx ? "end" : "middle" });
        tx.textContent = span > 500 * 864e5 ? d.slice(0, 7) : d.slice(5, 10); ax.appendChild(tx);
      }
      svg.append(g, ax, ns("line", { class: "base", x1: P.l, x2: W - P.r, y1: H - P.b, y2: H - P.b }));
      let d = ""; pts.forEach((p, i) => { d += (i ? "L" : "M") + X(xs[i]).toFixed(1) + "," + Y(p[1]).toFixed(1); });
      svg.appendChild(ns("path", { d, class: "line", stroke: "var(--s1)" }));
      const hair = ns("line", { class: "hair", y1: P.t, y2: H - P.b }), dot = ns("circle", { r: 4.5, class: "dotm", fill: "var(--s1)", style: "display:none" });
      const hit = ns("rect", { x: 0, y: 0, width: W, height: H, fill: "transparent" });
      svg.append(hair, dot, hit);
      const move = (e) => {
        const r = svg.getBoundingClientRect(); const px = ((e.clientX - r.left) / r.width) * W;
        const t = x0 + ((px - P.l) / (W - P.l - P.r)) * span;
        let lo = 0, hi = xs.length - 1; while (hi - lo > 1) { const mid = (lo + hi) >> 1; if (xs[mid] < t) lo = mid; else hi = mid; }
        const i = Math.abs(xs[lo] - t) < Math.abs(xs[hi] - t) ? lo : hi;
        const cx = X(xs[i]), cy = Y(pts[i][1]);
        hair.setAttribute("x1", cx); hair.setAttribute("x2", cx); hair.style.display = "block";
        dot.setAttribute("cx", cx); dot.setAttribute("cy", cy); dot.style.display = "block";
        tip.textContent = ""; tip.append(el("strong", { class: "num" }, fmtV(pts[i][1])), " ", el("span", { class: "tiny" }, pts[i][0]));
        tip.style.display = "block"; tip.style.left = cx / W > 0.6 ? "8px" : "auto"; tip.style.right = cx / W > 0.6 ? "auto" : "8px";
      };
      const leave = () => { hair.style.display = "none"; dot.style.display = "none"; tip.style.display = "none"; };
      hit.addEventListener("pointermove", move); hit.addEventListener("pointerleave", leave);
    }
    render();
    if (window.ResizeObserver) new ResizeObserver(render).observe(wrap);
    const det = el("details", {}, el("summary", { text: "Data table (latest 30)" }));
    const tb = el("tbody"); pts.slice(-30).reverse().forEach((p) => tb.appendChild(el("tr", {}, el("td", {}, p[0]), el("td", { class: "r num" }, fmtV(p[1])))));
    det.appendChild(el("div", { class: "scroll" }, el("table", {}, el("thead", {}, el("tr", {}, el("th", {}, "date"), el("th", { class: "r" }, "value"))), tb)));
    wrap.appendChild(det);
    return wrap;
  }
  function loadSeries(id) {
    if (!S.series[id]) S.series[id] = getJSON("data/series/" + id + ".json");
    return S.series[id];
  }

  // ---------------- shared pieces ----------------
  const ctryChip = (c) => el("span", { class: "chip ctry", title: COUNTRY[c] || c }, c === "GLOBAL" ? "GL" : c);
  const statusChip = (s) => el("span", { class: "chip " + (s === "confirmed" ? "conf" : "est"), title: s === "confirmed" ? "Date published by the institution or fixed in law" : "Date from a rule or past pattern; check it" }, s);
  const imp = (n) => el("span", { class: "imp", title: "importance " + n + " of 3", "aria-label": "importance " + n + " of 3" }, "●".repeat(n), el("i", {}, "●".repeat(3 - n)));
  const unitSuffix = (u) => (u === "pct" ? "%" : " bp");
  function underAttended(e) { return e.importance === 3 && e.attention && e.attention.score < 0.5 && daysUntil(e.date) >= 30; }
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
    return el("article", { class: "card tile" }, head,
      el("div", { class: "lvl" }, fmt(t.level, t.decimals), el("span", { class: "tiny" }, " " + (t.unit || ""))),
      el("div", { class: "chg" },
        el("span", { title: t.chg_1w_from ? "vs " + t.chg_1w_from : "no observation a week earlier" }, "1w ", el("b", {}, t.chg_1w == null ? "–" : signed(t.chg_1w, d) + u)),
        el("span", { title: t.chg_1m_from ? "vs " + t.chg_1m_from : "no observation a month earlier" }, "1m ", el("b", {}, t.chg_1m == null ? "–" : signed(t.chg_1m, d) + u)),
        el("span", { title: "level vs the past year: (level − mean) / sd over " + t.n_1y + " observations" }, "z 1y ", el("b", {}, t.z_1y == null ? "–" : signed(t.z_1y, 2)))),
      t.meta.note ? el("div", { class: "note" }, t.meta.note) : null, meta(t.meta));
  }

  function eventRow(e, calGenerated) {
    const d = daysUntil(e.date), ua = underAttended(e);
    const att = e.attention;
    const attCell = el("div", { class: "att" },
      att ? el("div", { class: "v", title: "GDELT coverage of this event's keywords: last 30 days vs the past 12 months (1.0 = normal)" }, "×" + fmt(att.score, 2)) : el("div", { class: "tiny" }, "no attention data"),
      ua ? el("span", { class: "chip flag", title: "Importance 3, attention under half the country's normal, 30+ days away" }, "under-attended") : null,
      att ? meta({ source: "GDELT", source_url: "https://api.gdeltproject.org/api/v2/doc/doc?query=" + encodeURIComponent(att.query) + "&mode=timelinevolraw&timespan=12m",
        source_id: att.query, as_of: att.as_of, evidence: (S.summary && S.summary.evidence_defaults.attention) }, { noId: true }) : null);
    return el("div", { class: "ev" + (ua ? " under" : "") },
      el("div", { class: "date" }, e.date.slice(5), el("small", {}, weekday(e.date) + " · " + (d === 0 ? "today" : "in " + d + "d"))),
      el("div", {},
        el("div", { class: "title" }, e.title),
        el("div", { class: "row2" }, ctryChip(e.country), el("span", {}, e.type), imp(e.importance), statusChip(e.status),
          e.source ? el("a", { href: e.source, target: "_blank", rel: "noopener" }, "source") : null),
        e.note ? el("details", {}, el("summary", {}, "note"), el("div", { class: "small muted" }, e.note)) : null,
        meta({ source: "calendar", as_of: calGenerated, evidence: S.summary && S.summary.evidence_defaults.countdown, source_url: e.source }, { noId: true })),
      attCell);
  }

  // ---------------- pages ----------------
  function pageToday() {
    const s = S.summary, f = el("div");
    f.append(el("div", { class: "sec" }, el("h1", {}, "Today"), el("span", { class: "tiny" }, "summary built " + s.generated_at.replace("T", " ").replace("Z", " UTC"))));
    const cats = el("div", { class: "grid" });
    (s.next_catalysts || []).forEach((e) => {
      const c = countdown(e.date);
      cats.appendChild(el("article", { class: "card cat" },
        el("div", { class: "cd", title: "countdown to " + e.date }, el("div", { class: "n" }, c.n), el("div", { class: "u" }, c.u)),
        el("div", { style: "min-width:0" }, el("div", { class: "t" }, e.title),
          el("div", { class: "d" }, ctryChip(e.country), " ", e.date + " (" + weekday(e.date) + ") ", imp(e.importance), " ", statusChip(e.status)),
          meta({ source: "source", source_url: e.source, as_of: S.calendar ? S.calendar.generated_at : null, evidence: s.evidence_defaults.countdown }))));
    });
    f.append(el("div", { class: "sec" }, el("h2", {}, "Next catalysts"), el("a", { href: "#calendar", class: "small" }, "full calendar →")), cats);
    const g = el("div", { class: "grid" }); s.tiles.forEach((t) => g.appendChild(tile(t)));
    f.append(el("div", { class: "sec" }, el("h2", {}, "Instruments"), el("span", { class: "tiny" }, "1w / 1m change; z = level vs the past year")), g);
    const st = Object.values(s.status.sources || {}), bad = st.filter((x) => ["error", "missing_secret"].includes(x.state));
    f.append(el("p", { class: "small muted", style: "margin-top:14px" }, st.length + " sources tracked, ", el("b", {}, String(bad.length)), " failing or missing a secret. ", el("a", { href: "#status" }, "Status page →")));
    return f;
  }

  function pageCalendar() {
    const cal = S.calendar, f = el("div");
    const lim = { "2w": 14, "3m": 92, "12m": 366 }[S.calTab];
    let evs = cal.events.filter((e) => { const d = daysUntil(e.date); return d >= 0 && d <= lim; });
    if (S.calCountry !== "ALL") evs = evs.filter((e) => e.country === S.calCountry);
    if (!S.calRoutine) evs = evs.filter((e) => e.importance > 1);
    const ua = evs.filter(underAttended).length;
    const tabs = el("div", { class: "tabs", role: "tablist" });
    [["2w", "Next 2 weeks"], ["3m", "3 months"], ["12m", "12 months"]].forEach(([k, l]) => tabs.appendChild(el("button", { class: S.calTab === k ? "on" : "", role: "tab", "aria-selected": String(S.calTab === k), type: "button", onclick: () => { S.calTab = k; location.hash = "#calendar/" + k; } }, l)));
    const fl = el("div", { class: "filters" });
    ["ALL", "FR", "BR", "MX", "GLOBAL"].forEach((c) => fl.appendChild(el("button", { type: "button", class: S.calCountry === c ? "on" : "", onclick: () => { S.calCountry = c; route(); } }, c === "ALL" ? "All" : c === "GLOBAL" ? "Global" : COUNTRY[c])));
    fl.appendChild(el("button", { type: "button", class: S.calRoutine ? "on" : "", onclick: () => { S.calRoutine = !S.calRoutine; route(); }, title: "Weekly/monthly surveys (importance 1)" }, S.calRoutine ? "Routine shown" : "Routine hidden"));
    f.append(el("div", { class: "sec" }, el("h1", {}, "Calendar"), tabs), fl,
      el("p", { class: "small muted" }, evs.length + " events · " + ua + " under-attended. Attention = news coverage of the event's keywords over the last 30 days relative to their normal level over the past year (GDELT); ×1.0 is normal."));
    const list = el("div", { class: "evlist" });
    evs.forEach((e) => list.appendChild(eventRow(e, cal.generated_at)));
    if (!evs.length) list.appendChild(el("div", { class: "empty" }, "No events in this window."));
    f.appendChild(list);
    if (cal.notes && cal.notes.length) f.appendChild(el("div", { class: "card", style: "margin-top:14px" }, el("h3", { style: "margin-top:0" }, "Notes"), el("ul", { class: "small muted" }, ...cal.notes.map((n) => el("li", {}, n)))));
    f.appendChild(el("p", { class: "tiny" }, "Definition: " + (cal.attention_definition || "") + ". Sources: events.yaml (hand-sourced), Federal Reserve and ECB calendars (scraped daily), recurring releases by rule, em-macro for " + cal.past_events.length + " past events."));
    return f;
  }

  function chartCard(item) {
    const card = el("article", { class: "card" });
    if (item.missing) {
      card.append(el("h2", {}, item.name), el("div", { class: "empty" }, "Not available yet — see the status page."), el("div", { class: "meta" }, el("span", { class: "dot stale" }), el("a", { href: "#status" }, "status"), badge(item.meta && item.meta.evidence)));
      return card;
    }
    const body = el("div", { class: "empty" }, "Loading…");
    card.append(el("h2", {}, item.name, item.fallback ? el("span", { class: "chip est", style: "margin-left:6px" }, "fallback") : null), body, meta(item.meta));
    loadSeries(item.series).then((s) => {
      const last = s.history[s.history.length - 1][0];
      const from = new Date(Date.parse(last) - (S.range === "5y" ? 5 * 365.25 : 365) * 864e5).toISOString().slice(0, 10);
      const pts = s.history.filter((r) => r[0] >= from).map((r) => [r[0], typeof r[1] === "number" ? r[1] : null]);
      const lv = pts.length ? pts[pts.length - 1][1] : null;
      body.replaceWith(el("div", {}, el("div", { class: "small" }, el("b", { class: "num" }, fmt(lv, 2)), " " + (s.unit || "") + " · " + pts.length + " obs in " + S.range), lineChart(pts)));
    }).catch((err) => body.replaceWith(el("div", { class: "err" }, String(err))));
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
      tb.appendChild(el("tr", {}, el("td", {}, el("b", {}, "Official: "), o.label || ""), el("td", { class: "r" }, cellVal(o.value, 2)),
        el("td", {}, o.source ? el("a", { href: o.source, target: "_blank", rel: "noopener" }, "link") : "–", " ", o.verified ? null : el("span", { class: "chip est" }, "to verify"))));
      (r.independent || []).forEach((i) => tb.appendChild(el("tr", {}, el("td", {}, i.name, i.note ? el("div", { class: "tiny" }, i.note) : null),
        el("td", { class: "r" }, cellVal(i.value, 2), i.as_of ? el("div", { class: "tiny" }, el("span", { class: "dot " + freshness(i.as_of).cls }), " " + i.as_of) : null),
        el("td", {}, i.source ? el("a", { href: i.source, target: "_blank", rel: "noopener" }, i.source_label || "link") : "–", " ", i.verified ? null : el("span", { class: "chip est" }, "to verify")))));
      t.appendChild(tb);
      wrap.append(el("h3", {}, r.metric + ", " + r.year),
        el("div", { class: "small" }, "Optimism gap (official − median independent): ", el("b", { class: "num" }, r.gap == null ? "–" : signed(r.gap, 2) + " pp"), " ", badge(ev)),
        el("div", { class: "scroll" }, t));
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
    const tabs = el("div", { class: "tabs" });
    [["1y", "1 year"], ["5y", "5 years"]].forEach(([k, l]) => tabs.appendChild(el("button", { type: "button", class: S.range === k ? "on" : "", onclick: () => { S.range = k; route(); } }, l)));
    const sub = el("div", { class: "filters" });
    ["FR", "BR", "MX"].forEach((k) => sub.appendChild(el("button", { type: "button", class: k === code ? "on" : "", onclick: () => { location.hash = "#country/" + k; } }, COUNTRY[k])));
    f.append(sub, el("div", { class: "sec" }, el("h1", {}, c.name), tabs));
    if (c.events && c.events.length) {
      const l = el("div", { class: "evlist" }); c.events.filter((e) => e.importance >= 2).slice(0, 4).forEach((e) => l.appendChild(eventRow(e, S.calendar && S.calendar.generated_at)));
      f.append(el("div", { class: "sec" }, el("h2", {}, "Next catalysts"), el("a", { class: "small", href: "#calendar" }, "calendar →")), l);
    }
    const g = el("div", { class: "grid wide" }); c.charts.forEach((it) => g.appendChild(chartCard(it)));
    f.append(el("div", { class: "sec" }, el("h2", {}, "Markets")), g);
    f.append(el("div", { class: "sec" }, el("h2", {}, "Fiscal optimism gap")), el("article", { class: "card" }, fiscalTable(c.fiscal_gap || [], S.summary.evidence_defaults.fiscal_gap)));
    const ex = el("div", { class: "grid wide" });
    (c.surveys || []).forEach((b) => ex.appendChild(surveyCard(b)));
    if (c.cot) ex.appendChild(cotCard(c.cot, code));
    if (!c.surveys.length && !c.cot) ex.appendChild(el("article", { class: "card" }, el("div", { class: "empty" }, "No survey or futures-positioning source for " + c.name + " in Phase 1 (no Focus- or Banxico-style survey with a public API; no CFTC-listed euro sovereign contract).")));
    f.append(el("div", { class: "sec" }, el("h2", {}, "Expectations and positioning")), ex);
    if (c.ratings) {
      const r = c.ratings, t = el("table", {}, el("thead", {}, el("tr", {}, el("th", {}, "agency"), el("th", {}, "rating"), el("th", {}, "outlook"), el("th", {}, "last action"), el("th", {}, "next review"))));
      const tb = el("tbody");
      r.rows.forEach((x) => tb.appendChild(r.origin === "aft" ? el("tr", {}, el("td", {}, x.agency), el("td", { colspan: 4 }, (x.cells || []).join(" · ")))
        : el("tr", {}, el("td", {}, x.agency), el("td", {}, el("b", {}, x.rating)), el("td", {}, x.outlook || "–"), el("td", { class: "small" }, x.last_action || "–"), el("td", {}, x.next_review || "–", x.verified ? null : el("span", { class: "chip est", style: "margin-left:4px" }, "to verify")))));
      t.appendChild(tb);
      f.append(el("div", { class: "sec" }, el("h2", {}, "Credit ratings")), el("article", { class: "card" }, el("div", { class: "scroll" }, t), meta(r.meta)));
    }
    if (c.markets && c.markets.length) {
      const t = el("table", {}, el("thead", {}, el("tr", {}, el("th", {}, "market"), el("th", { class: "r" }, "P(yes)"), el("th", { class: "r" }, "volume"), el("th", {}, "venue"))));
      const tb = el("tbody");
      c.markets.forEach((m) => tb.appendChild(el("tr", {}, el("td", {}, el("a", { href: m.url, target: "_blank", rel: "noopener" }, m.question)), el("td", { class: "r num" }, fmt(100 * m.prob, 0) + "%"), el("td", { class: "r num" }, m.volume == null ? "–" : "$" + fmt(m.volume / 1000, 0) + "k"), el("td", {}, m.venue))));
      t.appendChild(tb);
      f.append(el("div", { class: "sec" }, el("h2", {}, "Prediction markets"), el("a", { class: "small", href: "#crowd" }, "crowd →")), el("article", { class: "card" }, el("div", { class: "scroll" }, t), meta(c.markets[0].meta, { noId: true })));
    }
    return f;
  }

  function pageStatus() {
    const st = S.summary.status.sources || {}, f = el("div");
    f.append(el("div", { class: "sec" }, el("h1", {}, "Source status"), el("span", { class: "tiny" }, "updated " + (S.summary.status.updated_at || ""))));
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
    f.append(el("article", { class: "card" }, el("div", { class: "scroll" }, t)),
      el("p", { class: "small muted" }, "Green: succeeded on the last run. Red: failed or a secret is missing; it is skipped and everything else keeps working. Grey: a fallback that was not needed. Amber: partial."));
    return f;
  }

  function placeholder(title, phase, lines) {
    return el("div", { class: "ph" }, el("h1", {}, title), el("div", { class: "chip" }, "Coming in " + phase), el("ul", { class: "small" }, ...lines.map((l) => el("li", {}, l))));
  }
  function pageCrowd() {
    let n = 0; Object.values(S.summary.countries).forEach((c) => { n += (c.markets || []).length; });
    const st = S.summary.status.sources || {};
    return placeholder("Crowd", "Phase 4: crowd-error monitor", [
      "Will compare prediction-market, survey and futures-implied expectations with outcomes and flag where the crowd is systematically wrong.",
      "Already stored with full daily history: Polymarket (" + ((st.polymarket && st.polymarket.n_series) || 0) + " markets), Kalshi (" + ((st.kalshi && st.kalshi.n_series) || 0) + "), the Focus and Banxico surveys with dispersion, and CFTC positioning.",
      "Country pages already show the top markets by volume (" + n + " shown now)."]);
  }

  // ---------------- routing ----------------
  function route() {
    const h = (location.hash || "#today").slice(1), [page, arg] = h.split("/");
    if (page === "calendar" && ["2w", "3m", "12m"].includes(arg)) S.calTab = arg;
    document.querySelectorAll("[data-r]").forEach((a) => a.classList.toggle("on", a.dataset.r === page || a.dataset.r === h));
    app.textContent = "";
    if (!S.summary) { app.appendChild(el("div", { class: "empty" }, "Loading…")); return; }
    let node;
    if (page === "calendar") node = pageCalendar();
    else if (page === "country") node = pageCountry((arg || "BR").toUpperCase());
    else if (page === "status") node = pageStatus();
    else if (page === "scenarios") node = placeholder("Scenarios", "Phase 3", ["Scenario pages per country: what each catalyst outcome implies for the instruments on the Today page, with probabilities taken from the calendar and the crowd.", "Built on the stored series and the catalyst calendar (" + S.calendar.events.length + " upcoming events)."]);
    else if (page === "crowd") node = pageCrowd();
    else if (page === "record") node = placeholder("Record", "Phases 2 and 3: paper book, judgement forms and scoring", ["A paper trading book on the instruments above, marked to the stored daily closes.", "Judgement forms before each catalyst, scored afterwards; the forecast-panel scorecard lives in the Lab until then."]);
    else node = pageToday();
    app.appendChild(node);
  }

  // theme
  const btn = document.getElementById("theme");
  const apply = (t) => { if (t) document.documentElement.setAttribute("data-theme", t); else document.documentElement.removeAttribute("data-theme"); btn.textContent = t === "dark" ? "☾" : t === "light" ? "☀" : "◐"; btn.title = "Theme: " + (t || "auto"); };
  let theme = store.get("terminal.theme", ""); apply(theme);
  btn.addEventListener("click", () => { theme = theme === "" ? "light" : theme === "light" ? "dark" : ""; store.set("terminal.theme", theme); apply(theme); });

  window.addEventListener("hashchange", () => { route(); window.scrollTo(0, 0); });
  route();
  Promise.all([getJSON("data/summary.json"), getJSON("data/calendar.json")]).then(([s, c]) => { S.summary = s; S.calendar = c; route(); })
    .catch((err) => { app.textContent = ""; app.appendChild(el("div", { class: "ph" }, el("h1", {}, "Data not found"), el("p", {}, String(err)), el("p", { class: "small" }, "Locally: run `python -m terminal.run site` and serve the site folder with `python -m http.server`."))); });
})();
