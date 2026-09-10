# Task 1 report — desktop three-platform foreground collection

## Scope implemented

- Replaced the same-release native capability payload with `AVAILABLE.bindings` (1–3), enforcing unique platforms, one common mode, native account validation, and rejecting legacy XHS mode on video platforms.
- Generalized protected collection-account resolution to XIAOHONGSHU, DOUYIN, and BILIBILI using the existing native platform/account validators, original VERIFY receipt, exact profile scope, and exact current connection row.
- Capability discovery performs one authenticated current-row fetch, reads exactly the three protected platform profile slots, and attaches only independently verified available bindings; one missing platform does not suppress another.
- START remains single-target and preserves the existing journal/session/cancel/recovery flow. It now checks the selected target against server support mode and the exact confirmed strategy platform, then passes that target's private profile and expected public account to the driver.
- The Python driver keeps the existing host wire field `expected_account_public_id`, while validating it according to the selected native platform.
- Renderer capability attachment now maps xhs/douyin/bilibili to their native platform values and enables only an exact device/connection/account/version match. The existing single-platform, once, search-only boundary remains.

## Focused verification

- RED observed first: 6 expected failures across account binding, controller capability/start, and renderer attachment.
- `npm test -- --run tests/collectionAccountBinding.test.ts tests/foregroundCollectionController.test.ts tests/foregroundCollectionRenderer.test.ts tests/foregroundCollectionIntegration.test.ts tests/pythonCollectionDriver.test.ts tests/ui/foreground-collection.test.tsx` — 6 files, 85 tests passed.
- Follow-up changed-path checks:
  - `foregroundCollectionController.test.ts` — 15 passed.
  - `foregroundCollectionRenderer.test.ts` — 23 passed (including new video-platform start prerequisite).
- `git diff --check` — passed.
- One requested typecheck invocation found one TypeScript narrowing error at the `ApiResult` support response. The line was corrected by checking `response.ok` before reading `response.data`; per the task's one-typecheck limit, typecheck was not invoked a second time. No other diagnostics were reported in that invocation.

## Evidence boundary / concerns

- No build or full suite was run, as requested.
- No real Windows, real platform account, browser collection, or production proof was produced.
- Root-owned Python and documentation changes visible in the shared worktree were not staged or committed here.
- The backend mode/support contract and source-host guards must land compatibly with this desktop commit before integrated execution can pass.
