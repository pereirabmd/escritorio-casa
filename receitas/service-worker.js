const CACHE_NAME = 'receitas-shell-v2';
const SHELL_FILES = [
  './',
  './index.html',
  './icon-192.png',
  './icon-512.png'
];

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => cache.addAll(SHELL_FILES)).catch(() => {})
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

  // Only intercept same-origin GET requests. Never touch Google APIs,
  // OAuth, or any cross-origin call — those must always hit the network.
  if (url.origin !== self.location.origin || event.request.method !== 'GET') {
    return;
  }

  // Cache-first com atualização em segundo plano: o index.html embute
  // imagens em base64 e pode passar de 600 KB — esperar sempre pela rede
  // antes de mostrar algo (como acontecia antes) torna o arranque lento
  // mesmo quando já existe uma cópia local válida. Uma cópia nova só
  // substitui a cache para a PRÓXIMA visita (ver aviso "nova versão
  // disponível" no index.html).
  event.respondWith(
    caches.match(event.request).then((cached) => {
      const network = fetch(event.request).then((response) => {
        if (response && response.ok) {
          const copy = response.clone();
          caches.open(CACHE_NAME).then((cache) => cache.put(event.request, copy)).catch(() => {});
        }
        return response;
      }).catch(() => cached);
      return cached || network;
    })
  );
});
