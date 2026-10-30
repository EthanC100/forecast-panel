/* Horizons service worker: network first for everything, the last good copy kept for offline use.
   Its own caches (horizons-*) sit beside Catalyst's (prism-*); each app only clears its own. */
const VERSION = "horizons-v1";
const DATA = "horizons-data";
const SHELL = ["./", "index.html", "hz.css", "hz.js", "hz-terms.js", "hz-home.js", "hz-country.js", "hz-gold.js", "hz-markets.js", "hz-record.js", "hz-help.js",
  "manifest.webmanifest", "icons/icon.svg", "icons/icon-96.png", "icons/icon-192.png", "icons/icon-512.png", "icons/apple-touch-icon.png"];

self.addEventListener("install", (e) => {
  e.waitUntil(caches.open(VERSION).then((c) => c.addAll(SHELL)).catch(() => null).then(() => self.skipWaiting()));
});
self.addEventListener("activate", (e) => {
  e.waitUntil(caches.keys().then((keys) => Promise.all(keys.filter((k) => k.startsWith("horizons-") && k !== VERSION && k !== DATA).map((k) => caches.delete(k))))
    .then(() => self.clients.claim()));
});
self.addEventListener("fetch", (e) => {
  const url = new URL(e.request.url);
  if (e.request.method !== "GET" || url.origin !== location.origin) return;
  const bucket = url.pathname.includes("/data/") ? DATA : VERSION;
  e.respondWith(fetch(e.request).then((r) => {
    if (r.ok) { const copy = r.clone(); caches.open(bucket).then((c) => c.put(e.request, copy)); }
    return r;
  }).catch(() => caches.open(bucket).then((c) => c.match(e.request, { ignoreSearch: true }))
    .then((m) => m || (bucket === VERSION ? caches.match("index.html") : Response.error()))));
});
