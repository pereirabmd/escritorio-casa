/**
 * sw.js
 * Único service worker da app — só cache da app shell (funcionamento
 * offline / instalação PWA). Substitui o firebase-messaging-sw.js: a
 * entrega de notificações deixou de passar pelo browser (é a app ntfy no
 * telemóvel, subscrita ao tópico partilhado "tarefas" — ver PLANO em
 * tarefas/pi/), por isso já não há nada de push/Firebase aqui.
 *
 * Não voltar a criar um segundo service worker separado — dois SW no mesmo
 * scope competem entre si e um acaba por invalidar o outro.
 */

const CACHE_NAME = 'tarefas-casa-v17';
const APP_SHELL = [
  './',
  './index.html',
  './styles.css',
  './manifest.json',
  './icon-192.png',
  './icon-512.png',
  './about-logo.png'
];

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME)
      .then((cache) => cache.addAll(APP_SHELL))
      .catch((e) => console.warn('Pré-cache do app shell falhou parcialmente:', e))
    // Uma falha ao pré-cachear (ex: blip de rede num único ficheiro) não deve
    // impedir a instalação do service worker — o fetch handler cache-first
    // continua a cachear cada recurso normalmente à medida que é pedido.
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
  // Nunca intercetar pedidos a outros domínios (Google Sheets API, ntfy-api,
  // CDNs, etc.) — só cache da própria app, mesma-origem.
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

      return cached || fetchPromise;
    })
  );
});
