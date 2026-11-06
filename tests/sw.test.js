import test from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";

const serviceWorker = await readFile(new URL("../sw.js", import.meta.url), "utf8");

test("service worker refreshes the scoped app shell online and falls back offline", () => {
  assert.match(serviceWorker, /self\.location\.origin/);
  assert.match(serviceWorker, /response\.ok/);
  assert.match(serviceWorker, /response\.type === ['"]basic['"]/);
  assert.match(serviceWorker, /event\.request\.mode === ['"]navigate['"]/);
  assert.match(serviceWorker, /Response\.error\(\)/);
  assert.match(serviceWorker, /dynamic\/API routes/);
  assert.match(serviceWorker, /CACHE_PREFIX}v6/);

  const networkAttempt = serviceWorker.indexOf("await fetch(event.request)");
  const cacheFallback = serviceWorker.indexOf("await caches.match(cacheKey)");
  assert.ok(networkAttempt >= 0);
  assert.ok(cacheFallback > networkAttempt);
});

test("service worker cleanup preserves unrelated origin caches", () => {
  assert.match(
    serviceWorker,
    /key\.startsWith\(CACHE_PREFIX\) && key !== CACHE/,
  );
});
