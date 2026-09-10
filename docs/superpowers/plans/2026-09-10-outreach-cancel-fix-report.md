# Outreach scope cancellation fix report

Base: `3478556f3b44d20bc04ad9167ae968adb260964c`

## Reproduction

Before the fix, invalidating a worker scope while `channel.execute()` was awaiting did not abort the signal received by the channel. The focused RED run failed 5 cases: four production-scope signal assertions had no signal, and the execute-wait regression returned `RESULT_RECORDED` instead of cancelling before the simulated click.

## Fix

- Each real `openWorkerScope()` owns an `AbortController`; identity invalidation aborts and removes all old-scope controllers, and idempotent `close()` aborts/removes its own controller.
- Outreach requires a scope signal, combines it with the caller signal, and passes the combined signal through the consumer to channel checks/execution.
- A valid platform receipt arriving after cancellation remains `RESULT_PENDING`; cancellation does not erase the native fact.

No polling, timer, IPC, main wiring, or platform-driver change was introduced.

## Verification

- `npm test -- --run tests/deviceWorkerScope.test.ts tests/outreachDispatchSession.test.ts` — PASS, 2 files / 61 tests.
- `npm run typecheck` — PASS.

The tests include a real `createDeviceIdentityController` scope proving login/logout invalidation and close abort the production signal, an execute-internal wait proving the driver sees cancellation before clicking, and fail-closed behavior when an outreach scope lacks a signal.
