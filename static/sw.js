// MKOV Visa CRM — Service Worker
// Caches the app shell for offline/fast reloads. Cache version bumps
// automatically invalidate old caches on the next deploy.
const CACHE_NAME = 'mkov-crm-v1';
const APP_SHELL = [
  '/admin',
  '/static/icon-192.png',
  '/static/icon-512.png',
  '/manifest.json'
];

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => cache.addAll(APP_SHELL))
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

// Network-first for API calls (always want fresh data), cache-first for the app shell
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

  // Cache-first for the app shell (HTML, icons, manifest)
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
