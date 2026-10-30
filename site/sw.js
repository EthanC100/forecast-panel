/* Service worker: the app files are cached on install; everything is fetched from the network first
   and the last good copy is kept, so Catalyst opens offline with what it last loaded. */
const VERSION = "prism-v3";
const SHELL = ["./", "index.html", "terminal.css", "terminal.js", "charts.js", "teach.js", "record.js", "scenarios.js", "brief.js", "econ.js", "glossary.js",
  "manifest.webmanifest", "geo.json", "icons/icon-32.png", "icons/icon-192.png", "icons/icon-512.png", "icons/apple-touch-icon.png"];
const DATA = "prism-data";

self.addEventListener("install", (e) => {
  e.waitUntil(caches.open(VERSION).then((c) => c.addAll(SHELL)).then(() => self.skipWaiting()));
});
self.addEventListener("activate", (e) => {
  e.waitUntil(caches.keys().then((keys) => Promise.all(keys.filter((k) => k !== VERSION && k !== DATA).map((k) => caches.delete(k))))
    .then(() => self.clients.claim()));
});
self.addEventListener("fetch", (e) => {
  const url = new URL(e.request.url);
  if (e.request.method !== "GET" || url.origin !== location.origin) return;
  if (url.pathname.includes("/data/")) {
    // network first, fall back to the last copy; the page is told when it is offline
    e.respondWith(fetch(e.request).then((r) => {
      if (r.ok) { const copy = r.clone(); caches.open(DATA).then((c) => c.put(e.request, copy)); }
      return r;
    }).catch(() => caches.open(DATA).then((c) => c.match(e.request, { ignoreSearch: true })).then((m) => m || Response.error())));
    return;
  }
  // app files: network first too, so a new deploy never mixes old and new modules; the cache is the offline copy
  e.respondWith(fetch(e.request).then((r) => {
    if (r.ok) { const copy = r.clone(); caches.open(VERSION).then((c) => c.put(e.request, copy)); }
    return r;
  }).catch(() => caches.open(VERSION).then((c) => c.match(e.request, { ignoreSearch: true })).then((m) => m || caches.match("index.html"))));
});
