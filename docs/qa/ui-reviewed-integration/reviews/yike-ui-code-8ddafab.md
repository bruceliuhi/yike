# Independent code review — renderer runtime fix

- Candidate: `8ddafab6cc4cea21c244dcf1f052bf04defe8e87`.
- Base: `a31069fead15f395e7b4ec93c9c91e441beea798`.
- Reviewed on: 2026-09-10, Asia/Shanghai.
- Repository: `/Users/bruce/Developer/work/yike-ai-product-design`.
- Verdict: **PASS within the four files below; no P0/P1 or other actionable blocker found.** This is a code review, not independent approval of the complete package or all eight changed files.

## Independent scope

1. `desktop/vite.renderer.config.ts:7-9` — resolve real dependency paths and deduplicate React/React DOM.
2. `desktop/src/renderer/app/main.tsx:1` — bootstrap side-effect import before application/domain imports.
3. `desktop/src/renderer/app/validationRuntime.ts:1-5` — Zod interpreter configuration under the existing strict CSP.
4. `desktop/tests/rendererReactSingleton.test.ts:11-45` — reproducible linked-dependency regression.

The candidate contents in these paths are identical to the independently inspected working tree. The candidate does not change the CSP in `src/main/rendererAssets.ts` or `src/renderer/index.html`, or dependency manifests/lockfile.

I authored `run-packaged-smoke.mjs`, `packaged-smoke-policy.mjs`, `packagedSmoke.test.mjs`, and `packagedSmokePolicy.test.mjs`. Those four files are explicitly **excluded from this independent approval** and require another reviewer's approval.

## Findings and evidence

- Forge's installed Vite plugin supplies `preserveSymlinks: true` as its default and merges user configuration afterward. The candidate's explicit `false` therefore takes effect; `dedupe: ['react', 'react-dom']` covers application and component-library imports. No new alias, network endpoint, permission, or runtime authority is introduced.
- The regression creates an isolated linked dependency tree, including the nested `node_modules` link associated with the observed failure. It first proves that preserved symlink paths emit multiple React production modules, then verifies one module with the actual candidate configuration. It is not a test that merely mirrors a constant.
- **Independently executed:** `npm exec -- vitest run tests/rendererReactSingleton.test.ts` with Node 24.19.0 — **1 file, 1 passed**, tool output `5c2c32`.
- `validationRuntime` executes as the first dependency of the renderer entry. Its Zod dependency is initialized before the call, while application modules that create domain schemas are imported afterward. `jitless: true` uses the library's interpreter; no schema rules are removed and CSP is not loosened.
- **Independent runtime probe:** replaced global `Function` with a throwing counter, imported the actual `validationRuntime.ts`, then checked a strict Zod object. Valid input was accepted, invalid input rejected, and the generated-code counter remained **0** (`4b19d1`). This checks runtime behavior rather than only searching for the configuration text.

## Limits and delivery gate

- This review does not turn any optional/unconnected business service into a working backend.
- The singleton fixture builds and inspects the production module graph; it does not itself prove the complete Electron UI renders.
- The earlier `befacea…` package still failed the stricter smoke with a genuine renderer-level CSP error. It must not inherit a pass from visible workbench rendering. A new archive containing this bootstrap change must pass strict packaged smoke and the main thread's native acceptance before it is the delivery candidate.
- At review time, the new archive rebuild, full-suite results, and final native acceptance are being performed by the main thread. No result for them is claimed here. Windows real-machine acceptance, code signing, and notarization are outside this review.

No source files were changed during this independent review.
