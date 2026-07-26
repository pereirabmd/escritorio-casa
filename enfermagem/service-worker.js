// Service worker mínimo — o objetivo principal é satisfazer os requisitos
// de instalabilidade do Chrome (manifest + service worker com "fetch").
// Não pretende funcionar totalmente offline (a app depende de APIs online
// como o Google Sheets, OCR e PDF.js), só torna a aplicação instalável.

const CACHE_NAME = 'turnos-shell-v1';
const APP_SHELL = [
  './index.html',
  './manifest.json',
  './icon-192.png',
  './icon-512.png'
];

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => cache.addAll(APP_SHELL)).catch(() => {})
  );
  self.skipWaiting();
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((k) => k !== CACHE_NAME).map((k) => caches.delete(k)))
    )
  );
  self.clients.claim();
});

// Estratégia: tenta a rede primeiro (para dados sempre atualizados);
// se falhar (sem rede), tenta servir do cache do "app shell".
self.addEventListener('fetch', (event) => {
  if (event.request.method !== 'GET') return;
  event.respondWith(
    fetch(event.request).catch(() => caches.match(event.request))
  );
});
