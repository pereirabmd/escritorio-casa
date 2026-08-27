/**
 * firebase-messaging-sw.js
 * Recebe as notificações push quando a app está fechada ou em segundo plano.
 * Tem de ficar neste ficheiro (a Firebase SDK procura-o por convenção).
 *
 * ⚠️ Preenche a config abaixo com os valores do teu projeto Firebase:
 * Firebase Console → ⚙️ Definições do projeto → aba "Geral" →
 * secção "As suas apps" → se ainda não tiveres uma app Web registada,
 * cria uma ("</> " Adicionar app") → copia o objeto firebaseConfig.
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

// Notificação em segundo plano (app fechada ou noutro separador).
// Se o payload já vier com "notification", o browser mostra-a
// automaticamente; este handler é sobretudo para personalizar
// ícone/ações ou tratar payloads "data-only".
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

// Ao tocar na notificação, abre (ou foca) a app.
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
