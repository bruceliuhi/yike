# Task 1 monitor runtime report

## Scope and assumptions

- Baseline: `75fe6c5322b40d90b0161c831a9091cb1f33d7f8`.
- Implemented only the Task 1 owned paths. Root-owned API, policy, runtime assembly, web/UI and product docs were not edited.
- Runtime policy remains injected through `ExecutionRuntime.capability_check`; pulse additionally restricts monitor targets to `XIAOHONGSHU`, `DOUYIN`, and `BILIBILI` and requires monitor schedule policyVersion 1.
- The AGENTS-listed old discovery files do not exist in this successor checkout. The present `docs/README.md`, explicit Task 1 brief, and `docs/superpowers/plans/2026-09-11-monitor-execution.md` governed this change.

## Delivered behavior

- Added strict `MonitorPulseRequest` validation with canonical UUIDs, strict bounded credential version, existing `ExecutionTarget` validation, ordered 1..5 targets, and unique platforms.
- Added forced-owner-RLS binding and occurrence tables, immutable identity/request fields, one pending occurrence per plan, unique plan slot/request, and minimal update grants audited across SET ROLE reachable roles.
- Added `MonitorRuntime.pulse`: owner advisory serialization, existing device/credential/connection/profile/strategy fences, online re-anchoring, missed/offline states, strict-future calendar advancement, durable 90-second reservations, exact replay, restart recovery, and task/deadline settlement.
- Added monitor START reservation validation/linking inside the existing execution transaction. Stored START is normalized through `ExecutionOperation` before persistence and exact comparison.
- Added monitor-mode-gated task revision/plan/binding/occurrence checks to `_versions`; CLAIM/RENEW/submission/FINISH fail closed after pause/revision change or missing linkage, while CANCEL and ordinary once paths do not query migration 127.
- Added a final active-session fence before every successful pulse response after lock waits.

## TDD and verification evidence

RED:

```text
/tmp/yike-main-merge.PZkSlU/.venv/bin/python -m pytest -q tests/test_monitor_runtime_postgres.py
ERROR tests/test_monitor_runtime_postgres.py
ModuleNotFoundError: No module named 'pilot.monitor_runtime_contract'
```

GREEN, using the disposable dedicated PostgreSQL supplied for this batch:

```text
YIKE_MONITOR_RUNTIME_TEST_DATABASE_URL=postgresql://postgres:***@127.0.0.1:61296/yike_monitor_runtime_test \
  /tmp/yike-main-merge.PZkSlU/.venv/bin/python -m pytest -q \
  tests/test_monitor_runtime_postgres.py tests/test_execution_signing_payload.py tests/test_execution_contract.py
35 passed in 0.38s
```

Additional checks:

```text
/tmp/yike-main-merge.PZkSlU/.venv/bin/python -m py_compile pilot/monitor_runtime.py pilot/monitor_runtime_contract.py pilot/execution_runtime.py pilot/db.py
git diff --check
```

Both exited 0. Migration 127 was applied successfully to the disposable database. The PostgreSQL test verifies forced RLS and the immutable-vs-operational column privilege boundary. No full suite or build was run, per the user constraint.

## Concerns / integration notes

- The owned focused test proves the strict contract, default runtime hook, migration application, RLS, and ACL boundary. Root integration should exercise the complete formal-plan/native-connection pulse-to-signed-START flow in the single combined batch review; this task intentionally did not duplicate root-owned API/policy fixtures or run the full suite.
- `READY` means only a durable server reservation, and `RUNNING` means a linked server task. Neither is platform collection, Windows client, production, or customer evidence.
