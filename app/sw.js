/* Offline shell.
   Data (the plan) is network-first, so a Friday regeneration lands as soon as
   there's signal. The app files are stale-while-revalidate: the cached copy is
   served immediately, and a fresh one is fetched in the background for next
   launch. Cache-first would be faster to write but would pin an installed app
   to whatever version it first saw — pushed fixes would never arrive. */

const CACHE = "prep";
const SHELL = [
  "./", "./index.html", "./styles.css", "./app.js",
  "./manifest.webmanifest", "./data/plan.js",
  "./icons/icon-192.png", "./icons/icon-512.png", "./icons/apple-touch-icon.png",
];

const isData = url => /\/data\/plan\.(json|js)$/.test(new URL(url).pathname);

self.addEventListener("install", e => {
  e.waitUntil(caches.open(CACHE)
    .then(c => c.addAll(SHELL))
    .then(() => self.skipWaiting()));
});

self.addEventListener("activate", e => {
  e.waitUntil(caches.keys()
    .then(keys => Promise.all(keys.filter(k => k !== CACHE).map(k => caches.delete(k))))
    .then(() => self.clients.claim()));
});

self.addEventListener("fetch", e => {
  const { request } = e;
  if (request.method !== "GET") return;
  if (new URL(request.url).origin !== self.location.origin) return;

  // Network-first for the plan: this week's meals matter more than speed.
  if (isData(request.url)) {
    e.respondWith(
      fetch(request)
        .then(res => {
          if (res.ok) caches.open(CACHE).then(c => c.put(request, res.clone()));
          return res;
        })
        .catch(() => caches.match(request))
    );
    return;
  }

  // Stale-while-revalidate for everything else.
  e.respondWith(
    caches.match(request).then(hit => {
      const fresh = fetch(request).then(res => {
        if (res.ok && res.type === "basic") {
          caches.open(CACHE).then(c => c.put(request, res.clone()));
        }
        return res;
      }).catch(() => hit);
      return hit || fresh;
    })
  );
});
