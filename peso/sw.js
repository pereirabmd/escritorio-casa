/* ==========================================================================
   Peso — Service Worker
   Estratégia: cache do "app shell" (HTML/CSS/ícones/manifest) para permitir
   abrir a app offline. NUNCA cacheia pedidos ao Google (login, Sheets API)
   — esses são sempre pedidos à rede, e a app trata a falta de rede no
   próprio JavaScript (banner "sem ligação" + dados da última sincronização
   guardados localmente, nunca escritos por aqui).
   ========================================================================== */

const CACHE_VERSION = 'peso-v4.0.0-r1';
const SHELL_CACHE = CACHE_VERSION + '-shell';

const SHELL_ASSETS = [
  './',
  './index.html',
  './styles.css',
  './manifest.webmanifest',
  './pesoicon192.png',
  './pesoicon512.png',
];

// Domínios que nunca devem ser intercetados/cacheados: autenticação e dados
// reais do utilizador vivem exclusivamente no Google, nunca neste cache.
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
      .catch(() => {}) // uma falha ao pré-cachear não deve impedir a instalação
  );
  self.skipWaiting();
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((chaves) =>
      Promise.all(
        chaves
          .filter((chave) => chave.startsWith('peso-') && chave !== SHELL_CACHE)
          .map((chave) => caches.delete(chave))
      )
    )
  );
  self.clients.claim();
});

// Permite que a página force a ativação imediata de uma nova versão
// (usado pelo banner "nova versão disponível" no index.html).
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
  if (deveIgnorar(url)) return; // deixa passar direto para a rede, sem cache

  // Navegação (abrir/recarregar a app): tenta a rede primeiro para obter
  // sempre a versão mais recente; se falhar (offline), usa o shell em cache.
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

  // Restantes recursos same-origin (CSS, ícones, manifest, fontes/libs de CDN
  // permitidas): cache-first com atualização em segundo plano.
  if (url.origin === self.location.origin || url.hostname.endsWith('cdnjs.cloudflare.com') || url.hostname.endsWith('fonts.googleapis.com') || url.hostname.endsWith('fonts.gstatic.com')){
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
