import test from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
const app = await readFile(new URL("../app.js", import.meta.url), "utf8");
test("optional sharing targets the validated API", () => {
  assert.match(app, /HEATSHIFT_API_BASE/);
  assert.match(app, /\/api\/v1\/plans/);
  assert.match(app, /JSON\.stringify\(current\)/);
});
