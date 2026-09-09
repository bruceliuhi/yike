# V02-01C device key possession implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver the real server-side device key binding, one-use possession check and rotation chain required by V02-01C, without claiming that execution leases or candidate upload already exist.

**Architecture:** Existing authenticated product sessions identify users and tenants. A server-generated, persisted challenge is signed by device-held Ed25519 keys; a short PostgreSQL transaction rechecks session revocation, device ownership and the current key version before changing credentials and recording the result. This is the first implementation slice of the approved 01C card; connection generations, execution leases and submission guards remain required subsequent work, not removed scope.

**Tech Stack:** Python >=3.11,<3.13; existing FastAPI/Pydantic/psycopg; PostgreSQL; pinned PyNaCl==1.6.2 (libsodium Ed25519 verification and point validation, no handwritten cryptography).

## Global Constraints

- Current product authority is AUTHORITY.md; main is xinghetech/yike-ai2026/main. Preserve independent frontend and Win work.
- Tenant and user derive from verified product claims, never request JSON. Existing platform registration stays UNVERIFIED; platform capabilities stay unchanged.
- Private keys, raw product tokens, cookies and submitted signatures must not enter database, logs, exports or Git. Store public keys, public challenge data and nonsecret session revocation digest only.
- New migration 106; never edit 101–105. Explicit restricted-role grants, FORCE RLS, tenant/user/device composite references. No runtime administrator credentials, owner/BYPASSRLS role, new pilot_users UPDATE privilege or DELETE grant.
- Lock order: session revocation identity, device, challenge/current credential. Logout locks all its verified session identities in stable order before inserts. After waiting for locks recheck expiry with database clock, not transaction start time.
- Request identifiers are UUID strings; public keys canonical unpadded base64url of 32 bytes, signatures canonical unpadded base64url of 64 bytes. Strict fields/types/lengths; reject unknown fields and echo no rejected input in public errors.
- A successful possession receipt is historical evidence only, never an execution token. Windows private-key storage/transport, normal phone login, connection versions, lease/claim/renew/cancel, candidate API, real platform actions and release/UAT remain incomplete.

## Protocol decisions

Current device table has no user owner. Add nullable owner_user_id referencing (tenant_id,user_id). New registrations set it from the authenticated user; historical null owners cannot bind and are not assigned to the first claimant. Tenant management may still revoke devices using the existing behavior.

DeviceCredentialStore(database) owns this slice. Its public service methods take already-verified TokenClaims (internal only): create_challenge(claims, device_id, request), complete_challenge(claims, device_id, challenge_id, proof), get_receipt(claims, request_id). Runtime authorization never uses a caller-supplied tenant or public proof receipt.

Challenge request: request_id, operation BIND/PROVE/ROTATE, expected_credential_version (strict integer 0..2147483646), public_key (nullable only for PROVE). BIND requires version0/no existing key; PROVE requires current version and null public_key; ROTATE requires current version and a different new key. Expiry is server clock+120 seconds; nonce is secrets.token_urlsafe(32). Maximum five unexpired pending challenges per device, returning 429 challenge_limit; same request/body returns its original challenge before quota check. A failed completion consumes the challenge into REJECTED; expired completion records EXPIRED. A fresh request is required after rejection/expiry.

The exact signed message is returned by the server as signing_payload, an ASCII JSON string with sort_keys=True,separators=(',',':'). It contains protocol='yike-device-proof-v1', tenant_id,user_id,device_id,request_id,challenge_id,session_digest,operation,expected_credential_version,target_public_key,nonce,expires_at (UTC integer epoch). Clients sign these returned UTF-8 bytes unchanged; the protocol domain, random challenge and persisted server row prevent cross-operation/deployment replay. No client-created payload accepted at completion. Pending challenge carries its originating session digest; a newly logged-in session may query history but may not complete an older session's pending challenge.

Completion fields: signature, previous_signature (nullable except required for ROTATE). BIND verifies target key; PROVE verifies current key; ROTATE verifies BOTH current and target keys over identical bytes. Valid BIND version1; valid ROTATE current+1; PROVE no version change. Same request different intent is 409 request_conflict. Different challenge/device/user/session/current version cannot be substituted. Successful completion replay returns its original narrow receipt without repeating mutation. Historical receipt remains SUCCEEDED even if device later revoked or rotated; separate current-state checks decide future authority. Pending/rejected/expired requests have those literal states; unknown request is 404 request_not_found, not FAILED.

Routes under existing /api/ui and existing same-Origin wrapper: POST /devices/{device_id}/key-challenges; POST /devices/{device_id}/key-challenges/{challenge_id}/complete; GET /device-key-requests/{request_id}. All require current product session; production requires HTTPS. Return Cache-Control:no-store. New routes use separate pilot/device_api.py registration helper with the existing router, identity and HTTPS callbacks; do not rebuild authentication or enable CORS. Stable errors: invalid_request422, invalid_session401, device_unavailable404 (missing/wrong owner/revoked/history owner), request_conflict409, credential_conflict409, invalid_proof400, challenge_expired409, challenge_limit429, request_not_found404, internal_error500. Failure responses never return SQL, signature, token or keys.

## Task 1: Persisted device possession and rotation chain

**Files:**
- Create pilot/device_keys.py (strict DTOs, canonical encoding, Ed25519 verification and public errors).
- Create pilot/device_credentials.py (transactional service and receipts).
- Create pilot/device_api.py (thin HTTP registration on existing router).
- Create migrations/106_v02_device_credentials.sql; deploy/grant_device_credentials.sql.
- Modify pilot/db.py migration list; pilot/store.py register_device owner only; pilot/sessions.py internal claims and shared session-lock/recheck helpers; pilot/ui_api.py register new helper.
- Modify pyproject.toml and uv.lock with pinned dependency only.
- Create tests/test_device_keys.py, tests/test_device_credentials_postgres.py; extend session concurrency tests if necessary without changing old expected behavior.
- Create docs/contracts/V02_DEVICE_KEYS.md; update docs/CUSTOMER_PILOT_RUNBOOK.md and deploy/README.md with additive migration/grants only. docs/RUNBOOK.md is the historical SQLite reference and is not the correct operational entry point; leave it unchanged in every worktree.

**Interfaces:**
- Consume TokenClaims from pilot.auth and PilotDatabase from pilot.db; existing PilotSessionRegistry._tenant resolves and sets both RLS identities.
- Add PilotSessionRegistry.lock_session(cursor, claims) and require_active(cursor, claims): lock/recheck at the same transaction as mutation. SessionIdentity keeps user_id/tenant_id compatible and includes optional internal claims with repr=False; new routes require non-null claims. Existing authenticate_session populates claims.
- Produce DeviceCredentialStore methods defined above. They return JSON-compatible challenge/receipt dictionaries; no bearer grant. Public domain errors carry fixed code/status only.
- Two new tables: pilot_device_credentials keyed by tenant/device with owner, public key, positive credential_version and timestamps; pilot_device_key_requests keyed by tenant/user/request_id, unique challenge_id within tenant/user, device/owner composite FK, session_digest, request_sha256, public payload, expiry, state PENDING/SUCCEEDED/REJECTED/EXPIRED and narrow result version. Both FORCE RLS scoped by tenant AND user; device gains unique tenant/owner/device reference. Omit credential row until verified. New tables do not permit application DELETE. Add bounded constraints for all persisted enums/versions/digests.

- [ ] **Step 1: Establish failing contract and real PostgreSQL tests.** Add explicit tests for a complete BIND→PROVE→ROTATE→old-key rejection, same-tenant stranger, other tenant, historical null owner, new registration owner, malformed/extra input, wrong key/signature/padding, expiry, request conflict/replay, five-pending limit, restart and historical queries. Use generated ephemeral Ed25519 keys in tests only; no hardcoded production secret.

```python
def test_key_proof_is_not_reusable_after_rotation(service, claims, owned_device, keys):
    first = bind(service, claims, owned_device, keys[0])
    assert first['credential_version'] == 1
    pending = challenge(service, claims, owned_device, operation='PROVE', version=1)
    rotated = rotate(service, claims, owned_device, keys[0], keys[1], version=1)
    assert rotated['credential_version'] == 2
    with pytest.raises(DeviceKeyError, match='credential_conflict'):
        complete(service, claims, owned_device, pending, keys[0])
```

Test helpers bind/challenge/rotate/complete construct the explicit request/proof DTOs and sign server-returned signing_payload with the generated key; they must not mock SQL, cryptography or authorization. Run `uv run --frozen pytest -q tests/test_device_keys.py tests/test_device_credentials_postgres.py` before implementation, record the missing behavior/import failure. Baseline session/identity tests already run separately. Dependency installation is allowed before crypto tests; implement no production logic until RED observed.

- [ ] **Step 2: Add migration, grants and strict proof module.** Lock exact dependency with `uv lock`; add migration tuple ('v02-device-credentials', ...106...) without editing historical migrations. Follow grant_session_revocations.sql role validation but restrict grants to these new tables. Verify encoding by decode/re-encode exact equality, validate 32/64-byte lengths, reject invalid public points using nacl.bindings.crypto_core_ed25519_is_valid_point, then verify with nacl.signing.VerifyKey(public_key).verify(message,signature). Convert BadSignatureError/decoding failures to fixed DeviceKeyError codes. Generate private keys in tests/client only; production backend only verifies.

```python
decoded = base64.b64decode(value + '=' * (-len(value) % 4), altchars=b'-_', validate=True)
if len(decoded) != expected_size or base64.urlsafe_b64encode(decoded).rstrip(b'=').decode('ascii') != value:
    raise DeviceKeyError('invalid_request', 422)
```

- [ ] **Step 3: Implement transaction and session fence.** Derive a signed 64-bit advisory lock ID from SHA256 of protocol-tagged user_id/revocation_key; collisions only serialize extra requests. Stable-sort all IDs for multi-token logout before taking any tenant/device lock. In credential service take lock, resolve live user/tenant, query revocation and `clock_timestamp()` expiry, lock owned ACTIVE device, then request/current key. Validate before accepting, persist failed consumption without rolling it back when raising HTTP errors (return from transaction then raise domain error). Check expiry again after device lock and immediately before applying the change. Replays use saved receipt; receipt GET needs valid current product session but does not require still-active device or original session. No browser/network awaits in transactions.

```python
with database.connect() as connection:
    with connection.cursor() as cursor:
        tenant = sessions.require_active(cursor, claims)
        device = lock_owned_device(cursor, tenant, claims.user_id, device_id)
        # Device lock protects credential version, challenge consumption and revoke race.
        result, failure = complete_locked(cursor, claims, device, challenge_id, proof)
if failure is not None:
    raise failure
return result
```

The private helpers above belong to device_credentials.py and must be defined there. Recheck session expiry after any wait, not only on transaction entry. Version or signature rejection must not alter a verified credential.

- [ ] **Step 4: Wire real HTTP and operational upgrade.** Register three narrow routes using existing JSON error wrapper; use current.claims, require_session_https and DeviceCredentialStore(store.database). Handle domain errors as fixed code/message without input. Existing fake UI stores must not need a database until a new route is called. Add HTTPS/Origin/no-session/revoked-session/foreign-user/strict-body/no-store/response-leak tests using the real DB fixture and TestClient. Existing capability flags remain false.

- [ ] **Step 5: Prove concurrency and least privilege.** In a fresh restricted-role schema/database test, start from migration105, migrate twice to106, explicitly grant new permissions twice, verify no user UPDATE/table DELETE/schema CREATE/privileged role access. Test FORCE RLS and composite FKs. Use real PostgreSQL blockers and pg_stat_activity wait evidence (not sleep-only guesses) for revoke-device vs complete, logout vs complete both ordering directions, duplicate BIND/ROTATE races, and expiry while waiting. A logout that wins the lock makes completion fail; a completed transaction before logout remains historical success, and every subsequent write is denied. Run migration/grant checks, session/identity tests and the new test files serially on dedicated local test PG.

- [ ] **Step 6: Record and review.** `uv run --frozen python -m compileall -q pilot tests`, `bash scripts/secret_scan.sh`, `git diff --check`; root runs the complete backend suite once with all four test DSNs after handoff. Document exact API, signing bytes, public field lengths, bounded challenge lifecycle, role upgrade command, safe restart/retry, code-vs-Windows boundaries. Commit only allowed paths, return RED/GREEN commands/results and known issues for independent spec/code/architecture review. No push or merge by implementer.

## References and scope review

Approved task: [01C in dual-agent taskboard](../../DUAL_AGENT_TASKBOARD.md), [current task state](../../V02_IMPLEMENTATION_TASKBOOK.md). Existing 01A/B actual ACK f42ea909 covers registration/revocation; it is not an ACK for this new protocol. This plan changes implementation details within approved01C, not the product scope.

Initial PyCA cryptography50.0.1 selection was rejected by a real local preflight: public key bytes `01` followed by31 zero bytes and signature comprising that key followed by32 zero bytes verified an arbitrary message without a private key. The production dependency is therefore PyNaCl1.6.2 instead; the same local probe returns invalid point and BadSignatureError. Add this exact negative test plus zero/noncanonical point tests; do not implement a hand-maintained curve blacklist. Both algorithms remain Ed25519 with unchanged32/64-byte wire sizes. API references: [PyNaCl signing](https://pynacl.readthedocs.io/en/latest/signing/), [PyPI1.6.2](https://pypi.org/project/PyNaCl/1.6.2/), [libsodium point validation](https://doc.libsodium.org/advanced/point-arithmetic). This is an evidence-driven implementation correction, not a product scope change. Server proof and transport remain separated from platform login/collection and Windows acceptance.
