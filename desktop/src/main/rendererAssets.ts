import {readFileSync, realpathSync, statSync} from 'node:fs';
import path from 'node:path';

export const CONTENT_SECURITY_POLICY = [
  "default-src 'self'",
  "script-src 'self'",
  "style-src 'self'",
  "img-src 'self' data:",
  "font-src 'self'",
  "connect-src 'none'",
  "object-src 'none'",
  "frame-src 'none'",
  "worker-src 'none'",
  "base-uri 'none'",
  "form-action 'none'"
].join('; ');

function isAssetPath(value: unknown): value is string {
  return typeof value === 'string' && value.startsWith('assets/') &&
    !/[\\%?#:\x00-\x1f\x7f]/.test(value) && !value.includes('//') &&
    !/(?:^|\/)\.{1,2}(?:\/|$)/.test(value) && !value.endsWith('/');
}

/** Vite's manifest, not directory enumeration, is the resource allowlist. */
export function rendererManifestAssets(manifest: unknown): ReadonlySet<string> {
  if (!manifest || typeof manifest !== 'object' || Array.isArray(manifest)) {
    throw new Error('INVALID_RENDERER_MANIFEST');
  }
  const assets = new Set(['index.html']);
  let hasEntry = false;
  for (const item of Object.values(manifest)) {
    if (!item || typeof item !== 'object' || Array.isArray(item)) {
      throw new Error('INVALID_RENDERER_MANIFEST_ENTRY');
    }
    const entry = item as Record<string, unknown>;
    if (!isAssetPath(entry.file)) throw new Error('INVALID_RENDERER_ASSET');
    assets.add(entry.file);
    if (entry.isEntry === true && /\.m?js$/.test(entry.file)) hasEntry = true;
    for (const key of ['css', 'assets']) {
      const values = entry[key];
      if (values === undefined) continue;
      if (!Array.isArray(values) || !values.every(isAssetPath)) {
        throw new Error('INVALID_RENDERER_ASSET');
      }
      for (const value of values) assets.add(value);
    }
  }
  if (!hasEntry) throw new Error('MISSING_RENDERER_ENTRY');
  return assets;
}

export function loadRendererAssets(rendererRoot: string): ReadonlySet<string> {
  const assets = rendererManifestAssets(JSON.parse(
    readFileSync(path.join(rendererRoot, '.vite', 'manifest.json'), 'utf8')
  ));
  const root = realpathSync(rendererRoot);
  for (const asset of assets) {
    const file = realpathSync(path.join(root, ...asset.split('/')));
    if (!file.startsWith(root + path.sep) || !statSync(file).isFile()) {
      throw new Error('INVALID_RENDERER_RESOURCE');
    }
  }
  return assets;
}
