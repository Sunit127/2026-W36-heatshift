import test from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
const app = await readFile(new URL("../app.js", import.meta.url), "utf8");
const index = await readFile(new URL("../index.html", import.meta.url), "utf8");
test("optional sharing targets the validated API", () => {
  assert.match(app, /HEATSHIFT_API_BASE/);
  assert.match(app, /\/api\/v1\/plans/);
  assert.match(app, /JSON\.stringify\(sharePayload\)/);
  assert.match(app, /const sharePayload = \{/);
  assert.doesNotMatch(app, /body: JSON\.stringify\(currentPlan\)/);
});

test('frontend result and error states are keyboard reachable', () => {
  assert.match(index, /aria-describedby="form-error"/);
  assert.match(index, /id="form-error"[^>]*tabindex="-1"/);
  assert.match(index, /id="result-title"[^>]*tabindex="-1"/);
  assert.ok(app.includes("$('#result-title').focus"));
  assert.ok(app.includes('error.focus'));
});
