# Materials lifecycle independent batch review

Reviewed SHA: `85ddb164aab456368b20367d60cde46967a7ff74`; base `a266198`.
Verdict: **NO-GO at this SHA**. Review covers store, model/API/runtime and client assembly; no implementation edits by reviewer.

## Findings

- **P1 — Blocking authentication on the ASGI event loop.** `pilot/material_api.py:10-12,39-55` calls synchronous `identity(request)` directly from all four async routes. Identity performs PostgreSQL session authentication and waits for the session advisory transaction lock. A concurrent material parse holds that lock during its model call; a refresh or original-operation lookup consequently blocks the entire worker event loop, including unrelated customers. Offload the authentication path as well as service methods. Minimal isolated PostgreSQL/ASGI reproduction with a 0.8-second synthetic extraction delayed an unrelated 50 ms asyncio timer to **839 ms**; list returned 200 afterward.
- **P2 — Model wait holds the database transaction and session fence.** `pilot/materials.py:147-164` enters `_active` and an owner lock before extraction, and keeps both across the up-to-20-second provider operation. Same-session logout and authenticated reads queue behind extraction; the later `_active` cannot observe a logout waiting for its own held fence. This also contradicts AUTHORITY's short-transaction/no-model-wait constraint. Keep owner serialization/idempotency, but perform extraction outside the session/database transaction and reacquire/revalidate active session, original receipt and material CAS before committing.

## Evidence and boundary

Inspected current contract/plan, changed production source and focused tests; no additional substantive client DTO, original-receipt, quote-grounding, CAS, impact-token or owner-isolation blocker found in the defined batch. Reused implementer evidence supplied with the review: restricted-PostgreSQL store 6 passing; real HTTP/runtime/private child/loopback synthetic provider/PostgreSQL 2 passing; model/API/runtime 25 passing; client focused 48 passing plus fix deltas and TypeScript checking. These are supplied evidence, not rerun by this reviewer. Only the short concurrency reproduction above was newly executed; no full suite/build.

Empty managed-reference lists are honest for the currently implemented local profile-draft copy; managed-reference tracking is not claimed or added to this review. No real provider quality, customer UAT, platform execution, Windows package or production acceptance is granted. Re-review only these findings and their fix-related deltas at the replacement SHA.
