# Business materials lifecycle — implementation batch

Approved basis: UI_MATERIALS_CONTRACT.md and full V0.2 authority. Existing profile fields already persist in profile description; do not rewrite that flow. Connect the existing materials UI rather than add another workspace.

## Contract and boundaries

- Authenticated owner + tenant + profile version scope; material IDs support existing `local-<sha256>` drafts. Keep camelCase wire DTOs exactly as desktop domain/materials.ts.
- Store append-only material revisions and immutable request receipts. Stable request replay checks the original payload digest; edits use expectedVersion CAS. Removal hides a material but retains history. Unknown receipt never asserts no change.
- Parse uses the existing configured assessment model endpoint with a separate bounded extraction prompt, exact source quotes and strict fields. No configuration or failed extraction produces honest FAILED, never synthetic suggestions. Human confirm adopts a nonempty subset of extracted fields without changing the saved profile automatically.
- Impact tokens bind owner/profile/material/version/action/expiry and are consumed atomically. The present profile action copies selected fields to a local draft: there are no managed draft/material references yet. Report an empty managed-reference list honestly; do not claim recall of copied/sent text. READY is required for future external use; this batch does not auto-inject materials into contact drafts.
- No real provider calls, external sends, deployment or new packaged builds in this code batch.

## Backend interface (root/implementer agreement)

`MaterialStore(database, model=None)` with sync methods `list(claims, profileVersionId)`, `mutate(claims, dictRequest)`, `operation(claims, profileVersionId, requestId)`, `impact(claims, profileVersionId, materialId, version, action)` returning the existing UI DTOs. `model.extract(text)` returns `{fields, evidence}`; raises a fixed-message exception on failure. Revalidate all model results in store, including quote containment. Require active session before and after extraction. Scoped transaction/lock prevents concurrent CAS/idempotency races. Never serialize provider exceptions.

API routes: GET `/materials?profileVersionId=...`; POST `/materials/mutate`; GET `/materials/operation?profileVersionId=...&requestId=...`; POST `/materials/impact` with `{profileVersionId,materialId,version,action}`. Mutation returns immutable receipt, not the latest record. Operation missing returns 404 (client stays unresolved). API body <=32 KiB and strict JSON/Pydantic. No caller-supplied tenant/owner.

## Tasks

### Task 1: durable materials domain (backend implementer)
Own pilot/material_contract.py, pilot/materials.py, migrations/125_v02_materials.sql, pilot/db.py, deploy/grant_materials.sql, tests/test_materials_store.py. Strict request validation, append-only revisions/receipts, owner RLS, active session, CAS/replay, extraction/confirmation/revocation/removal, expiring bound impact. Write RED tests first. Use real isolated Postgres for store behavior; root coordinates its URL. Do not touch API/client/model files.

### Task 2: production client transport (client implementer)
Own desktop/src/shared/materialsApi.ts, shared/contracts.ts, main/servicePolicy.ts, renderer/services/materials.ts, renderer/services/client.ts, and new focused transport/policy tests. Fixed operations `materials.list/mutate/operation/impact` map to above routes. Reuse exact UI DTO validation and request identity checks, forward AbortSignal in browser transport, do not fabricate upload progress. Do not redesign UI or touch backend.

### Task 3: bounded model/API/runtime wiring (root)
Own pilot/material_model.py, pilot/material_api.py, pilot/runtime.py, pilot/web.py, pilot/ui_api.py and focused tests/docs. Reuse assessment credentials, separate strict extraction, finite timeout/bytes/no redirects or retries, sanitized failures. Connect MaterialStore to runtime/router. Validate API and client flow on the same real database setup.

### Task 4: one batch acceptance
Changed-path Python/TS checks only. One independent wholebatch review at exact commit; only fix-related delta tests/review. Update contract/taskbook with actual evidence and remaining managed-reference/platform/Windows/production boundaries. Fetch and push to yike-ai2026/main only after passing; full V0.2 goal remains active.
