/* Parse a pasted DECISION RECORD block into a decision (pure; no network). Used by app.js and by the
   tests (node). The block:
     DECISION RECORD
     Date: / Country: / Instrument: / Action: / Size (% of account at risk, max 2%): /
     Probability my view is right: / Horizon (date): / Entry trigger: / Stop / exit if wrong: /
     Thesis: / Key factors: / What would change my mind: / How this differs from market consensus:
   Labels may be bold or bulleted; a value may run over several lines until the next label. */
(function (root) {
  "use strict";
  const MAX_RISK = 2;
  const FIELDS = [
    ["date", /^date\b/],
    ["country", /^country\b/],
    ["instrument", /^instrument\b/],
    ["action", /^action\b/],
    ["size", /^size\b/],
    ["probability", /^probability\b/],
    ["horizon", /^horizon\b/],
    ["entry_trigger", /^entry trigger\b/],
    ["stop", /^stop\b/],
    ["thesis", /^thesis\b/],
    ["key_factors", /^key factors\b/],
    ["change_mind", /^what would change my mind\b/],
    ["vs_consensus", /^how (this|it) differs from (the )?(market )?consensus\b/],
  ];
  const COUNTRY = { brazil: "BR", brasil: "BR", br: "BR", mexico: "MX", méxico: "MX", mx: "MX", france: "FR", fr: "FR", gold: "GOLD", silver: "GOLD", xau: "GOLD", "gold and silver": "GOLD", "precious metals": "GOLD" };
  // book instruments: code -> [label, kind, country]; kind decides how a stop is read
  const INSTRUMENTS = {
    USDBRL: ["USD/BRL", "fx", "BR"], USDMXN: ["USD/MXN", "fx", "MX"], EURUSD: ["EUR/USD", "fx", "FR"],
    OATBUND: ["France–Germany 10y spread", "spread_bp", "FR"], BR10Y: ["Brazil 10y proxy", "yield", "BR"], MX10Y: ["Mexico 10y", "yield", "MX"],
    US10Y: ["US 10y", "yield", "GOLD"], DI27: ["Brazil DI Jan-27", "yield", "BR"], DI29: ["Brazil DI Jan-29", "yield", "BR"], DI31: ["Brazil DI Jan-31", "yield", "BR"],
    XAUUSD: ["Gold", "price", "GOLD"], XAGUSD: ["Silver", "price", "GOLD"],
  };
  const ALIASES = [
    [/usd\s*\/?\s*brl|brl|real\b|reais/, "USDBRL"], [/usd\s*\/?\s*mxn|mxn|peso/, "USDMXN"], [/eur\s*\/?\s*usd|euro/, "EURUSD"],
    [/oat|bund|france.{0,3}germany|fr.?de\b|spread/, "OATBUND"], [/di\s*jan.?27|di27/, "DI27"], [/di\s*jan.?29|di29/, "DI29"], [/di\s*jan.?31|di31/, "DI31"],
    [/brazil.{0,12}10|br10y|ntn|prefixado|tesouro/, "BR10Y"], [/mexico.{0,12}10|mx10y|m.?bono/, "MX10Y"], [/us.{0,4}10|ust|treasur|us10y/, "US10Y"],
    [/gold|xau/, "XAUUSD"], [/silver|xag/, "XAGUSD"],
  ];
  const ACTIONS = [[/^(buy|long|go long|add)\b/, "Buy"], [/^(sell|short|go short)\b/, "Sell"], [/^(hold|keep|maintain|stay)\b/, "Hold"],
    [/^(close|exit|take profit|cut)\b/, "Close"], [/^(no trade|none|no action|wait|pass|stand aside|flat)\b/, "No trade"]];

  const clean = (s) => s.replace(/\*\*|__/g, "").replace(/^\s*(?:[-*•–]\s+|\d+[.)]\s+)/, "").trim();
  const MONTHS = { jan: 0, feb: 1, mar: 2, apr: 3, may: 4, jun: 5, jul: 6, aug: 7, sep: 8, oct: 9, nov: 10, dec: 11 };
  function isoDate(s) {
    if (!s) return null;
    let m = s.match(/(\d{4})-(\d{2})-(\d{2})/);
    if (m) return valid(+m[1], +m[2] - 1, +m[3]);
    m = s.match(/(\d{1,2})\s+([a-z]{3})[a-z]*\.?,?\s+(\d{4})/i);
    if (m && MONTHS[m[2].toLowerCase()] != null) return valid(+m[3], MONTHS[m[2].toLowerCase()], +m[1]);
    m = s.match(/([a-z]{3})[a-z]*\.?\s+(\d{1,2}),?\s+(\d{4})/i);
    if (m && MONTHS[m[1].toLowerCase()] != null) return valid(+m[3], MONTHS[m[1].toLowerCase()], +m[2]);
    m = s.match(/(\d{1,2})\/(\d{1,2})\/(\d{4})/);   // day/month/year
    if (m) return valid(+m[3], +m[2] - 1, +m[1]);
    return null;
  }
  function valid(y, mo, d) {
    const t = new Date(Date.UTC(y, mo, d));
    return t.getUTCFullYear() === y && t.getUTCMonth() === mo && t.getUTCDate() === d ? t.toISOString().slice(0, 10) : null;
  }
  const firstNumber = (s) => { const m = (s || "").replace(/,(?=\d{3}\b)/g, "").match(/[-−]?\d+(?:[.,]\d+)?/); return m ? parseFloat(m[0].replace("−", "-").replace(",", ".")) : null; };

  /** parse(text) -> {ok, errors[], warnings[], decision, fields} */
  function parse(text) {
    const errors = [], warnings = [];
    const lines = String(text || "").replace(/\r/g, "").split("\n");
    if (!lines.some((l) => /decision record/i.test(l))) errors.push("This is not a decision record: the block must start with DECISION RECORD.");
    const fields = {};
    let cur = null;
    for (const raw of lines) {
      const line = clean(raw);
      if (!line || /^decision record\b/i.test(line)) { if (cur && !line) fields[cur] += "\n"; continue; }
      const low = line.toLowerCase();
      const hit = FIELDS.find(([, re]) => re.test(low));
      const colon = line.indexOf(":");
      if (hit && colon > -1 && !fields[hit[0]]) {
        cur = hit[0]; fields[cur] = line.slice(colon + 1).trim(); continue;
      }
      if (cur) fields[cur] += (fields[cur] && !fields[cur].endsWith("\n") ? "\n" : "") + line;
    }
    for (const k of Object.keys(fields)) fields[k] = fields[k].replace(/\n{2,}/g, "\n").trim();
    const need = ["date", "country", "instrument", "action", "size", "probability", "horizon", "stop", "thesis"];
    const names = { date: "Date", country: "Country", instrument: "Instrument", action: "Action", size: "Size", probability: "Probability my view is right", horizon: "Horizon", stop: "Stop / exit if wrong", thesis: "Thesis" };
    need.forEach((k) => { if (!fields[k]) errors.push("Missing “" + names[k] + "”."); });

    const d = { raw: String(text || "").trim() };
    d.decision_date = isoDate(fields.date);
    if (fields.date && !d.decision_date) errors.push("Date “" + fields.date + "” is not a date (use YYYY-MM-DD).");
    const cl = (fields.country || "").toLowerCase().trim().replace(/[.:]+$/, "");
    d.country = COUNTRY[cl] || (Object.keys(COUNTRY).find((k) => cl.startsWith(k)) ? COUNTRY[Object.keys(COUNTRY).find((k) => cl.startsWith(k))] : null);
    if (fields.country && !d.country) errors.push("Country “" + fields.country + "” must be Brazil, Mexico, France or Gold.");
    d.instrument_label = fields.instrument || null;
    const il = (fields.instrument || "").toLowerCase();
    const ali = ALIASES.find(([re]) => re.test(il));
    d.instrument = ali ? ali[1] : null;
    const al = (fields.action || "").toLowerCase().trim();
    const act = ACTIONS.find(([re]) => re.test(al));
    d.action = act ? act[1] : null;
    if (fields.action && !d.action) errors.push("Action “" + fields.action + "” must be Buy, Sell, Hold, Close or No trade.");
    const trades = d.action === "Buy" || d.action === "Sell";
    if (fields.instrument && !d.instrument) (trades || d.action === "Close" ? errors : warnings).push("Instrument “" + fields.instrument + "” is not in the paper book (USD/BRL, USD/MXN, EUR/USD, France–Germany spread, Brazil 10y, Mexico 10y, US 10y, gold, silver).");
    if (!d.instrument) d.instrument = fields.instrument || "";

    d.risk_pct = firstNumber(fields.size);
    if (fields.size && d.risk_pct == null) errors.push("Size “" + fields.size + "” has no number.");
    if (d.risk_pct != null && d.risk_pct > MAX_RISK) errors.push("Size is " + d.risk_pct + "% of the account at risk. The maximum is " + MAX_RISK + "%: reduce the size and paste the record again.");
    if (d.risk_pct != null && d.risk_pct < 0) errors.push("Size cannot be negative.");
    if (trades && !(d.risk_pct > 0)) errors.push("A " + d.action + " needs a size above 0% of the account at risk.");
    if (d.risk_pct == null) d.risk_pct = 0;

    let p = firstNumber(fields.probability);
    if (p != null && (/%/.test(fields.probability) || p > 1)) p = p / 100;
    d.probability = p;
    if (fields.probability && (p == null || !(p > 0 && p < 1))) errors.push("Probability “" + fields.probability + "” must be between 0% and 100%.");
    d.horizon = isoDate(fields.horizon);
    if (fields.horizon && !d.horizon) errors.push("Horizon “" + fields.horizon + "” is not a date (use YYYY-MM-DD).");
    if (d.horizon && d.decision_date && d.horizon <= d.decision_date) errors.push("The horizon must be after the decision date.");

    d.stop_text = fields.stop || null;
    d.stop_level = firstNumber(fields.stop);
    const kind = INSTRUMENTS[d.instrument] && INSTRUMENTS[d.instrument][1];
    if (trades) {
      if (d.stop_level == null) errors.push("Stop / exit if wrong must include a price or yield level.");
      else if ((kind === "fx" || kind === "price") && /^[^\d]*\d+(?:[.,]\d+)?\s*%/.test(fields.stop)) errors.push("Give the stop as a price level, not a percentage.");
    }
    d.entry_trigger = fields.entry_trigger || null;
    d.thesis = fields.thesis || null;
    d.key_factors = fields.key_factors || null;
    d.change_mind = fields.change_mind || null;
    d.vs_consensus = fields.vs_consensus || null;
    if (d.country && INSTRUMENTS[d.instrument] && INSTRUMENTS[d.instrument][2] !== d.country && d.country !== "GOLD")
      warnings.push(INSTRUMENTS[d.instrument][0] + " is filed under " + ({ BR: "Brazil", MX: "Mexico", FR: "France", GOLD: "Gold" })[d.country] + ".");
    return { ok: !errors.length, errors, warnings, decision: d, fields, direction: d.action === "Buy" ? "long" : d.action === "Sell" ? "short" : null, kind };
  }

  /** Is the stop on the losing side of the current level? long fx/price: stop below; long yield/spread (gains when it falls): stop above. */
  function stopSideOk(kind, direction, level, stop) {
    if (level == null || stop == null || !direction) return true;
    const sign = direction === "long" ? 1 : -1;
    const priceLike = kind === "fx" || kind === "price";
    return priceLike ? sign * (level - stop) > 0 : sign * (stop - level) > 0;
  }

  const api = { parse, stopSideOk, INSTRUMENTS, MAX_RISK, isoDate };
  if (typeof module !== "undefined" && module.exports) module.exports = api; else root.Decision = api;
})(typeof window !== "undefined" ? window : globalThis);
