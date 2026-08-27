/**
 * firebase-messaging-sw.js
 * ÚNICO service worker da app — faz DUAS coisas:
 *   1. Cache da app shell (funcionamento offline / instalação PWA)
 *   2. Receção de notificações push em segundo plano (Firebase Cloud Messaging)
 *
 * Tem de ficar neste ficheiro/nome (a Firebase SDK procura-o por convenção
 * quando getToken() é chamado sem indicar explicitamente o registration).
 * Não voltar a criar um segundo service-worker.js separado — dois SW no
 * mesmo scope competem entre si e um acaba por invalidar o outro.
 */

importScripts('https://www.gstatic.com/firebasejs/10.13.0/firebase-app-compat.js');
importScripts('https://www.gstatic.com/firebasejs/10.13.0/firebase-messaging-compat.js');

firebase.initializeApp({
  apiKey: 'AIzaSyDzjj6gCkFYSstqW4Y7tBUGnOKFIap9FlA',
  authDomain: 'bmdpereira-5a8f4.firebaseapp.com',
  projectId: 'bmdpereira-5a8f4',
  storageBucket: 'bmdpereira-5a8f4.firebasestorage.app',
  messagingSenderId: '951047052830',
  appId: '1:951047052830:web:921d360204b7155d80d80f'
});

const messaging = firebase.messaging();

// ---------------------------------------------------------------
// PARTE 1 — Cache da app shell
// ---------------------------------------------------------------
const CACHE_NAME = 'tarefas-casa-v2';
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

      return cached || fetchPromise;
    })
  );
});

// ---------------------------------------------------------------
// PARTE 2 — Notificações push (Firebase Cloud Messaging)
// ---------------------------------------------------------------
messaging.onBackgroundMessage((payload) => {
  const titulo = payload.notification?.title || 'Tarefas de Casa';
  const corpo = payload.notification?.body || '';

  self.registration.showNotification(titulo, {
    body: corpo,
    icon: './icon-192.png',
    badge: './icon-192.png',
    data: payload.fcmOptions?.link || './'
  });
});

self.addEventListener('notificationclick', (event) => {
  event.notification.close();
  const url = event.notification.data || './';

  event.waitUntil(
    clients.matchAll({ type: 'window', includeUncontrolled: true }).then((windowClients) => {
      for (const client of windowClients) {
        if (client.url.includes('/tarefas/') && 'focus' in client) {
          return client.focus();
        }
      }
      if (clients.openWindow) {
        return clients.openWindow(url);
      }
    })
  );
});
