# Legacy save timeout test correction — independent review

Base: `fcae33e62f77d38208a0b3eaf97028d337000acc`. Reviewed the single frozen modification in `desktop/tests/ui/r4-short-coach.test.tsx`; SHA-256 `2cce5c011400edc85fdc6ce36e193c02cb2954a12f8194bc1a58ac0ceb230b7b`. No product code edited by this reviewer.

**Limited PASS. No P0/P1/P2 found; assertions are strengthened, not relaxed.**

The production hook first awaits `snapshotDigest` (real WebCrypto), writes the durable PENDING entry, then calls `boundedRequest` for legacy `saveContact`. That second boundedRequest installs its 30,000 ms timer before scheduling the actual service invocation. The previous test advanced 30,001 fake milliseconds directly after the click, so it could still be waiting for WebCrypto rather than timing the dispatched save. The full-suite failure shows this test as the sole failure; the original unmodified single-file success is consistent with timing sensitivity, not evidence that the full run was green.

The test now waits for an explicit promise resolved inside the mocked `saveContact` call. No fake timer is advanced during this wait, and the test runner timeout still fails a request that never starts. Thus advancing time begins only after the save timer exists and the request has actually been dispatched. At 29,999 ms it asserts the save timeout message is absent; 2 ms later it requires that message. New assertions also require exactly one save call and a PENDING lock before the timing check. The old PENDING preservation, late success without notification, unmount/reopen disabled-save guard, unsupported original-request lookup and final one-call assertion are retained unchanged. The real digest is not stubbed or bypassed and no production timeout is changed.

Independent execution:

`node node_modules/vitest/vitest.mjs run tests/ui/r4-short-coach.test.tsx -t 'times out legacy saving'`

Result: **1 selected test passed / 30 name-filtered tests skipped**, one file; `/tmp/yike-short-coach-timeout-independent.log`. These 30 skips are the intentional `-t` selection, not production condition skips. The changed file also passes `git diff --check`. No whole-suite rerun was performed by this reviewer.

The original integration result remains **1339 passed / 23 skipped / 1 failed** in `docs/qa/ui-local-handoff/logs/integration-first-full-tests.log`; it must remain RED until a new complete run finishes. This review approves only the test synchronization correction, not a new package or visible acceptance.

## Committed test binding

The same correction was committed as `d816a9d5eb56ed9dd178fc42937bbd47d8227a7c`; the committed file SHA-256 is `2cce5c011400edc85fdc6ce36e193c02cb2954a12f8194bc1a58ac0ceb230b7b`. Compared with the original reviewed frozen text above, formatting expanded callback line breaks only; the dispatch barrier, 29,999 + 2 ms checks and all original assertions are unchanged. The original hash is retained as the pre-format review snapshot. Final full-suite results are recorded separately in the delivery report; the earlier integration RED is retained.
