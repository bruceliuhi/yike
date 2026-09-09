# Device Registration Recovery Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use subagent-driven-development; TDD、单任务规格/质量审核、整片独立最终审核。root唯一Git写入者，专用PG串行使用；用户已要求持续开发，沿已批准正常登录/恢复范围推进。

**Goal:** 普通客户端能按原请求可靠登记设备、恢复未知结果并读取本机当前公钥版本，衔接既有BIND/PROVE与实际采集入口。

**Architecture:** 复用当前HTTPS会话、PilotSessionRegistry、pilot_devices和公钥表；新登记原回执独立持久化，旧POST /devices兼容不动。历史成功回执与当前身份分开，不增加执行授权或通用设备管理。

**Tech Stack:** Python、FastAPI、PostgreSQL、既有PyNaCl、pytest/真实ASGI TestClient。

## Global Constraints

- 合同为`docs/contracts/V02_DEVICE_REGISTRATION_RECOVERY.md`；基线`5b1d7db`，116归Mac本片，108/110保留Win，101–115不得改写。
- 三个接口仅当前会话身份，HTTPS/Origin/no-store不放宽；未知结果按同request_id恢复，不按标签认领，不自动认领NULL owner。
- 不改Win desktop/worker/05G，不启任何真实采集或发送capability；不持久化私钥、token、Cookie或SQL错误。
- root唯一Git写入者；实现者完成后只报告未提交文件和测试，root提交。root先取得HTTP RED，随后将专用PG独占交给实现者；交还后root跑整链。

### Task 1: 原登记持久恢复与当前身份窄读取

**Files:** Create `pilot/device_registration.py`, `migrations/116_v02_device_registration.sql`, `deploy/grant_device_registration.sql`, `tests/test_device_registration.py`, `tests/test_device_registration_postgres.py`; modify `pilot/device_api.py`仅增加三个固定路由及有界解析、`pilot/db.py`仅注册116。root独占新增`tests/test_device_registration_http_postgres.py`和文档，不交叉写入。

**Interfaces:** Create `DeviceRegistrationStore(database)` with `register(claims, payload: dict) -> dict`, `get_receipt(claims, request_id: str) -> dict`, `get_identity(claims, device_id: str) -> dict`. Use `DeviceKeyError(code,status)` for fixed domain failures. `register` receives exact JSON object and validates even when called directly. See contract for exact response fields. Existing `register_device_api(router, store, identity, require_session_https)` assembles lazily from `store.database`; no new build_app dependency injection or CLI toggle.

- [ ] Write strict input/PG RED. Canonical UUID through `uuid_string`; dict keys must exactly equal request_id/device_label, strict string noNUL/invalidUnicode and normalized length1..128. Examples of required behavioral assertions:

```python
body = {"request_id": str(uuid4()), "device_label": "  客户的电脑  "}
first = service.register(claims, body)
assert first["device_label"] == "客户的电脑"
assert service.register(claims, body) == first
assert service.get_receipt(claims, body["request_id"]) == first
assert service.get_identity(claims, first["device_id"]) == {
    "device_id": first["device_id"], "device_status": "ACTIVE",
    "credential_version": 0, "public_key": None,
}
with pytest.raises(DeviceKeyError, match="request_conflict"):
    service.register(claims, body | {"device_label": "另一名称"})
```

- [ ] Implement minimal116 and explicit upgrade grants. Table columns: tenant_id/owner_user_id/request_id/device_id/device_label TEXT NOT NULL, registered_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(); PK(tenant_id,owner_user_id,request_id), UNIQUE(tenant_id,owner_user_id,device_id), composite FK to pilot_devices same three identity fields. Canonical UUID/label length checks; ENABLE/FORCE owner RLS. No runtime UPDATE/DELETE grants or policies; grant file follows existing restricted-role/owner rejection pattern and explicitly grants only SELECT/INSERT to this table. Root/fixtures may delete their own synthetic records through trusted admin only. Register migration key `v02-device-registration` at tail of PilotDatabase.migration_paths. No old migration edits or disabled triggers.
- [ ] Implement `register`: validate, short transaction, require_active, lock `(tenant,owner,request_id)` using a transaction advisory key with distinct namespace11601, recheck current session after waiting, SELECT stored original, compare normalized label or409, return original if found. Otherwise generate one UUID, INSERT owned device and INSERT registration with RETURNING in same transaction; require_active before commit. `_receipt` projects exactly five fields with stateSUCCEEDED and DB ISO timestamp; no mutable device status in original receipt. Catch only after transaction exit: preserve DeviceKeyError; InvalidPilotToken/PermissionError→401; unexpected persistence/commit errors→503 registration_outcome_unknown, no raw exception disclosure.
- [ ] Implement GET receipt: current auth, owner-keyed SELECT, recheck active before returning; not found404 request_not_found; DB failure503 device_registration_unavailable. Implement current identity with ONE SQL LEFT JOIN of owned device and owned credential, no field mixing across multiple queries; ACTIVE or REVOKED shown as current device_status, missing credential0/null. Known foreign/NULL owner404. Recheck current auth; no write or auto-bind.
- [ ] Add three API routes from contract. POST manually streams max4096 raw bytes (reject413), requiresJSON (415), uses existing strict_json_object, verifies finite JSON and UTF8, passes original object to domain validation; catch parse/Unicode/Recursion errors with fixed422. Call blocking DB methods via run_in_threadpool, preserving existing run/auth wrapper or a narrow helper. Preserve old key routes and DeviceInput path unchanged. Unknown fields/current user injection reject422; no generic client URLs.
- [ ] PG tests must prove same-user cross-session concurrent same request gives one device/one receipt, changed normalized label409 with no additional device; role/tenant/owner isolation including same UUID by two different owners; new session recovery; no claim of NULL owner; real BIND/PROVE/ROTATE reflected by identity and no change to original receipt, revoke remains historical receipt plus currentREVOKED; expiry after request-lock waiting rejects401 with no new rows; failure after device INSERT before receipt INSERT rolls back device; unknown commit outcome maps503 then originalGET recovers if committed. Scope synthetic fixture cleanup by exact tenantIDs. Reuse existing role/PG helpers, no new container or production access.
- [ ] Fresh115→116 plus second migration/grant succeeds with application non-superuser/NOBYPASSRLS/non-owner; original116 checksum unchanged. Own-row SELECT/INSERT works, other owner rows hidden, UPDATE/DELETE denied. Do not assign broad app privileges or rely only on admin tests.
- [ ] Run exact focused pure and PG commands after RED→GREEN: `uv run --frozen pytest -q tests/test_device_registration.py tests/test_device_keys.py`; with private test env `uv run --frozen pytest -q tests/test_device_registration_postgres.py`. Write report with original failure/output, final results, files, self-review and concerns. root adds actualHTTP regression below, commits task, generates review-package from saved pre-task SHA, dispatches independent task review; resolve findings and re-review before completion.

### Root integration and final gate

- [ ] Add actualHTTP test before implementation: authorized POST new route201; initial baseline404 is observed RED. After core, same product route must register→bind/prove with realEd25519→read exact identity→rebuild service and recover original→rotate/revoke; no mock SQL/domain methods. Only controlled error/fault seams for unknown storage tests, not happy path. Preserve old route compatibility, HTTPS/Origin/no-store/strict payload errors, other owner denial and session logout.
- [ ] Run root HTTP/PG plus existing device/connection/execution affected subset once, not unrelated desktop/full business suites. Record all false starts and synthetic boundaries. Update contract, unique taskbook and Win handoff; never mark Win consumption or platform proof from these tests.
- [ ] Independent task review then distinct whole-branch code/architecture/quality reviewer, exact SHA. Root normal fetch/integrate Win arrivals and push main+currentbranch; verify live remote SHA and preserve original user RUNBOOK changes. Goal staysACTIVE; next user-visible step is Win device→platform/run flow, plus Mac confirmed contact/reply mainline.
