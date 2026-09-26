/* Finanças — Service Worker. Cache do "app shell" para abrir offline.
   NUNCA cacheia o login Google nem a API de dados no Raspberry Pi (dados pessoais). */

const CACHE_VERSION = 'financas-v1.1.0';
const SHELL_CACHE = CACHE_VERSION + '-shell';
const SHELL_ASSETS = ['./', './index.html', './styles.css', './app.js', './manifest.webmanifest', './icon-192.png', './icon-512.png'];
const NUNCA_CACHEAR = ['accounts.google.com', 'googleapis.com', 'apis.google.com', 'gstatic.com', 'duckdns.org'];

self.addEventListener('install', (event) => {
  event.waitUntil(caches.open(SHELL_CACHE).then((c) => c.addAll(SHELL_ASSETS)).catch(() => {}));
  self.skipWaiting();
});

self.addEventListener('activate', (event) => {
  event.waitUntil(caches.keys().then((chaves) => Promise.all(
    chaves.filter((k) => k.startsWith('financas-') && k !== SHELL_CACHE).map((k) => caches.delete(k)))));
  self.clients.claim();
});

self.addEventListener('message', (event) => { if (event.data === 'skipWaiting') self.skipWaiting(); });

self.addEventListener('fetch', (event) => {
  const req = event.request;
  if (req.method !== 'GET') return;
  const url = new URL(req.url);
  if (NUNCA_CACHEAR.some((d) => url.hostname.endsWith(d))) return;

  // Navegação: rede primeiro (versão mais recente); offline usa o shell.
  if (req.mode === 'navigate') {
    event.respondWith(fetch(req).then((res) => {
      const copia = res.clone();
      caches.open(SHELL_CACHE).then((c) => c.put('./index.html', copia)).catch(() => {});
      return res;
    }).catch(() => caches.match('./index.html')));
    return;
  }

  // Restantes recursos permitidos: cache primeiro, atualizando em segundo plano.
  if (url.origin === self.location.origin || url.hostname.endsWith('cdnjs.cloudflare.com')) {
    event.respondWith(caches.match(req).then((cacheado) => {
      const buscar = fetch(req).then((res) => {
        if (res && res.ok) { const copia = res.clone(); caches.open(SHELL_CACHE).then((c) => c.put(req, copia)).catch(() => {}); }
        return res;
      }).catch(() => cacheado);
      return cacheado || buscar;
    }));
  }
});
