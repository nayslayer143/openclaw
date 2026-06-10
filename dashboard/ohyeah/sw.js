/* OH YEAH™ service worker — installable + offline, but never stale.
 * navigation + CSS/JS: network-first (always fresh when online, cache fallback offline).
 * images/icons/manifest: cache-first (instant; rarely change + are URL-versioned when they do).
 * Asset URLs are also query-versioned (styles.css?v=N) so updates bypass every cache layer.
 * Bump CACHE to evict the offline copies on a release. */
const CACHE = 'ohyeah-v10';
const SHELL = [
  '/', '/index.html', '/manifest.json', '/assets/logo.png',
  '/icons/icon-192.png', '/icons/icon-512.png', '/icons/apple-touch-icon.png',
];

self.addEventListener('install', (e) => {
  e.waitUntil(
    caches.open(CACHE)
      .then((c) => c.addAll(SHELL))
      .then(() => self.skipWaiting())
      .catch(() => self.skipWaiting())
  );
});

self.addEventListener('activate', (e) => {
  e.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

function networkFirst(req, fallbackKey) {
  return fetch(req)
    .then((resp) => {
      if (resp && resp.ok && resp.type === 'basic') {
        const copy = resp.clone();
        caches.open(CACHE).then((c) => c.put(fallbackKey || req, copy));
      }
      return resp;
    })
    .catch(() => caches.match(fallbackKey || req).then((r) => r || (fallbackKey ? caches.match('/index.html') : undefined)));
}

self.addEventListener('fetch', (e) => {
  const req = e.request;
  if (req.method !== 'GET') return;
  const url = new URL(req.url);
  const path = url.pathname;

  // HTML navigations — always try the network so updates show
  if (req.mode === 'navigate') { e.respondWith(networkFirst(req, '/')); return; }

  // CSS / JS — network-first so a deploy is never masked by a cached asset
  if (url.origin === location.origin && (path.endsWith('.css') || path.endsWith('.js'))) {
    e.respondWith(networkFirst(req)); return;
  }

  // everything else (images, icons, manifest, fonts) — cache-first
  e.respondWith(
    caches.match(req).then((cached) => cached || fetch(req).then((resp) => {
      if (resp.ok && resp.type === 'basic') {
        const copy = resp.clone();
        caches.open(CACHE).then((c) => c.put(req, copy));
      }
      return resp;
    }))
  );
});
