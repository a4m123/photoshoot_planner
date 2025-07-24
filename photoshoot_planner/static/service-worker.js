const CACHE_NAME = 'photoshoot-cache-v2';
const OFFLINE_URL = '/offline.html';

const STATIC_ASSETS = [
  '/',
  '/offline.html',
  '/static/css/style.css',
  '/static/js/main.js',
  '/static/icons/icon-192.png',
  '/static/icons/icon-512.png',
];

// Установка service worker и кэширование
self.addEventListener('install', event => {
  event.waitUntil(
    caches.open(CACHE_NAME)
      .then(cache => cache.addAll(STATIC_ASSETS))
      .then(() => self.skipWaiting())
  );
});

// Активация и удаление старого кэша
self.addEventListener('activate', event => {
  event.waitUntil(
    caches.keys().then(keys =>
      Promise.all(keys.filter(k => k !== CACHE_NAME).map(k => caches.delete(k)))
    )
  );
  self.clients.claim();
});

// Основная логика перехвата fetch
self.addEventListener('fetch', event => {
  const req = event.request;

  // Только GET
  if (req.method !== 'GET') return;

  // Пробуем из сети → если не получится — из кэша → fallback
  event.respondWith(
    fetch(req)
      .then(networkResp => {
        // Кэшируем GET-запросы на HTML и изображения
        if (req.url.startsWith(location.origin)) {
          caches.open(CACHE_NAME).then(cache => {
            cache.put(req, networkResp.clone());
          });
        }
        return networkResp;
      })
      .catch(() => caches.match(req).then(res => res || caches.match(OFFLINE_URL)))
  );
});
