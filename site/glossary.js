/* Glossary: tap a finance term anywhere for a two-sentence plain-English definition. The first use
   of each term inside a card (or paragraph) is made tappable; #glossary lists them all. */
(function () {
  "use strict";
  const T = window.TERM;
  const { el } = T;
  const TERMS = [
    ["carry", ["carry"], "The income a position earns (or pays) just by being held, before any price change. In a currency trade it is the interest-rate difference between the two currencies; in a bond it is the yield above the funding rate."],
    ["spread", ["spread", "spreads"], "The gap between two yields, usually a country's bond yield minus a benchmark such as Germany's (Bund) or the US Treasury. A wider spread means investors demand more to hold that country's debt."],
    ["duration", ["duration"], "How much a bond's price moves when its yield moves: a duration of 8 means about an 8% price change for a 1-point (100 bp) change in yield. Higher duration means more sensitivity, in both directions."],
    ["basis point", ["basis point", "basis points", "bp"], "One hundredth of a percentage point (0.01%). A yield going from 3.50% to 3.75% has risen 25 basis points."],
    ["Brier score", ["Brier score", "Brier"], "The average squared gap between a probability forecast and what happened (1 if it did, 0 if not). Lower is better: 0 is perfect and always saying 50% scores 0.25."],
    ["z-score", ["z-score", "z-scores"], "How unusual a number is: its distance from the average measured in standard deviations. A z-score of +2 means about two standard deviations above normal, which happens roughly 2% of the time."],
    ["drawdown", ["drawdown", "drawdowns"], "The fall from a portfolio's highest value to a later low, in percent. The worst drawdown is the largest such fall, a simple measure of how painful the ride was."],
    ["Sharpe ratio", ["Sharpe ratio", "Sharpe"], "Return per unit of risk: average excess return divided by its volatility, usually annualised. Above 1 is very good for a whole strategy; below 0.3 is weak."],
    ["notional", ["notional"], "The face size of a position, the amount the price change applies to. A $100,000 notional currency trade gains $1,000 on a 1% move in your favour."],
    ["percentile", ["percentile"], "Where a reading sits among past readings: the 90th percentile is higher than 90% of them. It tells you how extreme something is relative to its own history."],
    ["base rate", ["base rate", "base rates"], "How often an outcome happened in a set of similar past cases, before looking at the specifics. It anchors a forecast so that a vivid story does not move it too far."],
    ["fair value", ["fair value"], "The level a model says a price should be at, given the factors it uses. The gap between the actual price and fair value is the model's view of cheap or expensive."],
    ["abnormal move", ["abnormal move", "abnormal moves"], "The part of a price move not explained by the market-wide moves of that day (here the dollar, US yields and the VIX). It isolates the reaction to the event itself."],
    ["open interest", ["open interest"], "The number of futures contracts still open at the end of a day. It shows how big a market is, so a position can be judged relative to it."],
    ["reward-to-risk", ["reward-to-risk", "reward:risk"], "What you stand to make if right divided by what you stand to lose if wrong. At 2:1 a trade can be right only a third of the time and still break even."],
    ["stop", ["stop-loss", "stop"], "A pre-set level at which a losing trade is closed. It caps the loss and fixes the risk before the trade is opened."],
    ["yield", ["yield", "yields"], "The annual return a bond pays if bought at today's price and held to maturity. Prices and yields move in opposite directions."],
    ["standard deviation", ["standard deviation", "sd"], "The typical distance of readings from their average. About two-thirds of readings fall within one standard deviation of the mean."],
  ];
  const BY = {};
  TERMS.forEach(([key, words, def]) => words.forEach((w) => { BY[w.toLowerCase()] = { key, def }; }));
  const words = Object.keys(BY).sort((a, b) => b.length - a.length).map((w) => w.replace(/[.*+?^${}()|[\]\\:]/g, "\\$&"));
  const RX = new RegExp("(^|[^\\w-])(" + words.join("|") + ")(?![\\w-])", "i");
  const SKIP = "a, button, input, select, textarea, svg, script, style, code, .term, .formula, .tip, .gpop, .chip, .badge, summary, th, .tabs, .filters, .bottom, .top, .lvl, .num";

  let pop = null;
  function show(key) {
    const t = TERMS.find((x) => x[0] === key); if (!t) return;
    if (pop) pop.remove();
    pop = el("div", { class: "gpop", role: "dialog", "aria-label": t[0] },
      el("button", { class: "x", type: "button", "aria-label": "Close", onclick: () => { pop.remove(); pop = null; } }, "×"),
      el("b", {}, t[0]), t[2], el("div", { class: "tiny", style: "margin-top:6px" }, el("a", { href: "#glossary" }, "All terms →")));
    document.body.appendChild(pop);
  }
  document.addEventListener("click", (e) => {
    const t = e.target.closest && e.target.closest(".term");
    if (t) { e.preventDefault(); show(t.dataset.term); return; }
    if (pop && !e.target.closest(".gpop")) { pop.remove(); pop = null; }
  });
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && pop) { pop.remove(); pop = null; }
    if ((e.key === "Enter" || e.key === " ") && e.target.classList && e.target.classList.contains("term")) { e.preventDefault(); show(e.target.dataset.term); }
  });

  /** Mark the first use of each term inside every card / paragraph under root. */
  T.glossarize = function (root) {
    const scopes = [...root.querySelectorAll(".card, p, .ev, details.how > div")];
    if (root.matches && root.matches(".card, p, .ev, details.how")) scopes.push(root);
    scopes.forEach((scope) => {
      if (scope._gl === true) return;
      const seen = new Set([...scope.querySelectorAll(".term")].map((t) => t.dataset.term));
      const walker = document.createTreeWalker(scope, NodeFilter.SHOW_TEXT, {
        acceptNode: (n) => (!n.nodeValue.trim() || (n.parentElement && n.parentElement.closest(SKIP))) ? NodeFilter.FILTER_REJECT : NodeFilter.FILTER_ACCEPT });
      const nodes = []; while (walker.nextNode()) nodes.push(walker.currentNode);
      nodes.forEach((n) => {
        const m = RX.exec(n.nodeValue); if (!m) return;
        const hit = BY[m[2].toLowerCase()]; if (!hit || seen.has(hit.key)) return;
        seen.add(hit.key);
        const start = m.index + m[1].length, word = m[2];
        const after = n.splitText(start); after.nodeValue = after.nodeValue.slice(word.length);
        n.parentNode.insertBefore(el("span", { class: "term", "data-term": hit.key, tabindex: "0", role: "button", title: "What is " + hit.key + "?" }, word), after);
      });
    });
  };
  if (document.getElementById("app")) T.glossarize(document.getElementById("app"));

  T.pageGlossary = function () {
    const f = el("div");
    f.append(el("div", { class: "sec" }, el("h1", {}, "Terms")), el("p", { class: "small muted" }, "Plain-English definitions. Underlined words anywhere on the site open the same definition."));
    const list = el("div", { class: "grid" });
    TERMS.slice().sort((a, b) => a[0].localeCompare(b[0])).forEach(([k, , d]) => {
      const c = el("article", { class: "card", id: "term-" + k.replace(/\W+/g, "-") }, el("h2", {}, k), el("div", { class: "small" }, d));
      c._gl = true; list.appendChild(c);
    });
    f.append(list);
    return f;
  };
})();
