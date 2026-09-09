# Execution runtime slice implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Persistent authorized task → platform run → device lease → fenced result-submission boundary, with original-request lookup and cancellation, for subsequent02B ingestion.

**Architecture:** Implement approved01C/03A in independent modules; retain session, device key, connection-version and profile fences. Consume a database-only strategy resolver supplied by Win04B in the caller transaction; never manufacture an approved strategy. Missing real resolver/capability leaves execution unavailable. This is backend integration, not a completed customer collection journey.

**Tech Stack:** Python, Pydantic, psycopg/PostgreSQL, existing Ed25519 verification and FastAPI.

## Global Constraints

- Target yike-ai2026/main; existing isolated codex/mac-device-authorization worktree, base bc56ed1. Preserve Win work and historical migrations. Mac owns01C/03A/02B; Win owns04A/B+05B/C. Migration108 remains Win; this slice reserves110 only.
- Server session resolves tenant/user. Public input cannot assign tenant, owner, reviewer, approval, capability or server budget. Mutation rechecks active session in its own commit transaction.
- Device possession receipt, telemetry and connection registration are not execution authority. Require request-bound Ed25519 proof, current owned device/key and current CONNECTED connection version. PUBLIC_ANONYMOUS only for PUBLIC_WEB, still product/device authenticated.
- Lock order: session → operation-id advisory → device → credential → connection → profile aggregate/version → confirmed strategy → task/run/platform run. Current checks use database clock after waits and before returning writes. Pre-reads only discover IDs; locked reread decides authority.
- No transaction crosses platform/browser/model/network operations. Strategy resolver shares caller cursor, is database-only and cannot commit; source capability callback is fixed local policy, not client input or a network probe.
- Same original request ID+same semantic body returns durable original receipt; different body conflicts. Original success remains owner-readable after expiry/rotation/disconnect/cancel, but cannot act as a new grant.
- No mock fallback, fabricated connection, automaticAPPROVED opportunity, legacy admin importer, production capability switch, outbound sends or billing.
- Existing v1 TaskDraft/hash/unknown-request ledger unchanged. New backend protocol execution-runtime-v1 needs explicit05F adapter and04B integration; no silent reinterpretation of old requests.
- Confirmed strategy controls hard technical max_records1..10000 and max_runtime_seconds1..86400. These are not搜贝/pricing. Lease ≤120seconds and task deadline. Replay/renew/takeover do not refill budget.
- Initial one-shot task contains1..5 distinct platforms. Scheduling, multiple runs, physical-stop acknowledgement and candidate persistence remain separate03A/02B work, not completed here.

## Task 1: Persistent task/run/lease and caller-owned submission guard

**Files:** create `pilot/execution_contract.py`, `pilot/execution_runtime.py`, `migrations/110_v02_execution_runtime.sql`, `deploy/grant_execution_runtime.sql`, `tests/test_execution_contract.py`, `tests/test_execution_runtime_postgres.py`; append110 registry entry only in `pilot/db.py`.

**Interfaces (signatures; their full behavior is specified below):**

```python
@dataclass(frozen=True)
class ConfirmedExecutionStrategy:
    profile_version_id: str
    strategy_version_id: str
    configuration_sha256: str
    configuration: dict
    platforms: tuple[str, ...]
    max_records: int
    max_runtime_seconds: int

StrategyResolver = Callable[[Cursor, TokenClaims, str, str], ConfirmedExecutionStrategy]
CapabilityCheck = Callable[[str, str, dict], bool]

class ExecutionRuntime:
    def __init__(self, database, *, strategy_resolver=None, capability_check=None): ...
    def apply(self, claims, request: ExecutionOperation, signature: str) -> dict: ...
    def get_receipt(self, claims, request_id: str) -> dict: ...
    def get_task(self, claims, task_id: str) -> dict: ...
    def lock_submission(self, cursor, claims, *, batch: CandidateBatch, signature: str) -> dict: ...
    def recheck_submission_fence(self, cursor, claims, *, batch: CandidateBatch) -> None: ...

def execution_signing_payload(*, tenant_id: str, claims: TokenClaims,
                              operation: ExecutionOperation) -> str: ...
def submission_signing_payload(*, tenant_id: str, claims: TokenClaims,
                               batch: CandidateBatch) -> str: ...
```

**Exact behavior:**

Independent preflight corrections, before implementation: operation idempotency hash excludes session_digest, while signatures include it; same-owner historical replay occurs after active-session check but before rechecking obsolete device/connection/lease. Define stable `ExecutionRuntimeError(code, status)` in execution_contract. All fixed public failures expose only code, not input. START snapshot hashes canonicalJSON of profile_version_id, strategy_version_id, configuration, platforms, max_records and max_runtime_seconds (excluding configuration_sha256 itself); limits therefore participate in the confirmed digest. Revalidation must match the entire START snapshot and never refill its deadline/budget. max_records counts records in newly accepted upload requests, including repeated observations, not unique sources or commercial leads. First upload consumes count once; same-request replay consumes zero.

`recheck_submission_fence` is caller-only, same still-open transaction after `lock_submission`; it rechecks session/clock/deadline/lease/generation/cancel/versions, **not** pre-consumption remaining budget. It cannot grant authority on its own, be cached across transactions or be used in autocommit. Future02B order: session→batch-idempotency lock/original receipt→full submissionguard→sorted source writes→usage and receipt→finalfence. Original batch success returns before current lease checks or budget consumption. No candidate upload endpoint in this slice.

Cancellation stop_confirmed=true is permitted only when every platform execution_generation is0 (no execution lease ever granted). Once any lease was granted, including expired/reclassified leases, retain CANCELLING/stop_confirmed=false until a later explicit worker-stop protocol; current non-RUNNING alone is insufficient. This rule replaces the narrower RUNNING-only description below.

1. `ExecutionTarget`: platform02A service enum, access_mode and nullable connection_id/connection_version per02A; canonical UUID connection. Reject unknown/normalized input. Sort for lock acquisition only, preserve request order.
2. `ExecutionOperation`: strict/frozen/revalidated; schema_version=`execution-runtime-v1`, canonicalUUID request_id/device_id, credential_version strict1..2147483647; operation START/CLAIM/RENEW/CANCEL. START has profile_version_id/strategy_version_id/configuration_sha256 and1..5 distinct targets; task_id/platform_run_id/lease_id/execution_generation null. CLAIM has task_id/platform_run_id; RENEW adds lease_id/execution_generation; CANCEL has task_id only. Nonapplicable fields null, unknown fields rejected. IDs02Aopaque except specifiedUUIDs; signatures outside request. No client durations/budgets/state.
3. Signing: canonical UTF-8 JSON; domain `yike-execution-operation-v1` or `yike-candidate-submission-v1`, derived tenant/user/session_digest and entire operation or02A batch_fingerprint. Reuse `verify_signature`. Store only operation hash and safe receipt, no signature/token/keys in logs.
4. START locks real profile aggregate/version (ID is business_profile_versions.profile_version_id, not groupID) and CONFIRMED status, then resolver exact profile/strategy. Resolver output must match IDs, signed config hash, allowed platforms and strict limits. Hash is canonicalJSON of exact configuration; reject nonobject/nonfinite/oversized JSON. Resolver independently proves current confirmation/revocation and source scope. Local capability_check(platform,access_mode,configuration) must be true per target; missingresolver/policy rejects capability_unavailable without creating task/run/lease.
5. START persists exact immutable configuration snapshot/hash, true profile/strategyIDs, budget and owner; creates collectiontask, one run and distinct platformruns with server-generatedUUIDs. Status PENDING, not collection success; taskdeadline=DBcreationtime+confirmedruntime. Recordusage starts0 per platform, aggregate <=taskbudget enforced under tasklock. No legacy PilotStore.claim_task or research task reuse.
6. CLAIM rechecks key/device/connection/profile/strategy/capability and locks task/run/platform. Only PENDING or expiredRUNNING can claim; active lease conflicts. Freshlease_id, incrementgeneration(first1,max2147483647), exactdevice/key/connection binding, expiry=min(DBnow+120,taskdeadline). No budget refill. Reject expireddeadline/exhaustedbudget.
7. RENEW requires exact current owner/device/key/connection/lease/generation, active task and unexpiredlease/deadline. Extend only within caps; replay original request does not renew again. Never resurrect expired lease.
8. CANCEL must remain possible after profile/strategy/connection failure: session/owneddevice/currentkey then task/run/platformlocks, invalidate result submission/renewal atomically. If any platform RUNNING, task CANCELLING/stop_confirmed=false; otherwise CANCELED/stop_confirmed=true. Expiredlease/servercancel never proves externalprocess stopped. Return immutable cancellation receipt; no physical-stopclaim or platformnetwork call.
9. `lock_submission` uses caller short transaction (reject autocommit), frozen/revalidated02A batch, request-boundsignature and same full storedjoin. Match task/run/platform/profile/strategy IDs, platform/access, owner/device/key/connection, lease/generation/deadline/cancel/budget. Require len(records)<=remaining aggregatebudget. Return server IDs, remaining_records/deadline/generation for02B; no commit, candidatewrite or taskcomplete.02B will incrementusage and persist observations/receipt in sameTX and recheck fence/time beforecommit.
10. `get_receipt`/`get_task` active session+owner reads, including same-tenant otheruserdenied; absent404, no sensitive output. Receipt distinguishes historical operation result from live task state. Mutation replay cannot perform fresh effects.
11. Four new tables: `pilot_collection_tasks`, `pilot_collection_runs`, `pilot_collection_platform_runs`, `pilot_execution_operations`. Composite tenant/owner/task/run/platform/device/profile/connectionFKs; uniqueplatformperrun and(tenant,owner,request_id); strictstatus/generation/budgetchecks. Immutable config/receipt enforced; FORCE RLS with tenant+user scope; explicit restrictedappgrants SELECT/INSERT and only neededUPDATE, noDELETE/owner/admin privileges. Schema/grantrepeatable, historicalmigrationsunchanged.

- [ ] Write focused contract and real restrictedPG tests first. Initial RED may be missingnewmodule; subsequent REDs exercise missing behavior. Example aftersyntheticfixture binds realkey/profile/database-onlyteststrategy: `first=runtime.apply(claims,start,signed_start); assert runtime.apply(claims,start,signed_start)==first; assert row_count('pilot_collection_tasks')==1`. Alter same requestbody then assert stableconflict and unchangedrowcount.
- [ ] Implement minimal modules/schema/grants. Cover strictinput, signaturetampering, sessionexpiry/revoke, tenant/same-tenantowner, missing/unconfirmedstrategy/profile, falsecapability, START/CLAIM/RENEW/CANCEL replays, concurrency on originalrequest, leaseexpiredtakeover, stalegeneration/key/connection, canceledsubmission, budget and sameTXrollback. Bounded barriers for lockwaitexpiry/cancelrace, no longsleep/highcountloops.
- [ ] Validate real02A batches/Ed25519 proofs against restrictedPG guard. Strategy/capability fixture explicitly synthetic and database-only; never ship it as productionresolver. Include negativeapppermissions and liveDBclockafterwait tests.
- [ ] Run `uv run --frozen pytest -q tests/test_execution_contract.py tests/test_execution_runtime_postgres.py` using dedicatedidentityPG DSNs, plus affected session/device/connection/candidate tests once. No parallelPGfixtures or repeats fordocsedits.
- [ ] Commit ownedfiles; report exactRED/GREEN/SHA/limits and unresolvedproductiondependencies. Independent taskreview and finalreview.

## Task 2: HTTPS transport and handoff

**Files:** create `pilot/execution_api.py`, `tests/test_execution_api.py`; minimal `pilot/ui_api.py`, `pilot/web.py` integration; `docs/contracts/V02_EXECUTION_RUNTIME.md`, taskbook/integrationstatus update.

**Interfaces:** consume Task1service; `build_app(..., execution_runtime=None)` optional. FixedPOST `/api/ui/execution-operations` takes `{request: ExecutionOperation, signature: str}`; GET `/api/ui/execution-operations/{request_id}` and `/api/ui/execution-tasks/{task_id}`. No desktopchanges or generic forwarding.

- [ ] RED defaultserviceabsent501; strict422/noinputecho; authentication401; HTTPS400; foreignOrigin403; stableerrors/no-store; validatedsignature and scopedclaims passedto actualservice.
- [ ] Implement thinroutes using existingidentity/Origin/HTTPS/sanitizedUiRoute. Absentservicenofakefallback; knownruntimeerrorsstable, unknownsafe500. Keep task_execution=false untilactualstrategy/source/desktopintegration.
- [ ] Test realTask1service+restrictedPG transport START→CLAIM→CANCEL→originalreceipt. Fixtureproves engineeringroundtrip only, notplatformexecution orcustomerUAT.
- [ ] AffectedAPItests; independentlyreview; normalmerge newmain ifany, exacthandoff andverifiedpush. Do not mark01C/03A/02B/M1complete.

## Next integration

Mac02B will use guard with candidate/observation/receipt atomics and explicitcursor/finalization. Win04B provides real confirmedstrategyresolver,05F adapts confirmedv2 executioninputs and09B worker. Real sources, vendorSMS, stop/restart andmonitoring stillrequireevidence. No unrelated advancedmanagement or backupcrypto expansion inthisslice.
