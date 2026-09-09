# Connection Version Fencing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox syntax.

**Goal:** Complete the connection-version and mutation-receipt portion of approved V02-01C so reconnect, disconnect and device revocation cannot leave an indistinguishable old connection identity for future execution.

**Architecture:** PostgreSQL owns a monotonic connection version. A narrow authenticated, idempotent connection-operation API records mutation results; a transaction-local version checker is reusable by the later execution authorization chain. Keep old registration interfaces compatible but version every explicit registration and revalidate HTTP sessions inside their write transaction. This does not implement browser login, task start, execution leases or candidate upload.

**Tech Stack:** Existing Python 3.11–3.12/FastAPI/psycopg/PostgreSQL and locked dependencies; no new dependency. Base `714b323469a465e4291937bb2ab9a23438497826`, existing isolated `codex/mac-device-authorization` branch. V02-01C is the engineering ID; approved external V1.0/V1.1 mapping does not remove its launch requirement.

## Global Constraints

- 正式客户数据库使用 PostgreSQL；SQLite 仅用于明确标记的本地实验，不成为第二套正式客户库。
- 客户空间、画像、任务、候选、商机、触达与跟进按服务端身份解析的 tenant_id 隔离；自用商机不进入客户空间。
- 密钥、Cookie、Profile、验证码和私密会话不进入 Git、业务数据库、日志或导出；平台登录态置于隔离的专用凭据/会话存储。
- 应用与管理员数据库连接严格分离；运行时 env 禁止携带管理员连接。
- 任务使用唯一约束、幂等、租约与执行代次。有效结果、游标和任务完成在短事务内校验执行者并提交；事务不跨浏览器、模型或网络等待。
- Do not modify locked migrations101–106, desktop/, connectors/, old app/, or legacy docs/RUNBOOK.md. Do not turn registration or telemetry into CONNECTED or execution authorization. The existing platform capability defaults remain unchanged.
- Actual Windows ACK, real platform actions, full01C/03A/02B, production and UAT remain separately unproved. No external sends, credential inspection or production writes.

## Task 1: Versioned connection mutations and transaction-local current-version checks

This is one independently testable backend delivery within01C. Implement all requirements below before requesting review. The Global Constraints above bind this task; include them verbatim in its generated brief.

**Files and responsibilities:**
- Create `migrations/107_v02_connection_versions.sql`: connection version/trigger, durable operation receipts, composite tenant/user/device keys and FORCE RLS.
- Create `deploy/grant_connection_operations.sql`: explicit least-privilege upgrade for new receipts, no table DELETE/schema CREATE/user UPDATE grants.
- Create `pilot/connection_versions.py`: strict DTOs/stable errors, authenticated operation store, transaction-local current-connection checker. If separation helps, place DTOs in `pilot/connection_contract.py`; these two are the only new business modules.
- Create `pilot/connection_api.py`: thin router registration for the two new endpoints.
- Modify `pilot/db.py`: append107; `pilot/store.py`: explicit registration version bump, return/list version, transaction session recheck for HTTP mutation calls, consistent device→connection lock order on disconnect; `pilot/ui_api.py`: pass verified claims into legacy mutations and register safe errors/new routes. Reuse `sessions.require_active`, not a parallel session/token scheme.
- Create `tests/test_connection_versions.py`, `tests/test_connection_versions_postgres.py`; extend relevant identity/UI tests only where newly returned version or optional internal claims requires it. Keep all existing identity/device tests meaningful.
- Create `docs/contracts/V02_CONNECTION_VERSIONS.md`; update `docs/CUSTOMER_PILOT_RUNBOOK.md` and `deploy/README.md` with implemented107 migration/grant steps. Root owns QA/taskbook/integration/version-mapping documents; do not edit those.

**Version semantics:**
1. `pilot_platform_connections.connection_version INTEGER NOT NULL DEFAULT 1`, bounded1..2147483647. Existing rows receive1 without changing status, account or vault reference. INSERT must begin at1.
2. A BEFORE UPDATE trigger increments exactly once when device_id/platform/account_public_id/session_ref/status changes, or when caller explicitly requests oldversion+1. Arbitrary decrement/jump fails closed. No-op UPDATE leaves version unchanged. At maximum, attempted increment fails atomically with SQLSTATE `YC001`/stable `connection_version_exhausted`; invalid explicit version uses `YC002`/`connection_version_conflict`. No wrap/reset. Trigger never logs field values and is not SECURITY DEFINER.
3. Every explicit `connect_platform`/REGISTER call requests version+1 on an existing row even if account and vault ref are identical; a vault reference may represent a newly logged-in session. New idempotent API replay must not call the registration mutator twice. Registration remains UNVERIFIED. First disconnect changes status and increments; repeated disconnect is a no-op. Device revoke increments each affected connection via the trigger. Trusted future verification/expiry/account changes are covered by the same trigger; telemetry remains telemetry.
4. Legacy direct store calls continue to work as trusted internal/test interfaces. Add keyword-only `claims: TokenClaims | None = None` to legacy register-connection/disconnect/revoke-device methods; real HTTP callers always pass `current.claims`. When present, verify user matches claims and call `require_active` inside the mutation transaction before locks and after waits. Do not authenticate only outside that transaction. Preserve existing tenant-level management semantics of legacy interfaces; do not silently convert them into device-owner execution grants. New operation API requires its selected device to belong to the authenticated user.

**New operation contract:**

Root-approved SQL boundary clarification (2026-09-09): supported service/API mutations must return stable safe exhaustion; trigger-observable bound-field changes at MAX use YC001. Arbitrary raw SQL expressions such as INTEGER `connection_version + 1` may raise PostgreSQL numeric overflow before a BEFORE trigger runs. This separate expression boundary must never wrap or commit; no new column type/helper is required to intercept it. Test atomic rollback and document the distinction.
```python
class ConnectionOperation(BaseModel):
    # Config: strict=True, extra='forbid'; canonical UUID request/device IDs.
    request_id: str
    action: Literal['REGISTER', 'DISCONNECT']
    device_id: str
    connection_id: str | None
    expected_connection_version: int   # strict 0..2147483647
    platform: str | None              # service enum, exact
    account_public_id: str | None
    session_ref: str | None           # opaque validated vault ref, repr=False

class ConnectionOperationStore:
    def apply(self, claims: TokenClaims, request: ConnectionOperation) -> dict: ...
    def get_receipt(self, claims: TokenClaims, request_id: str) -> dict: ...
    def lock_current(self, cursor, claims: TokenClaims, *, device_id: str,
                     connection_id: str, connection_version: int, platform: str) -> dict: ...
```
REGISTER: exact supported service platform plus valid account_public_id/session_ref per existing validator, connection_id must be null. expected0 means absent natural key(tenant,device,platform,account); positive means that exact current row version. Wrong expectation yields durable REJECTED without mutation. DISCONNECT: canonical connection_id, expectedpositive; platform/account/session_ref must be null. Device identity always checked. Null/inconsistent/unknown/oversized/control/secret-like references rejected; structural errors do not echo raw input.

Request identity is `(tenant_id,owner_user_id,request_id)`; fingerprint SHA256 of canonical JSON of validated action/body excluding request_id, preserve semantically material strings. Receipt stores only fingerprint, safe fixed fields, result connection/version/status and timestamps, not session_ref, signatures, bearer or arbitrary payload. Composite FK to the same tenant/user/device; application SELECT/INSERT only for immutable receipts, tenant+user FORCE RLS, no DELETE/UPDATE grant or policy. Result receipt is inserted atomically with mutation; errors roll back both. No pending row outside the transaction is needed.

Implementation clarification: preserve a caller-supplied `requested_device_id` separately from nullable `authorized_device_id`. The latter has the composite tenant/user/device FK and, when present, must equal the requested ID. A null authorized binding is permitted only for `REJECTED/device_unavailable`, with all connection result fields null. This lets nonexistent or another owner's device produce the same safe, durable rejection without referencing or revealing unrelated ownership. Receipts always retain their authenticated tenant/user FK and user-level RLS. Response `device_id` is the caller's requested ID; a later ownership/state change never re-executes an already rejected request.

Acquire session lock, then a distinct namespace user/request advisory lock, then device, then connection. All new operation calls obey this order; receipt query reads only. Legacy mutators never acquire that request lock, so no inverse dependency. Recheck current session using database wall clock after any lock/unique wait and before commit. Same request/body returns original receipt even after disconnect/reconnect/device revoke (after authenticating current user); changed body returns409 `request_conflict`. Check for existing receipt before requiring active device/current expected version. Different request same expectation races: one succeeds, others REJECTED. Inserting receipt must never leave an unrecorded successful mutation under concurrency.

Return exact safe shape, with nullable connection fields for unsuccessful registration:
```json
{"request_id":"UUID","device_id":"UUID","action":"REGISTER","state":"SUCCEEDED","connection_id":"UUID","connection_version":1,"connection_status":"UNVERIFIED","error_code":null}
```
Business rejection returns the same binding with stateREJECTED and fixed error_code; no mutation. Result fields may identify only the authorized current/target connection, never unrelated rows. Both states are immutable historical receipts, not current readiness. `GET` missing receipt returns404 `request_not_found`, not evidence that a timed-out operation failed. No operation replay renews/changes its historical version. HTTP success is not platform login.

Routes (all existing HTTPS/Origin/no-store/session rules): `POST /api/ui/connection-operations`, `GET /api/ui/connection-operations/{request_id}`. No new IPC allowlist, arbitrary URL endpoint or capability toggle. Stable errors: `invalid_request`422, `invalid_session`401, `request_conflict`409, `request_not_found`404; durable rejection codes include `device_unavailable`, `connection_unavailable`, `connection_version_conflict`, `connection_version_exhausted`. Do not leak Pydantic inputs/SQL errors or private references. Legacy version exhaustion returns safe409.

**Current-version checker:** caller supplies an existing transaction cursor and verified claims. Validate IDs/platform/positive strict version; session→device(owner+ACTIVE)→connection locks, session recheck after waits. Require exact tenant/device/platform/version and CONNECTED, else stable error. Return safe `{connection_id,connection_version,platform,account_public_id}` only. It neither commits nor opens a second database connection. It is only one component of future execution authorization; no `AuthorizedExecution` result and no use of historical PROVE receipts. A future caller must still check possession/credential, task/config/run/lease/generation and commit its results in that SAME transaction. PUBLIC_ANONYMOUS execution is handled by the future execution layer, not by inventing a logged-in web connection here.

- [x] **Step1 — Observe RED against existing code.** In a dedicated realPG fixture, register once and again with the same vault reference and assert version1 then2, list exposes2. Verify failure is missing version, not a missing database. Add strict-DTO malformed and unknown-field assertions with no input echo. Reuse tests' restricted-role setup but own/clean only generated tenant IDs.
```python
first = store.connect_platform(user, 'BILIBILI', device, 'synthetic-id', 'vault://synthetic')
second = store.connect_platform(user, 'BILIBILI', device, 'synthetic-id', 'vault://synthetic')
assert first['connection_version'] == 1
assert second['connection_id'] == first['connection_id']
assert second['connection_version'] == 2
```
- [x] **Step2 — Add107 and compatible version/session writes.** Implement version trigger semantics and strict grants; append migration registration. Verify direct trusted SQL changes to every bound field increment, no-op doesn't, overflow rolls back. Verify reconnect/disconnect/device revoke and legacy HTTP/session paths; never patch101–106 checksums.
- [x] **Step3 — RED→GREEN durable operation service/API.** Implement typed validation, atomic request lock/receipt/mutation and authenticated lookup. Test REGISTER expected0→version1→same request exactlysame receipt→newrequest expected1→version2; changed body conflict; DISCONNECT expectedold rejected, correctexpected applied; replay after later mutation/restart remains original. Force receipt insertion failure and assert no mutation committed.
- [x] **Step4 — RED→GREEN same-transaction version checker/concurrency.** Trusted tests may set synthetic connection CONNECTED via admin SQL solely to verify version invalidation, explicitly not a real platform result. With real pg_stat_activity Lock waits test reconnect/disconnect/revoke vs checker in both directions, logout before/after new operation, expiry while blocked, same/different request races, cross-tenant and same-tenant other-device owner denial. Verify checker transaction rollback/commit remains under its caller's control. Do not substitute sleeps for observed blocking.
- [x] **Step5 — Upgrade/HTTP/cross-regression.** Dedicated random database upgrades101–106→107 twice and grants twice; baseline connection remainsUNVERIFIED/version1; restrictedrole mutation/query succeeds, receipts UPDATE/DELETE denied, owner/privileged/missing target grant fails. Real TestClient app+restrictedPG validates HTTPS, Origin, auth expiry/revocation, no-store, clean errors and preserved capabilities; no fake database for these tests.
```sh
uv run --frozen pytest -q tests/test_connection_versions.py tests/test_connection_versions_postgres.py tests/test_identity_contract.py tests/test_identity_postgres.py tests/test_device_keys.py tests/test_device_credentials_postgres.py tests/test_session_auth.py tests/test_session_revocation_postgres.py tests/test_session_upgrade_postgres.py tests/test_ui_api.py
uv run --frozen python -m compileall -q pilot tests
bash scripts/secret_scan.sh
git diff --check
```
Run with the dedicated `YIKE_IDENTITY_TEST_DATABASE_URL` and `YIKE_IDENTITY_TEST_APP_DATABASE_URL`; missing environment is unexecuted, notPASS. Root will run full backend serially after candidate. Do not run tests against an unrelated or production DB.
- [x] **Step6 — Contract/docs/commit/self-review.** Document exact schema/HTTP/replay/version semantics and least privilege upgrades. Record RED/GREEN commands/results, realPG concurrency/upgrade and all unsupported runtime boundaries in the report. Commit only task files; root independently reviews and synchronizes main. No self-final acceptance.

## Follow-on dependency order, not completion claims

After this portion:03A immutable confirmed configuration and task/run/platform records →01C new operation-bound proof/lease/fencing →02B atomic candidates/observations/cursor/outcome →03A actual scheduling/recovery. Preserve frontend `task:${draftId}:${revision}` and the exact `taskFingerprint`, distinct from connection/device requestUUIDs. Do not invent strategy versions, platform capabilities or CONNECTED records to unlock customer start. Existing04A/B confirmed-version work and actual adapters supply those inputs. Cancel must invalidate leases immediately but show CANCELLING until real executor-stop evidence permits terminal CANCELED. Full01C/03A/02B and launch Goal remain open.
