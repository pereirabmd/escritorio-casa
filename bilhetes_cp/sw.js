/* Service worker do Bilhetes CP — Workbox (PLANO_FINAL.md 3.7).
 *
 * - App shell em precache (abre offline e instantaneamente).
 * - Configuração não-secreta (estações): stale-while-revalidate, para poder
 *   mudar sem nova versão do service worker.
 * - Tipos de letra: stale-while-revalidate (são públicos).
 * - TUDO o resto (Google Sheets, Google Identity, API da CP, ntfy) NÃO é
 *   intercetado: vai sempre à rede, porque são dados privados ou mutáveis
 *   (network-only por omissão — nenhuma rota registada).
 *
 * Sempre que index.html, manifest ou ícones mudarem, subir VERSION.
 */
importScripts('https://storage.googleapis.com/workbox-cdn/releases/7.3.0/workbox-sw.js');

const VERSION = 'v1.1.2';

workbox.core.setCacheNameDetails({ prefix: 'bilhetes-cp', suffix: VERSION });
workbox.core.clientsClaim();

workbox.precaching.precacheAndRoute([
  { url: 'index.html', revision: VERSION },
  { url: 'manifest.webmanifest', revision: VERSION },
  { url: 'assets/icon-192.png', revision: VERSION },
  { url: 'assets/icon-512.png', revision: VERSION },
  { url: 'assets/icon-maskable-512.png', revision: VERSION },
  { url: 'assets/apple-touch-icon.png', revision: VERSION },
  { url: 'assets/favicon.png', revision: VERSION },
], { ignoreURLParametersMatching: [/^semana$/, /^utm_/] });

// Abrir a app (start_url './' ou './?semana=1') serve sempre o shell em cache.
workbox.routing.registerRoute(
  new workbox.routing.NavigationRoute(workbox.precaching.createHandlerBoundToURL('index.html'))
);

workbox.routing.registerRoute(
  ({ url }) => url.origin === self.location.origin && url.pathname.endsWith('/config/app_config.example.json'),
  new workbox.strategies.StaleWhileRevalidate({ cacheName: 'bilhetes-cp-config' })
);

workbox.routing.registerRoute(
  ({ url }) => url.origin === 'https://fonts.googleapis.com' || url.origin === 'https://fonts.gstatic.com',
  new workbox.strategies.StaleWhileRevalidate({
    cacheName: 'bilhetes-cp-fonts',
    plugins: [new workbox.expiration.ExpirationPlugin({ maxEntries: 20, maxAgeSeconds: 365 * 24 * 3600 })],
  })
);

// A página pede para ativar já a nova versão quando o utilizador toca em "Atualizar".
self.addEventListener('message', (e) => {
  if (e.data === 'skipWaiting') self.skipWaiting();
});
