#!/usr/bin/env node
/**
 * MapLibre v6 is ESM-only and loads its tile worker from a separate file that it
 * resolves against `import.meta.url`. Metro does not emit that file, so the
 * worker 404s at runtime and the map renders an empty canvas with no error that
 * points at the cause.
 *
 * The fix is to serve the worker ourselves out of `public/`, which Expo copies
 * verbatim into the web build, and point MapLibre at it with `setWorkerUrl()`.
 *
 * This script copies the worker from node_modules on every install and before
 * every web start/build, so it cannot drift out of sync with the installed
 * MapLibre version. Do not commit-and-forget a hand-copied worker instead — a
 * stale one fails in ways that look like tile-server problems.
 */
import { copyFileSync, mkdirSync, existsSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const root = join(dirname(fileURLToPath(import.meta.url)), '..');
const distDir = join(root, 'node_modules/maplibre-gl/dist');
const destDir = join(root, 'public');

// The worker itself does `import ... from "./maplibre-gl-shared.mjs"`, so the
// shared chunk has to sit next to it or the worker dies on its first line.
const files = ['maplibre-gl-worker.mjs', 'maplibre-gl-shared.mjs'];

mkdirSync(destDir, { recursive: true });

for (const name of files) {
  const src = join(distDir, name);
  if (!existsSync(src)) {
    console.warn('[maplibre] %s not found — is maplibre-gl installed?', name);
    process.exit(0);
  }
  copyFileSync(src, join(destDir, name));
}

console.log('[maplibre] synced to public/: %s', files.join(', '));
