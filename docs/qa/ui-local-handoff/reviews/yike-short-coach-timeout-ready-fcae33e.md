# P12 legacy save timeout test: bounded diagnosis

Source baseline: `fcae33e62f77d38208a0b3eaf97028d337000acc`. Only `desktop/tests/ui/r4-short-coach.test.tsx` changed; no production or packaging source changed. Not committed.

## Evidence and diagnosis

- Root's original full-suite failure is preserved at `docs/qa/ui-local-handoff/logs/integration-first-full-tests.log`: 1 failed / 1339 passed / 23 skipped. I did not execute that full run.
- My unchanged single-file rerun passed 31/31 (`/tmp/yike-short-coach-timeout-isolated-fcae33e.log`); the failure is not deterministic in isolation.
- Production `useContactDraftSave.ts:116–151` first awaits `snapshotDigest`, then persists the PENDING record, and only then begins the separate bounded legacy save. `snapshotDigest` uses real WebCrypto. The prior test installed fake timers and advanced 30,001 ms immediately after clicking; it never waited for the native digest or actual save dispatch. Therefore its elapsed-time assertion was not tied to the save stage. Under load, the virtual clock may advance while that prerequisite is still pending. This is a test synchronization defect; no product regression was established by this diagnosis.

## Minimal repair

The isolated `saveContact` mock resolves an explicit `requestStarted` promise when it is actually invoked. The test waits for it, verifies one dispatch and the durable PENDING lock, then asserts no save-timeout message at 29,999 ms and the exact original timeout message after two more milliseconds. Late success must still produce no notification; reopening must still block saving; original-request inspection must still explain the legacy query limitation; the save call count remains one.

No arbitrary sleep, longer timeout, broad retry, skipped test, changed product message, or weakened old assertion was added.

## Executed validation

- Updated single file: **31 passed**, exit 0, `/tmp/yike-short-coach-timeout-ready-green-fcae33e.log`.
- `npm run typecheck`: exit 0, `/tmp/yike-short-coach-timeout-ready-typecheck-fcae33e.log`.
- Scoped `git diff --check`: exit 0. Final subsequent edit is formatting only.

This is test-only evidence, not independent approval of the author's own test repair, a new full-suite result, live contact saving, native UAT, or Windows validation. The existing package remains bound to unchanged production bytes; root and the independent reviewer own final integration acceptance.
