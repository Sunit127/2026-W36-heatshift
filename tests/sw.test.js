import test from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";

const serviceWorker = await readFile(new URL("../sw.js", import.meta.url), "utf8");

test("service worker only caches the app shell and successful same-origin assets", () => {
  assert.match(serviceWorker, /self\.location\.origin/);
  assert.match(serviceWorker, /response\.ok/);
  assert.match(serviceWorker, /response\.type === ['"]basic['"]/);
  assert.match(serviceWorker, /event\.request\.mode === ['"]navigate['"]/);
  assert.match(serviceWorker, /Response\.error\(\)/);
  assert.match(serviceWorker, /dynamic\/API routes/);
});
