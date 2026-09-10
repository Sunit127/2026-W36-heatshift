const CACHE = 'heatshift-v4';
const ASSETS = [
  './',
  './index.html',
  './styles.css',
  './app.js',
  './logic.js',
  './manifest.webmanifest',
  './assets/heatshift-bg.svg',
];

const APP_ORIGIN = self.location.origin;
const ASSET_PATHS = new Set(
  ASSETS.map((asset) => new URL(asset, self.location.href).pathname),
);
const SHELL_PATHS = new Set([
  new URL('./', self.location.href).pathname,
  new URL('./index.html', self.location.href).pathname,
]);

function isAppRequest(request) {
  const url = new URL(request.url);
  return (
    url.origin === APP_ORIGIN
    && (url.protocol === 'http:' || url.protocol === 'https:')
  );
}

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE).then((cache) => cache.addAll(ASSETS)).then(() => {
      self.skipWaiting();
    }),
  );
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(
        keys.filter((key) => key !== CACHE).map((key) => caches.delete(key)),
      ))
      .then(() => self.clients.claim()),
  );
});

self.addEventListener('fetch', (event) => {
  if (event.request.method !== 'GET' || !isAppRequest(event.request)) {
    return;
  }

  const url = new URL(event.request.url);
  const isStaticAsset = ASSET_PATHS.has(url.pathname);
  const isAppNavigation = event.request.mode === 'navigate'
    && SHELL_PATHS.has(url.pathname);

  // Keep dynamic/API routes and unrelated same-origin paths out of this cache.
  if (!isStaticAsset && !isAppNavigation) {
    return;
  }

  event.respondWith(
    caches.match(event.request).then((cached) => {
      if (cached) {
        return cached;
      }

      return fetch(event.request).then((response) => {
        if (isStaticAsset && response.ok && response.type === 'basic') {
          caches.open(CACHE)
            .then((cache) => cache.put(event.request, response.clone()))
            .catch(() => {});
        }
        return response;
      }).catch(() => (
        isAppNavigation
          ? caches.match(new URL('./index.html', self.location.href).pathname)
          : Response.error()
      ));
    }),
  );
});
