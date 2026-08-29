/* ==========================================================================
   KLx RTO — Service Worker
   Estratégia: cache do "app shell" (HTML/CSS/ícones/manifest) para permitir
   abrir a app offline. NUNCA cacheia pedidos ao Google (login, Sheets API)
   — esses são sempre pedidos à rede; a app trata a falta de rede no próprio
   JavaScript (banner "sem ligação" + última cópia local dos dados, nunca
   escrita de volta na folha a partir daqui).
   ========================================================================== */

const CACHE_VERSION = 'rto-v5.0.0';
const SHELL_CACHE = CACHE_VERSION + '-shell';

const SHELL_ASSETS = [
  './',
  './index.html',
  './styles.css',
  './manifest.webmanifest',
  './icon192.png',
  './icon512.png',
  './shortcut-t.png',
  './shortcut-c.png',
  './logo.png',
  './footer-logo.png',
];

const NUNCA_CACHEAR = [
  'accounts.google.com',
  'sheets.googleapis.com',
  'googleapis.com',
  'apis.google.com',
  'gstatic.com',
];

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(SHELL_CACHE)
      .then((cache) => cache.addAll(SHELL_ASSETS))
      .catch(() => {})
  );
  self.skipWaiting();
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((chaves) =>
      Promise.all(
        chaves
          .filter((chave) => chave.startsWith('rto-') && chave !== SHELL_CACHE)
          .map((chave) => caches.delete(chave))
      )
    )
  );
  self.clients.claim();
});

self.addEventListener('message', (event) => {
  if (event.data === 'skipWaiting') self.skipWaiting();
});

function deveIgnorar(url){
  return NUNCA_CACHEAR.some((dominio) => url.hostname.endsWith(dominio));
}

self.addEventListener('fetch', (event) => {
  const req = event.request;
  if (req.method !== 'GET') return;

  const url = new URL(req.url);
  if (deveIgnorar(url)) return;

  if (req.mode === 'navigate'){
    event.respondWith(
      fetch(req)
        .then((res) => {
          const copia = res.clone();
          caches.open(SHELL_CACHE).then((cache) => cache.put('./index.html', copia)).catch(() => {});
          return res;
        })
        .catch(() => caches.match('./index.html'))
    );
    return;
  }

  if (url.origin === self.location.origin || url.hostname.endsWith('cdnjs.cloudflare.com')){
    event.respondWith(
      caches.match(req).then((cacheado) => {
        const buscar = fetch(req).then((res) => {
          if (res && res.ok){
            const copia = res.clone();
            caches.open(SHELL_CACHE).then((cache) => cache.put(req, copia)).catch(() => {});
          }
          return res;
        }).catch(() => cacheado);
        return cacheado || buscar;
      })
    );
  }
});
