/**
 * service-worker.js
 * Cache da app shell (funcionamento offline / instalação PWA).
 * Não tem nada a ver com notificações — isso é o firebase-messaging-sw.js.
 */

const CACHE_NAME = 'tarefas-casa-v1';
const APP_SHELL = [
  './',
  './index.html',
  './manifest.json',
  './icon-192.png',
  './icon-512.png'
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
        names
          .filter((name) => name !== CACHE_NAME)
          .map((name) => caches.delete(name))
      )
    )
  );
  self.clients.claim();
});

self.addEventListener('fetch', (event) => {
  // Nunca intercetar pedidos a outros domínios (Google Sheets API, FCM,
  // CDNs, etc.) — só cache da própria app, mesmo-origem.
  if (new URL(event.request.url).origin !== self.location.origin) {
    return;
  }

  if (event.request.method !== 'GET') {
    return;
  }

  event.respondWith(
    caches.match(event.request).then((cached) => {
      const fetchPromise = fetch(event.request)
        .then((response) => {
          if (response && response.status === 200) {
            const clone = response.clone();
            caches.open(CACHE_NAME).then((cache) => cache.put(event.request, clone));
          }
          return response;
        })
        .catch(() => cached);

      // Cache-first para resposta rápida offline, atualiza em segundo plano.
      return cached || fetchPromise;
    })
  );
});
