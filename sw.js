/* DocPulsee service worker: app install + offline. Pages always try the network first, so updates show at once. */
const V = "dp-v1";
const SHELL = ["/", "/index.html", "/offline.html", "/manifest.webmanifest", "/icons/icon-192.png", "/icons/icon-512.png"];
const CDN = /^(https:\/\/(cdnjs\.cloudflare\.com|cdn\.jsdelivr\.net|unpkg\.com|fonts\.googleapis\.com|fonts\.gstatic\.com|cdn\.tailwindcss\.com))/;
self.addEventListener("install", e => { e.waitUntil(caches.open(V).then(c => c.addAll(SHELL)).then(() => self.skipWaiting())); });
self.addEventListener("activate", e => { e.waitUntil(caches.keys().then(ks => Promise.all(ks.filter(k => k !== V).map(k => caches.delete(k)))).then(() => self.clients.claim())); });
function netFirst(req) {
  return fetch(req).then(r => { if (r && r.ok) { const c = r.clone(); caches.open(V).then(x => x.put(req, c)); } return r; })
    .catch(() => caches.match(req, { ignoreSearch: req.mode === "navigate" }).then(m => m || (req.mode === "navigate" ? caches.match("/offline.html") : Response.error())));
}
function staleWhile(req) {
  return caches.match(req).then(m => { const f = fetch(req).then(r => { if (r && (r.ok || r.type === "opaque")) { const c = r.clone(); caches.open(V).then(x => x.put(req, c)); } return r; }).catch(() => m); return m || f; });
}
self.addEventListener("fetch", e => {
  const req = e.request; if (req.method !== "GET") return;
  const u = new URL(req.url);
  if (u.origin === location.origin) {
    if (req.mode === "navigate" || u.pathname.endsWith(".html") || u.pathname.endsWith(".json")) { e.respondWith(netFirst(req)); return; }
    e.respondWith(staleWhile(req)); return;
  }
  if (CDN.test(req.url)) { e.respondWith(staleWhile(req)); return; }
  /* everything else (login, payments, live data) always goes straight to the network */
});
/* ---- deadline reminders ---- */
self.addEventListener("push", e => {
  let d = {}; try { d = e.data ? e.data.json() : {}; } catch (_e) { d = { title: "DocPulsee", body: e.data ? e.data.text() : "" }; }
  e.waitUntil(self.registration.showNotification(d.title || "DocPulsee reminder", {
    body: d.body || "", icon: "/icons/icon-192.png", badge: "/icons/icon-192.png", tag: d.tag || "dp", renotify: true,
    data: { url: d.url || "/?open=dates" }
  }));
});
self.addEventListener("notificationclick", e => {
  e.notification.close(); const url = (e.notification.data && e.notification.data.url) || "/";
  e.waitUntil(self.clients.matchAll({ type: "window", includeUncontrolled: true }).then(cs => { for (const c of cs) { if ("focus" in c) { c.navigate(url).catch(() => {}); return c.focus(); } } return self.clients.openWindow(url); }));
});
