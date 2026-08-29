var CACHE = 'ciclismo-shell-v23';
var SHELL = ['./', './index.html', './manifest.json', './icon-192.png', './icon-512.png', './icon-watermark.png'];

self.addEventListener('install', function(e){
  self.skipWaiting();
  e.waitUntil(caches.open(CACHE).then(function(cache){ return cache.addAll(SHELL); }));
});

self.addEventListener('activate', function(e){
  e.waitUntil(
    caches.keys().then(function(keys){
      return Promise.all(keys.filter(function(k){ return k !== CACHE; }).map(function(k){ return caches.delete(k); }));
    }).then(function(){ return self.clients.claim(); })
  );
});

self.addEventListener('message', function(e){
  if (e.data === 'skipWaiting') self.skipWaiting();
});

self.addEventListener('fetch', function(e){
  if (e.request.method !== 'GET') return;

  // Só a app shell (mesma origem) passa por cache. Pedidos ao Drive, ao
  // Sheets (peso) e à previsão do tempo têm sempre dados privados ou
  // mutáveis — nunca devem ser guardados nem servidos daqui, só pela
  // própria página (que já tem as suas próprias caches em localStorage).
  var url = new URL(e.request.url);
  if (url.origin !== self.location.origin) return;

  e.respondWith(
    caches.match(e.request).then(function(cached){
      var network = fetch(e.request).then(function(res){
        if (res && res.status === 200){
          var copy = res.clone();
          caches.open(CACHE).then(function(cache){ cache.put(e.request, copy); });
        }
        return res;
      }).catch(function(){ return cached; });
      return cached || network;
    })
  );
});
