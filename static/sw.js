// Define a new cache name to ensure updates are applied
const CACHE_NAME = 'goldshop-cache-v3'; // Incremented cache version

// List of static assets and core pages to cache during installation
const urlsToCache = [
  '/', // The root page (index)
  '/dashboard', // Explicitly cache the start_url for offline access
  '/login', // Essential for re-authentication offline
  '/static/style.css',
  '/static/images/icon-192x192.png',
  '/static/images/icon-512x512.png',
  '/static/images/icon-maskable-192x192.png',
  '/static/sw.js', // Cache the service worker itself
  '/offline.html', // A dedicated offline fallback page

  // Add other critical static assets here (e.g., any custom JS files, fonts)
  // Example: '/static/main.js',
  // Example: '/static/fonts/inter-v12-latin-regular.woff2',
];

// Event listener for the 'install' event of the service worker
self.addEventListener('install', (event) => {
  console.log('[Service Worker] Installing...');
  event.waitUntil(
    caches.open(CACHE_NAME) // Open the new cache
      .then((cache) => {
        console.log('[Service Worker] Caching essential assets:', urlsToCache);
        // Ensure all URLs are prefixed with the correct path if your app is not at the root
        const cachePromises = urlsToCache.map(url => {
          // url_for is not available in service worker, use absolute paths
          return cache.add(url).catch(error => {
            console.warn(`[Service Worker] Failed to cache ${url}:`, error);
          });
        });
        return Promise.all(cachePromises);
      })
      .catch((error) => {
        console.error('[Service Worker] Failed to cache during install:', error);
      })
  );
});

// Event listener for the 'fetch' event to serve cached content or fetch from network
self.addEventListener('fetch', (event) => {
  // Check if this is a navigation request (e.g., visiting a new page) for an HTML document
  const isHtmlNavigation = event.request.mode === 'navigate' ||
                           (event.request.method === 'GET' && event.request.headers.get('accept').includes('text/html'));

  event.respondWith(
    caches.match(event.request) // Try to match the request in the cache first
      .then((cachedResponse) => {
        // If a response is found in the cache, return it immediately (cache-first for static assets)
        if (cachedResponse) {
          console.log(`[Service Worker] Serving from cache: ${event.request.url}`);
          return cachedResponse;
        }

        // If not found in cache, proceed to network
        return fetch(event.request)
          .then((networkResponse) => {
            // Check if we received a valid response
            if (!networkResponse || networkResponse.status !== 200 || networkResponse.type !== 'basic') {
              // For non-200 responses, just return them.
              // For navigation requests, this is where you might show an offline page
              if (isHtmlNavigation) {
                console.log(`[Service Worker] Network failed or invalid response for ${event.request.url}, falling back to offline page.`);
                return caches.match('/offline.html');
              }
              return networkResponse;
            }

            // IMPORTANT: Clone the response. A response is a stream
            // and can only be consumed once. We consume it once to cache it,
            // and once for the browser.
            const responseToCache = networkResponse.clone();

            caches.open(CACHE_NAME)
              .then((cache) => {
                // Only cache GET requests and avoid caching dynamic or API routes
                if (event.request.method === 'GET' && !event.request.url.includes('/api/')) {
                    console.log(`[Service Worker] Caching new resource: ${event.request.url}`);
                    cache.put(event.request, responseToCache);
                }
              });

            return networkResponse;
          })
          .catch((error) => {
            console.error(`[Service Worker] Fetch failed for ${event.request.url}:`, error);
            // If fetch fails and it's an HTML navigation request, serve the offline page
            if (isHtmlNavigation) {
              console.log(`[Service Worker] Network failed for ${event.request.url}, falling back to offline page.`);
              return caches.match('/offline.html'); // Fallback to offline page
            }
            // For other types of requests (images, scripts), if fetch fails, just throw the error
            throw error;
          });
      })
  );
});

// Event listener for 'activate' event to clean up old caches
self.addEventListener('activate', (event) => {
  console.log('[Service Worker] Activating...');
  const cacheWhitelist = [CACHE_NAME]; // Only keep the current cache version
  event.waitUntil(
    caches.keys().then((cacheNames) => {
      return Promise.all(
        cacheNames.map((cacheName) => {
          if (cacheWhitelist.indexOf(cacheName) === -1) {
            console.log('[Service Worker] Deleting old cache:', cacheName);
            return caches.delete(cacheName); // Delete old caches
          }
        })
      );
    })
  );
  // Ensure the service worker takes control of the page immediately
  return self.clients.claim();
});
