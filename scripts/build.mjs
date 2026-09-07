import { cp, mkdir, rm } from "node:fs/promises";

const files = [
  "index.html",
  "styles.css",
  "app.js",
  "logic.js",
  "manifest.webmanifest",
  "sw.js",
  "assets",
];

await rm("dist", { recursive: true, force: true });
await mkdir("dist");

await Promise.all(
  files.map((file) =>
    file === "assets"
      ? cp(file, `dist/${file}`, { recursive: true })
      : cp(file, `dist/${file}`),
  ),
);

console.log(`Built ${files.length} items in dist/`);
