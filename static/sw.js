// MKOV Visa CRM — Service Worker
//
// IMPORTANT: bump CACHE_NAME on every deploy that changes admin.html
// structurally, so old installed PWAs evict their stale cache. This
// version bump (v1 -> v2) fixes a real bug: /admin was cache-first with
// no versioning, so staff who had the app installed kept seeing an old,
// out-of-date copy of the page no matter how many fixes were deployed
// to the server — they never actually reached the new code.
const CACHE_NAME = 'mkov-crm-v2';
const STATIC_ASSETS = [
  '/static/icon-192.png',
  '/static/icon-512.png',
  '/manifest.json'
];

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => cache.addAll(STATIC_ASSETS))
  );
  self.skipWaiting();
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((names) =>
      Promise.all(
        names.filter((name) => name !== CACHE_NAME).map((name) => caches.delete(name))
      )
    )
  );
  self.clients.claim();
});

self.addEventListener('fetch', (event) => {
  const url = new URL(event.request.url);

  // Never cache API calls — CRM data must always be live
  if (url.pathname.startsWith('/admin/') || url.pathname.startsWith('/auth/') || url.pathname.startsWith('/client/')) {
    event.respondWith(
      fetch(event.request).catch(() => new Response(
        JSON.stringify({ detail: 'You are offline. Please reconnect to continue.' }),
        { status: 503, headers: { 'Content-Type': 'application/json' } }
      ))
    );
    return;
  }

  // The app page itself (/admin, exact path) changes on every deploy —
  // ALWAYS try the network first so staff get the latest code the moment
  // they're online. Only fall back to a cached copy if genuinely offline.
  if (url.pathname === '/admin') {
    event.respondWith(
      fetch(event.request)
        .then((response) => {
          if (response.ok) {
            const clone = response.clone();
            caches.open(CACHE_NAME).then((cache) => cache.put(event.request, clone));
          }
          return response;
        })
        .catch(() => caches.match(event.request))
    );
    return;
  }

  // Static assets (icons, manifest) rarely change — cache-first is fine here
  event.respondWith(
    caches.match(event.request).then((cached) => {
      return cached || fetch(event.request).then((response) => {
        if (response.ok) {
          const clone = response.clone();
          caches.open(CACHE_NAME).then((cache) => cache.put(event.request, clone));
        }
        return response;
      }).catch(() => cached);
    })
  );
});
