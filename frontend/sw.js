/* TinNhanh AI service worker.
 *
 * Strategy:
 * - Pre-cache the small static shell (HTML/CSS/JS/manifest/icon) so the app
 *   opens instantly and works offline at the shell level.
 * - For navigation requests we serve the cached shell and let the JS layer
 *   re-fetch /api/dashboard, which keeps the home screen launchable offline.
 * - API requests (/api/*) use network-first, falling back to a stale cache
 *   when the device is offline. Only successful 2xx responses are cached.
 * - Anything else (e.g. fonts, lucide CDN) falls through to the network.
 */

const SW_VERSION = "tinnhanh-v16";
const SHELL_CACHE = `shell-${SW_VERSION}`;
const API_CACHE = `api-${SW_VERSION}`;

const SHELL_ASSETS = [
  "/",
  "/index.html",
  "/styles.css",
  "/app.js",
  "/manifest.webmanifest",
  "/icons/icon.svg",
  "/icons/icon-192.png",
  "/icons/icon-512.png",
];

// Cross-origin assets worth keeping for offline (icon font library, fonts).
const CDN_PREFIXES = [
  "https://unpkg.com/lucide",
  "https://fonts.googleapis.com",
  "https://fonts.gstatic.com",
];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches
      .open(SHELL_CACHE)
      .then((cache) => cache.addAll(SHELL_ASSETS))
      .then(() => self.skipWaiting()),
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((keys) =>
        Promise.all(
          keys
            .filter((key) => key !== SHELL_CACHE && key !== API_CACHE)
            .map((key) => caches.delete(key)),
        ),
      )
      .then(() => self.clients.claim()),
  );
});

function isApiRequest(url) {
  return url.pathname.startsWith("/api/");
}

function isCacheableCdn(url) {
  return CDN_PREFIXES.some((prefix) => url.href.startsWith(prefix));
}

// Stale-while-revalidate for CDN assets: serve cached copy instantly (works
// offline), refresh in the background when online.
async function staleWhileRevalidate(request) {
  const cache = await caches.open(SHELL_CACHE);
  const cached = await cache.match(request);
  const fetchPromise = fetch(request)
    .then((response) => {
      if (response && (response.ok || response.type === "opaque")) {
        cache.put(request, response.clone());
      }
      return response;
    })
    .catch(() => cached);
  return cached || fetchPromise;
}

async function networkFirstApi(request) {
  const cache = await caches.open(API_CACHE);
  try {
    const response = await fetch(request);
    if (response && response.ok) {
      cache.put(request, response.clone());
    }
    return response;
  } catch (error) {
    const cached = await cache.match(request);
    if (cached) return cached;
    return new Response(
      JSON.stringify({ error: "offline", message: "Bạn đang offline." }),
      { status: 503, headers: { "Content-Type": "application/json" } },
    );
  }
}

async function shellFirst(request) {
  const cache = await caches.open(SHELL_CACHE);
  const cached = await cache.match(request, { ignoreSearch: false });
  if (cached) return cached;
  try {
    const response = await fetch(request);
    if (response && response.ok && new URL(request.url).origin === self.location.origin) {
      cache.put(request, response.clone());
    }
    return response;
  } catch (error) {
    // For navigations, return the cached index as a last resort.
    if (request.mode === "navigate") {
      const indexCached = await cache.match("/index.html");
      if (indexCached) return indexCached;
    }
    throw error;
  }
}

self.addEventListener("fetch", (event) => {
  const request = event.request;
  if (request.method !== "GET") return;

  const url = new URL(request.url);
  if (url.origin !== self.location.origin) {
    // Cache select CDN assets (lucide, fonts) so icons render offline.
    if (isCacheableCdn(url)) {
      event.respondWith(staleWhileRevalidate(request));
    }
    return; // other cross-origin requests pass through untouched
  }

  if (isApiRequest(url)) {
    event.respondWith(networkFirstApi(request));
    return;
  }

  event.respondWith(shellFirst(request));
});

self.addEventListener("message", (event) => {
  if (event.data === "skipWaiting") self.skipWaiting();
});
