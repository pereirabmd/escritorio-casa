// Service worker mínimo — o objetivo principal é satisfazer os requisitos
// de instalabilidade do Chrome (manifest + service worker com "fetch").
// Não pretende funcionar totalmente offline (a app depende de APIs online
// como o Google Sheets, OCR e PDF.js), só torna a aplicação instalável.
//
// IMPORTANTE: só interceta pedidos do mesmo site (este domínio/pasta).
// Pedidos a CDNs externos (Google, jsdelivr, cdnjs, Sheets API, etc.) são
// deixados passar diretamente para o browser tratar — nunca são geridos
// por este service worker. E a resposta nunca fica "vazia": se a rede
// falhar e não houver nada em cache, devolve-se sempre uma resposta válida
// (nunca undefined), para nunca causar ERR_FAILED.

const CACHE_NAME = 'turnos-shell-v2';
const APP_SHELL = [
  './index.html',
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

self.addEventListener('fetch', (event) => {
  const req = event.request;
  if (req.method !== 'GET') return;

  const url = new URL(req.url);
  if (url.origin !== self.location.origin) return; // nunca intercetar CDNs/APIs externas

  event.respondWith(
    fetch(req)
      .then((res) => {
        const copia = res.clone();
        caches.open(CACHE_NAME).then((cache) => cache.put(req, copia)).catch(() => {});
        return res;
      })
      .catch(async () => {
        const emCache = await caches.match(req);
        if (emCache) return emCache;
        // nunca devolver undefined — evita ERR_FAILED quando não há rede nem cache
        return new Response('Sem ligação e sem versão em cache para este pedido.', {
          status: 503,
          statusText: 'Offline',
          headers: { 'Content-Type': 'text/plain; charset=utf-8' }
        });
      })
  );
});
